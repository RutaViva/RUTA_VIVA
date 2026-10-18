# services/request_simulator/app/simulator.py
import asyncio
import logging
import random
import time
from typing import Optional

import httpx

from config import settings

logger = logging.getLogger(__name__)


class RequestSimulator:
    def __init__(self):
        self.api_url = settings.api_url.rstrip("/")
        self.trip_endpoint = f"{self.api_url}/trip-requests"
        self.semaphore = asyncio.Semaphore(settings.concurrency_limit)
        self.client: Optional[httpx.AsyncClient] = None
        self.total_sent = 0
        self.total_success = 0
        self.total_failed = 0

    async def init_client(self):
        self.client = httpx.AsyncClient(
            timeout=10.0,
            limits=httpx.Limits(max_connections=100, max_keepalive_connections=50),
        )

    async def close_client(self):
        if self.client:
            await self.client.aclose()

    def generate_random_fare(self) -> float:
        """Genera una tarifa base realista centrada en ~$14.50."""
        fare = random.gauss(14.5, 5.0)
        return round(max(5.0, min(95.0, fare)), 2)

    async def send_single_request(self, zone_id: Optional[int] = None) -> bool:
        """Envía una solicitud de viaje individual hacia la API."""
        if zone_id is None:
            # Concentrar mayor peso en zonas de alta demanda (Manhattan central y aeropuertos)
            popular_zones = [161, 162, 230, 237, 132, 138, 48, 68, 79, 142]
            if random.random() < 0.4:
                target_zone = random.choice(popular_zones)
            else:
                target_zone = random.randint(settings.min_zone_id, settings.max_zone_id)
        else:
            target_zone = zone_id

        payload = {
            "zone_id": target_zone,
            "base_fare": self.generate_random_fare(),
        }

        async with self.semaphore:
            self.total_sent += 1
            try:
                response = await self.client.post(self.trip_endpoint, json=payload)
                if response.status_code == 201:
                    self.total_success += 1
                    data = response.json()
                    trip_id = data.get("trip_id")

                    # Simular asignación para el 70% de los viajes exitosos tras un breve intervalo
                    if random.random() < 0.7 and trip_id:
                        asyncio.create_task(self._simulate_assignment(trip_id))
                    return True
                else:
                    self.total_failed += 1
                    logger.warning("Fallo en solicitud a zona %d (HTTP %d)", target_zone, response.status_code)
                    return False
            except Exception as e:
                self.total_failed += 1
                logger.error("Error conectando con multiplier-api: %s", e)
                return False

    async def _simulate_assignment(self, trip_id: str):
        """Simula que un conductor acepta el viaje tras 3 a 15 segundos."""
        await asyncio.sleep(random.uniform(3.0, 15.0))
        try:
            await self.client.post(f"{self.trip_endpoint}/{trip_id}/assign")
        except Exception:
            pass

    async def run_burst(self, zone_id: int, count: int):
        """Dispara una ráfaga masiva de solicitudes (concierto / evento especial)."""
        logger.info("🚨 INICIANDO RÁFAGA DE DEMANDA: %d solicitudes en zona %d...", count, zone_id)
        start = time.time()
        tasks = [self.send_single_request(zone_id=zone_id) for _ in range(count)]
        results = await asyncio.gather(*tasks)
        elapsed = time.time() - start
        success_count = sum(1 for r in results if r)
        logger.info(
            "✅ Ráfaga completada en %.2f s. Éxitos: %d / %d (Throughput: %.1f req/s)",
            elapsed,
            success_count,
            count,
            count / max(0.01, elapsed),
        )

    async def start_continuous_simulation(self, stop_event: asyncio.Event):
        """Generador continuo de solicitudes con tasa regulada."""
        interval = 1.0 / max(0.1, settings.requests_per_second)
        logger.info("Iniciando simulación continua de demanda (tasa: %.1f req/s)...", settings.requests_per_second)

        last_burst_time = time.time()

        while not stop_event.is_set():
            asyncio.create_task(self.send_single_request())

            # Comprobar ráfaga periódica si está habilitada
            if settings.burst_enabled:
                if (time.time() - last_burst_time) >= settings.burst_interval_seconds:
                    asyncio.create_task(self.run_burst(settings.burst_target_zone, settings.burst_requests_count))
                    last_burst_time = time.time()

            try:
                await asyncio.wait_for(stop_event.wait(), timeout=interval)
            except asyncio.TimeoutError:
                pass
