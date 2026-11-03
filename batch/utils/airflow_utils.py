from __future__ import annotations

from airflow.operators.python import get_current_context


def previous_month_period(timezone: str) -> tuple[int, int]:
    interval_end = get_current_context()["data_interval_end"]
    previous_month = interval_end.in_timezone(timezone).subtract(months=1)
    return previous_month.year, previous_month.month


def previous_month_spark_arguments(timezone: str) -> list[str]:
    year, month = previous_month_period(timezone)
    return ["--year", str(year), "--month", str(month)]
