from __future__ import annotations

import csv
import os
from datetime import datetime
from pathlib import Path, PurePosixPath
from urllib.parse import urlsplit
from zoneinfo import ZoneInfo

TRIP_REQUESTS_QUERY = """
    SELECT
        tr.trip_id::text AS trip_id,
        tr.zone_id,
        tr.requested_at,
        tr.status,
        fa.base_fare,
        fa.multiplier,
        fa.charged_fare,
        fa.pressure_index,
        fa.rain_mm_h,
        fa.rule_version_id
    FROM trip_request AS tr
    LEFT JOIN fare_audit AS fa ON fa.trip_id = tr.trip_id
    WHERE tr.requested_at >= %s AND tr.requested_at < %s
    ORDER BY tr.requested_at, tr.trip_id
"""

ZONE_HISTORY_QUERY = """
    SELECT
        zone_id,
        interval_start,
        requests,
        free_vehicles,
        pressure_index,
        multiplier,
        estimated_wait_minutes
    FROM zone_state_history
    WHERE interval_start >= %s AND interval_start < %s
    ORDER BY interval_start, zone_id
"""

SERVICE_COMPLAINTS_QUERY = """
    SELECT
        complaint.complaint_id::text AS complaint_id,
        complaint.trip_id::text AS trip_id,
        trip.zone_id,
        complaint.created_at,
        complaint.category
    FROM service_complaint AS complaint
    JOIN trip_request AS trip ON trip.trip_id = complaint.trip_id
    WHERE complaint.created_at >= %s AND complaint.created_at < %s
    ORDER BY complaint.created_at, complaint.complaint_id
"""


def _period_bounds(year: int, month: int, timezone: str) -> tuple[datetime, datetime]:
    if month not in range(1, 13):
        raise ValueError(f"Mes inválido: {month}")
    start = datetime(year, month, 1, tzinfo=ZoneInfo(timezone))
    if month == 12:
        end = datetime(year + 1, 1, 1, tzinfo=ZoneInfo(timezone))
    else:
        end = datetime(year, month + 1, 1, tzinfo=ZoneInfo(timezone))
    return start, end


def _bronze_relative_dir(source_env: str, default: str) -> Path:
    source_uri = os.environ.get(source_env, "").strip()
    if not source_uri:
        return Path(*PurePosixPath(default).parts)

    bronze_uri = os.environ.get("S3_BRONZE_PATH", "").strip()
    if not bronze_uri:
        raise ValueError(f"S3_BRONZE_PATH es obligatorio al configurar {source_env}.")

    bronze = urlsplit(bronze_uri)
    source = urlsplit(source_uri)
    if bronze.scheme not in {"s3", "s3a"} or source.scheme not in {"s3", "s3a"}:
        raise ValueError(f"{source_env} y S3_BRONZE_PATH deben usar s3:// o s3a://.")
    if bronze.netloc != source.netloc:
        raise ValueError(
            f"{source_env} debe estar en el mismo bucket que S3_BRONZE_PATH."
        )

    bronze_prefix = bronze.path.strip("/")
    source_prefix = source.path.strip("/")
    if bronze_prefix:
        prefix = f"{bronze_prefix}/"
        if not source_prefix.startswith(prefix):
            raise ValueError(f"{source_env} debe apuntar dentro de S3_BRONZE_PATH.")
        relative = source_prefix[len(prefix):]
    else:
        relative = source_prefix

    parts = PurePosixPath(relative).parts
    if not parts or ".." in parts:
        raise ValueError(f"{source_env} debe apuntar a un subdirectorio de Bronze.")
    return Path(*parts)


def _export_query(
    connection,
    query: str,
    output_path: Path,
    bounds: tuple[datetime, datetime],
) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with connection.cursor() as cursor, output_path.open(
        "w", encoding="utf-8", newline=""
    ) as output:
        cursor.execute(query, bounds)
        writer = csv.writer(output)
        writer.writerow([column[0] for column in cursor.description])
        while rows := cursor.fetchmany(10_000):
            writer.writerows(rows)


def extract_monthly_operational_data(year: int, month: int) -> None:
    """Export the documented operational sources to the shared Bronze landing."""
    from airflow.providers.postgres.hooks.postgres import PostgresHook

    landing = Path(os.environ.get("BRONZE_LANDING_DIR", "").strip())
    if not landing.is_dir():
        raise FileNotFoundError(f"Directorio landing no válido: {landing}")

    timezone = os.environ.get("AIRFLOW_TIMEZONE", "America/New_York")
    bounds = _period_bounds(year, month, timezone)
    period = Path(f"year={year}", f"month={month:02d}", "data.csv")
    trip_requests_dir = _bronze_relative_dir(
        "S3_TRIP_REQUESTS_PATH", "operational/trip_requests"
    )
    history_dir = _bronze_relative_dir(
        "S3_ZONE_STATE_HISTORY_PATH", "zone_state_history"
    )
    complaints_dir = _bronze_relative_dir(
        "S3_SERVICE_COMPLAINTS_PATH", "operational/service_complaints"
    )

    hook = PostgresHook(
        postgres_conn_id=os.environ.get(
            "AIRFLOW_POSTGRES_CONN_ID", "postgres_default"
        )
    )
    connection = hook.get_conn()
    try:
        _export_query(
            connection,
            TRIP_REQUESTS_QUERY,
            landing / trip_requests_dir / period,
            bounds,
        )
        _export_query(
            connection,
            ZONE_HISTORY_QUERY,
            landing / history_dir / period,
            bounds,
        )
        _export_query(
            connection,
            SERVICE_COMPLAINTS_QUERY,
            landing / complaints_dir / period,
            bounds,
        )
    finally:
        connection.close()
