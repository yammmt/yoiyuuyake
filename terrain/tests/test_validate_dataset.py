from __future__ import annotations

import json
import struct
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1] / "scripts"))
from validate_dataset import DatasetValidationError, validate_dataset  # noqa: E402


class ValidateDatasetTests(unittest.TestCase):
    @staticmethod
    def _write_dataset(root: Path) -> None:
        tiles = root / "tiles"
        tiles.mkdir(parents=True)
        (tiles / "533945.dem").write_bytes(struct.pack("<4h", 1, -32768, 3, 4))
        index = {
            "format_version": 1,
            "missing_value": -32768,
            "tiles": [
                {
                    "mesh_code": "533945",
                    "file": "tiles/533945.dem",
                    "south": 35.0,
                    "north": 35.1,
                    "west": 139.0,
                    "east": 139.2,
                    "rows": 2,
                    "columns": 2,
                }
            ],
        }
        (root / "index.json").write_text(
            json.dumps(index, ensure_ascii=False), encoding="utf-8"
        )

    def test_reports_structure_bounds_and_missing_cells(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            self._write_dataset(root)

            result = validate_dataset(root, expected_tiles=1)

            self.assertEqual(result["tile_count"], 1)
            self.assertEqual(result["total_cells"], 4)
            self.assertEqual(result["total_tile_bytes"], 8)
            self.assertEqual(result["missing_cells"], 1)
            self.assertEqual(result["missing_ratio"], 0.25)
            self.assertEqual(result["bounds"]["west"], 139.0)

    def test_rejects_wrong_tile_size(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            self._write_dataset(root)
            (root / "tiles" / "533945.dem").write_bytes(b"\x00\x00")

            with self.assertRaisesRegex(DatasetValidationError, "サイズが不正"):
                validate_dataset(root)

    def test_rejects_unindexed_tile(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            self._write_dataset(root)
            (root / "tiles" / "533946.dem").write_bytes(b"\x00\x00")

            with self.assertRaisesRegex(DatasetValidationError, "indexとタイル"):
                validate_dataset(root)

    def test_rejects_non_object_index(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            (root / "index.json").write_text("[]", encoding="utf-8")

            with self.assertRaisesRegex(DatasetValidationError, "ルート"):
                validate_dataset(root)


if __name__ == "__main__":
    unittest.main()
