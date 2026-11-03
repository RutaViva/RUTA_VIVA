from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from batch.scripts.pipeline_readiness import validate_pipeline_inputs


class PipelineReadinessTests(unittest.TestCase):
    def _environment(self, landing: Path) -> dict[str, str]:
        return {
            "BRONZE_LANDING_DIR": str(landing),
            "S3_BRONZE_PATH": "s3://rutaviva-lake/bronze",
            "S3_SILVER_PATH": "s3://rutaviva-lake/silver",
            "S3_GOLD_PATH": "s3://rutaviva-lake/gold",
            "S3_QUARANTINE_PATH": "s3://rutaviva-lake/quarantine",
        }

    def _project_inputs(self, root: Path) -> None:
        catalog = root / "services" / "seed_cli" / "app" / "data" / "csv"
        shapes = root / "services" / "seed_cli" / "app" / "data" / "shapefiles"
        catalog.mkdir(parents=True)
        shapes.mkdir(parents=True)
        (catalog / "taxi_zone_lookup.csv").touch()
        (shapes / "taxi_zones.shp").touch()

    def test_local_historical_sources_are_ready(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            landing = root / "landing"
            for source in ("f1", "f3", "f7"):
                source_dir = landing / source
                source_dir.mkdir(parents=True)
                (source_dir / "data.csv").touch()
            self._project_inputs(root)

            with patch.dict(os.environ, self._environment(landing), clear=True):
                validate_pipeline_inputs(landing_dir=landing, project_root=root)

    def test_historical_sources_can_be_available_in_s3(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            landing = root / "landing"
            landing.mkdir()
            self._project_inputs(root)

            with (
                patch.dict(os.environ, self._environment(landing), clear=True),
                patch(
                    "batch.scripts.pipeline_readiness._has_s3_objects",
                    return_value=True,
                ) as has_objects,
            ):
                validate_pipeline_inputs(landing_dir=landing, project_root=root)

            self.assertEqual(
                [call.args[0] for call in has_objects.call_args_list],
                [
                    "s3://rutaviva-lake/bronze/f1",
                    "s3://rutaviva-lake/bronze/f3",
                    "s3://rutaviva-lake/bronze/f7",
                ],
            )

    def test_missing_historical_source_fails_readiness(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            landing = root / "landing"
            landing.mkdir()
            self._project_inputs(root)

            with (
                patch.dict(os.environ, self._environment(landing), clear=True),
                patch(
                    "batch.scripts.pipeline_readiness._has_s3_objects",
                    return_value=False,
                ),
                self.assertRaisesRegex(FileNotFoundError, "fuentes históricas"),
            ):
                validate_pipeline_inputs(landing_dir=landing, project_root=root)


if __name__ == "__main__":
    unittest.main()
