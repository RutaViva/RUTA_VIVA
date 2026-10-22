"""
batch/spark-jobs/common/quality_rules.py
Reglas de calidad de datos para viajes de taxi de RutaViva (RN-01, CA-01).

Criterio CA-01:
Un viaje se clasifica como inválido y se desvía a la capa de cuarentena con un motivo descriptivo:
1. "distancia inválida": trip_distance < 0.1 o trip_distance > 100.0
2. "tarifa negativa o cero": fare_amount <= 0.0
3. "duración absurda": duration_minutes < 1.0 o duration_minutes > 300.0
4. "identificador de zona inexistente": pu_location_id o do_location_id fuera de [1, 265] o nulos
5. "fechas invertidas": dropoff_datetime <= pickup_datetime
"""
from pyspark.sql import DataFrame
from pyspark.sql import functions as F
from pyspark.sql.types import StringType


def apply_trip_quality_rules(df: DataFrame) -> DataFrame:
    """
    Evalúa cada registro y añade las columnas:
    - is_valid (Boolean): True si pasa todas las reglas de calidad, False en caso contrario.
    - quarantine_reason (String): Descripción del motivo del rechazo según CA-01.
    - rejected_at (Timestamp): Fecha/hora UTC en que el registro fue evaluado.
    """
    # 1. Calcular duración en minutos a partir de timestamps
    duration_col = (F.col("dropoff_datetime").cast("long") - F.col("pickup_datetime").cast("long")) / 60.0
    df_with_duration = df.withColumn("duration_minutes", F.round(duration_col, 2))

    # 2. Condiciones individuales de falla
    c_invalid_distance = (F.col("trip_distance") < 0.1) | (F.col("trip_distance") > 100.0) | F.col("trip_distance").isNull()
    c_invalid_fare = (F.col("fare_amount") <= 0.0) | F.col("fare_amount").isNull()
    c_invalid_duration = (F.col("duration_minutes") < 1.0) | (F.col("duration_minutes") > 300.0)
    c_invalid_zones = (
        F.col("pu_location_id").isNull()
        | F.col("do_location_id").isNull()
        | (F.col("pu_location_id") < 1)
        | (F.col("pu_location_id") > 265)
        | (F.col("do_location_id") < 1)
        | (F.col("do_location_id") > 265)
    )
    c_inverted_dates = F.col("dropoff_datetime") <= F.col("pickup_datetime")

    # 3. Construcción del motivo de cuarentena (prioridad estricta)
    reason_expr = (
        F.when(c_invalid_distance, F.lit("distancia inválida"))
        .when(c_invalid_fare, F.lit("tarifa negativa o cero"))
        .when(c_invalid_duration, F.lit("duración absurda"))
        .when(c_invalid_zones, F.lit("identificador de zona inexistente"))
        .when(c_inverted_dates, F.lit("fechas invertidas"))
        .otherwise(F.lit(None).cast(StringType()))
    )

    evaluated_df = (
        df_with_duration
        .withColumn("quarantine_reason", reason_expr)
        .withColumn("is_valid", F.col("quarantine_reason").isNull())
        .withColumn(
            "rejected_at",
            F.when(F.col("is_valid").isNotNull() & (~F.col("is_valid")), F.current_timestamp())
            .otherwise(F.lit(None))
        )
    )

    return evaluated_df
