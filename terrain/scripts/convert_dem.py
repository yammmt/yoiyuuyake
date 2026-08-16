#!/usr/bin/env python3
"""Convert nested GSI DEM10B ZIP archives into compact local binary tiles."""

from __future__ import annotations

import argparse
import io
import json
import math
import struct
import tempfile
import xml.parsers.expat
import zipfile
from pathlib import Path

NODATA_INPUT = -9999.0
NODATA_OUTPUT = -32768
FORMAT_VERSION = 1


class DemGmlParser:
    """Streaming parser for the GML values needed by the local tile format."""

    def __init__(self) -> None:
        self._active_tag: str | None = None
        self._text: list[str] = []
        self._tuple_remainder = ""
        self._values: list[int] = []
        self.lower_corner: tuple[float, float] | None = None
        self.upper_corner: tuple[float, float] | None = None
        self.high: tuple[int, int] | None = None

    def start_element(self, name: str, _attrs: dict[str, str]) -> None:
        self._active_tag = name.rsplit(":", 1)[-1]
        self._text = []

    def end_element(self, name: str) -> None:
        tag = name.rsplit(":", 1)[-1]
        text = "".join(self._text).strip()
        if tag == "lowerCorner":
            self.lower_corner = tuple(map(float, text.split()))  # type: ignore[assignment]
        elif tag == "upperCorner":
            self.upper_corner = tuple(map(float, text.split()))  # type: ignore[assignment]
        elif tag == "high":
            self.high = tuple(map(int, text.split()))  # type: ignore[assignment]
        elif tag == "tupleList":
            self._consume_tuple_text("\n", final=True)
        self._active_tag = None
        self._text = []

    def character_data(self, data: str) -> None:
        if self._active_tag == "tupleList":
            self._consume_tuple_text(data)
        elif self._active_tag in {"lowerCorner", "upperCorner", "high"}:
            self._text.append(data)

    def _consume_tuple_text(self, data: str, final: bool = False) -> None:
        lines = (self._tuple_remainder + data).split("\n")
        self._tuple_remainder = lines.pop()
        for line in lines:
            self._append_tuple(line)
        if final:
            self._append_tuple(self._tuple_remainder)
            self._tuple_remainder = ""

    def _append_tuple(self, line: str) -> None:
        line = line.strip()
        if not line:
            return
        _classification, raw_height = line.rsplit(",", 1)
        height = float(raw_height)
        if math.isclose(height, NODATA_INPUT):
            self._values.append(NODATA_OUTPUT)
            return
        meters = round(height)
        if not -32767 <= meters <= 32767:
            raise ValueError(f"標高値が int16 の範囲外です: {height}")
        self._values.append(meters)

    def result(self) -> tuple[dict[str, object], bytes]:
        if not (self.lower_corner and self.upper_corner and self.high):
            raise ValueError("GML に格子メタデータが不足しています")
        columns, rows = self.high[0] + 1, self.high[1] + 1
        expected = columns * rows
        if len(self._values) != expected:
            raise ValueError(f"格子数が不正です: expected={expected}, actual={len(self._values)}")
        metadata = {
            "south": self.lower_corner[0],
            "west": self.lower_corner[1],
            "north": self.upper_corner[0],
            "east": self.upper_corner[1],
            "rows": rows,
            "columns": columns,
        }
        return metadata, struct.pack(f"<{expected}h", *self._values)


def parse_gml(stream: io.BufferedIOBase) -> tuple[dict[str, object], bytes]:
    parser_impl = DemGmlParser()
    parser = xml.parsers.expat.ParserCreate()
    parser.StartElementHandler = parser_impl.start_element
    parser.EndElementHandler = parser_impl.end_element
    parser.CharacterDataHandler = parser_impl.character_data
    while chunk := stream.read(1024 * 1024):
        parser.Parse(chunk, False)
    parser.Parse(b"", True)
    return parser_impl.result()


def convert_archive(source: Path, destination: Path, limit: int | None = None) -> dict[str, object]:
    tiles_dir = destination / "tiles"
    tiles_dir.mkdir(parents=True, exist_ok=True)
    converted: list[dict[str, object]] = []

    with zipfile.ZipFile(source) as outer:
        inner_names = sorted(name for name in outer.namelist() if "-DEM10B-" in name and name.endswith(".zip"))
        for inner_name in inner_names[:limit]:
            mesh_code = inner_name.split("-")[2]
            with zipfile.ZipFile(io.BytesIO(outer.read(inner_name))) as inner:
                gml_names = [name for name in inner.namelist() if name.endswith(".xml") and "-dem10b-" in name.lower()]
                if len(gml_names) != 1:
                    raise ValueError(f"DEM GML を一意に特定できません: {inner_name}")
                with inner.open(gml_names[0]) as gml:
                    metadata, payload = parse_gml(gml)

            filename = f"{mesh_code}.dem"
            temporary = tempfile.NamedTemporaryFile(dir=tiles_dir, delete=False)
            try:
                temporary.write(payload)
                temporary.close()
                Path(temporary.name).replace(tiles_dir / filename)
            finally:
                temporary.close()
                Path(temporary.name).unlink(missing_ok=True)

            converted.append({
                "mesh_code": mesh_code,
                "file": f"tiles/{filename}",
                "source": inner_name,
                **metadata,
            })

    index = {
        "format_version": FORMAT_VERSION,
        "value_unit": "1m",
        "byte_order": "little-endian",
        "missing_value": NODATA_OUTPUT,
        "tiles": converted,
    }
    (destination / "index.json").write_text(json.dumps(index, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return index


def main() -> None:
    argument_parser = argparse.ArgumentParser(description=__doc__)
    argument_parser.add_argument("source", type=Path, help="国土地理院から取得した外側 ZIP")
    argument_parser.add_argument("--output", type=Path, required=True, help="変換済みタイルの出力先")
    argument_parser.add_argument("--limit", type=int, help="変換するメッシュ数（動作確認用）")
    args = argument_parser.parse_args()

    if args.limit is not None and args.limit < 1:
        argument_parser.error("--limit は 1 以上にしてください")
    index = convert_archive(args.source, args.output, args.limit)
    print(f"{len(index['tiles'])} メッシュを {args.output} に変換しました。")


if __name__ == "__main__":
    main()
