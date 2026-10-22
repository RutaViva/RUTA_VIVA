"""
batch/spark-jobs/job1_clean_validate/schema_evolution.py
Mapeo y unificación de esquemas de viajes de NYC TLC a lo largo de distintos años (CA-09).
Estandariza nomenclaturas divergentes a un esquema canónico homogéneo.
"""
from pyspark.sql import DataFrame
from pyspark.sql import functions as F
from pyspark.sql.types import (
    DoubleType,
    IntegerType,
    StructField,
    StructType,
    TimestampType,
)

# Esquema canónico estándar esperado en la capa Silver
CANONICAL_SCHEMA = StructType([
    StructField("vendor_id", IntegerType(), True),
    StructField("pickup_datetime", TimestampType(), False),
    StructField("dropoff_datetime", TimestampType(), False),
    StructField("passenger_count", IntegerType(), True),
    StructField("trip_distance", DoubleType(), False),
    StructField("pu_location_id", IntegerType(), False),
    StructField("do_location_id", IntegerType(), False),
    StructField("fare_amount", DoubleType(), False),
    StructField("tip_amount", DoubleType(), True),
    StructField("total_amount", DoubleType(), False),
])

# Mapeos de alias conocidos en fuentes históricas de NYC Yellow Taxi
COLUMN_ALIASES = {
    "vendor_id": ["VendorID", "vendor_id", "vendor_name", "Vendor_Id"],
    "pickup_datetime": ["tpep_pickup_datetime", "Trip_Pickup_DateTime", "pickup_datetime", "Trip_Pickup_Date"],
    "dropoff_datetime": ["tpep_dropoff_datetime", "Trip_Dropoff_DateTime", "dropoff_datetime", "Trip_Dropoff_Date"],
    "passenger_count": ["passenger_count", "Passenger_Count"],
    "trip_distance": ["trip_distance", "Trip_Distance"],
    "pu_location_id": ["PULocationID", "pu_location_id", "pulocationid", "PU_Location_ID", "PickupLocationID"],
    "do_location_id": ["DOLocationID", "do_location_id", "dolocationid", "DO_Location_ID", "DropoffLocationID"],
    "fare_amount": ["fare_amount", "Fare_Amt", "fare", "Fare_Amount"],
    "tip_amount": ["tip_amount", "Tip_Amt", "tip", "Tip_Amount"],
    "total_amount": ["total_amount", "Total_Amt", "total", "Total_Amount"],
}


def standardize_schema(df: DataFrame) -> DataFrame:
    """
    Toma un DataFrame con columnas en cualquier variante histórica
    y lo proyecta al esquema canónico estándar con los tipos de datos correctos.
    """
    existing_cols = {c.lower(): c for c in df.columns}
    select_exprs = []

    for target_col, aliases in COLUMN_ALIASES.items():
        found = False
        for alias in aliases:
            if alias.lower() in existing_cols:
                actual_name = existing_cols[alias.lower()]
                select_exprs.append(F.col(actual_name).alias(target_col))
                found = True
                break
        if not found:
            # Si una columna opcional falta (ej: tip_amount), se asigna 0.0 o null
            if target_col in ("tip_amount", "passenger_count"):
                default_val = 0 if target_col == "passenger_count" else 0.0
                select_exprs.append(F.lit(default_val).alias(target_col))
            else:
                select_exprs.append(F.lit(None).alias(target_col))

    standardized = df.select(*select_exprs)

    # Casteo seguro a los tipos canónicos
    return (
        standardized
        .withColumn("vendor_id", F.col("vendor_id").cast(IntegerType()))
        .withColumn("pickup_datetime", F.col("pickup_datetime").cast(TimestampType()))
        .withColumn("dropoff_datetime", F.col("dropoff_datetime").cast(TimestampType()))
        .withColumn("passenger_count", F.col("passenger_count").cast(IntegerType()))
        .withColumn("trip_distance", F.col("trip_distance").cast(DoubleType()))
        .withColumn("pu_location_id", F.col("pu_location_id").cast(IntegerType()))
        .withColumn("do_location_id", F.col("do_location_id").cast(IntegerType()))
        .withColumn("fare_amount", F.col("fare_amount").cast(DoubleType()))
        .withColumn("tip_amount", F.col("tip_amount").cast(DoubleType()))
        .withColumn("total_amount", F.col("total_amount").cast(DoubleType()))
    )
