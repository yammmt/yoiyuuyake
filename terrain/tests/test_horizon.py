from __future__ import annotations

import math
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1] / "scripts"))
from dem_store import ElevationSample  # noqa: E402
from horizon import calculate_horizon, destination_point  # noqa: E402


class FlatTerrain:
    def elevation_at(self, latitude: float, longitude: float) -> ElevationSample:
        return ElevationSample(100.0, "test", 0, 0)


class EasternRidge:
    def elevation_at(self, latitude: float, longitude: float) -> ElevationSample:
        elevation = 200.0 if longitude > 0.006 else 100.0
        return ElevationSample(elevation, "test", 0, 0)


class HorizonTests(unittest.TestCase):
    def test_destination_point_moves_east(self) -> None:
        latitude, longitude = destination_point(0, 0, 90, 1_000)

        self.assertAlmostEqual(latitude, 0, places=5)
        self.assertAlmostEqual(longitude, 0.00899, places=4)

    def test_flat_terrain_has_a_low_horizon(self) -> None:
        profile = calculate_horizon(
            FlatTerrain(), 0, 0, 270, ray_count=1, max_distance_meters=200, sample_interval_meters=100
        )

        self.assertAlmostEqual(profile.maximum_ray.maximum_elevation_angle_degrees, -0.4584, places=3)
        self.assertEqual(profile.maximum_ray.obstruction_distance_meters, 200)

    def test_ridge_is_reported_at_its_highest_angle(self) -> None:
        profile = calculate_horizon(
            EasternRidge(), 0, 0, 90, ray_count=1, max_distance_meters=1_000, sample_interval_meters=100
        )

        self.assertAlmostEqual(profile.maximum_ray.maximum_elevation_angle_degrees, math.degrees(math.atan2(98.4, 700)), places=3)
        self.assertEqual(profile.maximum_ray.obstruction_distance_meters, 700)
