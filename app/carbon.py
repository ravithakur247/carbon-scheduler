"""
Carbon intensity providers.

- MockCarbonProvider: deterministic sinusoidal day/night curve per region, so the
  whole system is demoable offline with no API key, and the numbers still behave
  the way a real grid does (dirty in the evening peak, clean overnight).
- ElectricityMapsProvider: real integration, used automatically when
  CARBON_PROVIDER=electricitymaps and an API key is set.

Both implement the same async interface: get_intensity(region) -> float (gCO2/kWh).
"""
import math
import time
from abc import ABC, abstractmethod

import httpx

from .config import settings


class CarbonProvider(ABC):
    @abstractmethod
    async def get_intensity(self, region: str) -> float:
        ...

    async def get_intensity_all(self, regions: list[str]) -> dict[str, float]:
        return {r: await self.get_intensity(r) for r in regions}


class MockCarbonProvider(CarbonProvider):
    """
    Simulates a realistic carbon curve:
      - Peaks ~600-700 gCO2/kWh around 6-9 PM local time (evening demand + gas peakers)
      - Troughs ~100-150 gCO2/kWh around 2-5 AM (wind/nuclear baseload)
    Each region gets a different phase/amplitude so multi-region routing has something
    to route around.
    """

    _region_profile = {
        # name: (baseline, amplitude, phase_shift_hours)
        "US-MIDA-PJM": (380, 270, 0),
        "US-CAL-CISO": (300, 200, 2),   # more solar -> cleaner midday, different peak
        "EU-FR": (140, 60, 1),          # nuclear-heavy -> much cleaner overall
    }

    def _hour_fraction(self) -> float:
        t = time.localtime()
        return t.tm_hour + t.tm_min / 60.0

    async def get_intensity(self, region: str) -> float:
        baseline, amplitude, phase = self._region_profile.get(region, (350, 250, 0))
        hour = self._hour_fraction()
        # Cosine peaking at 18:00 (6 PM), trough at 6 AM, shifted per region
        radians = 2 * math.pi * ((hour - 18 - phase) / 24.0)
        intensity = baseline + amplitude * math.cos(radians)
        return round(max(intensity, 50), 1)


class ElectricityMapsProvider(CarbonProvider):
    def __init__(self, api_key: str):
        self.api_key = api_key

    async def get_intensity(self, region: str) -> float:
        async with httpx.AsyncClient(timeout=10) as client:
            r = await client.get(
                settings.CARBON_API_BASE,
                params={"zone": region},
                headers={"auth-token": self.api_key},
            )
            r.raise_for_status()
            return float(r.json()["carbonIntensity"])


def get_provider() -> CarbonProvider:
    if settings.CARBON_PROVIDER == "electricitymaps" and settings.ELECTRICITYMAPS_API_KEY:
        return ElectricityMapsProvider(settings.ELECTRICITYMAPS_API_KEY)
    return MockCarbonProvider()


provider = get_provider()
