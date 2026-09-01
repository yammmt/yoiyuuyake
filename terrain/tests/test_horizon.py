from __future__ import annotations

import math
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1] / "scripts"))
from dem_store import (  # noqa: E402
    DemNoElevationError,
    DemOutOfCoverageError,
    DemSampleRole,
    ElevationSample,
)
from horizon import calculate_horizon, destination_point  # noqa: E402


class FlatTerrain:
    def elevation_at(self, latitude: float, longitude: float) -> ElevationSample:
        return ElevationSample(100.0, "test", 0, 0)


class EasternRidge:
    def elevation_at(self, latitude: float, longitude: float) -> ElevationSample:
        elevation = 200.0 if longitude > 0.006 else 100.0
        return ElevationSample(elevation, "test", 0, 0)


class ObserverMissing:
    def elevation_at(self, latitude: float, longitude: float) -> ElevationSample:
        raise DemNoElevationError("指定地点の標高データがありません")


class CoastalMissingRay:
    def elevation_at(self, latitude: float, longitude: float) -> ElevationSample:
        if latitude == 0 and longitude == 0:
            return ElevationSample(5.0, "coast", 0, 0)
        raise DemNoElevationError("レイ上の標高データがありません")


class CoverageBoundary:
    def elevation_at(self, latitude: float, longitude: float) -> ElevationSample:
        if latitude == 0 and longitude == 0:
            return ElevationSample(100.0, "edge", 0, 0)
        raise DemOutOfCoverageError("準備済みの DEM 範囲外です")


class HorizonTests(unittest.TestCase):
    def test_destination_point_moves_east(self) -> None:
        latitude, longitude = destination_point(0, 0, 90, 1_000)

        self.assertAlmostEqual(latitude, 0, places=5)
        self.assertAlmostEqual(longitude, 0.00899, places=4)

    def test_flat_terrain_has_a_low_horizon(self) -> None:
        profile = calculate_horizon(
            FlatTerrain(),
            0,
            0,
            270,
            ray_count=1,
            max_distance_meters=200,
            sample_interval_meters=100,
        )

        self.assertAlmostEqual(profile.maximum_ray.maximum_elevation_angle_degrees, -0.4584, places=3)
        self.assertEqual(profile.maximum_ray.obstruction_distance_meters, 200)

    def test_ridge_is_reported_at_its_highest_angle(self) -> None:
        profile = calculate_horizon(
            EasternRidge(),
            0,
            0,
            90,
            ray_count=1,
            max_distance_meters=1_000,
            sample_interval_meters=100,
        )

        self.assertAlmostEqual(
            profile.maximum_ray.maximum_elevation_angle_degrees,
            math.degrees(math.atan2(98.4, 700)),
            places=3,
        )
        self.assertEqual(profile.maximum_ray.obstruction_distance_meters, 700)

    def test_observer_missing_is_identified_and_stops_calculation(self) -> None:
        with self.assertRaises(DemNoElevationError) as caught:
            calculate_horizon(
                ObserverMissing(),
                0,
                0,
                270,
                ray_count=1,
                max_distance_meters=100,
                sample_interval_meters=100,
            )

        context = caught.exception.sample_context
        self.assertIsNotNone(context)
        self.assertEqual(context.role, DemSampleRole.OBSERVER)
        self.assertEqual((context.latitude, context.longitude), (0, 0))
        self.assertIsNone(context.distance_meters)

    def test_coastal_missing_cell_is_identified_and_never_returns_a_profile(self) -> None:
        with self.assertRaises(DemNoElevationError) as caught:
            calculate_horizon(
                CoastalMissingRay(),
                0,
                0,
                270,
                ray_count=1,
                max_distance_meters=100,
                sample_interval_meters=100,
            )

        context = caught.exception.sample_context
        self.assertIsNotNone(context)
        self.assertEqual(context.role, DemSampleRole.RAY)
        self.assertEqual(context.azimuth_degrees, 270)
        self.assertEqual(context.distance_meters, 100)

    def test_coverage_boundary_is_identified_and_never_returns_a_profile(self) -> None:
        with self.assertRaises(DemOutOfCoverageError) as caught:
            calculate_horizon(
                CoverageBoundary(),
                0,
                0,
                90,
                ray_count=1,
                max_distance_meters=200,
                sample_interval_meters=100,
            )

        context = caught.exception.sample_context
        self.assertIsNotNone(context)
        self.assertEqual(context.role, DemSampleRole.RAY)
        self.assertEqual(context.azimuth_degrees, 90)
        self.assertEqual(context.distance_meters, 100)
