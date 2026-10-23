"""Small shared helpers for Spark input and output paths."""

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


def write_parquet(
    df: DataFrame, path: str, partition_by: Sequence[str] = ()
) -> None:
    writer = df.write.mode("overwrite")
    if partition_by:
        writer = writer.partitionBy(*partition_by)
    writer.parquet(path)
