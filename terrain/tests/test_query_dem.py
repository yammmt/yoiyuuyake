from __future__ import annotations

import json
import struct
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


class QueryDemTests(unittest.TestCase):
    def test_cli_returns_the_requested_elevation_as_json(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            (root / "tiles").mkdir()
            (root / "tiles" / "demo.dem").write_bytes(struct.pack("<h", 123))
            (root / "index.json").write_text(json.dumps({
                "format_version": 1,
                "missing_value": -32768,
                "tiles": [{
                    "mesh_code": "demo",
                    "file": "tiles/demo.dem",
                    "south": 35.0,
                    "west": 139.0,
                    "north": 35.1,
                    "east": 139.2,
                    "rows": 1,
                    "columns": 1,
                }],
            }), encoding="utf-8")

            result = subprocess.run([
                sys.executable,
                "terrain/scripts/query_dem.py",
                "--data", str(root),
                "--latitude", "35.05",
                "--longitude", "139.10",
            ], check=True, capture_output=True, text=True)

        response = json.loads(result.stdout)
        self.assertEqual(response["elevation_meters"], 123.0)
        self.assertEqual(response["mesh_code"], "demo")
