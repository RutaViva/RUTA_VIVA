"""Enrich Silver trips and write the RutaViva Gold tables."""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

import geopandas as gpd
import pandas as pd
from pyspark.sql import DataFrame, SparkSession
from pyspark.sql import functions as F
from pyspark.sql.types import IntegerType, StringType, StructField, StructType

from common.io import (
    join_path,
    path_exists,
    read_source,
    replace_partition,
    required_env,
    write_parquet,
)
from common.spark_session import create_spark_session

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))

from services.seed_cli.app.zone_data import load_zone_catalog, load_zones_gdf


def _require_columns(df: DataFrame, columns: tuple[str, ...], source: str) -> None:
    missing = sorted(set(columns) - set(df.columns))
    if missing:
        raise ValueError(f"{source} no tiene el esquema canónico; faltan: {', '.join(missing)}")


def _zone_dimension(
    spark: SparkSession, zones: gpd.GeoDataFrame, catalog: pd.DataFrame
) -> DataFrame:
    shape_zones = zones[["LocationID", "borough", "zone"]].rename(
        columns={
            "LocationID": "zone_key",
            "borough": "shape_borough",
            "zone": "shape_zone_name",
        }
    )
    catalog_zones = catalog.rename(
        columns={
            "LocationID": "zone_key",
            "Borough": "catalog_borough",
            "Zone": "catalog_zone_name",
        }
    )
    merged = catalog_zones.merge(shape_zones, on="zone_key", how="left")
    records = [
        (
            int(row.zone_key),
            row.shape_borough
            if isinstance(row.shape_borough, str)
            else row.catalog_borough,
            row.shape_zone_name
            if isinstance(row.shape_zone_name, str)
            else row.catalog_zone_name,
        )
        for row in merged.itertuples(index=False)
    ]
    schema = StructType(
        [
            StructField("zone_key", IntegerType(), nullable=False),
            StructField("borough", StringType(), nullable=False),
            StructField("zone_name", StringType(), nullable=False),
        ]
    )
    return spark.createDataFrame(records, schema)


def _zone_lookup_udf(spark: SparkSession, zones: gpd.GeoDataFrame):
    records = tuple(
        (int(row.LocationID), bytes(row.geometry.wkb))
        for row in zones[["LocationID", "geometry"]]
        .sort_values("LocationID")
        .itertuples(index=False)
    )
    zone_records = spark.sparkContext.broadcast(records)
    worker_index = {}

    def locate_zone(latitude, longitude):
        if latitude is None or longitude is None:
            return None
        if "tree" not in worker_index:
            from shapely import wkb
            from shapely.strtree import STRtree

            values = zone_records.value
            worker_index["zone_ids"] = [record[0] for record in values]
            worker_index["tree"] = STRtree(
                [wkb.loads(record[1]) for record in values]
            )

        from shapely.geometry import Point

        matches = worker_index["tree"].query(
            Point(float(longitude), float(latitude)), predicate="within"
        )
        if len(matches) == 0:
            return None
        return min(worker_index["zone_ids"][int(index)] for index in matches)

    return F.udf(locate_zone, "int")


def _weather_dimension(source: DataFrame) -> DataFrame:
    _require_columns(source, ("weather_hour", "rain_mm_h"), "F3")
    hourly = (
        source.select(
            F.date_trunc("hour", F.col("weather_hour").cast("timestamp")).alias(
                "weather_hour"
            ),
            F.col("rain_mm_h").cast("double").alias("rain_mm_h"),
        )
        .filter(F.col("weather_hour").isNotNull())
        .groupBy("weather_hour")
        .agg(F.avg("rain_mm_h").alias("rain_mm_h"))
    )
    return (
        hourly.withColumn(
            "weather_key", F.date_format("weather_hour", "yyyyMMddHH").cast("int")
        )
        .withColumn(
            "rain_category",
            F.when(F.col("rain_mm_h").isNull(), F.lit(None).cast("string"))
            .when(F.col("rain_mm_h") <= 2, "low")
            .when(F.col("rain_mm_h") <= 10, "moderate")
            .when(F.col("rain_mm_h") <= 22, "heavy")
            .otherwise("extreme"),
        )
        .withColumn("rain_above_threshold", F.col("rain_mm_h") > 2)
        .select(
            "weather_key",
            "weather_hour",
            "rain_mm_h",
            "rain_category",
            "rain_above_threshold",
        )
    )


def _event_intervals(source: DataFrame) -> DataFrame:
    _require_columns(source, ("zone_id", "starts_at", "ends_at"), "F7")
    return (
        source.select(
            F.col("zone_id").cast("int").alias("zone_id"),
            F.col("starts_at").cast("timestamp").alias("starts_at"),
            F.col("ends_at").cast("timestamp").alias("ends_at"),
        )
        .filter(
            F.col("starts_at").isNotNull()
            & F.col("ends_at").isNotNull()
            & (F.col("ends_at") > F.col("starts_at"))
        )
        .distinct()
    )


def _zone_intervals(source: DataFrame) -> DataFrame:
    columns = (
        "zone_id",
        "interval_start",
        "requests",
        "free_vehicles",
        "pressure_index",
        "estimated_wait_minutes",
    )
    _require_columns(source, columns, "ZONE_STATE_HISTORY")
    return source.select(
        F.col("zone_id").cast("int"),
        F.col("interval_start").cast("timestamp"),
        F.col("requests").cast("int"),
        F.col("free_vehicles").cast("int"),
        F.col("pressure_index").cast("double"),
        F.col("estimated_wait_minutes").cast("double"),
    )


def _date_dimension(trips: DataFrame, intervals: DataFrame) -> DataFrame:
    dates = (
        trips.select(F.to_date("tpep_pickup_datetime").alias("full_date"))
        .unionByName(intervals.select(F.to_date("interval_start").alias("full_date")))
        .filter(F.col("full_date").isNotNull())
        .distinct()
    )
    return (
        dates.withColumn(
            "date_key", F.date_format("full_date", "yyyyMMdd").cast("int")
        )
        .withColumn("month", F.month("full_date"))
        .withColumn("year", F.year("full_date"))
        .select("date_key", "full_date", "month", "year")
    )


def _time_slot_dimension(spark: SparkSession) -> DataFrame:
    return spark.range(24).select(
        F.col("id").cast("int").alias("time_slot_key"),
        F.format_string("%02d:00-%02d:59", F.col("id"), F.col("id")).alias(
            "label"
        ),
    )


def _trip_fact(
    trips: DataFrame,
    weather: DataFrame,
    events: DataFrame,
    locate_zone,
) -> DataFrame:
    _require_columns(
        trips,
        ("tpep_pickup_datetime", "tpep_dropoff_datetime", "fare_amount", "total_amount"),
        "Silver",
    )

    def zone_key(zone_id: str, latitude: str, longitude: str):
        zone = (
            F.col(zone_id).cast("int")
            if zone_id in trips.columns
            else F.lit(None).cast("int")
        )
        if latitude in trips.columns and longitude in trips.columns:
            return F.coalesce(zone, locate_zone(latitude, longitude))
        if zone_id not in trips.columns:
            raise ValueError(f"Silver requiere {zone_id} o coordenadas {latitude}/{longitude}.")
        return zone

    base = trips.select(
        F.col("tpep_pickup_datetime").cast("timestamp"),
        F.col("tpep_dropoff_datetime").cast("timestamp"),
        zone_key("pickup_zone_id", "pickup_latitude", "pickup_longitude").alias("pickup_zone_key"),
        zone_key("dropoff_zone_id", "dropoff_latitude", "dropoff_longitude").alias("dropoff_zone_key"),
        F.col("fare_amount").cast("double").alias("base_fare"),
        F.col("total_amount").cast("double").alias("fare_amount"),
    ).withColumn(
        "trip_key",
        F.xxhash64(
            "tpep_pickup_datetime",
            "tpep_dropoff_datetime",
            "pickup_zone_key",
            "dropoff_zone_key",
            "base_fare",
            "fare_amount",
        ),
    )

    event_hits = (
        base.alias("trip")
        .join(
            events.alias("event"),
            (
                F.col("event.zone_id").isNull()
                | (F.col("trip.pickup_zone_key") == F.col("event.zone_id"))
            )
            & (F.col("trip.tpep_pickup_datetime") >= F.col("event.starts_at"))
            & (F.col("trip.tpep_pickup_datetime") < F.col("event.ends_at")),
            "left_semi",
        )
        .select("trip_key")
        .distinct()
        .withColumn("is_special_event", F.lit(True))
    )
    hourly_weather = weather.select("weather_hour", "weather_key").alias("weather")
    return (
        base.withColumn(
            "pickup_hour", F.date_trunc("hour", F.col("tpep_pickup_datetime"))
        )
        .join(
            hourly_weather,
            F.col("pickup_hour") == F.col("weather.weather_hour"),
            "left",
        )
        .join(event_hits, "trip_key", "left")
        .withColumn(
            "date_key",
            F.date_format("tpep_pickup_datetime", "yyyyMMdd").cast("int"),
        )
        .withColumn("time_slot_key", F.hour("tpep_pickup_datetime"))
        .withColumn("extra_revenue", F.col("fare_amount") - F.col("base_fare"))
        .withColumn("multiplier", F.lit(None).cast("double"))
        .withColumn("wait_minutes", F.lit(None).cast("double"))
        .withColumn("rule_version_key", F.lit(None).cast("int"))
        .withColumn(
            "is_special_event",
            F.coalesce(F.col("is_special_event"), F.lit(False)),
        )
        .withColumn("year", F.year("tpep_pickup_datetime"))
        .withColumn("month", F.month("tpep_pickup_datetime"))
        .select(
            "trip_key",
            "pickup_zone_key",
            "dropoff_zone_key",
            "date_key",
            "time_slot_key",
            "weather_key",
            "rule_version_key",
            "base_fare",
            "fare_amount",
            "multiplier",
            "extra_revenue",
            "wait_minutes",
            "is_special_event",
            "year",
            "month",
        )
    )


def _zone_interval_fact(
    intervals: DataFrame, weather: DataFrame
) -> DataFrame:
    hourly = intervals.withColumn(
        "interval_hour", F.date_trunc("hour", F.col("interval_start"))
    )
    return (
        hourly.join(
            weather.select("weather_hour", "weather_key").alias("weather"),
            F.col("interval_hour") == F.col("weather.weather_hour"),
            "left",
        )
        .withColumn(
            "date_key",
            F.date_format("interval_start", "yyyyMMdd").cast("int"),
        )
        .withColumn("time_slot_key", F.hour("interval_start"))
        .withColumn(
            "is_underserved",
            (F.col("free_vehicles") == 0) & (F.col("requests") > 0),
        )
        .withColumn("year", F.year("interval_start"))
        .withColumn("month", F.month("interval_start"))
        .select(
            F.col("zone_id").alias("zone_key"),
            "date_key",
            "time_slot_key",
            "weather_key",
            "requests",
            "free_vehicles",
            "pressure_index",
            "is_underserved",
            "year",
            "month",
        )
    )


def _rn11_monthly_report(
    trip_requests: DataFrame,
    intervals: DataFrame,
    complaints: DataFrame,
    zones: DataFrame,
    year: int,
    month: int,
) -> DataFrame:
    _require_columns(
        trip_requests,
        ("zone_id", "requested_at", "charged_fare", "multiplier"),
        "TRIP_REQUEST/FARE_AUDIT",
    )
    _require_columns(
        intervals,
        ("zone_id", "interval_start", "estimated_wait_minutes"),
        "ZONE_STATE_HISTORY",
    )
    _require_columns(
        complaints,
        ("zone_id", "created_at"),
        "SERVICE_COMPLAINT",
    )
    _require_columns(zones, ("zone_key", "borough"), "DIM_ZONE")

    zone_boroughs = zones.select(
        F.col("zone_key").cast("int").alias("zone_id"), "borough"
    )
    requests = trip_requests.select(
        F.col("zone_id").cast("int").alias("zone_id"),
        F.col("requested_at").cast("timestamp").alias("requested_at"),
        F.col("charged_fare").cast("double").alias("charged_fare"),
        F.col("multiplier").cast("double").alias("multiplier"),
    ).filter(
        (F.year("requested_at") == year) & (F.month("requested_at") == month)
    )
    request_metrics = (
        requests.join(zone_boroughs, "zone_id", "inner")
        .groupBy("borough")
        .agg(
            F.count(F.lit(1)).cast("long").alias("trip_count"),
            F.avg("charged_fare").alias("average_fare"),
            F.count("multiplier").alias("audited_trip_count"),
            F.sum(
                F.when(F.col("multiplier") > 1, 1).otherwise(0)
            ).alias("surge_trip_count"),
        )
        .withColumn(
            "multiplier_gt_one_pct",
            F.when(
                F.col("audited_trip_count") > 0,
                F.col("surge_trip_count") * F.lit(100.0)
                / F.col("audited_trip_count"),
            ).otherwise(F.lit(None).cast("double")),
        )
        .select(
            "borough",
            "trip_count",
            "average_fare",
            "multiplier_gt_one_pct",
        )
    )

    wait_metrics = (
        intervals.select(
            F.col("zone_id").cast("int").alias("zone_id"),
            F.col("interval_start").cast("timestamp").alias("interval_start"),
            F.col("estimated_wait_minutes")
            .cast("double")
            .alias("estimated_wait_minutes"),
        )
        .filter(
            (F.year("interval_start") == year)
            & (F.month("interval_start") == month)
        )
        .join(zone_boroughs, "zone_id", "inner")
        .groupBy("borough")
        .agg(F.avg("estimated_wait_minutes").alias("average_wait_minutes"))
    )

    complaint_metrics = (
        complaints.select(
            F.col("zone_id").cast("int").alias("zone_id"),
            F.col("created_at").cast("timestamp").alias("created_at"),
        )
        .filter(
            (F.year("created_at") == year) & (F.month("created_at") == month)
        )
        .join(zone_boroughs, "zone_id", "inner")
        .groupBy("borough")
        .agg(F.count(F.lit(1)).cast("long").alias("complaint_count"))
    )

    return (
        zones.select("borough")
        .distinct()
        .join(request_metrics, "borough", "left")
        .join(wait_metrics, "borough", "left")
        .join(complaint_metrics, "borough", "left")
        .withColumn("year", F.lit(year).cast("int"))
        .withColumn("month", F.lit(month).cast("int"))
        .withColumn(
            "trip_count",
            F.coalesce(F.col("trip_count"), F.lit(0)).cast("long"),
        )
        .withColumn(
            "complaint_count",
            F.coalesce(F.col("complaint_count"), F.lit(0)).cast("long"),
        )
        .select(
            "borough",
            "trip_count",
            "average_fare",
            "average_wait_minutes",
            "multiplier_gt_one_pct",
            "complaint_count",
            "year",
            "month",
        )
    )


def _write_table(
    spark: SparkSession,
    df: DataFrame,
    gold_path: str,
    table_name: str,
    year: int,
    month: int,
) -> None:
    path = join_path(gold_path, table_name)
    if {"year", "month"}.issubset(df.columns):
        replace_partition(spark, df, path, ("year", "month"), (year, month))
    else:
        write_parquet(df, path)


def _read_monthly_silver(
    spark: SparkSession,
    silver_path: str,
    quarantine_path: str,
    year: int,
    month: int,
) -> DataFrame:
    if path_exists(spark, silver_path):
        source = spark.read.parquet(silver_path)
    else:
        quarantine = spark.read.parquet(quarantine_path)
        source = quarantine.drop("reject_reason").limit(0)
    return source.filter(
        (F.col("pickup_year") == year) & (F.col("pickup_month") == month)
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--year", type=int, required=True)
    parser.add_argument("--month", type=int, choices=range(1, 13), required=True)
    args = parser.parse_args()

    bronze_path = required_env("S3_BRONZE_PATH")
    silver_path = required_env("S3_SILVER_PATH")
    quarantine_path = required_env("S3_QUARANTINE_PATH")
    gold_path = required_env("S3_GOLD_PATH")
    weather_path = os.environ.get("S3_WEATHER_PATH") or join_path(bronze_path, "f3")
    events_path = os.environ.get("S3_EVENTS_PATH") or join_path(bronze_path, "f7")
    history_path = os.environ.get("S3_ZONE_STATE_HISTORY_PATH") or join_path(
        bronze_path, "zone_state_history"
    )
    trip_requests_path = os.environ.get("S3_TRIP_REQUESTS_PATH") or join_path(
        bronze_path, "operational/trip_requests"
    )
    complaints_path = os.environ.get("S3_SERVICE_COMPLAINTS_PATH") or join_path(
        bronze_path, "operational/service_complaints"
    )
    shapefile_path = os.environ.get(
        "RUTAVIVA_ZONE_SHAPEFILE_PATH",
        str(
            PROJECT_ROOT
            / "services"
            / "seed_cli"
            / "app"
            / "data"
            / "shapefiles"
            / "taxi_zones.shp"
        ),
    )
    catalog_path = os.environ.get(
        "RUTAVIVA_ZONE_CATALOG_PATH",
        str(
            PROJECT_ROOT
            / "services"
            / "seed_cli"
            / "app"
            / "data"
            / "csv"
            / "taxi_zone_lookup.csv"
        ),
    )

    spark = create_spark_session("RutaViva-job2-enrich-model")
    try:
        trips = _read_monthly_silver(
            spark, silver_path, quarantine_path, args.year, args.month
        )
        weather = _weather_dimension(read_source(spark, weather_path, "F3_FORMAT"))
        events = _event_intervals(read_source(spark, events_path, "F7_FORMAT"))
        intervals = _zone_intervals(
            read_source(spark, history_path, "ZONE_STATE_HISTORY_FORMAT")
        ).filter(
            (F.year("interval_start") == args.year)
            & (F.month("interval_start") == args.month)
        )
        trip_requests = read_source(
            spark, trip_requests_path, "TRIP_REQUESTS_FORMAT"
        )
        complaints = read_source(
            spark, complaints_path, "SERVICE_COMPLAINTS_FORMAT"
        )
        zones_gdf = load_zones_gdf(shapefile_path)
        zone_catalog = load_zone_catalog(catalog_path)
        locate_zone = _zone_lookup_udf(spark, zones_gdf)
        zone_dimension = _zone_dimension(spark, zones_gdf, zone_catalog)

        _write_table(
            spark, _date_dimension(trips, intervals), gold_path, "DIM_DATE",
            args.year, args.month
        )
        _write_table(
            spark, _time_slot_dimension(spark), gold_path, "DIM_TIME_SLOT",
            args.year, args.month
        )
        _write_table(
            spark, weather, gold_path, "DIM_WEATHER", args.year, args.month
        )
        _write_table(
            spark,
            zone_dimension,
            gold_path,
            "DIM_ZONE",
            args.year,
            args.month,
        )
        _write_table(
            spark,
            _trip_fact(trips, weather, events, locate_zone),
            gold_path,
            "FACT_TRIP",
            args.year,
            args.month,
        )
        _write_table(
            spark,
            _zone_interval_fact(intervals, weather),
            gold_path,
            "FACT_ZONE_INTERVAL",
            args.year,
            args.month,
        )
        _write_table(
            spark,
            _rn11_monthly_report(
                trip_requests,
                intervals,
                complaints,
                zone_dimension,
                args.year,
                args.month,
            ),
            gold_path,
            "RN11_MONTHLY_REPORT",
            args.year,
            args.month,
        )
    finally:
        spark.stop()


if __name__ == "__main__":
    main()
