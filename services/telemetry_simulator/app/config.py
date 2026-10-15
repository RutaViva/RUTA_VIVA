# config.py
import os
from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict

PROJECT_ROOT = Path(__file__).resolve().parents[3]
LOCAL_ENV = Path(__file__).resolve().parent.parent / ".env"


class Settings(BaseSettings):
    database_url: str = "postgresql+psycopg://admin:admin1234@localhost:5438/rutaviva_db"
    rabbitmq_url: str = "amqp://admin:admin1234@localhost:5672/"
    silent_vehicles_pct: float = 5.0
    out_of_city_pct: float = 3.0
    defect_delay_seconds: int = 60

    model_config = SettingsConfigDict(
        env_file=(LOCAL_ENV, PROJECT_ROOT / ".env"),
        extra="ignore",
    )


_settings = Settings()

DATABASE_URL = _settings.database_url
RABBITMQ_URL = _settings.rabbitmq_url
SILENT_VEHICLES_PCT = _settings.silent_vehicles_pct
OUT_OF_CITY_PCT = _settings.out_of_city_pct
DEFECT_DELAY_SECONDS = _settings.defect_delay_seconds

# --- Parámetros de la simulación ---
INTERVALO_TELEMETRIA = 15  # segundos
TAMANO_LOTE = 500          # vehículos por lote de envío
MAX_CONCURRENCIA = 20      # tareas de envío simultáneas (semáforo)

# --- Parámetros geográficos (Ciudad de Nueva York / Taxi Zones) ---
LAT_MIN, LAT_MAX = 40.4900, 40.9200
LON_MIN, LON_MAX = -74.2700, -73.6800
VELOCIDAD_MIN_KMH = 5.0
VELOCIDAD_MAX_KMH = 60.0

# --- Límites fuera de la ciudad para inyección de defectos ---
OUTSIDE_MIN_LAT, OUTSIDE_MAX_LAT = 39.0000, 39.5000
OUTSIDE_MIN_LON, OUTSIDE_MAX_LON = -73.0000, -72.0000

# --- Estados del vehículo ---
ESTADOS = ["available", "busy", "offline", "maintenance"]
ESTADOS_OPERATIVOS = {"available", "busy"}
TIEMPO_LIMITE_SIN_TELEMETRIA = 120

# Probabilidad de cambiar a cada estado en un tick (15 segundos).
PROBABILIDADES_TRANSICION = {
    "available": {"busy": 0.02, "offline": 0.0005, "maintenance": 0.0001},
    "busy": {"available": 0.10, "offline": 0.0005, "maintenance": 0.0001},
    "offline": {"available": 0.01},
    "maintenance": {"available": 0.02},
}

# --- RabbitMQ ---
EXCHANGE_NAME = "telemetria.viajes"
QUEUE_NAME = "telemetria.vehiculos"
ROUTING_KEY = "vehiculo.telemetria"

# --- Rendimiento ---
PUBLISHER_CONFIRMS = False  # Desactivado para máximo throughput