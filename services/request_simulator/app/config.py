# services/request_simulator/app/config.py
import os
from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict

_parents = Path(__file__).resolve().parents
PROJECT_ROOT = _parents[3] if len(_parents) > 3 else _parents[0]
LOCAL_ENV = PROJECT_ROOT / ".env"


class Settings(BaseSettings):
    api_url: str = "http://localhost:8000"
    min_zone_id: int = 1
    max_zone_id: int = 265

    # Parámetros de simulación (F5: >= 30 solicitudes/segundo pico)
    requests_per_second: float = 30.0
    concurrency_limit: int = 50

    # Ráfagas (burst mode) para simulación de conciertos/eventos (CA-10)
    burst_enabled: bool = True
    burst_requests_count: int = 1000
    burst_interval_seconds: int = 180
    burst_target_zone: int = 161  # Midtown Center / Madison Square Garden

    model_config = SettingsConfigDict(
        env_file=(LOCAL_ENV, PROJECT_ROOT / ".env"),
        extra="ignore",
    )


settings = Settings()
