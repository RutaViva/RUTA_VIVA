"""Tests for the canonical Spark Job 1 implementation."""

from __future__ import annotations

import sys
from pathlib import Path
from datetime import datetime

import pytest
from pyspark.sql import SparkSession

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "spark_jobs"))

from job1_clean_validate import _normalize_f1_columns, _prepare_trips


@pytest.fixture(scope="module")
def spark() -> SparkSession:
    session = (
        SparkSession.builder.master("local[2]")
        .appName("RutaViva-Job1-Tests")
        .config("spark.sql.session.timeZone", "America/New_York")
        .getOrCreate()
    )
    session.sparkContext.setLogLevel("ERROR")
    yield session
    session.stop()


def _trip_frame(spark: SparkSession, **overrides: object):
    values = {
        "tpep_pickup_datetime": datetime(2026, 10, 15, 10, 0),
        "tpep_dropoff_datetime": datetime(2026, 10, 15, 10, 20),
        "trip_distance": 4.2,
        "fare_amount": 18.5,
        "total_amount": 21.5,
        "pickup_zone_id": 161,
        "dropoff_zone_id": 237,
    }
    values.update(overrides)
    return spark.createDataFrame([values])


def test_schema_normalization_supports_tlc_name_variants(
    spark: SparkSession,
) -> None:
    legacy = spark.createDataFrame(
        [
            (
                "2026-10-15 14:00:00",
                "2026-10-15 14:20:00",
                3.5,
                161,
                230,
                18.5,
                22.0,
            )
        ],
        [
            "pickup_datetime",
            "dropoff_datetime",
            "trip_distance",
            "PULocationID",
            "DOLocationID",
            "fare_amount",
            "total_amount",
        ],
    )

    canonical = _prepare_trips(_normalize_f1_columns(legacy)).first()

    assert canonical.pickup_zone_id == 161
    assert canonical.dropoff_zone_id == 230
    assert canonical.trip_distance == 3.5
    assert canonical.reject_reason == ""


@pytest.mark.parametrize(
    ("overrides", "expected_reason"),
    [
        ({"trip_distance": 0.05}, "distance_out_of_range"),
        ({"fare_amount": 0.0}, "fare_amount_non_positive"),
        ({"pickup_zone_id": 0}, "invalid_pickup_zone_id"),
    ],
)
def test_invalid_trips_are_marked_for_quarantine(
    spark: SparkSession,
    overrides: dict[str, object],
    expected_reason: str,
) -> None:
    trip = _prepare_trips(_trip_frame(spark, **overrides)).first()

    assert expected_reason in trip.reject_reason


def test_valid_trip_has_no_rejection_reason(spark: SparkSession) -> None:
    trip = _prepare_trips(_trip_frame(spark)).first()

    assert trip.reject_reason == ""
    assert trip.pickup_year == 2026
    assert trip.pickup_month == 10


def test_missing_required_f1_columns_are_rejected(spark: SparkSession) -> None:
    raw = spark.createDataFrame([("2026-10-15",)], ["pickupdatetime"])

    with pytest.raises(ValueError, match="esquema TLC reconocido"):
        _normalize_f1_columns(raw)
