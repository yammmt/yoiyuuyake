"""Read local DEM tiles by geographic coordinate without loading whole datasets."""

from __future__ import annotations

import json
import math
import struct
from collections import OrderedDict
from dataclasses import dataclass
from pathlib import Path
from typing import BinaryIO


class DemDataUnavailableError(RuntimeError):
    """Raised when the requested coordinate is outside the prepared DEM coverage."""


class DemNoElevationError(RuntimeError):
    """Raised when the DEM tile has no elevation value at the requested coordinate."""


@dataclass(frozen=True)
class ElevationSample:
    elevation_meters: float
    mesh_code: str
    row: int
    column: int


class LocalDemStore:
    def __init__(self, root: Path) -> None:
        self.root = root
        self.index = json.loads((root / "index.json").read_text(encoding="utf-8"))
        if self.index.get("format_version") != 1:
            raise ValueError("未対応の DEM タイル形式です")
        self.missing_value = self.index["missing_value"]
        self.tiles = sorted(self.index["tiles"], key=lambda tile: tile["mesh_code"])
        self._open_files: OrderedDict[str, BinaryIO] = OrderedDict()

    def elevation_at(self, latitude: float, longitude: float) -> ElevationSample:
        tile = self._find_tile(latitude, longitude)
        row, column = self._grid_position(tile, latitude, longitude)
        offset = (row * tile["columns"] + column) * 2
        dem_file = self._file_for(tile["file"])
        dem_file.seek(offset)
        raw_value = dem_file.read(2)
        if len(raw_value) != 2:
            raise DemDataUnavailableError(f"DEM タイルが途中で切れています: {tile['mesh_code']}")
        value = struct.unpack("<h", raw_value)[0]
        if value == self.missing_value:
            raise DemNoElevationError("指定地点の標高データがありません")
        return ElevationSample(float(value), tile["mesh_code"], row, column)

    def close(self) -> None:
        for dem_file in self._open_files.values():
            dem_file.close()
        self._open_files.clear()

    def _file_for(self, relative_path: str) -> BinaryIO:
        cached = self._open_files.pop(relative_path, None)
        if cached is None:
            cached = (self.root / relative_path).open("rb")
        self._open_files[relative_path] = cached
        while len(self._open_files) > 24:
            _discarded_path, discarded_file = self._open_files.popitem(last=False)
            discarded_file.close()
        return cached

    def _find_tile(self, latitude: float, longitude: float) -> dict[str, object]:
        for tile in self.tiles:
            if tile["south"] <= latitude <= tile["north"] and tile["west"] <= longitude <= tile["east"]:
                return tile
        raise DemDataUnavailableError("指定地点は準備済みの DEM 範囲外です")

    @staticmethod
    def _grid_position(tile: dict[str, object], latitude: float, longitude: float) -> tuple[int, int]:
        latitude_step = (tile["north"] - tile["south"]) / tile["rows"]
        longitude_step = (tile["east"] - tile["west"]) / tile["columns"]
        row = math.floor((tile["north"] - latitude) / latitude_step)
        column = math.floor((longitude - tile["west"]) / longitude_step)
        return max(0, min(tile["rows"] - 1, row)), max(0, min(tile["columns"] - 1, column))
