#!/usr/bin/env python3
"""Calculate a local terrain-horizon profile and its MVP visibility label."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from dem_store import DemDataUnavailableError, DemNoElevationError, LocalDemStore
from horizon import calculate_horizon
from visibility import assess_visibility, ray_to_dict


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data", required=True, type=Path, help="変換済みDEMのディレクトリ")
    parser.add_argument("--latitude", required=True, type=float, help="緯度（度）")
    parser.add_argument("--longitude", required=True, type=float, help="経度（度）")
    parser.add_argument("--azimuth", required=True, type=float, help="日没方位（度）")
    parser.add_argument("--sun-altitude", type=float, default=0.0, help="比較する太陽高度（度）")
    parser.add_argument("--max-distance", type=int, default=50_000, help="レイの最大距離（m）")
    parser.add_argument("--sample-interval", type=int, default=50, help="レイの間隔（m）")
    parser.add_argument("--ray-count", type=int, default=9, help="レイの本数")
    args = parser.parse_args()

    store = LocalDemStore(args.data)
    try:
        profile = calculate_horizon(
            store,
            args.latitude,
            args.longitude,
            args.azimuth,
            ray_count=args.ray_count,
            max_distance_meters=args.max_distance,
            sample_interval_meters=args.sample_interval,
        )
        assessment = assess_visibility(profile, args.sun_altitude)
    except (DemDataUnavailableError, DemNoElevationError, ValueError) as error:
        print(str(error), file=sys.stderr)
        raise SystemExit(2) from error
    finally:
        store.close()

    print(json.dumps({
        "latitude": args.latitude,
        "longitude": args.longitude,
        "center_azimuth_degrees": profile.center_azimuth_degrees,
        "observer_elevation_meters": profile.observer_elevation_meters,
        "visibility": assessment.__dict__,
        "rays": [ray_to_dict(ray) for ray in profile.rays],
    }, ensure_ascii=False))


if __name__ == "__main__":
    main()
