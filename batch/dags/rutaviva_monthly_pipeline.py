from __future__ import annotations

import sys
from pathlib import Path

import pendulum
from airflow import DAG
from airflow.decorators import task


PROJECT_ROOT = Path(__file__).resolve().parents[2]
BATCH_ROOT = PROJECT_ROOT / "batch"
SPARK_JOBS = BATCH_ROOT / "spark_jobs"
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from batch.scripts.bronze_ingestion import ingest_bronze
from batch.scripts.operational_bronze_extract import (
    extract_monthly_operational_data,
)
from batch.utils.airflow_utils import (
    previous_month_period,
    previous_month_spark_arguments,
)
from batch.utils.spark_utils import submit_spark_job


TIMEZONE = "America/New_York"

DEFAULT_ARGS = {
    "owner": "rutaviva-data",
    "depends_on_past": False,
    "retries": 2,
    "retry_delay": pendulum.duration(minutes=5),
}

with DAG(
    dag_id="rutaviva_monthly_pipeline",
    description="Ingesta operacional y procesamiento mensual hasta Gold",
    schedule="0 3 2 * *",
    start_date=pendulum.datetime(2026, 1, 1, tz=TIMEZONE),
    catchup=False,
    max_active_runs=1,
    default_args=DEFAULT_ARGS
) as dag:

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
            script_name="job1_clean_validate.py",
            spark_jobs_dir=SPARK_JOBS,
            application_args=previous_month_spark_arguments(TIMEZONE),
        )

    @task(task_id="job2_enrich_model")
    def job2_enrich_model_task() -> None:
        submit_spark_job(
            script_name="job2_enrich_model.py",
            spark_jobs_dir=SPARK_JOBS,
            application_args=previous_month_spark_arguments(TIMEZONE),
        )

    extract_operational_sources = extract_operational_sources_task()
    bronze_ingestion = bronze_ingestion_task()
    job1_clean_validate = job1_clean_validate_task()
    job2_enrich_model = job2_enrich_model_task()

    (
        extract_operational_sources
        >> bronze_ingestion
        >> job1_clean_validate
        >> job2_enrich_model
    )