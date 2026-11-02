from __future__ import annotations

import os
from typing import Sequence

from pyspark.sql import DataFrame, SparkSession


def required_env(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        raise ValueError(f"Falta la variable de entorno obligatoria {name}.")
    return value


def join_path(base: str, child: str) -> str:
    return f"{base.rstrip('/')}/{child.lstrip('/')}"


def read_source(spark: SparkSession, path: str, format_env: str) -> DataFrame:
    source_format = os.environ.get(format_env, "").strip().lower()
    if not source_format:
        filename = path.rsplit("/", 1)[-1]
        source_format = filename.rsplit(".", 1)[-1].lower() if "." in filename else "csv"

    reader = spark.read.option("recursiveFileLookup", "true")
    if source_format == "csv":
        return reader.option("header", "true").csv(path)
    if source_format == "json":
        return reader.json(path)
    if source_format == "parquet":
        return reader.parquet(path)
    raise ValueError(f"{format_env} debe ser csv, json o parquet; se recibió {source_format!r}.")


def list_source_files(spark: SparkSession, path: str) -> list[str]:
    hadoop_path = spark.sparkContext._jvm.org.apache.hadoop.fs.Path(path)
    filesystem = hadoop_path.getFileSystem(spark.sparkContext._jsc.hadoopConfiguration())
    if not filesystem.exists(hadoop_path):
        raise FileNotFoundError(f"No existe la ruta de entrada: {path}")

    status = filesystem.getFileStatus(hadoop_path)
    if status.isFile():
        return [hadoop_path.toString()]

    files = filesystem.listFiles(hadoop_path, True)
    paths = []
    while files.hasNext():
        file_path = files.next().getPath()
        if not file_path.getName().startswith((".", "_")):
            paths.append(file_path.toString())
    return sorted(paths)


def path_exists(spark: SparkSession, path: str) -> bool:
    hadoop_path = spark.sparkContext._jvm.org.apache.hadoop.fs.Path(path)
    filesystem = hadoop_path.getFileSystem(spark.sparkContext._jsc.hadoopConfiguration())
    return filesystem.exists(hadoop_path)


def write_parquet(
    df: DataFrame, path: str, partition_by: Sequence[str] = ()
) -> None:
    writer = df.write.mode("overwrite")
    if partition_by:
        writer = writer.partitionBy(*partition_by)
    writer.parquet(path)


def replace_partition(
    spark: SparkSession,
    df: DataFrame,
    path: str,
    partition_by: Sequence[str],
    values: Sequence[object],
) -> None:
    if not partition_by or len(partition_by) != len(values):
        raise ValueError("Partition columns and values must have the same nonzero length.")
    is_empty = df.rdd.isEmpty()

    partition_path = path.rstrip("/")
    for column, value in zip(partition_by, values):
        if value is None:
            raise ValueError("Partition values cannot be null.")
        partition_path = join_path(partition_path, f"{column}={value}")

    hadoop_path = spark.sparkContext._jvm.org.apache.hadoop.fs.Path(partition_path)
    filesystem = hadoop_path.getFileSystem(
        spark.sparkContext._jsc.hadoopConfiguration()
    )
    if filesystem.exists(hadoop_path) and not filesystem.delete(hadoop_path, True):
        raise OSError(f"No se pudo reemplazar la partición {partition_path}")

    if not is_empty:
        df.write.mode("append").partitionBy(*partition_by).parquet(path)
