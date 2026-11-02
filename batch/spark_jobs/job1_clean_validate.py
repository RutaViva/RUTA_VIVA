"""Validate canonical F1 trips and write Silver and Quarantine Parquet."""

from __future__ import annotations

import argparse
import os
import re
from pathlib import Path

from pyspark.sql import Column, DataFrame, SparkSession
from pyspark.sql import functions as F

from common.io import join_path, list_source_files, replace_partition, required_env
from common.spark_session import create_spark_session


REQUIRED_F1_COLUMNS = (
    "tpep_pickup_datetime",
    "tpep_dropoff_datetime",
    "trip_distance",
    "fare_amount",
    "total_amount",
)

F1_COLUMN_ALIASES = {
    "tpep_pickup_datetime": ("tpep_pickup_datetime", "pickup_datetime"),
    "tpep_dropoff_datetime": ("tpep_dropoff_datetime", "dropoff_datetime"),
    "trip_distance": ("trip_distance",),
    "pickup_longitude": ("pickup_longitude",),
    "pickup_latitude": ("pickup_latitude",),
    "dropoff_longitude": ("dropoff_longitude",),
    "dropoff_latitude": ("dropoff_latitude",),
    "fare_amount": ("fare_amount",),
    "extra": ("extra", "surcharge"),
    "total_amount": ("total_amount",),
    "pickup_zone_id": ("pickup_zone_id", "PULocationID"),
    "dropoff_zone_id": ("dropoff_zone_id", "DOLocationID"),
}


def _column_key(name: str) -> str:
    return "".join(character.lower() for character in name if character.isalnum())


def _normalize_f1_columns(raw: DataFrame) -> DataFrame:
    selected = []
    source_columns = {_column_key(column): column for column in raw.columns}
    missing = []
    for canonical, aliases in F1_COLUMN_ALIASES.items():
        sources = [source_columns[_column_key(alias)] for alias in aliases
                   if _column_key(alias) in source_columns]
        if sources:
            selected.append(F.coalesce(*[F.col(name) for name in sources]).alias(canonical))
        elif canonical in REQUIRED_F1_COLUMNS:
            missing.append(canonical)

    if missing:
        raise ValueError(
            "F1 no tiene un esquema TLC reconocido; no se pudieron resolver "
            "las columnas obligatorias: " + ", ".join(sorted(missing))
        )
    for zone_column in ("pickup_zone_id", "dropoff_zone_id"):
        aliases = F1_COLUMN_ALIASES[zone_column]
        present = any(_column_key(alias) in source_columns for alias in aliases)
        selected.append(F.lit(present).alias(f"_{zone_column}_present"))
    return raw.select(*selected)


def _read_f1_source(
    spark: SparkSession, path: str, year: int, month: int
) -> DataFrame:
    configured_format = os.environ.get("F1_FORMAT", "").strip().lower()
    if configured_format and configured_format not in {"csv", "json", "parquet"}:
        raise ValueError(
            f"F1_FORMAT debe ser csv, json o parquet; se recibió {configured_format!r}."
        )

    files = list_source_files(spark, path)
    if not files:
        raise FileNotFoundError(f"No se encontraron archivos F1 en {path}")
    # Filtramos los archivos que coinciden con el año y mes especificados, si es posible:
    period = re.compile(
        rf"(?<!\d){year}[-_/]0?{month}(?!\d)", re.IGNORECASE
    )

    matching_files = []

    # Esta parte lee los formats de los archivos en el path y filtra los que coinciden con el año y mes especificados
    for file_path in files:
        normalized_path = file_path.lower().replace("year=", "").replace("month=", "")
        if period.search(normalized_path):
            matching_files.append(file_path)
    if matching_files:
        files = matching_files

    normalized = []

    for file_path in files:
        # Si se especifica un formato en F1_FORMAT, lo usamos; de lo contrario, inferimos el formato del archivo a partir de su extensión
        source_format = configured_format or Path(file_path).suffix.lstrip(".").lower() or "csv"
        if source_format not in {"csv", "json", "parquet"}:
            raise ValueError(
                f"Formato F1 no soportado para {file_path}: {source_format!r}."
            )
        # Leemos segun el formato del archivo
        if source_format == "csv":
            raw = spark.read.option("header", "true").csv(file_path)
        elif source_format == "json":
            raw = spark.read.json(file_path)
        else:
            raw = spark.read.parquet(file_path)
        normalized.append(_normalize_f1_columns(raw))

    # Unificamos todos los DataFrames normalizados en uno solo, permitiendo columnas faltantes 
    # para cumplir con el requisito de esquema unificado a lo largo de los años
    result = normalized[0]
    for dataframe in normalized[1:]:
        result = result.unionByName(dataframe, allowMissingColumns=True)
    return result


def _prepare_trips(raw: DataFrame) -> DataFrame:
    missing = sorted(set(REQUIRED_F1_COLUMNS) - set(raw.columns))
    if missing:
        raise ValueError(
            "F1 no tiene un esquema TLC reconocido; faltan: " + ", ".join(missing)
        )

    columns = [
        F.col("tpep_pickup_datetime").cast("timestamp"),
        F.col("tpep_dropoff_datetime").cast("timestamp"),
        F.col("trip_distance").cast("double"),
        F.col("fare_amount").cast("double"),
        F.col("total_amount").cast("double"),
    ]

    # Agregamos las columnas de coordenadas y extra, asegurándonos de que estén presentes en el DataFrame final, 
    # incluso si no existen en el DataFrame original
    
    for coordinate in (
        "pickup_longitude",
        "pickup_latitude",
        "dropoff_longitude",
        "dropoff_latitude",
    ):
        columns.append(
            F.col(coordinate).cast("double")
            if coordinate in raw.columns
            else F.lit(None).cast("double").alias(coordinate)
        )

    # Agregamos la columna "extra" si está presente, o una columna nula si no lo está
    
    columns.append(
        F.col("extra").cast("double")
        if "extra" in raw.columns
        else F.lit(None).cast("double").alias("extra")
    )

    # Hacemos lo mismo para las columnas de zona de recogida y entrega, y agregamos marcadores booleanos para indicar si estaban presentes en el DataFrame original
    
    for zone_column in ("pickup_zone_id", "dropoff_zone_id"):
        marker = f"_{zone_column}_present"
        zone_present = (
            F.coalesce(F.col(marker), F.lit(False))
            if marker in raw.columns
            else F.lit(zone_column in raw.columns)
        )
        columns.extend([
            F.col(zone_column).cast("int")
            if zone_column in raw.columns
            else F.lit(None).cast("int").alias(zone_column),
            zone_present.alias(marker),
        ])

    trips = raw.select(*columns)
    pickup_zone_available = F.col("_pickup_zone_id_present")
    dropoff_zone_available = F.col("_dropoff_zone_id_present")

    def invalid_coordinates(
        latitude_name: str, longitude_name: str, has_zone: Column
    ) -> Column:
        latitude = F.col(latitude_name)
        longitude = F.col(longitude_name)
        present = latitude.isNotNull() | longitude.isNotNull()
        invalid = (
            latitude.isNull()
            != longitude.isNull()
        ) | (
            present
            & (
                (latitude < -90)
                | (latitude > 90)
                | (longitude < -180)
                | (longitude > 180)
                | F.isnan(latitude)
                | F.isnan(longitude)
                | ((latitude == 0) & (longitude == 0))
            )
        )
        return invalid | (~has_zone & (latitude.isNull() | longitude.isNull()))

    pickup_zone = F.col("pickup_zone_id")
    dropoff_zone = F.col("dropoff_zone_id")
    pickup_ts = F.col("tpep_pickup_datetime")
    dropoff_ts = F.col("tpep_dropoff_datetime")
    distance = F.col("trip_distance")
    fare = F.col("fare_amount")
    total = F.col("total_amount")
    # Guarda las razones de rechazo en una sola columna, separadas por punto y coma, para cada fila que no cumpla con las validaciones
    reject_reason = F.concat_ws(
        ";",
        F.when(
            distance.isNull()
            | F.isnan(distance)
            | (F.abs(distance) == float("inf"))
            | (distance < 0.1)
            | (distance > 100),
            "distance_out_of_range",
        ),
        F.when(
            fare.isNull()
            | F.isnan(fare)
            | (F.abs(fare) == float("inf"))
            | (fare <= 0),
            "fare_amount_non_positive",
        ),
        F.when(
            total.isNull() | F.isnan(total) | (F.abs(total) == float("inf")),
            "missing_total_amount",
        ),
        F.when(
            pickup_ts.isNull()
            | dropoff_ts.isNull()
            | (dropoff_ts < pickup_ts)
            | (
                (F.unix_timestamp(dropoff_ts) - F.unix_timestamp(pickup_ts))
                > 300 * 60
            ),
            "invalid_trip_duration",
        ),
        F.when(
            invalid_coordinates(
                "pickup_latitude", "pickup_longitude", pickup_zone_available
            ),
            "invalid_pickup_coordinates",
        ),
        F.when(
            invalid_coordinates(
                "dropoff_latitude", "dropoff_longitude", dropoff_zone_available
            ),
            "invalid_dropoff_coordinates",
        ),
        F.when(
            pickup_zone_available
            & (pickup_zone.isNull() | ~pickup_zone.between(1, 265)),
            "invalid_pickup_zone_id",
        ),
        F.when(
            dropoff_zone_available
            & (dropoff_zone.isNull() | ~dropoff_zone.between(1, 265)),
            "invalid_dropoff_zone_id",
        ),
    )

    return (
        trips.withColumn("reject_reason", reject_reason)
        .withColumn("pickup_year", F.year(pickup_ts))
        .withColumn("pickup_month", F.month(pickup_ts))
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--year", type=int, required=True)
    parser.add_argument("--month", type=int, choices=range(1, 13), required=True)
    args = parser.parse_args()

    bronze_path = required_env("S3_BRONZE_PATH")
    silver_path = required_env("S3_SILVER_PATH")
    quarantine_path = required_env("S3_QUARANTINE_PATH")
    f1_path = os.environ.get("S3_F1_PATH") or join_path(bronze_path, "f1")

    spark = create_spark_session("RutaViva-job1-clean-validate")
    try:
        trips = _prepare_trips(
            _read_f1_source(spark, f1_path, args.year, args.month)
        ).filter(
            (F.col("pickup_year") == args.year)
            & (F.col("pickup_month") == args.month)
        )
        if not trips.take(1):
            raise ValueError(
                f"No hay viajes F1 para el período {args.year:04d}-{args.month:02d}; "
                "no se reemplazaron las salidas."
            )

        internal_columns = ("reject_reason", "_pickup_zone_id_present", "_dropoff_zone_id_present")
        valid = trips.filter(F.col("reject_reason") == "").drop(*internal_columns)
        rejected = trips.filter(F.col("reject_reason") != "").drop(*internal_columns)
        partition_columns = ("pickup_year", "pickup_month")
        partition_values = (args.year, args.month)
        replace_partition(
            spark, valid, silver_path, partition_columns, partition_values
        )
        replace_partition(
            spark, rejected, quarantine_path, partition_columns, partition_values
        )
    finally:
        spark.stop()


if __name__ == "__main__":
    main()
