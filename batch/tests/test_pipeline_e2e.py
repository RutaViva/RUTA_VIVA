"""Integration test for the canonical Job 1 -> RN-11 report flow."""

from __future__ import annotations

import csv
import json
import sys
import tempfile
from pathlib import Path

import pytest
from pyspark.sql import SparkSession

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "spark_jobs"))

from common.io import replace_partition
from job1_clean_validate import _prepare_trips, _read_f1_source
from job2_enrich_model import _rn11_monthly_report
from batch.reports.generate_regulatory_report import (
    generate_operational_regulatory_report,
)


@pytest.fixture(scope="module")
def spark() -> SparkSession:
    session = (
        SparkSession.builder.master("local[2]")
        .appName("RutaViva-Canonical-Pipeline-E2E")
        .config("spark.sql.session.timeZone", "America/New_York")
        .getOrCreate()
    )
    session.sparkContext.setLogLevel("ERROR")
    yield session
    session.stop()


def test_job1_to_monthly_rn11_report(spark: SparkSession) -> None:
    with tempfile.TemporaryDirectory(prefix="rutaviva_batch_test_") as temporary:
        root = Path(temporary)
        landing = root / "f1"
        landing.mkdir()
        f1_file = landing / "trips_2026-10.csv"
        f1_file.write_text(
            "tpep_pickup_datetime,tpep_dropoff_datetime,trip_distance,"
            "PULocationID,DOLocationID,fare_amount,total_amount\n"
            "2026-10-15 10:00:00,2026-10-15 10:20:00,3.2,161,237,16.5,19.0\n"
            "2026-10-15 11:00:00,2026-10-15 11:25:00,5.0,161,162,22.0,25.0\n"
            "2026-10-15 23:00:00,2026-10-15 23:30:00,8.1,230,132,35.0,40.0\n"
            "2026-10-15 12:00:00,2026-10-15 12:10:00,0.02,161,162,12.0,12.0\n",
            encoding="utf-8",
        )

        with pytest.MonkeyPatch.context() as monkeypatch:
            monkeypatch.setenv("F1_FORMAT", "csv")
            classified = _prepare_trips(
                _read_f1_source(spark, str(landing), 2026, 10)
            ).filter("pickup_year = 2026 AND pickup_month = 10")

        valid = classified.filter("reject_reason = ''").drop(
            "reject_reason",
            "_pickup_zone_id_present",
            "_dropoff_zone_id_present",
        )
        rejected = classified.filter("reject_reason != ''").drop(
            "reject_reason",
            "_pickup_zone_id_present",
            "_dropoff_zone_id_present",
        )
        silver_path = str(root / "silver")
        quarantine_path = str(root / "quarantine")
        partition = ("pickup_year", "pickup_month")
        replace_partition(spark, valid, silver_path, partition, (2026, 10))
        replace_partition(spark, rejected, quarantine_path, partition, (2026, 10))

        assert spark.read.parquet(silver_path).count() == 3
        assert spark.read.parquet(quarantine_path).count() == 1

        requests = spark.createDataFrame(
            [
                (161, "2026-10-05 10:00:00", 20.0, 1.2),
                (162, "2026-10-15 10:00:00", 30.0, 1.0),
            ],
            ["zone_id", "requested_at", "charged_fare", "multiplier"],
        )
        intervals = spark.createDataFrame(
            [
                (161, "2026-10-05 10:00:00", 10.0),
                (162, "2026-10-15 10:00:00", 20.0),
            ],
            ["zone_id", "interval_start", "estimated_wait_minutes"],
        )
        complaints = spark.createDataFrame(
            [(161, "2026-10-09 10:00:00")],
            ["zone_id", "created_at"],
        )
        zones = spark.createDataFrame(
            [(161, "Manhattan"), (162, "Manhattan"), (237, "Queens")],
            ["zone_key", "borough"],
        )

        rn11 = _rn11_monthly_report(
            requests,
            intervals,
            complaints,
            zones,
            2026,
            10,
        )
        rn11_path = root / "gold" / "RN11_MONTHLY_REPORT"
        rn11.write.mode("overwrite").partitionBy("year", "month").parquet(
            str(rn11_path)
        )

        report_dir = root / "reports"
        metadata = generate_operational_regulatory_report(
            rn11_gold_path=str(rn11_path),
            output_dir=str(report_dir),
            target_year=2026,
            target_month=10,
        )

        assert metadata["total_trips_evaluated"] == 2
        assert metadata["total_complaints"] == 1
        assert (report_dir / "regulatory_report_2026_10.json").is_file()
        csv_path = report_dir / "regulatory_report_by_borough_2026_10.csv"
        assert csv_path.is_file()
        loaded_json = json.loads(
            (report_dir / "regulatory_report_2026_10.json").read_text(
                encoding="utf-8"
            )
        )
        assert loaded_json["total_trips_evaluated"] == 2
        with csv_path.open(encoding="utf-8", newline="") as output:
            borough_rows = list(csv.DictReader(output))
        manhattan = next(row for row in borough_rows if row["borough"] == "Manhattan")
        assert int(manhattan["trip_count"]) == 2
        assert int(manhattan["complaint_count"]) == 1
