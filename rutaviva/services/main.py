"""
Script principal de ejecución CLI para el Seeding de Datos.
Administra lotes, transacciones, argumentos de consola e inserción ordenada.
"""
import sys
import argparse
import logging
import time
from typing import Any, Dict, List, Type

from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session
from sqlalchemy import select, func
from .models import Driver, Vehicle, Zone

from .database import SessionLocal, clean_database, engine
from .seed_cli.app.seeder import (
    apply_driver_status,
    generate_drivers,
    generate_licenses,
    generate_sanctions,
    generate_vehicles,
    generate_vehicle_states,
    generate_zones,
)
from .models import (
    Driver,
    License,
    Sanction,
    Vehicle,
    VehicleState,
    Zone,
)

# Configuración de Logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger("DataSeeder")
logger.info(f"engine.url: {engine.url}")


def bulk_insert_in_chunks(session, model_cls, data: list, chunk_size: int = 5000):
    """
    Inserta datos en lotes utilizando ON CONFLICT DO NOTHING para garantizar 
    idempotencia sin necesidad de limpiar la tabla previamente.
    """
    if not data:
        return
        
    for i in range(0, len(data), chunk_size):
        chunk = data[i : i + chunk_size]
        
        # 1. Crear la sentencia de inserción específica de PostgreSQL
        stmt = pg_insert(model_cls).values(chunk)
        
        # 2. Agregar la regla de Upsert (Ignorar si ya existe la clave primaria)
        # Si prefieres que actualice los datos, se usaría .on_conflict_do_update()
        stmt = stmt.on_conflict_do_nothing()
        
        # 3. Ejecutar el lote
        session.execute(stmt)
        
    session.commit()



def run_seeder(drivers_count: int, clean_first: bool):
    start_time = time.time()
    logger.info("Iniciando proceso de Seeding de Datos...")

    if clean_first:
        clean_database()

    session: Session = SessionLocal()

    try:
        logger.info("Generando zonas, conductores, vehículos, licencias, sanciones y estados...")

        zones_data = generate_zones()
        drivers_data = generate_drivers(count=drivers_count)
        driver_ids = [driver["driver_id"] for driver in drivers_data]
        licenses_data = generate_licenses(driver_ids)
        sanctions_data = generate_sanctions(driver_ids, max_sanctions=int(drivers_count * 0.1))
        drivers_data = apply_driver_status(drivers_data, licenses_data, sanctions_data)
        vehicles_data = generate_vehicles(
            driver_ids,
            min_vehicles_per_driver=1,
            max_vehicles_per_driver=2,
        )
        vehicle_ids = [vehicle["vehicle_id"] for vehicle in vehicles_data]
        vehicle_states_data = generate_vehicle_states(vehicle_ids)

        bulk_insert_in_chunks(session, Zone, zones_data)
        bulk_insert_in_chunks(session, Driver, drivers_data)
        bulk_insert_in_chunks(session, License, licenses_data)
        bulk_insert_in_chunks(session, Sanction, sanctions_data)
        bulk_insert_in_chunks(session, Vehicle, vehicles_data)
        bulk_insert_in_chunks(session, VehicleState, vehicle_states_data)

        # Confirmación de la Transacción
        session.commit()
        elapsed_time = round(time.time() - start_time, 2)
        logger.info(f"¡Seeding completado con éxito en {elapsed_time} segundos!")
        for model in (Zone, Driver, Vehicle):
            n = session.execute(select(func.count()).select_from(model)).scalar()
            logger.info(f"{model.__tablename__}: {n} filas")

    except Exception as e:
        session.rollback()
        logger.critical(f"Error durante el seeding. Se realizó ROLLBACK de la transacción. Detalles: {e}", exc_info=True)
        raise e
    finally:
        session.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Script de Poblamiento de Datos (Seeder) para Fleet & Dynamic Pricing")
    parser.add_argument("--clean", action="store_true", help="Limpia (TRUNCATE) las tablas antes de poblar.")
    parser.add_argument("--drivers", type=int, default=100, help="Cantidad de conductores a generar (default: 100).")

    args = parser.parse_args()

    run_seeder(
        drivers_count=args.drivers,
        clean_first=args.clean
    )