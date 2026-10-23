"""Focused tests; install the Spark job requirements and provide Java."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

from pyspark.sql import SparkSession

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "spark_jobs"))

from job1_clean_validate import _prepare_trips
from job2_enrich_model import (
    _date_dimension,
    _event_intervals,
    _time_slot_dimension,
    _trip_fact,
    _weather_dimension,
    _zone_dimension,
    _zone_lookup_udf,
    _zone_intervals,
    _zone_interval_fact,
)
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

    def test_job1_rejects_noncanonical_headers(self) -> None:
        raw = self.spark.createDataFrame([("2026-01-01",)], ["pickupdatetime"])
        with self.assertRaisesRegex(ValueError, "esquema canónico"):
            _prepare_trips(raw)

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


if __name__ == "__main__":
    unittest.main()
