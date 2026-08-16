from __future__ import annotations

import json
import struct
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1] / "scripts"))
from dem_store import DemDataUnavailableError, DemNoElevationError, LocalDemStore  # noqa: E402


class LocalDemStoreTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary_directory.name)
        (self.root / "tiles").mkdir()
        (self.root / "tiles" / "demo.dem").write_bytes(struct.pack("<4h", 12, 23, -32768, 45))
        (self.root / "index.json").write_text(json.dumps({
            "format_version": 1,
            "missing_value": -32768,
            "tiles": [{
                "mesh_code": "demo",
                "file": "tiles/demo.dem",
                "south": 35.0,
                "west": 139.0,
                "north": 35.1,
                "east": 139.2,
                "rows": 2,
                "columns": 2,
            }],
        }), encoding="utf-8")
        self.store = LocalDemStore(self.root)

    def tearDown(self) -> None:
        self.temporary_directory.cleanup()

    def test_reads_an_elevation_without_loading_the_whole_tile(self) -> None:
        sample = self.store.elevation_at(35.09, 139.01)

        self.assertEqual(sample.elevation_meters, 12.0)
        self.assertEqual(sample.mesh_code, "demo")
        self.assertEqual((sample.row, sample.column), (0, 0))

    def test_reads_a_southern_eastern_cell(self) -> None:
        sample = self.store.elevation_at(35.01, 139.19)

        self.assertEqual(sample.elevation_meters, 45.0)
        self.assertEqual((sample.row, sample.column), (1, 1))

    def test_reports_missing_values(self) -> None:
        with self.assertRaises(DemNoElevationError):
            self.store.elevation_at(35.01, 139.01)

    def test_reports_coordinates_outside_the_prepared_area(self) -> None:
        with self.assertRaises(DemDataUnavailableError):
            self.store.elevation_at(34.9, 139.01)


if __name__ == "__main__":
    unittest.main()
