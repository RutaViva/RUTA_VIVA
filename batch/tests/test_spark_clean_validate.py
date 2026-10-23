"""
batch/tests/test_spark_clean_validate.py
Pruebas unitarias para el Job 1 de PySpark, reglas de calidad (RN-01, CA-01) y evolución de esquema (CA-09).
"""
import pytest
from datetime import datetime
from pyspark.sql.types import (
    DoubleType,
    IntegerType,
    StringType,
    StructField,
    StructType,
)

from batch.spark_jobs.common.spark_session import get_spark_session
from batch.spark_jobs.common.quality_rules import apply_trip_quality_rules
from batch.spark_jobs.job1_clean_validate.schema_evolution import standardize_schema


@pytest.fixture(scope="session")
def spark():
    """Sesión de Spark compartida para las pruebas unitarias de batch."""
    session = get_spark_session("PySpark-Batch-UnitTests")
    yield session
    session.stop()


def test_schema_evolution_unifies_column_variants_ca09(spark):
    """
    CA-09: Unificación de esquemas de datos de viajes con distintas nomenclaturas históricas.
    """
    # Esquema legacy con nombres antiguos de NYC TLC
    legacy_data = [
        (1, "2026-10-15 14:00:00", "2026-10-15 14:20:00", 2, 3.5, 161, 230, 18.5, 3.5, 22.0)
    ]
    schema = StructType([
        StructField("VendorID", IntegerType(), True),
        StructField("tpep_pickup_datetime", StringType(), True),
        StructField("tpep_dropoff_datetime", StringType(), True),
        StructField("passenger_count", IntegerType(), True),
        StructField("trip_distance", DoubleType(), True),
        StructField("PULocationID", IntegerType(), True),
        StructField("DOLocationID", IntegerType(), True),
        StructField("fare_amount", DoubleType(), True),
        StructField("tip_amount", DoubleType(), True),
        StructField("total_amount", DoubleType(), True),
    ])

    raw_df = spark.createDataFrame(legacy_data, schema)
    canonical_df = standardize_schema(raw_df)

    expected_cols = [
        "vendor_id", "pickup_datetime", "dropoff_datetime", "passenger_count",
        "trip_distance", "pu_location_id", "do_location_id", "fare_amount",
        "tip_amount", "total_amount"
    ]
    assert canonical_df.columns == expected_cols
    assert canonical_df.count() == 1

    row = canonical_df.first()
    assert row.pu_location_id == 161
    assert row.do_location_id == 230
    assert row.trip_distance == 3.5


def test_quarantine_filters_invalid_distance_ca01(spark):
    """
    CA-01: Viaje con distancia inválida (< 0.1 o > 100) se desvía a cuarentena con motivo 'distancia inválida'.
    """
    data = [
        (
            1,
            datetime(2026, 10, 15, 10, 0, 0),
            datetime(2026, 10, 15, 10, 15, 0),
            1,
            0.05,  # Distancia inválida (< 0.1)
            161,
            162,
            15.0,
            2.0,
            17.0,
        )
    ]
    cols = [
        "vendor_id", "pickup_datetime", "dropoff_datetime", "passenger_count",
        "trip_distance", "pu_location_id", "do_location_id", "fare_amount",
        "tip_amount", "total_amount"
    ]
    df = spark.createDataFrame(data, cols)
    evaluated = apply_trip_quality_rules(df)

    row = evaluated.first()
    assert row.is_valid is False
    assert row.quarantine_reason == "distancia inválida"
    assert row.rejected_at is not None


def test_quarantine_filters_negative_or_zero_fare_ca01(spark):
    """
    CA-01: Viaje con tarifa negativa o cero se desvía a cuarentena con motivo 'tarifa negativa o cero'.
    """
    data = [
        (
            1,
            datetime(2026, 10, 15, 10, 0, 0),
            datetime(2026, 10, 15, 10, 15, 0),
            1,
            2.5,
            161,
            162,
            -5.0,  # Tarifa negativa
            0.0,
            -5.0,
        )
    ]
    cols = [
        "vendor_id", "pickup_datetime", "dropoff_datetime", "passenger_count",
        "trip_distance", "pu_location_id", "do_location_id", "fare_amount",
        "tip_amount", "total_amount"
    ]
    df = spark.createDataFrame(data, cols)
    evaluated = apply_trip_quality_rules(df)

    row = evaluated.first()
    assert row.is_valid is False
    assert row.quarantine_reason == "tarifa negativa o cero"


def test_quarantine_filters_invalid_zone_ids_ca01(spark):
    """
    CA-01: Viaje con zona fuera del rango oficial [1, 265] va a cuarentena con motivo 'identificador de zona inexistente'.
    """
    data = [
        (
            1,
            datetime(2026, 10, 15, 10, 0, 0),
            datetime(2026, 10, 15, 10, 15, 0),
            1,
            2.5,
            0,  # Zona 0 inválida
            300,  # Zona 300 inválida
            15.0,
            2.0,
            17.0,
        )
    ]
    cols = [
        "vendor_id", "pickup_datetime", "dropoff_datetime", "passenger_count",
        "trip_distance", "pu_location_id", "do_location_id", "fare_amount",
        "tip_amount", "total_amount"
    ]
    df = spark.createDataFrame(data, cols)
    evaluated = apply_trip_quality_rules(df)

    row = evaluated.first()
    assert row.is_valid is False
    assert row.quarantine_reason == "identificador de zona inexistente"


def test_valid_trip_passes_cleanly(spark):
    """
    Verifica que un viaje legítimo cumple todos los criterios y es marcado como válido para la capa Silver.
    """
    data = [
        (
            1,
            datetime(2026, 10, 15, 10, 0, 0),
            datetime(2026, 10, 15, 10, 20, 0),
            1,
            4.2,
            161,
            237,
            18.5,
            3.0,
            21.5,
        )
    ]
    cols = [
        "vendor_id", "pickup_datetime", "dropoff_datetime", "passenger_count",
        "trip_distance", "pu_location_id", "do_location_id", "fare_amount",
        "tip_amount", "total_amount"
    ]
    df = spark.createDataFrame(data, cols)
    evaluated = apply_trip_quality_rules(df)

    row = evaluated.first()
    assert row.is_valid is True
    assert row.quarantine_reason is None
    assert row.duration_minutes == 20.0
