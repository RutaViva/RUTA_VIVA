# services/request_simulator/app/main.py
import sys
from pathlib import Path

_app_dir = Path(__file__).resolve().parent
if str(_app_dir) not in sys.path:
    sys.path.insert(0, str(_app_dir))

import asyncio
import logging
import signal

from simulator import RequestSimulator

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("request_simulator")


async def main():
    logger.info("Iniciando simulador de solicitudes de viaje de RutaViva...")
    stop_event = asyncio.Event()

    simulator = RequestSimulator()
    await simulator.init_client()

    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, lambda: stop_event.set())
        except NotImplementedError:
            pass

    sim_task = asyncio.create_task(simulator.start_continuous_simulation(stop_event))

    await stop_event.wait()
    logger.info("Señal de parada recibida. Finalizando simulador...")

    sim_task.cancel()
    await asyncio.gather(sim_task, return_exceptions=True)
    await simulator.close_client()
    logger.info(
        "Estadísticas finales: %d enviadas | %d exitosas | %d fallidas",
        simulator.total_sent,
        simulator.total_success,
        simulator.total_failed,
    )


if __name__ == "__main__":
    asyncio.run(main())
