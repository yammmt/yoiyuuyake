import sys
import unittest
from dataclasses import replace
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

sys.path.insert(0, str(Path(__file__).parents[2]))

from weather.scripts.open_meteo import WeatherHour  # noqa: E402
from weather.scripts.scoring import (  # noqa: E402
    WeatherScoringError,
    normalize_weather,
    score_weather,
)

JST = ZoneInfo("Asia/Tokyo")


def weather_hour(**changes) -> WeatherHour:
    hour = WeatherHour(
        time=datetime(2026, 8, 16, 18, tzinfo=JST),
        cloud_cover_low=10,
        cloud_cover_mid=40,
        cloud_cover_high=50,
        cloud_cover=50,
        visibility=25_000,
        relative_humidity=50,
        precipitation=0,
        wind_speed=3,
    )
    return replace(hour, **changes)


class WeatherNormalizationTests(unittest.TestCase):
    def test_normalizes_documented_boundaries(self):
        normalized = normalize_weather(
            (
                weather_hour(
                    cloud_cover_low=0,
                    cloud_cover_mid=0,
                    cloud_cover_high=100,
                    cloud_cover=100,
                    visibility=5_000,
                    relative_humidity=40,
                    precipitation=1,
                    wind_speed=15,
                ),
            )
        )

        self.assertEqual(normalized.low_cloud_clear, 1)
        self.assertEqual(normalized.mid_cloud, 0)
        self.assertEqual(normalized.high_cloud, 1)
        self.assertEqual(normalized.total_cloud_clear, 0)
        self.assertEqual(normalized.visibility, 0)
        self.assertEqual(normalized.dry_air, 1)
        self.assertEqual(normalized.precipitation_free, 0)
        self.assertEqual(normalized.calm_wind, 0)

    def test_averages_each_variable_across_the_window(self):
        normalized = normalize_weather(
            (
                weather_hour(cloud_cover_low=0, visibility=5_000),
                weather_hour(cloud_cover_low=100, visibility=25_000),
            )
        )

        self.assertEqual(normalized.low_cloud_clear, 0.5)
        self.assertEqual(normalized.visibility, 0.5)

    def test_clamps_values_outside_normalization_thresholds(self):
        normalized = normalize_weather(
            (
                weather_hour(
                    visibility=40_000,
                    relative_humidity=100,
                    precipitation=5,
                    wind_speed=30,
                ),
            )
        )

        self.assertEqual(normalized.visibility, 1)
        self.assertEqual(normalized.dry_air, 0)
        self.assertEqual(normalized.precipitation_free, 0)
        self.assertEqual(normalized.calm_wind, 0)

    def test_rejects_empty_or_invalid_inputs(self):
        with self.assertRaisesRegex(WeatherScoringError, "ありません"):
            normalize_weather(())

        invalid_cases = (
            ("cloud_cover_low", 101),
            ("relative_humidity", True),
            ("visibility", float("nan")),
            ("precipitation", -0.1),
        )
        for name, value in invalid_cases:
            with self.subTest(name=name, value=value):
                with self.assertRaisesRegex(WeatherScoringError, name):
                    normalize_weather((weather_hour(**{name: value}),))


class WeatherScoringTests(unittest.TestCase):
    def test_clear_weather_favors_gradient_over_dramatic(self):
        scores = score_weather(
            (
                weather_hour(
                    cloud_cover_low=0,
                    cloud_cover_mid=0,
                    cloud_cover_high=0,
                    cloud_cover=0,
                    visibility=25_000,
                    relative_humidity=40,
                    precipitation=0,
                    wind_speed=5,
                ),
            )
        )

        self.assertEqual(scores.gradient.score, 100)
        self.assertEqual(scores.dramatic.score, 50)
        self.assertIn("中層雲が適量でない", scores.dramatic.negative_factors)
        self.assertIn("高層雲が適量でない", scores.dramatic.negative_factors)

    def test_moderate_mid_and_high_cloud_favors_dramatic(self):
        scores = score_weather((weather_hour(),))

        self.assertGreaterEqual(scores.dramatic.score, 90)
        self.assertGreater(scores.dramatic.score, scores.gradient.score)
        self.assertIn("中層雲が適量", scores.dramatic.positive_factors)
        self.assertIn("高層雲が適量", scores.dramatic.positive_factors)

    def test_thick_low_cloud_reduces_both_scores(self):
        scores = score_weather(
            (
                weather_hour(
                    cloud_cover_low=100,
                    cloud_cover_mid=100,
                    cloud_cover_high=100,
                    cloud_cover=100,
                ),
            )
        )

        self.assertLess(scores.gradient.score, 60)
        self.assertLess(scores.dramatic.score, 60)
        self.assertIn("低層雲が多い", scores.gradient.negative_factors)
        self.assertIn("低層雲が多い", scores.dramatic.negative_factors)

    def test_precipitation_removes_its_points_from_both_scores(self):
        dry = score_weather((weather_hour(precipitation=0),))
        rainy = score_weather((weather_hour(precipitation=1),))

        self.assertEqual(dry.gradient.score - rainy.gradient.score, 20)
        self.assertEqual(dry.dramatic.score - rainy.dramatic.score, 15)
        self.assertIn("降水がある", rainy.gradient.negative_factors)
        self.assertIn("降水がある", rainy.dramatic.negative_factors)

    def test_cloud_optimum_has_inclusive_plateau_and_zero_edges(self):
        cases = (
            (5, 0),
            (30, 20),
            (60, 20),
            (95, 0),
        )
        for mid_cloud, expected_points in cases:
            with self.subTest(mid_cloud=mid_cloud):
                result = score_weather((weather_hour(cloud_cover_mid=mid_cloud),))
                factor = next(
                    factor
                    for factor in result.dramatic.factors
                    if factor.key == "mid_cloud_optimal"
                )
                self.assertEqual(factor.points, expected_points)

    def test_scores_and_factor_points_stay_in_their_ranges(self):
        for hour in (
            weather_hour(
                cloud_cover_low=0,
                cloud_cover_mid=0,
                cloud_cover_high=0,
                cloud_cover=0,
                visibility=0,
                relative_humidity=0,
                precipitation=0,
                wind_speed=0,
            ),
            weather_hour(
                cloud_cover_low=100,
                cloud_cover_mid=100,
                cloud_cover_high=100,
                cloud_cover=100,
                visibility=100_000,
                relative_humidity=100,
                precipitation=100,
                wind_speed=100,
            ),
        ):
            with self.subTest(hour=hour):
                scores = score_weather((hour,))
                for breakdown in (scores.gradient, scores.dramatic):
                    self.assertGreaterEqual(breakdown.score, 0)
                    self.assertLessEqual(breakdown.score, 100)
                    for factor in breakdown.factors:
                        self.assertGreaterEqual(factor.points, 0)
                        self.assertLessEqual(factor.points, factor.max_points)


if __name__ == "__main__":
    unittest.main()
