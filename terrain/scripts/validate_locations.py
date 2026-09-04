#!/usr/bin/env python3
"""Run fixed-point terrain-horizon regression checks against local DEM tiles."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from dem_store import DemError, LocalDemStore
from horizon import calculate_horizon
from visibility import assess_visibility


def _validate_case(store: LocalDemStore, case: dict[str, Any]) -> tuple[bool, str]:
    case_id = case["id"]
    try:
        profile = calculate_horizon(
            store,
            case["latitude"],
            case["longitude"],
            case["azimuth"],
        )
        assessment = assess_visibility(profile, 1)
    except DemError as error:
        expected_error = case.get("expected_error")
        if type(error).__name__ != expected_error:
            return False, f"{case_id}: {type(error).__name__}: {error}"
        expected_role = case.get("expected_role")
        actual_role = error.sample_context.role.value if error.sample_context else None
        if expected_role is not None and actual_role != expected_role:
            return False, f"{case_id}: expected role {expected_role}, got {actual_role}"
        return True, f"{case_id}: {type(error).__name__} ({actual_role})"

    if "expected_error" in case:
        return False, f"{case_id}: expected {case['expected_error']}, got result"
    angle = assessment.maximum_horizon_angle_degrees
    if assessment.label != case["expected_label"] or abs(angle - case["expected_angle"]) > case["tolerance"]:
        return False, f"{case_id}: got {assessment.label} {angle:.3f}°"
    return True, f"{case_id}: {assessment.label} {angle:.3f}°"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data", required=True, type=Path)
    parser.add_argument(
        "--cases",
        type=Path,
        default=Path("terrain/validation/locations.json"),
    )
    args = parser.parse_args()
    cases = json.loads(args.cases.read_text(encoding="utf-8"))["locations"]
    store = LocalDemStore(args.data)
    failures = []
    try:
        for case in cases:
            passed, message = _validate_case(store, case)
            if passed:
                print(f"PASS {message}")
            else:
                failures.append(message)
    finally:
        store.close()
    if failures:
        print("\n".join(failures))
        raise SystemExit(1)


if __name__ == "__main__":
    main()
