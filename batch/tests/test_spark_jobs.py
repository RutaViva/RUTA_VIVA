"""Focused tests; install the Spark job requirements and provide Java."""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from pyspark.sql import SparkSession

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "spark_jobs"))

from job1_clean_validate import (
    _normalize_f1_columns,
    _prepare_trips,
    _read_f1_source,
)
from job2_enrich_model import (
    _date_dimension,
    _event_intervals,
    _rn11_monthly_report,
    _time_slot_dimension,
    _trip_fact,
    _weather_dimension,
    _zone_dimension,
    _zone_lookup_udf,
    _zone_intervals,
    _zone_interval_fact,
)
from common.io import replace_partition
from services.seed_cli.app.zone_data import load_zone_catalog, load_zones_gdf


class SparkJobTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.spark = (
            SparkSession.builder.master("local[2]")
            .appName("RutaViva-spark-job-tests")
            .config("spark.sql.session.timeZone", "America/New_York")
            .getOrCreate()
        )
        cls.spark.sparkContext.setLogLevel("ERROR")

    @classmethod
    def tearDownClass(cls) -> None:
        cls.spark.stop()

    def test_job1_separates_valid_and_rejected_trips(self) -> None:
        fields = [
            "tpep_pickup_datetime",
            "tpep_dropoff_datetime",
            "trip_distance",
            "pickup_longitude",
            "pickup_latitude",
            "dropoff_longitude",
            "dropoff_latitude",
            "fare_amount",
            "extra",
            "total_amount",
            "pickup_zone_id",
            "dropoff_zone_id",
        ]
        rows = [
            ("2026-01-01 10:00:00", "2026-01-01 10:20:00", "1.2", "-73.9", "40.7", "-73.8", "40.8", "10", "1", "12", "7", "8"),
            ("2026-01-01 10:00:00", "2026-01-01 10:20:00", "0", "-73.9", "40.7", "-73.8", "40.8", "10", "1", "12", "7", "8"),
            ("2026-01-01 10:00:00", "2026-01-01 10:20:00", "1.2", "-73.9", "40.7", "-73.8", "40.8", "10", "1", "12", "999", "8"),
        ]
        trips = _prepare_trips(self.spark.createDataFrame(rows, fields))

        self.assertEqual(trips.filter("reject_reason = ''").count(), 1)
        rejected = {
            row.reject_reason
            for row in trips.filter("reject_reason != ''")
            .select("reject_reason")
            .collect()
        }
        self.assertEqual(len(rejected), 2)
        self.assertTrue(any("distance_out_of_range" in reason for reason in rejected))
        self.assertTrue(any("invalid_pickup_zone_id" in reason for reason in rejected))

    def test_job1_normalizes_tlc_schema_variants(self) -> None:
        with tempfile.TemporaryDirectory() as source_dir:
            Path(source_dir, "legacy_2026-01.csv").write_text(
                "pickup_datetime,dropoff_datetime,trip_distance,"
                "pickup_longitude,pickup_latitude,dropoff_longitude,"
                "dropoff_latitude,fare_amount,extra,total_amount\n"
                "2026-01-01 10:00:00,2026-01-01 10:20:00,1.2,"
                "-73.9,40.7,-73.8,40.8,10,1,12\n",
                encoding="utf-8",
            )
            Path(source_dir, "location_ids_2026-01.csv").write_text(
                "tpep_pickup_datetime,tpep_dropoff_datetime,trip_distance,"
                "PULocationID,DOLocationID,fare_amount,total_amount\n"
                "2026-01-02 10:00:00,2026-01-02 10:20:00,1.5,7,8,11,13\n",
                encoding="utf-8",
            )

            with patch.dict("os.environ", {"F1_FORMAT": "csv"}):
                trips = _prepare_trips(
                    _read_f1_source(self.spark, source_dir, 2026, 1)
                )

            self.assertEqual(trips.count(), 2)
            self.assertEqual(trips.filter("reject_reason = ''").count(), 2)
            location_record = trips.filter("pickup_zone_id = 7").first()
            self.assertEqual(location_record.pickup_zone_id, 7)
            self.assertEqual(location_record.dropoff_zone_id, 8)
            self.assertIsNone(location_record.pickup_longitude)

    def test_job1_rejects_unrecognized_f1_schema(self) -> None:
        raw = self.spark.createDataFrame([("2026-01-01",)], ["pickupdatetime"])
        with self.assertRaisesRegex(ValueError, "esquema TLC reconocido"):
            _normalize_f1_columns(raw)

    def test_reprocessing_replaces_only_the_requested_partition(self) -> None:
        with tempfile.TemporaryDirectory() as output_dir:
            initial = self.spark.createDataFrame(
                [("january-old", 2026, 1), ("february", 2026, 2)],
                ["value", "pickup_year", "pickup_month"],
            )
            initial.write.mode("overwrite").partitionBy(
                "pickup_year", "pickup_month"
            ).parquet(output_dir)

            january = self.spark.createDataFrame(
                [("january-updated", 2026, 1)],
                ["value", "pickup_year", "pickup_month"],
            )
            replace_partition(
                self.spark,
                january,
                output_dir,
                ("pickup_year", "pickup_month"),
                (2026, 1),
            )
            rows = {
                (row.pickup_month, row.value)
                for row in self.spark.read.parquet(output_dir).collect()
            }
            self.assertEqual(rows, {(1, "january-updated"), (2, "february")})

            empty_february = initial.filter("pickup_month = 2").limit(0)
            replace_partition(
                self.spark,
                empty_february,
                output_dir,
                ("pickup_year", "pickup_month"),
                (2026, 2),
            )
            rows = {
                (row.pickup_month, row.value)
                for row in self.spark.read.parquet(output_dir).collect()
            }
            self.assertEqual(rows, {(1, "january-updated")})

    def test_trip_fact_uses_zone_ids_without_coordinates(self) -> None:
        weather = _weather_dimension(
            self.spark.createDataFrame(
                [("2026-01-01 10:00:00", 0.0)],
                ["weather_hour", "rain_mm_h"],
            ).filter("1 = 0")
        )
        events = _event_intervals(
            self.spark.createDataFrame(
                [(7, "2026-01-01 10:00:00", "2026-01-01 11:00:00")],
                ["zone_id", "starts_at", "ends_at"],
            ).filter("1 = 0")
        )
        trips = self.spark.createDataFrame(
            [
                (
                    "2026-01-01 10:15:00",
                    "2026-01-01 10:35:00",
                    7,
                    8,
                    10.0,
                    12.0,
                )
            ],
            [
                "tpep_pickup_datetime",
                "tpep_dropoff_datetime",
                "pickup_zone_id",
                "dropoff_zone_id",
                "fare_amount",
                "total_amount",
            ],
        )
        fact = _trip_fact(trips, weather, events, None).first()
        self.assertEqual(fact.pickup_zone_key, 7)
        self.assertEqual(fact.dropoff_zone_key, 8)

    def test_job2_builds_weather_event_and_zone_facts(self) -> None:
        weather = _weather_dimension(
            self.spark.createDataFrame(
                [("2026-01-01 10:00:00", 5.0)],
                ["weather_hour", "rain_mm_h"],
            )
        )
        events = _event_intervals(
            self.spark.createDataFrame(
                [(7, "2026-01-01 10:00:00", "2026-01-01 11:00:00")],
                ["zone_id", "starts_at", "ends_at"],
            )
        )
        zones = load_zones_gdf()
        pickup = zones.loc[zones["LocationID"] == 7, "geometry"].iloc[0].representative_point()
        dropoff = zones.loc[zones["LocationID"] == 8, "geometry"].iloc[0].representative_point()
        trips = self.spark.createDataFrame(
            [
                (
                    "2026-01-01 10:15:00",
                    "2026-01-01 10:35:00",
                    pickup.y,
                    pickup.x,
                    dropoff.y,
                    dropoff.x,
                    10.0,
                    12.0,
                )
            ],
            [
                "tpep_pickup_datetime",
                "tpep_dropoff_datetime",
                "pickup_latitude",
                "pickup_longitude",
                "dropoff_latitude",
                "dropoff_longitude",
                "fare_amount",
                "total_amount",
            ],
        )
        fact_trip = _trip_fact(
            trips, weather, events, _zone_lookup_udf(self.spark, zones)
        ).first()

        self.assertEqual(fact_trip.pickup_zone_key, 7)
        self.assertEqual(fact_trip.dropoff_zone_key, 8)
        self.assertEqual(fact_trip.weather_key, 2026010110)
        self.assertTrue(fact_trip.is_special_event)
        self.assertEqual(fact_trip.extra_revenue, 2.0)
        zone_dimension = _zone_dimension(self.spark, zones, load_zone_catalog())
        self.assertEqual(zone_dimension.count(), 265)
        self.assertEqual(zone_dimension.schema["zone_key"].dataType.typeName(), "integer")
        self.assertEqual(
            {row.zone_key for row in zone_dimension.filter("zone_key in (264, 265)").collect()},
            {264, 265},
        )
        outside = self.spark.createDataFrame([(0.0, 0.0)], ["latitude", "longitude"])
        self.assertIsNone(
            outside.select(
                _zone_lookup_udf(self.spark, zones)("latitude", "longitude")
            ).first()[0]
        )

        intervals = _zone_intervals(
            self.spark.createDataFrame(
                [(7, "2026-01-01 10:00:00", 5, 0, 5.0, 12.0)],
                [
                    "zone_id",
                    "interval_start",
                    "requests",
                    "free_vehicles",
                    "pressure_index",
                    "estimated_wait_minutes",
                ],
            )
        )
        zone_fact = _zone_interval_fact(intervals, weather).first()
        self.assertTrue(zone_fact.is_underserved)
        self.assertEqual(zone_fact.weather_key, 2026010110)
        self.assertEqual(_date_dimension(trips, intervals).count(), 1)
        self.assertEqual(_time_slot_dimension(self.spark).count(), 24)

    def test_rn11_report_aggregates_operational_sources_by_borough(self) -> None:
        requests = self.spark.createDataFrame(
            [
                (7, "2026-01-05 10:00:00", 20.0, 1.2),
                (9, "2026-01-15 10:00:00", 30.0, 1.0),
                (8, "2026-01-21 10:00:00", 10.0, None),
                (7, "2026-02-01 10:00:00", 50.0, 1.5),
            ],
            ["zone_id", "requested_at", "charged_fare", "multiplier"],
        )
        intervals = self.spark.createDataFrame(
            [
                (7, "2026-01-05 10:00:00", 10.0),
                (9, "2026-01-15 10:00:00", 20.0),
                (8, "2026-01-21 10:00:00", 4.0),
            ],
            ["zone_id", "interval_start", "estimated_wait_minutes"],
        )
        complaints = self.spark.createDataFrame(
            [
                (7, "2026-01-09 10:00:00"),
                (7, "2026-01-19 10:00:00"),
                (8, "2026-02-01 10:00:00"),
            ],
            ["zone_id", "created_at"],
        )
        zones = self.spark.createDataFrame(
            [
                (7, "Manhattan"),
                (8, "Queens"),
                (9, "Manhattan"),
                (10, "Brooklyn"),
            ],
            ["zone_key", "borough"],
        )

        report = {
            row.borough: row
            for row in _rn11_monthly_report(
                requests, intervals, complaints, zones, 2026, 1
            ).collect()
        }

        self.assertEqual(report["Manhattan"].trip_count, 2)
        self.assertEqual(report["Manhattan"].average_fare, 25.0)
        self.assertEqual(report["Manhattan"].average_wait_minutes, 15.0)
        self.assertEqual(report["Manhattan"].multiplier_gt_one_pct, 50.0)
        self.assertEqual(report["Manhattan"].complaint_count, 2)
        self.assertEqual(report["Queens"].trip_count, 1)
        self.assertEqual(report["Queens"].average_fare, 10.0)
        self.assertEqual(report["Queens"].average_wait_minutes, 4.0)
        self.assertIsNone(report["Queens"].multiplier_gt_one_pct)
        self.assertEqual(report["Queens"].complaint_count, 0)
        self.assertEqual(report["Brooklyn"].trip_count, 0)
        self.assertIsNone(report["Brooklyn"].average_fare)
        self.assertEqual(report["Brooklyn"].complaint_count, 0)
        self.assertEqual(report["Manhattan"].year, 2026)
        self.assertEqual(report["Manhattan"].month, 1)


if __name__ == "__main__":
    unittest.main()
