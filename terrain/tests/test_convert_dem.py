from __future__ import annotations

import io
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1] / "scripts"))
from convert_dem import NODATA_OUTPUT, convert_archive, parse_gml  # noqa: E402


GML = b'''<?xml version="1.0" encoding="UTF-8"?>
<root xmlns:gml="http://www.opengis.net/gml/3.2">
  <gml:lowerCorner>35.0 139.0</gml:lowerCorner>
  <gml:upperCorner>35.1 139.2</gml:upperCorner>
  <gml:high>1 1</gml:high>
  <gml:tupleList>
other,1.2
other,-9999.00
other,3.4
other,-5.6
  </gml:tupleList>
</root>
'''


class ConvertDemTests(unittest.TestCase):
    def test_parse_gml_preserves_grid_order_and_missing_values(self) -> None:
        metadata, payload = parse_gml(io.BytesIO(GML))

        self.assertEqual(metadata["rows"], 2)
        self.assertEqual(metadata["columns"], 2)
        self.assertEqual(metadata["north"], 35.1)
        self.assertEqual(payload, b"\x01\x00\x00\x80\x03\x00\xfa\xff")

    def test_convert_archive_writes_tile_and_index(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            inner_bytes = io.BytesIO()
            with zipfile.ZipFile(inner_bytes, "w") as inner:
                inner.writestr("FG-GML-5339-45-dem10b-20260816.xml", GML)
            source = root / "source.zip"
            with zipfile.ZipFile(source, "w") as outer:
                outer.writestr("FG-GML-533945-DEM10B-20260816.zip", inner_bytes.getvalue())

            index = convert_archive(source, root / "output")

            self.assertEqual(index["missing_value"], NODATA_OUTPUT)
            self.assertEqual(index["tiles"][0]["mesh_code"], "533945")
            self.assertEqual((root / "output" / "tiles" / "533945.dem").read_bytes()[2:4], b"\x00\x80")


if __name__ == "__main__":
    unittest.main()
