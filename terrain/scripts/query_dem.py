#!/usr/bin/env python3
"""Print the local DEM elevation at one latitude/longitude coordinate."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from dem_store import DemDataUnavailableError, DemNoElevationError, LocalDemStore


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data", required=True, type=Path, help="変換済みDEMのディレクトリ")
    parser.add_argument("--latitude", required=True, type=float, help="緯度（度）")
    parser.add_argument("--longitude", required=True, type=float, help="経度（度）")
    args = parser.parse_args()

    try:
        sample = LocalDemStore(args.data).elevation_at(args.latitude, args.longitude)
    except (DemDataUnavailableError, DemNoElevationError, FileNotFoundError, ValueError) as error:
        print(str(error), file=sys.stderr)
        raise SystemExit(2) from error

    print(json.dumps({
        "latitude": args.latitude,
        "longitude": args.longitude,
        "elevation_meters": sample.elevation_meters,
        "mesh_code": sample.mesh_code,
        "row": sample.row,
        "column": sample.column,
    }, ensure_ascii=False))


if __name__ == "__main__":
    main()
