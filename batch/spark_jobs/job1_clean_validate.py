"""Validate canonical F1 trips and write Silver and Quarantine Parquet."""

from __future__ import annotations

import os

from pyspark.sql import Column, DataFrame, SparkSession
from pyspark.sql import functions as F

from common.io import join_path, read_source, required_env, write_parquet
from common.spark_session import create_spark_session


REQUIRED_COLUMNS = (
    "tpep_pickup_datetime",
    "tpep_dropoff_datetime",
    "trip_distance",
    "pickup_longitude",
    "pickup_latitude",
    "dropoff_longitude",
    "dropoff_latitude",
    "fare_amount",
    "extra",
    "total_amount",
)


def _prepare_trips(raw: DataFrame) -> DataFrame:
    missing = sorted(set(REQUIRED_COLUMNS) - set(raw.columns))
    if missing:
        raise ValueError(
            "F1 no tiene el esquema canónico; faltan: " + ", ".join(missing)
        )

    columns = [
        F.col("tpep_pickup_datetime").cast("timestamp"),
        F.col("tpep_dropoff_datetime").cast("timestamp"),
        F.col("trip_distance").cast("double"),
        F.col("pickup_longitude").cast("double"),
        F.col("pickup_latitude").cast("double"),
        F.col("dropoff_longitude").cast("double"),
        F.col("dropoff_latitude").cast("double"),
        F.col("fare_amount").cast("double"),
        F.col("extra").cast("double"),
        F.col("total_amount").cast("double"),
    ]
    for zone_column in ("pickup_zone_id", "dropoff_zone_id"):
        if zone_column in raw.columns:
            columns.append(F.col(zone_column).cast("int"))
        else:
            columns.append(F.lit(None).cast("int").alias(zone_column))

    trips = raw.select(*columns)
    pickup_zone_available = "pickup_zone_id" in raw.columns
    dropoff_zone_available = "dropoff_zone_id" in raw.columns

    def invalid_coordinates(
        latitude_name: str, longitude_name: str, has_zone: bool
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
        if not has_zone:
            invalid = invalid | latitude.isNull() | longitude.isNull()
        return invalid

    pickup_zone = F.col("pickup_zone_id")
    dropoff_zone = F.col("dropoff_zone_id")
    pickup_ts = F.col("tpep_pickup_datetime")
    dropoff_ts = F.col("tpep_dropoff_datetime")
    distance = F.col("trip_distance")
    fare = F.col("fare_amount")
    total = F.col("total_amount")
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
            F.lit(pickup_zone_available)
            & (pickup_zone.isNull() | ~pickup_zone.between(1, 265)),
            "invalid_pickup_zone_id",
        ),
        F.when(
            F.lit(dropoff_zone_available)
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
    bronze_path = required_env("S3_BRONZE_PATH")
    silver_path = required_env("S3_SILVER_PATH")
    quarantine_path = required_env("S3_QUARANTINE_PATH")
    f1_path = os.environ.get("S3_F1_PATH") or join_path(bronze_path, "f1")

    spark = create_spark_session("RutaViva-job1-clean-validate")
    try:
        trips = _prepare_trips(read_source(spark, f1_path, "F1_FORMAT"))
        valid = trips.filter(F.col("reject_reason") == "").drop("reject_reason")
        rejected = trips.filter(F.col("reject_reason") != "")
        write_parquet(valid, silver_path, ("pickup_year", "pickup_month"))
        write_parquet(rejected, quarantine_path, ("pickup_year", "pickup_month"))
    finally:
        spark.stop()


if __name__ == "__main__":
    main()
