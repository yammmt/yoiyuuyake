from __future__ import annotations

import io
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1] / "scripts"))
from convert_dem import (  # noqa: E402
    NODATA_OUTPUT,
    convert_archive,
    convert_archives,
    parse_gml,
)


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

PARTIAL_GML = b'''<?xml version="1.0" encoding="UTF-8"?>
<root xmlns:gml="http://www.opengis.net/gml/3.2">
  <gml:lowerCorner>35.0 139.0</gml:lowerCorner>
  <gml:upperCorner>35.1 139.2</gml:upperCorner>
  <gml:low>0 0</gml:low>
  <gml:high>1 1</gml:high>
  <gml:tupleList>
other,1.2
other,3.4
  </gml:tupleList>
  <gml:GridFunction>
    <gml:sequenceRule order="+x-y">Linear</gml:sequenceRule>
    <gml:startPoint>1 0</gml:startPoint>
  </gml:GridFunction>
</root>
'''


class ConvertDemTests(unittest.TestCase):
    @staticmethod
    def _write_outer_archive(path: Path, mesh_code: str, gml: bytes = GML) -> None:
        inner_bytes = io.BytesIO()
        with zipfile.ZipFile(inner_bytes, "w") as inner:
            inner.writestr(f"FG-GML-{mesh_code[:4]}-{mesh_code[4:]}-dem10b-20260816.xml", gml)
        with zipfile.ZipFile(path, "w") as outer:
            outer.writestr(f"FG-GML-{mesh_code}-DEM10B-20260816.zip", inner_bytes.getvalue())

    def test_parse_gml_preserves_grid_order_and_missing_values(self) -> None:
        metadata, payload = parse_gml(io.BytesIO(GML))

        self.assertEqual(metadata["rows"], 2)
        self.assertEqual(metadata["columns"], 2)
        self.assertEqual(metadata["north"], 35.1)
        self.assertEqual(payload, b"\x01\x00\x00\x80\x03\x00\xfa\xff")

    def test_parse_gml_fills_cells_omitted_before_and_after_start_point(self) -> None:
        metadata, payload = parse_gml(io.BytesIO(PARTIAL_GML))

        self.assertEqual(metadata["rows"], 2)
        self.assertEqual(metadata["columns"], 2)
        self.assertEqual(payload, b"\x00\x80\x01\x00\x03\x00\x00\x80")

    def test_convert_archive_writes_tile_and_index(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            source = root / "source.zip"
            self._write_outer_archive(source, "533945")

            index = convert_archive(source, root / "output")

            self.assertEqual(index["missing_value"], NODATA_OUTPUT)
            self.assertEqual(index["tiles"][0]["mesh_code"], "533945")
            self.assertEqual((root / "output" / "tiles" / "533945.dem").read_bytes()[2:4], b"\x00\x80")

    def test_convert_archives_merges_sources_in_mesh_order(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            first = root / "first.zip"
            second = root / "second.zip"
            self._write_outer_archive(first, "533946")
            self._write_outer_archive(second, "303650")

            index = convert_archives([first, second], root / "output")

            self.assertEqual([tile["mesh_code"] for tile in index["tiles"]], ["303650", "533946"])
            self.assertEqual(
                sorted(path.name for path in (root / "output" / "tiles").iterdir()),
                ["303650.dem", "533946.dem"],
            )

            reverse_output = root / "reverse-output"
            convert_archives([second, first], reverse_output)
            self.assertEqual(
                (root / "output" / "index.json").read_bytes(),
                (reverse_output / "index.json").read_bytes(),
            )
            for mesh_code in ("303650", "533946"):
                self.assertEqual(
                    (root / "output" / "tiles" / f"{mesh_code}.dem").read_bytes(),
                    (reverse_output / "tiles" / f"{mesh_code}.dem").read_bytes(),
                )

    def test_convert_archives_deduplicates_identical_meshes(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            first = root / "first.zip"
            second = root / "second.zip"
            self._write_outer_archive(first, "533945")
            self._write_outer_archive(second, "533945")

            index = convert_archives([second, first], root / "output")

            self.assertEqual(len(index["tiles"]), 1)
            self.assertEqual(index["tiles"][0]["mesh_code"], "533945")

    def test_convert_archives_rejects_conflicting_mesh_without_publishing(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            first = root / "first.zip"
            second = root / "second.zip"
            self._write_outer_archive(first, "533945")
            self._write_outer_archive(second, "533945", GML.replace(b"other,1.2", b"other,2.2"))
            output = root / "output"

            with self.assertRaisesRegex(ValueError, "異なる DEM10B"):
                convert_archives([first, second], output)

            self.assertFalse(output.exists())

    def test_convert_archives_does_not_overwrite_existing_output(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            source = root / "source.zip"
            self._write_outer_archive(source, "533945")
            output = root / "output"
            output.mkdir()
            marker = output / "marker"
            marker.write_text("keep", encoding="utf-8")

            with self.assertRaises(FileExistsError):
                convert_archives([source], output)

            self.assertEqual(marker.read_text(encoding="utf-8"), "keep")

    def test_convert_archives_rejects_input_without_dem10b(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            source = root / "source.zip"
            with zipfile.ZipFile(source, "w") as outer:
                outer.writestr("FG-GML-533945-DEM10A-20260816.zip", b"not used")

            with self.assertRaisesRegex(ValueError, "DEM10B がありません"):
                convert_archives([source], root / "output")

            self.assertFalse((root / "output").exists())


if __name__ == "__main__":
    unittest.main()
