#!/usr/bin/env python3
"""Convert nested GSI DEM10B ZIP archives into compact local binary tiles."""

from __future__ import annotations

import argparse
import io
import json
import math
import re
import struct
import tempfile
import xml.parsers.expat
import zipfile
from collections import defaultdict
from collections.abc import Sequence
from contextlib import ExitStack
from pathlib import Path

NODATA_INPUT = -9999.0
NODATA_OUTPUT = -32768
FORMAT_VERSION = 1
DEM10B_ARCHIVE_PATTERN = re.compile(r"(?:^|/)FG-GML-(\d{6})-DEM10B-[^/]+\.zip$")


class DemGmlParser:
    """Streaming parser for the GML values needed by the local tile format."""

    def __init__(self) -> None:
        self._active_tag: str | None = None
        self._text: list[str] = []
        self._tuple_remainder = ""
        self._values: list[int] = []
        self.lower_corner: tuple[float, float] | None = None
        self.upper_corner: tuple[float, float] | None = None
        self.low: tuple[int, int] | None = None
        self.high: tuple[int, int] | None = None
        self.start_point: tuple[int, int] | None = None
        self.sequence_order: str | None = None

    def start_element(self, name: str, attrs: dict[str, str]) -> None:
        self._active_tag = name.rsplit(":", 1)[-1]
        self._text = []
        if self._active_tag == "sequenceRule":
            self.sequence_order = attrs.get("order")

    def end_element(self, name: str) -> None:
        tag = name.rsplit(":", 1)[-1]
        text = "".join(self._text).strip()
        if tag == "lowerCorner":
            self.lower_corner = tuple(map(float, text.split()))  # type: ignore[assignment]
        elif tag == "upperCorner":
            self.upper_corner = tuple(map(float, text.split()))  # type: ignore[assignment]
        elif tag == "low":
            self.low = tuple(map(int, text.split()))  # type: ignore[assignment]
        elif tag == "high":
            self.high = tuple(map(int, text.split()))  # type: ignore[assignment]
        elif tag == "startPoint":
            self.start_point = tuple(map(int, text.split()))  # type: ignore[assignment]
        elif tag == "tupleList":
            self._consume_tuple_text("\n", final=True)
        self._active_tag = None
        self._text = []

    def character_data(self, data: str) -> None:
        if self._active_tag == "tupleList":
            self._consume_tuple_text(data)
        elif self._active_tag in {"lowerCorner", "upperCorner", "low", "high", "startPoint"}:
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
        if self.low is None:
            columns, rows = self.high[0] + 1, self.high[1] + 1
        else:
            columns = self.high[0] - self.low[0] + 1
            rows = self.high[1] - self.low[1] + 1
        expected = columns * rows
        if self.start_point is not None:
            if self.low is None:
                raise ValueError("startPoint に対応する low がありません")
            if self.sequence_order != "+x-y":
                raise ValueError(f"未対応の格子走査順です: {self.sequence_order}")
            start_column = self.start_point[0] - self.low[0]
            start_row = self.start_point[1] - self.low[1]
            if not 0 <= start_column < columns or not 0 <= start_row < rows:
                raise ValueError(f"startPoint が格子範囲外です: {self.start_point}")
            leading_missing = start_row * columns + start_column
            trailing_missing = expected - leading_missing - len(self._values)
            if trailing_missing < 0:
                raise ValueError(
                    f"格子数が不正です: expected={expected}, start={leading_missing}, "
                    f"actual={len(self._values)}"
                )
            self._values[:0] = [NODATA_OUTPUT] * leading_missing
            self._values.extend([NODATA_OUTPUT] * trailing_missing)
        elif len(self._values) != expected:
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


def _archive_members(
    archives: Sequence[tuple[Path, zipfile.ZipFile]],
) -> dict[str, list[tuple[Path, str]]]:
    members: dict[str, list[tuple[Path, str]]] = defaultdict(list)
    for source, outer in archives:
        for name in outer.namelist():
            match = DEM10B_ARCHIVE_PATTERN.search(name)
            if match:
                members[match.group(1)].append((source, name))
    return members


def _read_unique_inner_archive(
    mesh_code: str,
    members: Sequence[tuple[Path, str]],
    archives: dict[Path, zipfile.ZipFile],
) -> tuple[str, bytes]:
    selected_name: str | None = None
    selected_payload: bytes | None = None
    for source, inner_name in members:
        payload = archives[source].read(inner_name)
        if selected_payload is None:
            selected_name = inner_name
            selected_payload = payload
        elif payload != selected_payload:
            locations = ", ".join(f"{path.name}:{name}" for path, name in members)
            raise ValueError(f"同じメッシュ番号に異なる DEM10B があります: {mesh_code} ({locations})")
    if selected_name is None or selected_payload is None:
        raise ValueError(f"DEM10B が見つかりません: {mesh_code}")
    return selected_name, selected_payload


def _convert_to_staging(
    sources: Sequence[Path], destination: Path, limit: int | None = None
) -> dict[str, object]:
    tiles_dir = destination / "tiles"
    tiles_dir.mkdir(parents=True, exist_ok=True)
    converted: list[dict[str, object]] = []

    unique_sources = sorted(set(sources), key=lambda path: path.as_posix())
    with ExitStack() as stack:
        archives = {source: stack.enter_context(zipfile.ZipFile(source)) for source in unique_sources}
        members_by_mesh = _archive_members(list(archives.items()))
        if not members_by_mesh:
            raise ValueError("入力 ZIP に DEM10B がありません")
        mesh_codes = sorted(members_by_mesh)
        if limit is not None:
            mesh_codes = mesh_codes[:limit]
        for mesh_code in mesh_codes:
            inner_name, inner_payload = _read_unique_inner_archive(
                mesh_code, members_by_mesh[mesh_code], archives
            )
            with zipfile.ZipFile(io.BytesIO(inner_payload)) as inner:
                gml_names = [
                    name
                    for name in inner.namelist()
                    if name.endswith(".xml") and "-dem10b-" in name.lower()
                ]
                if len(gml_names) != 1:
                    raise ValueError(f"DEM GML を一意に特定できません: {inner_name}")
                with inner.open(gml_names[0]) as gml:
                    try:
                        metadata, payload = parse_gml(gml)
                    except (ValueError, xml.parsers.expat.ExpatError) as error:
                        raise ValueError(
                            f"DEM GML の変換に失敗しました: mesh={mesh_code}, "
                            f"source={inner_name}: {error}"
                        ) from error

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


def convert_archives(
    sources: Sequence[Path], destination: Path, limit: int | None = None
) -> dict[str, object]:
    if not sources:
        raise ValueError("入力 ZIP を1つ以上指定してください")
    if destination.exists():
        raise FileExistsError(f"出力先が既に存在します: {destination}")
    destination.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=f".{destination.name}.", dir=destination.parent) as temporary:
        staging = Path(temporary) / "dataset"
        index = _convert_to_staging(sources, staging, limit)
        staging.replace(destination)
    return index


def convert_archive(source: Path, destination: Path, limit: int | None = None) -> dict[str, object]:
    return convert_archives([source], destination, limit)


def main() -> None:
    argument_parser = argparse.ArgumentParser(description=__doc__)
    argument_parser.add_argument("sources", nargs="+", type=Path, help="国土地理院から取得した外側 ZIP")
    argument_parser.add_argument("--output", type=Path, required=True, help="変換済みタイルの出力先")
    argument_parser.add_argument("--limit", type=int, help="変換するメッシュ数（動作確認用）")
    args = argument_parser.parse_args()

    if args.limit is not None and args.limit < 1:
        argument_parser.error("--limit は 1 以上にしてください")
    index = convert_archives(args.sources, args.output, args.limit)
    print(f"{len(index['tiles'])} メッシュを {args.output} に変換しました。")


if __name__ == "__main__":
    main()
