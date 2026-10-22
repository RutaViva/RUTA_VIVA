# telemetry_generator.py
import sys
from pathlib import Path

# Permitir ejecución tanto como script directo, módulo desde la raíz o dentro de Docker
_app_dir = Path(__file__).resolve().parent
if str(_app_dir) not in sys.path:
    sys.path.insert(0, str(_app_dir))

import asyncio
import logging
import time

from config import (
    DEFECT_DELAY_SECONDS,
    INTERVALO_TELEMETRIA,
    OUT_OF_CITY_PCT,
    SILENT_VEHICLES_PCT,
    TAMANO_LOTE,
    TIEMPO_LIMITE_SIN_TELEMETRIA,
)
from defects import out_of_city_position, plan_defects
from rabbit_publisher import RabbitPublisher
from vehicle import Vehiculo
from vehicle_repository import cargar_estados_iniciales
from zone_locator import ZoneLocator

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("simulador")


async def bucle_simulacion():
    """Bucle principal: genera telemetría y la publica cada 15 segundos con inyección de defectos."""
    # 1. Inicializar vehículos con los IDs y el último estado guardado por el seeder
    estados_iniciales = cargar_estados_iniciales()
    zone_locator = ZoneLocator()
    vehiculos = [
        Vehiculo(**estado, zone_locator=zone_locator)
        for estado in estados_iniciales
    ]
    total_vehiculos = len(vehiculos)
    vehicle_ids = [v.id for v in vehiculos]
    logger.info("Cargados %s vehículos desde vehicle_state.", total_vehiculos)

    # 2. Planificar defectos de calidad (silenciosos y fuera de la ciudad)
    defect_plan = plan_defects(
        vehicle_ids=vehicle_ids,
        silent_pct=SILENT_VEHICLES_PCT,
        out_of_city_pct=OUT_OF_CITY_PCT,
    )
    logger.info(
        "Plan de defectos configurado: %d silenciosos (%.1f%%), %d fuera de ciudad (%.1f%%). Activación tras %ds.",
        len(defect_plan.silent_ids),
        SILENT_VEHICLES_PCT,
        len(defect_plan.out_of_city_ids),
        OUT_OF_CITY_PCT,
        DEFECT_DELAY_SECONDS,
    )

    # 3. Conectar a RabbitMQ
    publisher = RabbitPublisher()
    await publisher.connect()

    start_time = time.time()

    try:
        ciclo = 0
        while True:
            ciclo += 1
            now = time.time()
            defects_active = (now - start_time) >= DEFECT_DELAY_SECONDS

            logger.info(
                "--- Ciclo %d: actualizando %d vehículos (Defectos activos: %s) ---",
                ciclo,
                total_vehiculos,
                defects_active,
            )

            # Publica una vez el estado sembrado antes de empezar a simular cambios cinemáticos.
            if ciclo > 1:
                for v in vehiculos:
                    v.tick(intervalo_segundos=INTERVALO_TELEMETRIA)

            # 4. Convertir a payloads aplicando defectos si están activos
            payloads = []
            vehiculos_reportados = []
            for v in vehiculos:
                if v.marcar_offline_si_sin_telemetria(TIEMPO_LIMITE_SIN_TELEMETRIA):
                    logger.warning(
                        "Vehículo %s marcado offline tras %ds sin telemetría.",
                        v.id,
                        TIEMPO_LIMITE_SIN_TELEMETRIA,
                    )

                if not v.puede_reportar_telemetria:
                    continue

                # Defecto 1: Vehículos silenciosos (dejan de reportar)
                if defects_active and v.id in defect_plan.silent_ids:
                    continue

                # Defecto 2: Vehículos que reportan coordenadas fuera de la ciudad
                if defects_active and v.id in defect_plan.out_of_city_ids:
                    out_coords = out_of_city_position()
                    payloads.append(v.to_payload(override_coords=out_coords))
                else:
                    payloads.append(v.to_payload())
                vehiculos_reportados.append(v)

            # 5. Dividir en lotes y publicar en paralelo
            lotes = [
                payloads[i : i + TAMANO_LOTE]
                for i in range(0, len(payloads), TAMANO_LOTE)
            ]
            logger.info(
                "Publicando %d mensajes en %d lotes de hasta %d mensajes...",
                len(payloads),
                len(lotes),
                TAMANO_LOTE,
            )

            tareas = [publisher.publish_batch(lote) for lote in lotes]
            await asyncio.gather(*tareas)
            for v in vehiculos_reportados:
                v.registrar_reporte_telemetria()

            logger.info("Ciclo %d completado. Esperando %ds...", ciclo, INTERVALO_TELEMETRIA)
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
