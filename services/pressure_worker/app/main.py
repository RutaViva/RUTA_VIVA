# services/pressure_worker/app/main.py
import sys
from pathlib import Path

_app_dir = Path(__file__).resolve().parent
if str(_app_dir) not in sys.path:
    sys.path.insert(0, str(_app_dir))

import asyncio
import logging
import signal
from datetime import datetime, timezone

from worker_config import settings
from consumer import TelemetryConsumer
from database import get_db_session
from pressure_calculator import compute_zone_metrics

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("pressure_worker")


async def periodic_pressure_recalc(stop_event: asyncio.Event):
    """Tarea periódica que recalcula el estado de presión y multiplicadores por zona."""
    logger.info("Iniciando tarea periódica de cálculo de presión (intervalo: %ds)...", settings.calculation_interval_seconds)
    while not stop_event.is_set():
        try:
            now_utc = datetime.now(timezone.utc)
            with get_db_session() as session:
                compute_zone_metrics(session, now_utc)
        except Exception:
            logger.exception("Error durante el cálculo periódico de presión de zonas.")

        try:
            await asyncio.wait_for(stop_event.wait(), timeout=settings.calculation_interval_seconds)
        except asyncio.TimeoutError:
            pass


async def main():
    logger.info("Iniciando servicio Pressure Worker de RutaViva...")
    stop_event = asyncio.Event()

    consumer = TelemetryConsumer()
    await consumer.connect()

    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, lambda: stop_event.set())
        except NotImplementedError:
            pass  # En Windows/ciertos entornos

    consumer_task = asyncio.create_task(consumer.start_consuming())
    calculator_task = asyncio.create_task(periodic_pressure_recalc(stop_event))

    await stop_event.wait()
    logger.info("Señal de parada recibida. Deteniendo worker...")

    await consumer.close()
    calculator_task.cancel()
    await asyncio.gather(consumer_task, calculator_task, return_exceptions=True)
    logger.info("Pressure Worker finalizado correctamente.")


if __name__ == "__main__":
    asyncio.run(main())
