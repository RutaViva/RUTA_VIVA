"""Shared Spark and S3A session configuration."""

from __future__ import annotations

import os

from pyspark.sql import SparkSession


def create_spark_session(app_name: str) -> SparkSession:
    builder = (
        SparkSession.builder.appName(app_name)
        .config("spark.hadoop.fs.s3a.impl", "org.apache.hadoop.fs.s3a.S3AFileSystem")
        .config(
            "spark.sql.session.timeZone",
            os.environ.get("SPARK_TIMEZONE", "America/New_York"),
        )
        .config("spark.sql.ansi.enabled", "false")
    )

    region = os.environ.get("AWS_REGION") or os.environ.get("AWS_DEFAULT_REGION")
    endpoint = os.environ.get("S3_ENDPOINT")
    if region:
        builder = builder.config("spark.hadoop.fs.s3a.endpoint.region", region)
    if endpoint:
        builder = (
            builder.config("spark.hadoop.fs.s3a.endpoint", endpoint)
            .config(
                "spark.hadoop.fs.s3a.path.style.access",
                os.environ.get("S3_PATH_STYLE_ACCESS", "true"),
            )
        )

    paths = (
        "S3_BRONZE_PATH",
        "S3_F1_PATH",
        "S3_SILVER_PATH",
        "S3_QUARANTINE_PATH",
        "S3_GOLD_PATH",
        "S3_WEATHER_PATH",
        "S3_EVENTS_PATH",
        "S3_ZONE_STATE_HISTORY_PATH",
    )
    uses_s3a = any(
        os.environ.get(name, "").strip().startswith("s3a://") for name in paths
    )
    packages = os.environ.get("SPARK_JARS_PACKAGES", "").strip()
    if uses_s3a:
        version = os.environ.get("HADOOP_AWS_VERSION", "3.5.0")
        connector = f"org.apache.hadoop:hadoop-aws:{version}"
        configured = [package.strip() for package in packages.split(",") if package.strip()]
        if not any(package.startswith("org.apache.hadoop:hadoop-aws:") for package in configured):
            configured.insert(0, connector)
        packages = ",".join(configured)
    if packages:
        builder = builder.config("spark.jars.packages", packages)

    return builder.getOrCreate()
