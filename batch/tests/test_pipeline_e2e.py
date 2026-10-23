"""
batch/tests/test_pipeline_e2e.py
Prueba de integración end-to-end del pipeline batch de PySpark y reporte regulatorio (CA-01, CA-08, CA-09).
Verifica: Bronze -> Silver/Quarantine -> Gold (fact & dims) -> Reporte Regulatorio (JSON/CSV).
"""
import json
import os
import shutil
import tempfile
import pytest


from batch.spark_jobs.common.spark_session import get_spark_session
from batch.spark_jobs.job1_clean_validate.main import run_clean_validate_job
from batch.spark_jobs.job2_enrich_model.main import run_enrich_model_job
from batch.reports.generate_regulatory_report import generate_monthly_regulatory_report


@pytest.fixture(scope="module")
def spark():
    session = get_spark_session("PySpark-E2E-Pipeline-Test")
    yield session
    session.stop()


def test_end_to_end_batch_data_pipeline_ca01_ca08_ca09(spark):
    """
    Validación completa del flujo Medallion y generación regulatoria:
    1. Ingesta de dataset sintético representativo de F1.
    2. Job 1: Enrutamiento de registros válidos y anómalos (CA-01, CA-09).
    3. Job 2: Construcción de Gold fact_trips y dimensiones estrella.
    4. Reporte Regulatorio: Generación de métricas de cumplimiento (CA-08).
    """
    temp_dir = tempfile.mkdtemp(prefix="rutaviva_batch_test_")
    try:
        raw_csv_path = os.path.join(temp_dir, "raw_trips.csv")
        silver_path = os.path.join(temp_dir, "silver")
        quarantine_path = os.path.join(temp_dir, "quarantine")
        gold_path = os.path.join(temp_dir, "gold")
        reports_path = os.path.join(temp_dir, "reports")
        zones_csv = "services/seed_cli/app/data/csv/taxi_zone_lookup.csv"

        # 1. Crear dataset sintético de prueba con casos mixtos (válidos e inválidos)
        # 3 válidos, 1 con distancia negativa (cuarentena), 1 con tarifa cero (cuarentena)
        raw_rows = [
            # VendorID, tpep_pickup_datetime, tpep_dropoff_datetime, passenger_count, trip_distance, PULocationID, DOLocationID, fare_amount, tip_amount, total_amount
            "1,2026-10-15 10:00:00,2026-10-15 10:15:00,1,3.2,161,237,16.5,2.5,19.0",  # Válido
            "1,2026-10-15 11:00:00,2026-10-15 11:25:00,2,5.0,161,162,22.0,3.0,25.0",  # Válido
            "2,2026-10-15 23:00:00,2026-10-15 23:30:00,1,8.1,230,132,35.0,5.0,40.0",  # Válido nocturno
            "1,2026-10-15 12:00:00,2026-10-15 12:10:00,1,0.02,161,162,12.0,0.0,12.0",  # Inválido: distancia < 0.1
            "2,2026-10-15 13:00:00,2026-10-15 13:20:00,1,4.0,161,162,-10.0,0.0,-10.0", # Inválido: tarifa negativa
        ]

        with open(raw_csv_path, "w", encoding="utf-8") as f:
            f.write("VendorID,tpep_pickup_datetime,tpep_dropoff_datetime,passenger_count,trip_distance,PULocationID,DOLocationID,fare_amount,tip_amount,total_amount\n")
            for r in raw_rows:
                f.write(r + "\n")

        # 2. Ejecutar Job 1 (Limpieza, Estandarización y Cuarentena)
        job1_metrics = run_clean_validate_job(
            input_path=raw_csv_path,
            silver_output_path=silver_path,
            quarantine_output_path=quarantine_path,
            file_format="csv",
        )

        assert job1_metrics["total_records"] == 5
        assert job1_metrics["valid_count"] == 3, "Deben existir exactamente 3 registros válidos en Silver"
        assert job1_metrics["quarantine_count"] == 2, "Deben existir exactamente 2 registros en Cuarentena"
        assert "distancia inválida" in job1_metrics["reasons"]
        assert "tarifa negativa o cero" in job1_metrics["reasons"]

        # 3. Ejecutar Job 2 (Enriquecimiento y Modelo Dimensional Gold)
        job2_metrics = run_enrich_model_job(
            silver_trips_path=silver_path,
            zones_lookup_path=zones_csv,
            gold_output_path=gold_path,
        )

        assert job2_metrics["gold_trips_count"] == 3
        assert job2_metrics["zones_count"] == 265
        assert os.path.exists(os.path.join(gold_path, "fact_trips"))
        assert os.path.exists(os.path.join(gold_path, "dim_zone"))
        assert os.path.exists(os.path.join(gold_path, "dim_date"))
        assert os.path.exists(os.path.join(gold_path, "dim_time_window"))

        # 4. Ejecutar Generación de Reporte Regulatorio (CA-08, E-16)
        report_meta = generate_monthly_regulatory_report(
            gold_fact_path=os.path.join(gold_path, "fact_trips"),
            output_dir=reports_path,
            target_year=2026,
            target_month=10,
        )

        assert report_meta["total_trips_evaluated"] == 3
        assert len(report_meta["borough_breakdown"]) > 0
        assert os.path.exists(os.path.join(reports_path, "regulatory_report_2026_10.json"))
        assert os.path.exists(os.path.join(reports_path, "regulatory_report_by_borough_2026_10.csv"))

        # Validar consistencia del reporte JSON
        with open(os.path.join(reports_path, "regulatory_report_2026_10.json"), "r", encoding="utf-8") as f:
            loaded_json = json.load(f)
            assert loaded_json["report_type"] == "Monthly Dynamic Pricing & Operational Fleet Audit (RN-11 / CA-08)"
            assert loaded_json["total_trips_evaluated"] == 3

    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)
