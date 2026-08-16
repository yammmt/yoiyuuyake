from __future__ import annotations

import json
import struct
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


class QueryHorizonTests(unittest.TestCase):
    def test_cli_returns_visibility_and_ray_diagnostics(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            (root / "tiles").mkdir()
            (root / "tiles" / "demo.dem").write_bytes(struct.pack("<h", 100))
            (root / "index.json").write_text(json.dumps({
                "format_version": 1,
                "missing_value": -32768,
                "tiles": [{
                    "mesh_code": "demo",
                    "file": "tiles/demo.dem",
                    "south": 34.0,
                    "west": 138.0,
                    "north": 36.0,
                    "east": 140.0,
                    "rows": 1,
                    "columns": 1,
                }],
            }), encoding="utf-8")
            result = subprocess.run([
                sys.executable,
                "terrain/scripts/query_horizon.py",
                "--data", str(root),
                "--latitude", "35.0",
                "--longitude", "139.0",
                "--azimuth", "270",
                "--max-distance", "100",
                "--sample-interval", "100",
                "--ray-count", "1",
            ], check=True, capture_output=True, text=True)

        response = json.loads(result.stdout)
        self.assertEqual(response["visibility"]["label"], "広い")
        self.assertEqual(len(response["rays"]), 1)
        self.assertIn("obstruction_distance_meters", response["rays"][0])
