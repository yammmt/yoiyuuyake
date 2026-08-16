"""Turn terrain-horizon measurements into the MVP's three visibility labels."""

from __future__ import annotations

from dataclasses import dataclass

from horizon import HorizonProfile, RayHorizon

WIDE_HORIZON_DEGREES = 1.0
PARTIALLY_BLOCKED_HORIZON_DEGREES = 4.0


@dataclass(frozen=True)
class VisibilityAssessment:
    label: str
    description: str
    maximum_horizon_angle_degrees: float
    obstructing_azimuth_degrees: float
    obstructing_distance_meters: int
    sun_altitude_degrees: float
    sun_likely_occluded: bool


def assess_visibility(profile: HorizonProfile, sun_altitude_degrees: float) -> VisibilityAssessment:
    """Classify terrain openness and report whether terrain is above the sun."""
    ray = profile.maximum_ray
    angle = ray.maximum_elevation_angle_degrees
    sun_likely_occluded = angle >= sun_altitude_degrees
    if angle <= WIDE_HORIZON_DEGREES:
        label = "広い"
        description = "日没方向の地形による遮蔽は小さい見込みです。"
    elif angle <= PARTIALLY_BLOCKED_HORIZON_DEGREES:
        label = "一部遮られる"
        description = "日没直前の太陽は、地形により早く隠れる可能性があります。"
    else:
        label = "遮られやすい"
        description = "山・丘・尾根により、日没方向の低空が大きく隠れやすい見込みです。"
    return VisibilityAssessment(
        label=label,
        description=description,
        maximum_horizon_angle_degrees=angle,
        obstructing_azimuth_degrees=ray.azimuth_degrees,
        obstructing_distance_meters=ray.obstruction_distance_meters,
        sun_altitude_degrees=sun_altitude_degrees,
        sun_likely_occluded=sun_likely_occluded,
    )


def ray_to_dict(ray: RayHorizon) -> dict[str, float | int]:
    return {
        "azimuth_degrees": ray.azimuth_degrees,
        "maximum_elevation_angle_degrees": ray.maximum_elevation_angle_degrees,
        "obstruction_distance_meters": ray.obstruction_distance_meters,
        "obstruction_elevation_meters": ray.obstruction_elevation_meters,
    }
