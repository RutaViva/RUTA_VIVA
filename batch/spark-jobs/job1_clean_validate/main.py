"""
batch/spark-jobs/job1_clean_validate/main.py
Job 1 de PySpark: Ingesta, Estandarización de Esquemas y Cuarentena de Calidad (CA-01, CA-09).
Lee viajes en crudo (Bronze), estandariza esquemas históricos, aplica aserciones de calidad
y escribe los viajes limpios a Silver Parquet y las anomalías a Quarantine Parquet.
"""
import argparse
import logging
import os
import sys
from pathlib import Path

# Permitir resolución de imports locales de common y job1
current_dir = Path(__file__).resolve().parent
spark_jobs_dir = current_dir.parent
if str(spark_jobs_dir) not in sys.path:
    sys.path.insert(0, str(spark_jobs_dir))

from common.spark_session import get_spark_session
from common.quality_rules import apply_trip_quality_rules
from job1_clean_validate.schema_evolution import standardize_schema
from pyspark.sql import functions as F

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("Job1-CleanValidate")


def run_clean_validate_job(
    input_path: str,
    silver_output_path: str,
    quarantine_output_path: str,
    file_format: str = "csv",
) -> dict:
    """
    Ejecuta el Job 1 completo:
    1. Lee datos crudos con formato especificado.
    2. Aplica evolución de esquema hacia el formato canónico (CA-09).
    3. Clasifica registros según reglas de calidad y motivo de rechazo (CA-01).
    4. Escribe particiones Parquet en Silver y Cuarentena.
    5. Retorna diccionario con métricas del procesamiento.
    """
    spark = get_spark_session("RutaViva-Job1-CleanValidate")
    logger.info("Iniciando Job 1 desde fuente: %s", input_path)

    # 1. Lectura de datos en crudo
    if file_format == "csv":
        raw_df = spark.read.option("header", "true").option("inferSchema", "true").csv(input_path)
    elif file_format == "parquet":
        raw_df = spark.read.parquet(input_path)
    else:
        raise ValueError(f"Formato no soportado: {file_format}")

    total_records = raw_df.count()
    logger.info("Total registros leídos: %d", total_records)

    # 2. Estandarización canónica de esquema (CA-09)
    standardized_df = standardize_schema(raw_df)

    # 3. Aplicación de reglas de calidad y clasificación de cuarentena (CA-01)
    evaluated_df = apply_trip_quality_rules(standardized_df)

    # Agregar particiones por año y mes
    partitioned_df = (
        evaluated_df
        .withColumn("year", F.year("pickup_datetime"))
        .withColumn("month", F.month("pickup_datetime"))
    )

    # 4. Separación de conjuntos
    valid_df = partitioned_df.filter(F.col("is_valid") == True).drop("is_valid", "quarantine_reason", "rejected_at")
    quarantine_df = partitioned_df.filter(F.col("is_valid") == False).drop("is_valid")

    valid_count = valid_df.count()
    quarantine_count = quarantine_df.count()

    # Desglose de motivos de rechazo
    reasons_breakdown = (
        quarantine_df.groupBy("quarantine_reason")
        .count()
        .rdd.collectAsMap()
        if quarantine_count > 0 else {}
    )

    logger.info("Registros limpios para Silver: %d (%.2f%%)", valid_count, (valid_count / max(1, total_records)) * 100)
    logger.info("Registros rechazados para Cuarentena: %d (%.2f%%)", quarantine_count, (quarantine_count / max(1, total_records)) * 100)
    logger.info("Desglose de cuarentena: %s", reasons_breakdown)

    # 5. Escritura optimizada en Parquet
    os.makedirs(silver_output_path, exist_ok=True)
    os.makedirs(quarantine_output_path, exist_ok=True)

    if valid_count > 0:
        valid_df.write.mode("overwrite").partitionBy("year", "month").parquet(silver_output_path)
        logger.info("Capa Silver guardada exitosamente en %s", silver_output_path)

    if quarantine_count > 0:
        quarantine_df.write.mode("overwrite").partitionBy("year", "month").parquet(quarantine_output_path)
        logger.info("Capa Cuarentena guardada exitosamente en %s", quarantine_output_path)

    metrics = {
        "total_records": total_records,
        "valid_count": valid_count,
        "quarantine_count": quarantine_count,
        "reasons": reasons_breakdown,
    }
    return metrics


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="PySpark Job 1: Ingesta, Limpieza y Cuarentena de Viajes")
    parser.add_argument("--input", required=True, help="Ruta o URI de entrada (CSV o Parquet)")
    parser.add_argument("--silver", default="data/silver/trips", help="Ruta de salida Silver Parquet")
    parser.add_argument("--quarantine", default="data/quarantine/trips", help="Ruta de salida Cuarentena Parquet")
    parser.add_argument("--format", default="csv", choices=["csv", "parquet"], help="Formato de entrada")

    args = parser.parse_args()
    run_clean_validate_job(
        input_path=args.input,
        silver_output_path=args.silver,
        quarantine_output_path=args.quarantine,
        file_format=args.format,
    )
