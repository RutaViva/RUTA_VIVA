# services/pressure_worker/app/worker_config.py
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

_parents = Path(__file__).resolve().parents
PROJECT_ROOT = _parents[3] if len(_parents) > 3 else _parents[0]
LOCAL_ENV = PROJECT_ROOT / ".env"


class Settings(BaseSettings):
    database_url: str = "postgresql+psycopg://admin:admin1234@localhost:5438/rutaviva_db"
    rabbitmq_url: str = "amqp://admin:admin1234@localhost:5672/"

    # RabbitMQ Topology
    exchange_name: str = "telemetria.viajes"
    queue_name: str = "telemetria.vehiculos"
    routing_key: str = "vehiculo.telemetria"

    # Batching & Intervals (optimizado para flujo de 8.000 vehículos = ~533 msg/s)
    batch_size: int = 1000
    flush_interval_seconds: float = 3.0
    calculation_interval_seconds: float = 30.0  # Recalcula zone_state cada 30s (o máx 5 min por RN-02)

    # Reglas de negocio
    max_multiplier: float = 2.0         # RN-05
    night_max_multiplier: float = 1.5   # RN-05 (22:00 a 05:00)
    rain_threshold_mm_h: float = 2.0    # RN-04
    offline_threshold_seconds: int = 120 # RN-10 (2 minutos sin telemetría)

    model_config = SettingsConfigDict(
        env_file=(LOCAL_ENV, PROJECT_ROOT / ".env"),
        extra="ignore",
    )


settings = Settings()
