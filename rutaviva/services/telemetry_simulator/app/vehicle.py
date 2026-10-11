# vehicle.py
import datetime
import random
from config import (
    LAT_MIN, LAT_MAX, LON_MIN, LON_MAX,
    VELOCIDAD_MIN_KMH, VELOCIDAD_MAX_KMH,
    PROBABILIDADES_TRANSICION,
)
from zone_locator import ZoneLocator

class Vehiculo:
    def __init__(
        self,
        vehicle_id: str,
        zone_id: int,
        latitude: float,
        longitude: float,
        status: str,
        zone_locator: ZoneLocator,
    ):
        self.id = vehicle_id
        self.zone_id = zone_id
        self.lat = latitude
        self.lon = longitude
        self.zone_locator = zone_locator
        # Velocidad y dirección en radianes
        self.velocidad_kmh = random.uniform(VELOCIDAD_MIN_KMH, VELOCIDAD_MAX_KMH)
        self.direccion = random.uniform(0, 2 * 3.14159)
        self.estado = status

    def tick(self, intervalo_segundos: float = 15.0):
        """Avanza el vehículo un paso de simulación."""
        # 1. Actualizar posición según velocidad y dirección
        self._mover(intervalo_segundos)
        # 2. Mantener la zona sincronizada con las coordenadas actuales
        self.zone_id = self.zone_locator.locate(self.lat, self.lon, self.zone_id)
        # 3. Gestionar transición de estado
        self._transicionar_estado()
        # 4. Variar ligeramente la velocidad (tráfico, semáforos)
        self.velocidad_kmh = max(
            VELOCIDAD_MIN_KMH,
            min(VELOCIDAD_MAX_KMH, self.velocidad_kmh + random.uniform(-5, 5))
        )

    def _mover(self, intervalo_segundos: float):
        """Movimiento simple: avance lineal con ligera perturbación."""
        # Convertir km/h a grados aproximados por segundo
        # 1 grado de latitud ≈ 111 km; 1 grado de longitud ≈ 111 * cos(lat)
        import math
        distancia_km = (self.velocidad_kmh / 3600.0) * intervalo_segundos
        delta_lat = distancia_km / 111.0
        delta_lon = distancia_km / (111.0 * math.cos(math.radians(self.lat)))

        self.lat += delta_lat * math.cos(self.direccion)
        self.lon += delta_lon * math.sin(self.direccion)

        # Rebotar dentro del área simulada (como si fuera una frontera)
        if not (LAT_MIN <= self.lat <= LAT_MAX):
            self.direccion = 3.14159 - self.direccion  # reflejar
            self.lat = max(LAT_MIN, min(LAT_MAX, self.lat))
        if not (LON_MIN <= self.lon <= LON_MAX):
            self.direccion = -self.direccion
            self.lon = max(LON_MIN, min(LON_MAX, self.lon))

        # Pequeña perturbación aleatoria en la dirección
        self.direccion += random.uniform(-0.1, 0.1)

    def _transicionar_estado(self):
        """Cambia de estado usando las probabilidades configuradas por tick."""
        probabilidad = random.random()
        probabilidad_acumulada = 0.0
        for estado_destino, probabilidad_transicion in PROBABILIDADES_TRANSICION[self.estado].items():
            probabilidad_acumulada += probabilidad_transicion
            if probabilidad < probabilidad_acumulada:
                self.estado = estado_destino
                return

    def to_payload(self) -> dict:
        """Serializa el estado actual para enviarlo por RabbitMQ."""
        return {
            "vehicle_id": self.id,
            "lat": round(self.lat, 6),
            "zone_id": self.zone_id,
            "lon": round(self.lon, 6),
            "status": self.estado,
            "last_seen_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        }