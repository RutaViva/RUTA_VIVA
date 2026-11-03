from __future__ import annotations

import os
from pathlib import Path
from urllib.parse import urlsplit


REQUIRED_S3_PATHS = (
    "S3_BRONZE_PATH",
    "S3_SILVER_PATH",
    "S3_GOLD_PATH",
    "S3_QUARANTINE_PATH",
)

HISTORICAL_SOURCES = (
    ("f1", "S3_F1_PATH"),
    ("f3", "S3_WEATHER_PATH"),
    ("f7", "S3_EVENTS_PATH"),
)


def _validate_s3_uri(name: str, value: str) -> None:
    parsed = urlsplit(value)
    if parsed.scheme not in {"s3", "s3a"} or not parsed.netloc:
        raise ValueError(f"{name} debe ser una URI s3:// o s3a:// con bucket.")
    if "reemplaza-con-tu-bucket" in parsed.netloc:
        raise ValueError(f"{name} todavía contiene el bucket de ejemplo.")


def _has_source_files(path: Path) -> bool:
    return path.is_dir() and any(
        file.is_file()
        and not any(part.startswith((".", "_")) for part in file.relative_to(path).parts)
        for file in path.rglob("*")
    )


def _has_s3_objects(uri: str) -> bool:
    from batch.scripts.bronze_ingestion import make_s3_client

    parsed = urlsplit(uri)
    prefix = parsed.path.strip("/")
    if prefix:
        prefix += "/"

    paginator = make_s3_client().get_paginator("list_objects_v2")
    for page in paginator.paginate(Bucket=parsed.netloc, Prefix=prefix):
        if any(
            item.get("Key", "").strip("/") != prefix.strip("/")
            for item in page.get("Contents", [])
        ):
            return True
    return False


def validate_pipeline_inputs(
    landing_dir: Path | None = None,
    project_root: Path | None = None,
) -> None:
    """Fail before extraction unless historical sources and Spark inputs are ready."""
    landing_value = os.environ.get("BRONZE_LANDING_DIR", "").strip()
    if landing_dir is None and not landing_value:
        raise ValueError("Falta configurar BRONZE_LANDING_DIR.")
    landing = landing_dir or Path(landing_value)
    if not landing.is_dir():
        raise FileNotFoundError(f"Directorio landing no válido: {landing}")

    for name in REQUIRED_S3_PATHS:
        value = os.environ.get(name, "").strip()
        if not value:
            raise ValueError(f"Falta configurar {name}.")
        _validate_s3_uri(name, value)

    bronze_uri = os.environ.get("S3_BRONZE_PATH", "").strip()
    missing_sources = []
    for directory, variable in HISTORICAL_SOURCES:
        configured_uri = os.environ.get(variable, "").strip()
        source_uri = configured_uri or f"{bronze_uri.rstrip('/')}/{directory}"
        if configured_uri:
            _validate_s3_uri(variable, configured_uri)

        local_source = landing / directory
        if not configured_uri and _has_source_files(local_source):
            continue
        if not _has_s3_objects(source_uri):
            missing_sources.append(source_uri)
    if missing_sources:
        raise FileNotFoundError(
            "No se encontraron fuentes históricas en Bronze landing o S3: "
            + ", ".join(missing_sources)
        )

    root = project_root or Path(__file__).resolve().parents[2]
    required_local_inputs = (
        (
            "RUTAVIVA_ZONE_CATALOG_PATH",
            root / "services" / "seed_cli" / "app" / "data" / "csv" / "taxi_zone_lookup.csv",
        ),
        (
            "RUTAVIVA_ZONE_SHAPEFILE_PATH",
            root
            / "services"
            / "seed_cli"
            / "app"
            / "data"
            / "shapefiles"
            / "taxi_zones.shp",
        ),
    )
    missing_local_inputs = [
        str(Path(os.environ.get(name, "").strip() or default))
        for name, default in required_local_inputs
        if not Path(os.environ.get(name, "").strip() or default).is_file()
    ]
    if missing_local_inputs:
        raise FileNotFoundError(
            "Faltan archivos locales requeridos por Job 2: "
            + ", ".join(missing_local_inputs)
        )
