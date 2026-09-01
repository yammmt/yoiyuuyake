"""Calculate terrain horizons from local DEM elevations."""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Protocol

try:
    from .dem_store import (
        DemError,
        DemSampleContext,
        DemSampleRole,
        ElevationSample,
    )
except ImportError:  # Direct execution from terrain/scripts.
    from dem_store import (
        DemError,
        DemSampleContext,
        DemSampleRole,
        ElevationSample,
    )

EARTH_RADIUS_METERS = 6_371_008.8


class ElevationReader(Protocol):
    def elevation_at(self, latitude: float, longitude: float) -> ElevationSample: ...


@dataclass(frozen=True)
class RayHorizon:
    azimuth_degrees: float
    maximum_elevation_angle_degrees: float
    obstruction_distance_meters: int
    obstruction_elevation_meters: float


@dataclass(frozen=True)
class HorizonProfile:
    observer_elevation_meters: float
    center_azimuth_degrees: float
    rays: tuple[RayHorizon, ...]

    @property
    def maximum_ray(self) -> RayHorizon:
        return max(self.rays, key=lambda ray: ray.maximum_elevation_angle_degrees)


def destination_point(
    latitude: float, longitude: float, azimuth_degrees: float, distance_meters: float
) -> tuple[float, float]:
    """Return a point reached by travelling along a great-circle bearing."""
    angular_distance = distance_meters / EARTH_RADIUS_METERS
    bearing = math.radians(azimuth_degrees)
    source_latitude = math.radians(latitude)
    source_longitude = math.radians(longitude)
    target_latitude = math.asin(
        math.sin(source_latitude) * math.cos(angular_distance)
        + math.cos(source_latitude) * math.sin(angular_distance) * math.cos(bearing)
    )
    target_longitude = source_longitude + math.atan2(
        math.sin(bearing) * math.sin(angular_distance) * math.cos(source_latitude),
        math.cos(angular_distance) - math.sin(source_latitude) * math.sin(target_latitude),
    )
    return math.degrees(target_latitude), ((math.degrees(target_longitude) + 540) % 360) - 180


def calculate_horizon(
    elevations: ElevationReader,
    latitude: float,
    longitude: float,
    center_azimuth_degrees: float,
    *,
    spread_degrees: float = 20,
    ray_count: int = 9,
    max_distance_meters: int = 50_000,
    sample_interval_meters: int = 50,
    observer_height_meters: float = 1.6,
) -> HorizonProfile:
    """Sample a fan of rays and return the highest terrain angle on each ray."""
    if ray_count < 1:
        raise ValueError("ray_count は 1 以上にしてください")
    if max_distance_meters < sample_interval_meters or sample_interval_meters <= 0:
        raise ValueError("距離とサンプリング間隔の指定が不正です")

    try:
        observer = elevations.elevation_at(latitude, longitude)
    except DemError as error:
        error.sample_context = DemSampleContext(
            role=DemSampleRole.OBSERVER,
            latitude=latitude,
            longitude=longitude,
        )
        raise
    azimuths = _ray_azimuths(center_azimuth_degrees, spread_degrees, ray_count)
    rays = tuple(
        _calculate_ray(
            elevations,
            latitude,
            longitude,
            observer.elevation_meters + observer_height_meters,
            azimuth,
            max_distance_meters,
            sample_interval_meters,
        )
        for azimuth in azimuths
    )
    return HorizonProfile(observer.elevation_meters, center_azimuth_degrees % 360, rays)


def _ray_azimuths(center_azimuth_degrees: float, spread_degrees: float, ray_count: int) -> tuple[float, ...]:
    if ray_count == 1:
        return (center_azimuth_degrees % 360,)
    step = 2 * spread_degrees / (ray_count - 1)
    return tuple((center_azimuth_degrees - spread_degrees + step * index) % 360 for index in range(ray_count))


def _calculate_ray(
    elevations: ElevationReader,
    latitude: float,
    longitude: float,
    observer_eye_elevation_meters: float,
    azimuth_degrees: float,
    max_distance_meters: int,
    sample_interval_meters: int,
) -> RayHorizon:
    maximum_angle = -math.inf
    maximum_distance = 0
    maximum_elevation = 0.0
    for distance in range(
        sample_interval_meters, max_distance_meters + 1, sample_interval_meters
    ):
        sample_latitude, sample_longitude = destination_point(
            latitude, longitude, azimuth_degrees, distance
        )
        try:
            sample = elevations.elevation_at(sample_latitude, sample_longitude)
        except DemError as error:
            error.sample_context = DemSampleContext(
                role=DemSampleRole.RAY,
                latitude=sample_latitude,
                longitude=sample_longitude,
                azimuth_degrees=azimuth_degrees,
                distance_meters=distance,
            )
            raise
        angle = math.degrees(
            math.atan2(
                sample.elevation_meters - observer_eye_elevation_meters, distance
            )
        )
        if angle > maximum_angle:
            maximum_angle = angle
            maximum_distance = distance
            maximum_elevation = sample.elevation_meters
    return RayHorizon(azimuth_degrees, maximum_angle, maximum_distance, maximum_elevation)
