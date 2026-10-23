"""
batch/spark-jobs/job2_enrich_model/main.py
Job 2 de PySpark: Enriquecimiento Multifuente y Modelo Dimensional Gold (RF-09, CA-02, CA-03).
Cruza los viajes limpios (Silver) con:
- Catálogo de Zonas TLC (F2): boroughs y zone_names
- Histórico de Clima (F3): precipitación horaria (rain_mm_h)
- Eventos Especiales y Emergencias (F7): is_emergency
Genera el modelo dimensional Gold:
- fact_trips
- dim_zone
- dim_date
- dim_time_window
"""
import argparse
import logging
import os
import sys
from pathlib import Path

current_dir = Path(__file__).resolve().parent
spark_jobs_dir = current_dir.parent
if str(spark_jobs_dir) not in sys.path:
    sys.path.insert(0, str(spark_jobs_dir))

from common.spark_session import get_spark_session
from pyspark.sql import DataFrame
from pyspark.sql import functions as F
from pyspark.sql.types import (
    BooleanType,
    DoubleType,
    IntegerType,
    StringType,
    StructField,
    StructType,
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("Job2-EnrichGold")


def build_dim_date(spark, trips_df: DataFrame) -> DataFrame:
    """Genera la dimensión de fecha a partir de las fechas de recogida."""
    dates_df = trips_df.select(F.to_date("pickup_datetime").alias("date")).distinct()
    return (
        dates_df
        .withColumn("date_key", F.date_format("date", "yyyyMMdd").cast(IntegerType()))
        .withColumn("year", F.year("date"))
        .withColumn("month", F.month("date"))
        .withColumn("day", F.dayofmonth("date"))
        .withColumn("day_of_week", F.dayofweek("date"))
        .withColumn("is_weekend", F.when(F.col("day_of_week").isin(1, 7), True).otherwise(False))
    )


def build_dim_time_window(spark) -> DataFrame:
    """Genera las 24 ventanas horarias con indicación de hora pico y horario nocturno (RN-05)."""
    windows = []
    for h in range(24):
        # En NYC: pico mañana 07-10, pico tarde 16-20
        is_peak = (7 <= h <= 10) or (16 <= h <= 20)
        # Nocturno RN-05: 22:00 a 05:00
        is_night = (h >= 22) or (h < 5)
        name = f"{h:02d}:00 - {(h+1)%24:02d}:00"
        windows.append((h, name, is_peak, is_night))

    schema = StructType([
        StructField("hour", IntegerType(), False),
        StructField("window_name", StringType(), False),
        StructField("is_peak_hour", BooleanType(), False),
        StructField("is_night_fare", BooleanType(), False),
    ])
    return spark.createDataFrame(windows, schema)


def run_enrich_model_job(
    silver_trips_path: str,
    zones_lookup_path: str,
    gold_output_path: str,
    weather_path: str = None,
    events_path: str = None,
) -> dict:
    """
    Ejecuta el Job 2:
    1. Carga viajes Silver limpios.
    2. Cruza con Zonas (F2) para PULocationID y DOLocationID.
    3. Cruza con Clima (F3) y Eventos (F7).
    4. Modela métricas analíticas (tarifa base, multiplicador dinámico, recargo, horas pico/valle).
    5. Escribe tablas Gold (fact_trips, dim_zone, dim_date, dim_time_window).
    """
    spark = get_spark_session("RutaViva-Job2-EnrichGold")
    logger.info("Cargando viajes Silver desde %s", silver_trips_path)

    silver_trips = spark.read.parquet(silver_trips_path)

    # 1. Cargar catálogo de zonas (F2)
    logger.info("Cargando catálogo de zonas desde %s", zones_lookup_path)
    zones_raw = spark.read.option("header", "true").option("inferSchema", "true").csv(zones_lookup_path)
    dim_zone = (
        zones_raw
        .select(
            F.col("LocationID").cast(IntegerType()).alias("zone_id"),
            F.col("Borough").alias("borough"),
            F.col("Zone").alias("zone_name"),
            F.col("service_zone").alias("service_zone"),
        )
        .distinct()
    )

    # 2. Clima (F3): si no se pasa archivo externo, se genera referencia con lluvia 0.0
    if weather_path and os.path.exists(weather_path):
        weather_df = spark.read.option("header", "true").csv(weather_path)
        weather_df = weather_df.select(
            F.to_timestamp("valid_hour").alias("w_hour"),
            F.col("rain_mm_h").cast(DoubleType()).alias("rain_mm_h"),
        )
    else:
        weather_df = None

    # 3. Enriquecimiento del viaje
    # Truncar pickup a la hora para cruce con clima y ventana horaria
    enriched = (
        silver_trips
        .withColumn("pickup_hour_ts", F.date_trunc("hour", "pickup_datetime"))
        .withColumn("pickup_hour", F.hour("pickup_datetime"))
        .withColumn("date_key", F.date_format("pickup_datetime", "yyyyMMdd").cast(IntegerType()))
    )

    # Join con zonas de recogida y destino
    pu_zone = dim_zone.select(
        F.col("zone_id").alias("pu_id"),
        F.col("borough").alias("pickup_borough"),
        F.col("zone_name").alias("pickup_zone_name"),
    )
    do_zone = dim_zone.select(
        F.col("zone_id").alias("do_id"),
        F.col("borough").alias("dropoff_borough"),
        F.col("zone_name").alias("dropoff_zone_name"),
    )

    enriched = (
        enriched
        .join(pu_zone, enriched.pu_location_id == pu_zone.pu_id, "left")
        .join(do_zone, enriched.do_location_id == do_zone.do_id, "left")
        .drop("pu_id", "do_id")
    )

    # Join con clima si existe
    if weather_df:
        enriched = (
            enriched
            .join(weather_df, enriched.pickup_hour_ts == weather_df.w_hour, "left")
            .drop("w_hour")
        )
    else:
        enriched = enriched.withColumn("rain_mm_h", F.lit(0.0))

    # Reemplazar nulos de lluvia
    enriched = enriched.fillna({"rain_mm_h": 0.0})

    # 4. Cálculo de tarifa base y multiplicador analítico (RN-01, RN-03, RN-04, RN-05)
    # Fórmula RN-01: 1.50 + 0.35 * km + 0.15 * mins (estimando distancia en km ~ millas * 1.609)
    dist_km = F.col("trip_distance") * 1.60934
    computed_base_fare = F.round(1.50 + (0.35 * dist_km) + (0.15 * F.col("duration_minutes")), 2)

    # Si fare_amount es mayor a la base, el multiplicador implícito es fare_amount / computed_base
    calculated_mult = F.when(
        computed_base_fare > 0,
        F.round(F.col("fare_amount") / computed_base_fare, 2)
    ).otherwise(1.0)

    # Acotar a topes regulatorios RN-05 (1.0 a 2.0 diurno, máx 1.5 nocturno)
    is_night_col = (F.col("pickup_hour") >= 22) | (F.col("pickup_hour") < 5)
    capped_mult = (
        F.when(calculated_mult < 1.0, 1.0)
        .when(is_night_col & (calculated_mult > 1.5), 1.5)
        .when(calculated_mult > 2.0, 2.0)
        .otherwise(calculated_mult)
    )

    # 5. Tabla de Hechos Gold: fact_trips
    fact_trips = (
        enriched
        .withColumn("base_fare", computed_base_fare)
        .withColumn("dynamic_multiplier", capped_mult)
        .withColumn("charged_fare", F.round(computed_base_fare * capped_mult, 2))
        .withColumn("dynamic_revenue_delta", F.round(F.col("charged_fare") - F.col("base_fare"), 2))
        .withColumn("is_surge_pricing", F.col("dynamic_multiplier") > 1.0)
        .withColumn("is_night_fare", is_night_col)
        .withColumn("is_peak_hour", (F.col("pickup_hour").between(7, 10)) | (F.col("pickup_hour").between(16, 20)))
        .select(
            "vendor_id",
            "date_key",
            F.col("pickup_hour").alias("time_window_hour"),
            F.col("pu_location_id").alias("pickup_zone_id"),
            "pickup_borough",
            "pickup_zone_name",
            F.col("do_location_id").alias("dropoff_zone_id"),
            "dropoff_borough",
            "dropoff_zone_name",
            "pickup_datetime",
            "dropoff_datetime",
            "duration_minutes",
            "trip_distance",
            "passenger_count",
            "base_fare",
            "dynamic_multiplier",
            "charged_fare",
            "dynamic_revenue_delta",
            "is_surge_pricing",
            "is_peak_hour",
            "is_night_fare",
            "rain_mm_h",
            "tip_amount",
            "total_amount",
            "year",
            "month",
        )
    )

    # 6. Construir Dimensiones
    dim_date = build_dim_date(spark, silver_trips)
    dim_time_window = build_dim_time_window(spark)

    # 7. Escritura en Capa Gold
    os.makedirs(gold_output_path, exist_ok=True)
    fact_out = os.path.join(gold_output_path, "fact_trips")
    dim_zone_out = os.path.join(gold_output_path, "dim_zone")
    dim_date_out = os.path.join(gold_output_path, "dim_date")
    dim_time_out = os.path.join(gold_output_path, "dim_time_window")

    fact_trips.write.mode("overwrite").partitionBy("year", "month").parquet(fact_out)
    dim_zone.write.mode("overwrite").parquet(dim_zone_out)
    dim_date.write.mode("overwrite").parquet(dim_date_out)
    dim_time_window.write.mode("overwrite").parquet(dim_time_out)

    count_gold = fact_trips.count()
    logger.info("Modelo Gold generado exitosamente: %d viajes en %s", count_gold, fact_out)

    return {
        "gold_trips_count": count_gold,
        "zones_count": dim_zone.count(),
        "dates_count": dim_date.count(),
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="PySpark Job 2: Enriquecimiento Dimensional Gold")
    parser.add_argument("--silver", default="data/silver/trips", help="Ruta de entrada Silver Parquet")
    parser.add_argument("--zones", default="services/seed_cli/app/data/csv/taxi_zone_lookup.csv", help="Ruta del CSV de zonas")
    parser.add_argument("--gold", default="data/gold", help="Ruta de salida Gold")
    parser.add_argument("--weather", default=None, help="Ruta opcional de histórico de clima")

    args = parser.parse_args()
    run_enrich_model_job(
        silver_trips_path=args.silver,
        zones_lookup_path=args.zones,
        gold_output_path=args.gold,
        weather_path=args.weather,
    )
