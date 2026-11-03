"""
batch/reports/generate_regulatory_report.py
Generador automático del Reporte Regulatorio Mensual de RutaViva (RN-11, CA-08, E-16).
Debe generarse el día 2 de cada mes sin intervención humana.
Calcula:
1. Total de viajes por distrito y zona de recogida.
2. Multiplicador promedio y distribución horaria.
3. Porcentaje de viajes con multiplicador > 1.0 (tarificación dinámica).
4. Delta de ingresos generados por el multiplicador dinámico frente a la tarifa base.
5. Impacto de lluvia en el multiplicador y tiempo de viaje.
"""
import argparse
import csv
import json
import logging
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

current_dir = Path(__file__).resolve().parent
project_root = current_dir.parents[1]
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from batch.spark_jobs.common.spark_session import create_spark_session
from pyspark.sql import functions as F

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("RegulatoryReport")


def generate_operational_regulatory_report(
    rn11_gold_path: str,
    output_dir: str,
    target_year: int,
    target_month: int,
) -> dict:
    """Export the monthly RN-11 Gold aggregate as a JSON and borough CSV report."""
    spark = create_spark_session("RutaViva-RN11-Regulatory-Report")
    try:
        report = spark.read.parquet(rn11_gold_path)
        required_columns = {
            "borough",
            "trip_count",
            "average_fare",
            "average_wait_minutes",
            "multiplier_gt_one_pct",
            "complaint_count",
            "year",
            "month",
        }
        missing_columns = sorted(required_columns - set(report.columns))
        if missing_columns:
            raise ValueError(
                "RN11_MONTHLY_REPORT no contiene las columnas requeridas: "
                + ", ".join(missing_columns)
            )

        monthly_report = report.filter(
            (F.col("year") == target_year) & (F.col("month") == target_month)
        ).orderBy("borough")
        borough_records = [
            row.asDict(recursive=True) for row in monthly_report.collect()
        ]
        if not borough_records:
            raise ValueError(
                f"RN11_MONTHLY_REPORT no tiene datos para "
                f"{target_year:04d}-{target_month:02d}."
            )

        metadata = {
            "regulatory_entity": "NYC Taxi and Limousine Commission (TLC) / RutaViva Compliance",
            "report_type": "Monthly Operational Fleet and Dynamic Pricing Report (RN-11 / CA-08)",
            "period": f"{target_year}-{target_month:02d}",
            "generated_at_utc": datetime.now(timezone.utc).isoformat(),
            "total_trips_evaluated": sum(
                int(row["trip_count"] or 0) for row in borough_records
            ),
            "total_complaints": sum(
                int(row["complaint_count"] or 0) for row in borough_records
            ),
            "borough_breakdown": borough_records,
        }

        destination = Path(output_dir)
        destination.mkdir(parents=True, exist_ok=True)
        json_path = destination / f"regulatory_report_{target_year}_{target_month:02d}.json"
        csv_path = (
            destination
            / f"regulatory_report_by_borough_{target_year}_{target_month:02d}.csv"
        )
        with json_path.open("w", encoding="utf-8") as output:
            json.dump(metadata, output, indent=2, ensure_ascii=False)
        with csv_path.open("w", encoding="utf-8", newline="") as output:
            writer = csv.DictWriter(output, fieldnames=borough_records[0].keys())
            writer.writeheader()
            writer.writerows(borough_records)

        logger.info("Reporte RN-11 generado para %04d-%02d en %s", target_year, target_month, destination)
        return metadata
    finally:
        spark.stop()


def generate_monthly_regulatory_report(
    gold_fact_path: str,
    output_dir: str,
    target_year: int = 2026,
    target_month: int = 10,
) -> dict:
    """
    Lee la tabla Gold fact_trips y genera los resúmenes regulatorios oficiales.
    """
    spark = create_spark_session("RutaViva-Regulatory-Report")
    logger.info("Leyendo datos Gold de %s para %04d-%02d...", gold_fact_path, target_year, target_month)

    df = spark.read.parquet(gold_fact_path)

    # Filtrar por mes/año regulatorio si existen las columnas de partición
    if "year" in df.columns and "month" in df.columns:
        month_df = df.filter((F.col("year") == target_year) & (F.col("month") == target_month))
        if month_df.count() == 0:
            logger.warning("No hay datos para %04d-%02d; usando todos los registros disponibles para el reporte.", target_year, target_month)
            month_df = df
    else:
        month_df = df

    total_trips = month_df.count()
    logger.info("Total de viajes analizados en el período regulatorio: %d", total_trips)

    # 1. Resumen por Distrito (Borough)
    borough_summary = (
        month_df.groupBy("pickup_borough")
        .agg(
            F.count("*").alias("total_trips"),
            F.round(F.avg("trip_distance"), 2).alias("avg_distance_miles"),
            F.round(F.avg("duration_minutes"), 2).alias("avg_duration_min"),
            F.round(F.avg("base_fare"), 2).alias("avg_base_fare"),
            F.round(F.avg("dynamic_multiplier"), 3).alias("avg_multiplier"),
            F.round(F.sum("dynamic_revenue_delta"), 2).alias("total_surge_revenue"),
            F.round((F.sum(F.when(F.col("is_surge_pricing") == True, 1).otherwise(0)) / F.count("*")) * 100.0, 2).alias("surge_trips_pct"),
        )
        .orderBy(F.desc("total_trips"))
    )

    # 2. Resumen Horario (Franjas del Día)
    hourly_summary = (
        month_df.groupBy("time_window_hour")
        .agg(
            F.count("*").alias("trips_in_hour"),
            F.round(F.avg("dynamic_multiplier"), 3).alias("avg_multiplier"),
            F.round(F.max("dynamic_multiplier"), 2).alias("max_multiplier"),
            F.round(F.avg("rain_mm_h"), 2).alias("avg_rain_mm_h"),
        )
        .orderBy("time_window_hour")
    )

    # 3. Top Zonas con Mayor Presión y Tarifa Dinámica
    top_surge_zones = (
        month_df.groupBy("pickup_zone_id", "pickup_zone_name", "pickup_borough")
        .agg(
            F.count("*").alias("zone_trips"),
            F.round(F.avg("dynamic_multiplier"), 3).alias("zone_avg_multiplier"),
            F.round(F.sum("dynamic_revenue_delta"), 2).alias("zone_surge_revenue"),
        )
        .orderBy(F.desc("zone_avg_multiplier"))
        .limit(10)
    )

    # Convertir a Pandas/JSON para exportación
    borough_records = [row.asDict() for row in borough_summary.collect()]
    hourly_records = [row.asDict() for row in hourly_summary.collect()]
    top_zones_records = [row.asDict() for row in top_surge_zones.collect()]

    report_metadata = {
        "regulatory_entity": "NYC Taxi and Limousine Commission (TLC) / RutaViva Compliance",
        "report_type": "Monthly Dynamic Pricing & Operational Fleet Audit (RN-11 / CA-08)",
        "period": f"{target_year}-{target_month:02d}",
        "generated_at_utc": datetime.utcnow().isoformat() + "Z",
        "total_trips_evaluated": total_trips,
        "borough_breakdown": borough_records,
        "hourly_breakdown": hourly_records,
        "top_surge_zones": top_zones_records,
    }

    # Guardar reporte
    os.makedirs(output_dir, exist_ok=True)
    json_path = os.path.join(output_dir, f"regulatory_report_{target_year}_{target_month:02d}.json")
    csv_path = os.path.join(output_dir, f"regulatory_report_by_borough_{target_year}_{target_month:02d}.csv")

    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(report_metadata, f, indent=2, ensure_ascii=False)

    borough_summary.toPandas().to_csv(csv_path, index=False)

    logger.info("✅ Reporte regulatorio generado exitosamente:")
    logger.info("   JSON: %s", json_path)
    logger.info("   CSV:  %s", csv_path)

    return report_metadata


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Generador de Reporte Regulatorio Mensual (RN-11 / CA-08)")
    parser.add_argument("--gold", default="data/gold/fact_trips", help="Ruta de fact_trips en Gold Parquet")
    parser.add_argument(
        "--rn11",
        help="Ruta de RN11_MONTHLY_REPORT Gold Parquet; si se indica, genera el reporte operacional.",
    )
    parser.add_argument("--out", default="data/reports", help="Directorio de salida para los reportes")
    parser.add_argument("--year", type=int, default=2026, help="Año de análisis")
    parser.add_argument("--month", type=int, default=10, help="Mes de análisis")

    args = parser.parse_args()
    if args.rn11:
        generate_operational_regulatory_report(
            rn11_gold_path=args.rn11,
            output_dir=args.out,
            target_year=args.year,
            target_month=args.month,
        )
    else:
        generate_monthly_regulatory_report(
            gold_fact_path=args.gold,
            output_dir=args.out,
            target_year=args.year,
            target_month=args.month,
        )
