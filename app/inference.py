"""
The actual "do the work" step.

This is a mock so the whole system runs with zero external dependencies. To go
real: replace `run_inference` with a call to your vLLM / TGI / llama.cpp
endpoint, and keep the token count so the energy estimate still works (or pull
energy straight from your GPU's power draw if you're measuring it directly).
"""
import asyncio

from .config import settings


async def run_inference(prompt: str, estimated_tokens: int) -> tuple[str, float]:
    """
    Returns (result_text, energy_kwh).
    Simulates latency proportional to token count so the demo feels real.
    """
    await asyncio.sleep(min(2.0, estimated_tokens / 2000))  # capped fake "compute time"
    energy_kwh = (estimated_tokens / 1000) * settings.ENERGY_PER_1K_TOKENS_KWH
    result = f"[mock output for prompt: {prompt[:60]!r}... — {estimated_tokens} tokens generated]"
    return result, energy_kwh
