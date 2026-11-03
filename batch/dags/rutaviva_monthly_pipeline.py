from __future__ import annotations

import os
from pathlib import Path
import sys

import pendulum
from airflow import DAG
from airflow.decorators import task


PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from batch.scripts.bronze_ingestion import ingest_bronze
from batch.scripts.operational_bronze_extract import (
    extract_monthly_operational_data,
)
from batch.scripts.pipeline_readiness import validate_pipeline_inputs
from batch.scripts.report_publication import publish_regulatory_report
from batch.utils.airflow_utils import previous_month_period
from batch.utils.airflow_utils import previous_month_spark_arguments
from batch.utils.spark_utils import submit_spark_job


TIMEZONE = "America/New_York"
SPARK_JOBS = PROJECT_ROOT / "batch" / "spark_jobs"
REPORT_SCRIPT = PROJECT_ROOT / "batch" / "reports" / "generate_regulatory_report.py"
REPORT_DIR = Path(os.environ.get("REGULATORY_REPORT_DIR", "/opt/airflow/reports"))

DEFAULT_ARGS = {
    "owner": "rutaviva-data",
    "depends_on_past": False,
    "retries": 2,
    "retry_delay": pendulum.duration(minutes=5),
}

with DAG(
    dag_id="rutaviva_monthly_pipeline",
    description="Pipeline mensual PostgreSQL -> Bronze -> Silver/Quarantine -> Gold -> reporte RN-11",
    schedule="0 3 2 * *",
    start_date=pendulum.datetime(2026, 1, 1, tz=TIMEZONE),
    catchup=False,
    max_active_runs=1,
    default_args=DEFAULT_ARGS,
    tags=["rutaviva", "batch", "spark", "regulatory"],
) as dag:

    @task(task_id="check_data_readiness")
    def check_data_readiness_task() -> None:
        validate_pipeline_inputs()

    @task(task_id="extract_operational_sources")
    def extract_operational_sources_task() -> None:
        year, month = previous_month_period(TIMEZONE)
        extract_monthly_operational_data(year, month)

    @task(task_id="bronze_ingestion")
    def bronze_ingestion_task() -> None:
        ingest_bronze()

    @task(task_id="job1_clean_validate")
    def job1_clean_validate_task() -> None:
        submit_spark_job(
            script_path=SPARK_JOBS / "job1_clean_validate.py",
            application_args=previous_month_spark_arguments(TIMEZONE),
        )

    @task(task_id="job2_enrich_model")
    def job2_enrich_model_task() -> None:
        submit_spark_job(
            script_path=SPARK_JOBS / "job2_enrich_model.py",
            application_args=previous_month_spark_arguments(TIMEZONE),
        )

    @task(task_id="generate_regulatory_report")
    def generate_regulatory_report_task() -> None:
        year, month = previous_month_period(TIMEZONE)
        gold_path = os.environ.get("S3_GOLD_PATH", "").strip()
        if not gold_path:
            raise ValueError("Falta configurar S3_GOLD_PATH.")
        rn11_path = f"{gold_path.rstrip('/')}/RN11_MONTHLY_REPORT"
        submit_spark_job(
            script_path=REPORT_SCRIPT,
            application_args=[
                "--rn11",
                rn11_path,
                "--out",
                str(REPORT_DIR / f"year={year}" / f"month={month:02d}"),
                "--year",
                str(year),
                "--month",
                str(month),
            ],
        )

    @task(task_id="publish_regulatory_report")
    def publish_regulatory_report_task() -> None:
        year, month = previous_month_period(TIMEZONE)
        output_dir = REPORT_DIR / f"year={year}" / f"month={month:02d}"
        publish_regulatory_report(
            output_dir=output_dir,
            year=year,
            month=month,
        )

    (
        check_data_readiness_task()
        >> extract_operational_sources_task()
        >> bronze_ingestion_task()
        >> job1_clean_validate_task()
        >> job2_enrich_model_task()
        >> generate_regulatory_report_task()
        >> publish_regulatory_report_task()
    )
