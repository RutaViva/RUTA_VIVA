# main.py
import asyncio
import logging
from config import INTERVALO_TELEMETRIA, TAMANO_LOTE
from vehicle import Vehiculo
from rabbit_publisher import RabbitPublisher
from vehicle_repository import cargar_estados_iniciales

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("simulador")


async def bucle_simulacion():
    """Bucle principal: genera telemetría y la publica cada 15 segundos."""
    # 1. Inicializar vehículos con los IDs y el último estado guardado por el seeder
    estados_iniciales = cargar_estados_iniciales()
    vehiculos = [Vehiculo(**estado) for estado in estados_iniciales]
    total_vehiculos = len(vehiculos)
    logger.info("Cargados %s vehículos desde vehicle_state.", total_vehiculos)

    # 2. Conectar a RabbitMQ
    publisher = RabbitPublisher()
    await publisher.connect()

    try:
        ciclo = 0
        while True:
            ciclo += 1
            logger.info(f"--- Ciclo {ciclo}: actualizando {total_vehiculos} vehículos ---")

            # Publica una vez el estado sembrado antes de empezar a simular cambios.
            if ciclo > 1:
                for v in vehiculos:
                    v.tick(intervalo_segundos=INTERVALO_TELEMETRIA)

            # 4. Convertir a payloads
            payloads = [v.to_payload() for v in vehiculos]

            # 5. Dividir en lotes y publicar en paralelo
            lotes = [
                payloads[i:i + TAMANO_LOTE]
                for i in range(0, len(payloads), TAMANO_LOTE)
            ]
            logger.info(f"Publicando {len(lotes)} lotes de {TAMANO_LOTE} mensajes...")

            tareas = [publisher.publish_batch(lote) for lote in lotes]
            await asyncio.gather(*tareas)

            logger.info(f"Ciclo {ciclo} completado. Esperando {INTERVALO_TELEMETRIA}s...")
            # 6. Esperar hasta el próximo ciclo
            await asyncio.sleep(INTERVALO_TELEMETRIA)

    except asyncio.CancelledError:
        logger.info("Simulación cancelada. Cerrando conexión...")
    finally:
        await publisher.close()
        logger.info("Conexión cerrada. Simulador detenido.")


def main():
    try:
        asyncio.run(bucle_simulacion())
    except KeyboardInterrupt:
        logger.info("Interrupción manual detectada (Ctrl+C)")


if __name__ == "__main__":
    main()