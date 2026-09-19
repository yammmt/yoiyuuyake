#!/usr/bin/env python3
"""Copy whole DEM tiles intersecting a bounding box into a separate dataset."""

from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path
from tempfile import TemporaryDirectory

from validate_dataset import validate_dataset


def subset_dem(
    source: Path,
    output: Path,
    *,
    south: float,
    north: float,
    west: float,
    east: float,
) -> dict:
    if not (-90 <= south < north <= 90 and -180 <= west < east <= 180):
        raise ValueError("緯度・経度の範囲が不正です")
    if output.exists() or output.is_symlink():
        raise FileExistsError(f"出力先は既に存在します: {output}")
    validate_dataset(source, scan_missing=False)
    index = json.loads((source / "index.json").read_text(encoding="utf-8"))
    index["tiles"] = [
        tile for tile in index["tiles"]
        if tile["north"] >= south and tile["south"] <= north
        and tile["east"] >= west and tile["west"] <= east
    ]
    if not index["tiles"]:
        raise ValueError("指定範囲に重なるタイルがありません")

    output.parent.mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory(prefix=".dem-subset-", dir=output.parent) as temporary:
        staged = Path(temporary) / "dataset"
        (staged / "tiles").mkdir(parents=True)
        for tile in index["tiles"]:
            shutil.copyfile(source / tile["file"], staged / tile["file"])
        (staged / "index.json").write_text(
            json.dumps(index, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        result = validate_dataset(staged, scan_missing=False)
        if output.exists() or output.is_symlink():
            raise FileExistsError(f"出力先は既に存在します: {output}")
        staged.rename(output)
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    for name in ("south", "north", "west", "east"):
        parser.add_argument(f"--{name}", required=True, type=float)
    args = parser.parse_args()
    try:
        result = subset_dem(
            args.data, args.output,
            south=args.south, north=args.north, west=args.west, east=args.east,
        )
    except (OSError, ValueError) as error:
        parser.exit(1, f"ERROR: {error}\n")
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
