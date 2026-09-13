"""
Central configuration for the Carbon-Aware Inference Scheduler.
All values are overridable via environment variables (see .env.example).
"""
import os
from dotenv import load_dotenv

load_dotenv()


class Settings:
    # --- Redis ---
    REDIS_URL: str = os.getenv("REDIS_URL", "redis://localhost:6379/0")

    # --- Carbon data source ---
    # "mock"           -> deterministic simulated day/night carbon curve (no API key needed, works offline)
    # "electricitymaps" -> real Electricity Maps API (needs ELECTRICITYMAPS_API_KEY)
    CARBON_PROVIDER: str = os.getenv("CARBON_PROVIDER", "mock")
    ELECTRICITYMAPS_API_KEY: str = os.getenv("ELECTRICITYMAPS_API_KEY", "")
    ELECTRICITYMAPS_ZONE: str = os.getenv("ELECTRICITYMAPS_ZONE", "US-MIDA-PJM")
    CARBON_API_BASE: str = "https://api.electricitymap.org/v3/carbon-intensity/latest"

    # --- Scheduler behavior ---
    CLEAN_THRESHOLD_G_PER_KWH: float = float(os.getenv("CLEAN_THRESHOLD_G_PER_KWH", "250"))
    POLL_INTERVAL_SECONDS: int = int(os.getenv("POLL_INTERVAL_SECONDS", "15"))
    MAX_WAIT_MINUTES: int = int(os.getenv("MAX_WAIT_MINUTES", "60"))
    MIN_BATCH_SIZE: int = int(os.getenv("MIN_BATCH_SIZE", "1"))  # 1 = run as soon as clean, no batching required

    # --- Inference simulation (swap for a real vLLM/llama.cpp call) ---
    ENERGY_PER_1K_TOKENS_KWH: float = float(os.getenv("ENERGY_PER_1K_TOKENS_KWH", "0.0024"))

    # --- Regions (for multi-region routing demo) ---
    REGIONS: list[str] = os.getenv("REGIONS", "US-MIDA-PJM,US-CAL-CISO,EU-FR").split(",")


settings = Settings()
