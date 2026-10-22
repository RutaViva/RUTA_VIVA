"""
batch/spark-jobs/common/spark_session.py
Configuración optimizada de SparkSession para el pipeline batch de RutaViva.
Configura memoria, paralelismo, compresión snappy y compatibilidad con Parquet.
"""
import os
from pyspark.sql import SparkSession


def get_spark_session(app_name: str = "RutaViva-Batch-Pipeline") -> SparkSession:
    """
    Retorna una instancia singleton o configurada de SparkSession
    optimizada para ejecución en contenedores o local.
    """
    builder = (
        SparkSession.builder
        .appName(app_name)
        .master(os.getenv("SPARK_MASTER", "local[*]"))
        .config("spark.driver.memory", os.getenv("SPARK_DRIVER_MEMORY", "2g"))
        .config("spark.executor.memory", os.getenv("SPARK_EXECUTOR_MEMORY", "2g"))
        .config("spark.sql.shuffle.partitions", os.getenv("SPARK_SHUFFLE_PARTITIONS", "10"))
        .config("spark.default.parallelism", "4")
        .config("spark.sql.parquet.compression.codec", "snappy")
        .config("spark.sql.execution.arrow.pyspark.enabled", "true")
        .config("spark.sql.session.timeZone", "UTC")
    )

    spark = builder.getOrCreate()
    spark.sparkContext.setLogLevel("WARN")
    return spark
