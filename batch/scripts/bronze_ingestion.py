from __future__ import annotations

import os
from pathlib import Path
from typing import Any


def _parse_s3_uri(uri: str) -> tuple[str, str]:
    if not uri.startswith(("s3://", "s3a://")):
        raise ValueError("S3_BRONZE_PATH debe iniciar con s3:// o s3a://")

    _, _, location = uri.partition("://")
    bucket, _, prefix = location.partition("/")
    if not bucket:
        raise ValueError("La URI de S3 debe incluir un nombre de bucket.")
    return bucket, prefix.strip("/")


def _get_config_values() -> tuple[Path, str, str, str]:
    landing_dir = Path(os.environ.get("BRONZE_LANDING_DIR", "").strip())
    bronze_uri = os.environ.get("S3_BRONZE_PATH", "").strip()
    if not landing_dir.is_dir():
        raise FileNotFoundError(f"Directorio landing no válido: {landing_dir}")
    bucket, prefix = _parse_s3_uri(bronze_uri)
    return landing_dir, bucket, prefix, bronze_uri


def _make_s3_client() -> Any:
    from airflow.providers.amazon.aws.hooks.base_aws import AwsBaseHook
    from botocore.config import Config

    endpoint = os.environ.get("S3_ENDPOINT", "").strip() or None
    path_style = True if endpoint else (
        os.environ.get("S3_PATH_STYLE_ACCESS", "false").lower() == "true"
    )
    region = os.environ.get("AWS_REGION") or os.environ.get("AWS_DEFAULT_REGION")

    hook = AwsBaseHook(
        aws_conn_id=os.environ.get("AIRFLOW_AWS_CONN_ID", "aws_default"),
        client_type="s3",
        region_name=region,
    )
    
    return hook.get_session().client(
        "s3",
        endpoint_url=endpoint,
        region_name=region,
        config=Config(s3={"addressing_style": "path" if path_style else "auto"}),
    )


def ingest_bronze() -> None:
    from botocore.exceptions import ClientError

    landing_dir, bucket, prefix, _ = _get_config_values()
    files = sorted(path for path in landing_dir.rglob("*") if path.is_file())
    if not files:
        raise FileNotFoundError(f"No se encontraron archivos en: {landing_dir}")

    s3 = _make_s3_client()

    for path in files:
        relative_path = path.relative_to(landing_dir).as_posix()
        key = f"{prefix}/{relative_path}" if prefix else relative_path
        stat = path.stat()
        metadata = {
            "source-size": str(stat.st_size),
            "source-mtime-ns": str(stat.st_mtime_ns),
        }

        try:
            existing = s3.head_object(Bucket=bucket, Key=key)
            if existing.get("Metadata", {}) == metadata:
                continue
        except ClientError as error:
            error_code = str(error.response.get("Error", {}).get("Code", ""))
            if error_code not in {"404", "NoSuchKey", "NotFound"}:
                raise

        s3.upload_file(
            str(path),
            bucket,
            key,
            ExtraArgs={"Metadata": metadata},
        )