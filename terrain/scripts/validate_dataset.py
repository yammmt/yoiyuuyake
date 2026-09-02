#!/usr/bin/env python3
"""Validate a converted DEM dataset and report reproducible coverage statistics."""

from __future__ import annotations

import argparse
import json
import math
import sys
from array import array
from pathlib import Path
from typing import Any


class DatasetValidationError(ValueError):
    """Raised when a converted DEM dataset violates its format contract."""


def _require_number(value: object, field: str) -> float:
    if (
        not isinstance(value, (int, float))
        or isinstance(value, bool)
        or not math.isfinite(value)
    ):
        raise DatasetValidationError(f"{field} が数値ではありません")
    return float(value)


def _require_positive_int(value: object, field: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value < 1:
        raise DatasetValidationError(f"{field} は1以上の整数である必要があります")
    return value


def _missing_value_count(path: Path, value_count: int, missing_value: int) -> int:
    values = array("h")
    with path.open("rb") as stream:
        values.fromfile(stream, value_count)
    if sys.byteorder != "little":
        values.byteswap()
    return values.count(missing_value)


def validate_dataset(
    root: Path,
    *,
    scan_missing: bool = True,
    expected_tiles: int | None = None,
) -> dict[str, Any]:
    try:
        index = json.loads((root / "index.json").read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise DatasetValidationError(f"index.json を読み込めません: {error}") from error

    if not isinstance(index, dict):
        raise DatasetValidationError("index.json のルートがオブジェクトではありません")
    if index.get("format_version") != 1:
        raise DatasetValidationError("未対応の format_version です")
    missing_value = index.get("missing_value")
    if not isinstance(missing_value, int) or not -32768 <= missing_value <= 32767:
        raise DatasetValidationError("missing_value が int16 の範囲外です")
    tiles = index.get("tiles")
    if not isinstance(tiles, list) or not tiles:
        raise DatasetValidationError("tiles が空または配列ではありません")
    if expected_tiles is not None and len(tiles) != expected_tiles:
        raise DatasetValidationError(
            f"タイル数が一致しません: expected={expected_tiles}, actual={len(tiles)}"
        )

    codes: list[str] = []
    expected_files: set[str] = set()
    normalized_tiles: list[tuple[Path, int, dict[str, float]]] = []
    for position, tile in enumerate(tiles):
        if not isinstance(tile, dict):
            raise DatasetValidationError(f"tiles[{position}] がオブジェクトではありません")
        mesh_code = tile.get("mesh_code")
        if not isinstance(mesh_code, str) or len(mesh_code) != 6 or not mesh_code.isdigit():
            raise DatasetValidationError(f"tiles[{position}].mesh_code が不正です")
        relative_file = tile.get("file")
        expected_file = f"tiles/{mesh_code}.dem"
        if relative_file != expected_file:
            raise DatasetValidationError(
                f"{mesh_code} のファイルパスがフラット形式ではありません: {relative_file}"
            )
        rows = _require_positive_int(tile.get("rows"), f"{mesh_code}.rows")
        columns = _require_positive_int(tile.get("columns"), f"{mesh_code}.columns")
        bounds = {
            name: _require_number(tile.get(name), f"{mesh_code}.{name}")
            for name in ("south", "north", "west", "east")
        }
        if bounds["south"] >= bounds["north"] or bounds["west"] >= bounds["east"]:
            raise DatasetValidationError(f"{mesh_code} の地理範囲が不正です")
        codes.append(mesh_code)
        expected_files.add(expected_file)
        normalized_tiles.append((root / expected_file, rows * columns, bounds))

    if len(codes) != len(set(codes)):
        raise DatasetValidationError("index.json に重複したメッシュ番号があります")
    if codes != sorted(codes):
        raise DatasetValidationError("index.json のメッシュ番号が昇順ではありません")

    tiles_directory = root / "tiles"
    try:
        actual_files = {
            path.relative_to(root).as_posix()
            for path in tiles_directory.iterdir()
            if path.is_file() and path.suffix == ".dem"
        }
    except OSError as error:
        raise DatasetValidationError(f"tiles ディレクトリを読み込めません: {error}") from error
    missing_files = expected_files - actual_files
    unindexed_files = actual_files - expected_files
    if missing_files or unindexed_files:
        raise DatasetValidationError(
            f"indexとタイルが一致しません: missing={len(missing_files)}, "
            f"unindexed={len(unindexed_files)}"
        )

    total_cells = 0
    total_bytes = 0
    missing_cells = 0
    for path, value_count, _bounds in normalized_tiles:
        expected_size = value_count * 2
        try:
            actual_size = path.stat().st_size
        except OSError as error:
            raise DatasetValidationError(f"{path.name} を読み込めません: {error}") from error
        if actual_size != expected_size:
            raise DatasetValidationError(
                f"{path.name} のサイズが不正です: expected={expected_size}, actual={actual_size}"
            )
        total_cells += value_count
        total_bytes += actual_size
        if scan_missing:
            missing_cells += _missing_value_count(path, value_count, missing_value)

    all_bounds = [bounds for _path, _value_count, bounds in normalized_tiles]
    result: dict[str, Any] = {
        "format_version": index["format_version"],
        "tile_count": len(normalized_tiles),
        "total_cells": total_cells,
        "total_tile_bytes": total_bytes,
        "bounds": {
            "south": min(bounds["south"] for bounds in all_bounds),
            "north": max(bounds["north"] for bounds in all_bounds),
            "west": min(bounds["west"] for bounds in all_bounds),
            "east": max(bounds["east"] for bounds in all_bounds),
        },
    }
    if scan_missing:
        result["missing_cells"] = missing_cells
        result["missing_ratio"] = missing_cells / total_cells
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data", required=True, type=Path, help="変換済みDEMのディレクトリ")
    parser.add_argument("--expected-tiles", type=int, help="期待するタイル数")
    parser.add_argument(
        "--skip-missing-scan",
        action="store_true",
        help="標高欠損セルの全数走査を省略する",
    )
    args = parser.parse_args()
    try:
        result = validate_dataset(
            args.data,
            scan_missing=not args.skip_missing_scan,
            expected_tiles=args.expected_tiles,
        )
    except DatasetValidationError as error:
        parser.exit(1, f"ERROR: {error}\n")
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
