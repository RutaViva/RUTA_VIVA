# config.py

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


PROJECT_ROOT = Path(__file__).resolve().parents[3]


class Settings(BaseSettings):
    database_url: str

    model_config = SettingsConfigDict(
        env_file=PROJECT_ROOT / ".env",
        extra="ignore",
    )


DATABASE_URL = Settings().database_url

# --- Parámetros de la simulación ---
INTERVALO_TELEMETRIA = 15  # segundos
TAMANO_LOTE = 500          # vehículos por lote de envío
MAX_CONCURRENCIA = 20      # tareas de envío simultáneas (semáforo)

# --- Parámetros geográficos (Bogotá como ejemplo, sin calles reales) ---
LAT_MIN, LAT_MAX = 40.4900, 40.9200
LON_MIN, LON_MAX = -74.2700, -73.6800
VELOCIDAD_MIN_KMH = 5.0
VELOCIDAD_MAX_KMH = 60.0

# --- Estados del vehículo ---
ESTADOS = ["available", "busy", "offline", "maintenance"]

# Probabilidad de cambiar a cada estado en un tick (15 segundos).
# La probabilidad restante mantiene el estado actual.
PROBABILIDADES_TRANSICION = {
    "available": {"busy": 0.02, "offline": 0.0005, "maintenance": 0.0001},
    "busy": {"available": 0.10, "offline": 0.0005, "maintenance": 0.0001},
    "offline": {"available": 0.01},
    "maintenance": {"available": 0.02},
}

# --- RabbitMQ ---
RABBITMQ_URL = "amqp://admin:admin1234@localhost:5672/"
EXCHANGE_NAME = "telemetria.viajes"
QUEUE_NAME = "telemetria.vehiculos"
ROUTING_KEY = "vehiculo.telemetria"

# --- Rendimiento ---
PUBLISHER_CONFIRMS = False  # Desactivado para máximo throughput