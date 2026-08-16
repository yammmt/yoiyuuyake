#!/usr/bin/env python3
"""Run fixed-point terrain-horizon regression checks against local DEM tiles."""
from __future__ import annotations
import argparse, json
from pathlib import Path
from dem_store import DemDataUnavailableError, DemNoElevationError, LocalDemStore
from horizon import calculate_horizon
from visibility import assess_visibility

def main() -> None:
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--data", required=True, type=Path)
    p.add_argument("--cases", type=Path, default=Path("terrain/validation/locations.json"))
    args=p.parse_args(); cases=json.loads(args.cases.read_text(encoding="utf-8"))["locations"]
    store=LocalDemStore(args.data); failures=[]
    try:
        for case in cases:
            try:
                profile=calculate_horizon(store, case["latitude"], case["longitude"], case["azimuth"])
                assessment=assess_visibility(profile, 1)
                if "expected_error" in case:
                    failures.append(f"{case['id']}: expected {case['expected_error']}, got result")
                elif assessment.label != case["expected_label"] or abs(assessment.maximum_horizon_angle_degrees-case["expected_angle"]) > case["tolerance"]:
                    failures.append(f"{case['id']}: got {assessment.label} {assessment.maximum_horizon_angle_degrees:.3f}°")
                else: print(f"PASS {case['id']}: {assessment.label} {assessment.maximum_horizon_angle_degrees:.3f}°")
            except (DemDataUnavailableError, DemNoElevationError) as error:
                if type(error).__name__ == case.get("expected_error"):
                    print(f"PASS {case['id']}: {type(error).__name__}")
                else: failures.append(f"{case['id']}: {type(error).__name__}: {error}")
    finally: store.close()
    if failures:
        print("\n".join(failures)); raise SystemExit(1)
if __name__ == "__main__": main()
