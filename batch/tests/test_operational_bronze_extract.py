from __future__ import annotations

import csv
import os
import sys
import tempfile
import types
import unittest
from datetime import datetime
from pathlib import Path
from unittest.mock import patch
from zoneinfo import ZoneInfo

from batch.scripts.operational_bronze_extract import (
    SERVICE_COMPLAINTS_QUERY,
    TRIP_REQUESTS_QUERY,
    ZONE_HISTORY_QUERY,
    _bronze_relative_dir,
    _period_bounds,
    extract_monthly_operational_data,
)


class _Cursor:
    def __init__(self) -> None:
        self.description: list[tuple[str]] = []
        self.rows: list[tuple[object, ...]] = []
        self.executed: tuple[str, object] | None = None

    def __enter__(self) -> _Cursor:
        return self

    def __exit__(self, *args: object) -> None:
        return None

    def execute(self, query: str, bounds: object) -> None:
        self.executed = query, bounds
        if query == TRIP_REQUESTS_QUERY:
            self.description = [("trip_id",), ("zone_id",), ("charged_fare",)]
            self.rows = [("trip-1", 7, 18.5)]
        elif query == ZONE_HISTORY_QUERY:
            self.description = [("zone_id",), ("estimated_wait_minutes",)]
            self.rows = [(7, 4.5)]
        else:
            self.description = [
                ("complaint_id",),
                ("trip_id",),
                ("zone_id",),
                ("created_at",),
                ("category",),
            ]
            self.rows = [
                ("complaint-1", "trip-1", 7, "2026-01-20", "service")
            ]

    def fetchmany(self, size: int) -> list[tuple[object, ...]]:
        rows, self.rows = self.rows[:size], self.rows[size:]
        return rows


class _Connection:
    def __init__(self) -> None:
        self.cursors: list[_Cursor] = []
        self.closed = False

    def cursor(self) -> _Cursor:
        cursor = _Cursor()
        self.cursors.append(cursor)
        return cursor

    def close(self) -> None:
        self.closed = True


class OperationalBronzeExtractTests(unittest.TestCase):
    def test_period_bounds_use_local_calendar_month(self) -> None:
        start, end = _period_bounds(2026, 1, "America/New_York")

        self.assertEqual(
            start,
            datetime(2026, 1, 1, tzinfo=ZoneInfo("America/New_York")),
        )
        self.assertEqual(end, datetime(2026, 2, 1, tzinfo=ZoneInfo("America/New_York")))

    def test_period_bounds_reject_invalid_month(self) -> None:
        with self.assertRaisesRegex(ValueError, "Mes inválido"):
            _period_bounds(2026, 13, "America/New_York")

    def test_source_paths_resolve_inside_bronze_prefix(self) -> None:
        with patch.dict(
            os.environ,
            {
                "S3_BRONZE_PATH": "s3a://rutaviva-lake/bronze",
                "S3_TRIP_REQUESTS_PATH": (
                    "s3a://rutaviva-lake/bronze/operational/requests"
                ),
            },
        ):
            self.assertEqual(
                _bronze_relative_dir("S3_TRIP_REQUESTS_PATH", "unused"),
                Path("operational", "requests"),
            )

    def test_source_paths_cannot_escape_bronze_prefix(self) -> None:
        with patch.dict(
            os.environ,
            {
                "S3_BRONZE_PATH": "s3a://rutaviva-lake/bronze",
                "S3_TRIP_REQUESTS_PATH": "s3a://other-lake/requests",
            },
        ), self.assertRaisesRegex(ValueError, "mismo bucket"):
            _bronze_relative_dir("S3_TRIP_REQUESTS_PATH", "unused")

    def test_extract_exports_requests_audits_and_zone_history(self) -> None:
        airflow_modules = {
            name: types.ModuleType(name)
            for name in (
                "airflow",
                "airflow.providers",
                "airflow.providers.postgres",
                "airflow.providers.postgres.hooks",
                "airflow.providers.postgres.hooks.postgres",
            )
        }
        for module in airflow_modules.values():
            module.__path__ = []

        connection = _Connection()

        class FakePostgresHook:
            def __init__(self, postgres_conn_id: str) -> None:
                self.connection_id = postgres_conn_id

            def get_conn(self) -> _Connection:
                return connection

        airflow_modules[
            "airflow.providers.postgres.hooks.postgres"
        ].PostgresHook = FakePostgresHook

        with tempfile.TemporaryDirectory() as landing:
            with (
                patch.dict(sys.modules, airflow_modules),
                patch.dict(
                    os.environ,
                    {
                        "BRONZE_LANDING_DIR": landing,
                        "AIRFLOW_POSTGRES_CONN_ID": "rutaviva_readonly",
                        "AIRFLOW_TIMEZONE": "America/New_York",
                        "S3_BRONZE_PATH": "s3a://rutaviva-lake/bronze",
                        "S3_TRIP_REQUESTS_PATH": (
                            "s3a://rutaviva-lake/bronze/operational/trip_requests"
                        ),
                        "S3_ZONE_STATE_HISTORY_PATH": (
                            "s3a://rutaviva-lake/bronze/zone_state_history"
                        ),
                        "S3_SERVICE_COMPLAINTS_PATH": (
                            "s3a://rutaviva-lake/bronze/operational/service_complaints"
                        ),
                    },
                ),
            ):
                extract_monthly_operational_data(2026, 1)

            requests_path = Path(
                landing,
                "operational",
                "trip_requests",
                "year=2026",
                "month=01",
                "data.csv",
            )
            history_path = Path(
                landing,
                "zone_state_history",
                "year=2026",
                "month=01",
                "data.csv",
            )
            complaints_path = Path(
                landing,
                "operational",
                "service_complaints",
                "year=2026",
                "month=01",
                "data.csv",
            )
            with requests_path.open(encoding="utf-8", newline="") as source:
                requests_rows = list(csv.reader(source))
            with history_path.open(encoding="utf-8", newline="") as source:
                history_rows = list(csv.reader(source))
            with complaints_path.open(encoding="utf-8", newline="") as source:
                complaint_rows = list(csv.reader(source))

        self.assertEqual(
            requests_rows[0],
            ["trip_id", "zone_id", "charged_fare"],
        )
        self.assertEqual(requests_rows[1], ["trip-1", "7", "18.5"])
        self.assertEqual(history_rows[1], ["7", "4.5"])
        self.assertEqual(complaint_rows[0][-2:], ["created_at", "category"])
        self.assertEqual(complaint_rows[1][-2:], ["2026-01-20", "service"])
        self.assertEqual(len(connection.cursors), 3)
        self.assertTrue(connection.closed)
        self.assertEqual(
            [cursor.executed[0] for cursor in connection.cursors],
            [
                TRIP_REQUESTS_QUERY,
                ZONE_HISTORY_QUERY,
                SERVICE_COMPLAINTS_QUERY,
            ],
        )
        self.assertEqual(
            connection.cursors[0].executed[1],
            _period_bounds(2026, 1, "America/New_York"),
        )


if __name__ == "__main__":
    unittest.main()
