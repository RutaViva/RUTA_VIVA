"""
Configuración de la conexión a la base de datos y utilidades DDL.
"""

import logging
import os
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from .models import Base

logger = logging.getLogger("DataSeeder")

DATABASE_URL = os.getenv(
    "DATABASE_URL", 
    "postgresql+psycopg://admin:admin1234@localhost:5438/rutaviva_db"
)

engine = create_engine(DATABASE_URL, echo=False, pool_size=20, max_overflow=10)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)

def clean_database():
    """
    Realiza un TRUNCATE en orden inverso de dependencias FK
    o un TRUNCATE CASCADE para reiniciar la base de datos limpiamente.
    """
    logger.info("Iniciando limpieza completa de tablas...")
    tables_in_reverse_order = [
        "fare_audit",
        "trip_request",
        "zone_state_history",
        "zone_state",
        "vehicle_state",
        "special_event",
        "sanction",
        "license",
        "vehicle",
        "weather_current",
        "tariff_rule_version",
        "driver",
        "zone",
    ]

    with engine.begin() as conn:
        for table in tables_in_reverse_order:
            try:
                conn.execute(text(f"TRUNCATE TABLE {table} CASCADE;"))
                logger.info(f"Tabla '{table}' limpiada.")
            except Exception as e:
                logger.warning(f"No se pudo truncar '{table}' (posiblemente vacía o inexistente): {e}")
    logger.info("Base de datos limpiada con éxito.")