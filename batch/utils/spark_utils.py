"""Factories and configuration helpers for Airflow Spark tasks."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Sequence

S3_PATH_ENV_VARS = (
    "S3_BRONZE_PATH",
    "S3_SILVER_PATH",
    "S3_GOLD_PATH",
    "S3_QUARANTINE_PATH",
)


SPARK_CONFIG_ENV_VARS = (
    "S3_F1_PATH",
    "S3_WEATHER_PATH",
    "S3_EVENTS_PATH",
    "S3_TRIP_REQUESTS_PATH",
    "S3_ZONE_STATE_HISTORY_PATH",
    "S3_SERVICE_COMPLAINTS_PATH",
    "F1_FORMAT",
    "F3_FORMAT",
    "F7_FORMAT",
    "TRIP_REQUESTS_FORMAT",
    "ZONE_STATE_HISTORY_FORMAT",
    "SERVICE_COMPLAINTS_FORMAT",
    "AWS_REGION",
    "AWS_DEFAULT_REGION",
    "S3_ENDPOINT",
    "S3_PATH_STYLE_ACCESS",
    "SPARK_JARS_PACKAGES",
    "HADOOP_AWS_VERSION",
    "SPARK_TIMEZONE",
    "SPARK_EXECUTOR_PYTHON",
    "RUTAVIVA_ZONE_SHAPEFILE_PATH",
    "RUTAVIVA_ZONE_CATALOG_PATH",
    "AWS_ACCESS_KEY_ID",
    "AWS_SECRET_ACCESS_KEY",
    "AWS_SESSION_TOKEN",
)


def spark_environment() -> dict[str, str]:

    # obtenemos un diccionario con el nombre de la variable y su valor limpio
    required = {name: os.environ.get(name, "").strip() for name in S3_PATH_ENV_VARS}
    # filtramos de manera explícita cuáles de esas variables quedaron vacías
    missing = [name for name, value in required.items() if not value]
    if missing:
        raise ValueError(
            "Missing required S3 path environment variables: " + ", ".join(missing)
        )

    configured = {
        name: os.environ[name]
        for name in SPARK_CONFIG_ENV_VARS
        if name in os.environ
    }
    return {**required, **configured}


def submit_spark_job(
    *,
    script_path: Path,
    conn_id: str = "spark_default",
    application_args: Sequence[str] | None = None,
) -> None:
    from airflow.providers.apache.spark.hooks.spark_submit import SparkSubmitHook

    if not script_path.is_file():
        raise FileNotFoundError(f"No existe la aplicación Spark: {script_path}")

    hook = SparkSubmitHook(
        conn_id=conn_id,
        env_vars=spark_environment(),
        name=f"rutaviva-{script_path.stem.replace('_', '-')}",
        application_args=list(application_args or ()),
    )
    hook.submit(str(script_path))
