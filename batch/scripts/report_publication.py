from __future__ import annotations

import os
from pathlib import Path
from urllib.parse import urlsplit

from batch.scripts.bronze_ingestion import make_s3_client


def publish_regulatory_report(
    *,
    output_dir: Path,
    year: int,
    month: int,
) -> list[str]:
    gold_uri = os.environ.get("S3_GOLD_PATH", "").strip()
    parsed = urlsplit(gold_uri)
    if parsed.scheme not in {"s3", "s3a"} or not parsed.netloc:
        raise ValueError("S3_GOLD_PATH debe ser una URI s3:// o s3a:// con bucket.")

    report_names = (
        f"regulatory_report_{year}_{month:02d}.json",
        f"regulatory_report_by_borough_{year}_{month:02d}.csv",
    )
    files = [output_dir / name for name in report_names]
    missing = [str(path) for path in files if not path.is_file() or path.stat().st_size == 0]
    if missing:
        raise FileNotFoundError(
            "No se generaron todos los archivos del reporte: " + ", ".join(missing)
        )

    prefix = parsed.path.strip("/")
    report_prefix = f"{prefix}/reports" if prefix else "reports"
    period_prefix = f"{report_prefix}/year={year}/month={month:02d}"
    s3 = make_s3_client()
    keys = []
    for path in files:
        key = f"{period_prefix}/{path.name}"
        s3.upload_file(str(path), parsed.netloc, key)
        keys.append(key)

    return keys
