from __future__ import annotations

import os
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from batch.scripts.bronze_ingestion import _parse_s3_uri, ingest_bronze


class BronzeIngestionTests(unittest.TestCase):
    def test_parse_s3_and_s3a_paths(self) -> None:
        self.assertEqual(
            _parse_s3_uri("s3://rutaviva-lake/bronze/f1"),
            ("rutaviva-lake", "bronze/f1"),
        )
        self.assertEqual(
            _parse_s3_uri("s3a://rutaviva-lake"),
            ("rutaviva-lake", ""),
        )

    def test_reject_invalid_s3_paths(self) -> None:
        for uri in ("", "file:///tmp/bronze", "s3:///bronze"):
            with self.subTest(uri=uri), self.assertRaises(ValueError):
                _parse_s3_uri(uri)

    def test_ingestion_skips_existing_objects_and_uploads_missing_files(self) -> None:
        class FakeClientError(Exception):
            def __init__(self) -> None:
                self.response = {
                    "Error": {"Code": "404"},
                    "ResponseMetadata": {"HTTPStatusCode": 404},
                }

        botocore = types.ModuleType("botocore")
        botocore_exceptions = types.ModuleType("botocore.exceptions")
        botocore_exceptions.ClientError = FakeClientError

        with tempfile.TemporaryDirectory() as landing:
            existing_path = Path(landing, "existing.csv")
            existing_path.write_text("existing", encoding="utf-8")
            changed_path = Path(landing, "changed.csv")
            changed_path.write_text("changed", encoding="utf-8")
            new_path = Path(landing, "new.csv")
            new_path.write_text("new", encoding="utf-8")
            existing_stat = existing_path.stat()
            s3 = Mock()

            def head_object(*, Bucket: str, Key: str) -> dict[str, dict[str, str]]:
                if Key.endswith("existing.csv"):
                    return {
                        "Metadata": {
                            "source-size": str(existing_stat.st_size),
                            "source-mtime-ns": str(existing_stat.st_mtime_ns),
                        }
                    }
                if Key.endswith("changed.csv"):
                    return {"Metadata": {"source-size": "0", "source-mtime-ns": "0"}}
                raise FakeClientError()

            s3.head_object.side_effect = head_object
            with (
                patch.dict(
                    sys.modules,
                    {
                        "botocore": botocore,
                        "botocore.exceptions": botocore_exceptions,
                    },
                ),
                patch.dict(
                    os.environ,
                    {
                        "BRONZE_LANDING_DIR": landing,
                        "S3_BRONZE_PATH": "s3a://rutaviva-lake/bronze",
                    },
                ),
                patch("batch.scripts.bronze_ingestion._make_s3_client", return_value=s3),
            ):
                ingest_bronze()

            self.assertEqual(s3.upload_file.call_count, 2)
            self.assertEqual(
                s3.upload_file.call_args_list[0].args,
                (str(changed_path), "rutaviva-lake", "bronze/changed.csv"),
            )
            self.assertEqual(
                s3.upload_file.call_args_list[1].args,
                (str(new_path), "rutaviva-lake", "bronze/new.csv"),
            )
            self.assertIn(
                "source-mtime-ns",
                s3.upload_file.call_args_list[0].kwargs["ExtraArgs"]["Metadata"],
            )


if __name__ == "__main__":
    unittest.main()
