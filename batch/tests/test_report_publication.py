from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from batch.scripts.report_publication import publish_regulatory_report


class ReportPublicationTests(unittest.TestCase):
    def test_publishes_both_report_files_under_gold_period_prefix(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            output_dir = Path(directory)
            for name in (
                "regulatory_report_2026_01.json",
                "regulatory_report_by_borough_2026_01.csv",
            ):
                (output_dir / name).write_text("report", encoding="utf-8")
            s3 = Mock()

            with (
                patch.dict(os.environ, {"S3_GOLD_PATH": "s3://lake/gold"}),
                patch(
                    "batch.scripts.report_publication.make_s3_client",
                    return_value=s3,
                ),
            ):
                keys = publish_regulatory_report(
                    output_dir=output_dir,
                    year=2026,
                    month=1,
                )

        self.assertEqual(
            keys,
            [
                "gold/reports/year=2026/month=01/regulatory_report_2026_01.json",
                "gold/reports/year=2026/month=01/regulatory_report_by_borough_2026_01.csv",
            ],
        )
        self.assertEqual(s3.upload_file.call_count, 2)

    def test_missing_report_file_fails_before_upload(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            s3_factory = Mock()
            with (
                patch.dict(os.environ, {"S3_GOLD_PATH": "s3://lake/gold"}),
                patch(
                    "batch.scripts.report_publication.make_s3_client",
                    s3_factory,
                ),
                self.assertRaisesRegex(FileNotFoundError, "No se generaron"),
            ):
                publish_regulatory_report(
                    output_dir=Path(directory),
                    year=2026,
                    month=1,
                )
            s3_factory.assert_not_called()


if __name__ == "__main__":
    unittest.main()
