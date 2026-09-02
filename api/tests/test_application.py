from __future__ import annotations

import json
import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import Mock, patch

from api.application import (
    TERRAIN_NOTICE,
    ApiError,
    ApiErrorCode,
    ApiErrorReason,
    evaluate_location,
)
from terrain.scripts.dem_store import (
    DemDataUnavailableError,
    DemNoElevationError,
    DemOutOfCoverageError,
    DemSampleContext,
    DemSampleRole,
)
from terrain.scripts.horizon import HorizonProfile, RayHorizon
from weather.scripts.evaluation import (
    SunsetWeatherEvaluation,
    WeatherEvaluationError,
    WeatherEvaluationErrorCode,
)
from weather.scripts.scoring import ScoreBreakdown


def score(value: int, positive: str, negative: str) -> ScoreBreakdown:
    return ScoreBreakdown(value, (), (positive,), (negative,))


class IntegratedApplicationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.store = Mock()
        self.profile = HorizonProfile(
            observer_elevation_meters=12.0,
            center_azimuth_degrees=270.0,
            rays=(RayHorizon(271.5, 0.8, 2_000, 30.0),),
        )

    def weather(self, latitude, longitude, sunset):
        return SunsetWeatherEvaluation(
            latitude=latitude,
            longitude=longitude,
            sunset=sunset,
            starts_at=sunset - timedelta(minutes=20),
            ends_at=sunset + timedelta(minutes=25),
            gradient=score(77, "視程が良い", "低層雲が多い"),
            dramatic=score(94, "中層雲が適量", "降水がある"),
        )

    def evaluate(self, **changes):
        options = {
            "dem_root": Path("unused"),
            "weather_evaluator": self.weather,
            "horizon_calculator": lambda *_args: self.profile,
        }
        options.update(changes)
        with patch("api.application.LocalDemStore", return_value=self.store):
            return evaluate_location(35.6812, 139.7671, **options)

    def test_returns_one_complete_site_friendly_result(self) -> None:
        result = self.evaluate()

        self.assertEqual(
            result["location"], {"latitude": 35.6812, "longitude": 139.7671}
        )
        self.assertEqual(result["weather"]["gradient"]["score"], 77)
        self.assertEqual(result["weather"]["dramatic"]["score"], 94)
        self.assertEqual(result["terrain"]["visibility"], "広い")
        self.assertEqual(result["terrain"]["observer_elevation_meters"], 12.0)
        self.assertFalse(result["terrain"]["sun_likely_occluded"])
        self.assertEqual(result["notice"], TERRAIN_NOTICE)
        self.assertEqual(
            datetime.fromisoformat(result["sunset"]["viewing_window"]["starts_at"]),
            datetime.fromisoformat(result["sunset"]["time"])
            - timedelta(minutes=20),
        )
        self.store.close.assert_called_once_with()

    def test_invalid_coordinates_stop_before_any_evaluation(self) -> None:
        weather = Mock()
        with patch("api.application.LocalDemStore") as store_class:
            with self.assertRaises(ApiError) as caught:
                evaluate_location(
                    0,
                    139.7671,
                    dem_root=Path("unused"),
                    weather_evaluator=weather,
                )

        self.assertEqual(caught.exception.code, ApiErrorCode.INVALID_INPUT)
        store_class.assert_not_called()
        weather.assert_not_called()

    def test_dem_failure_returns_no_weather_result(self) -> None:
        weather = Mock()

        def fail_dem(*_args):
            raise DemDataUnavailableError("範囲外")

        with self.assertRaises(ApiError) as caught:
            self.evaluate(weather_evaluator=weather, horizon_calculator=fail_dem)

        self.assertEqual(caught.exception.code, ApiErrorCode.DEM_UNAVAILABLE)
        self.assertEqual(
            caught.exception.reason, ApiErrorReason.DEM_DATA_UNAVAILABLE
        )
        self.assertIsInstance(caught.exception.__cause__, DemDataUnavailableError)
        weather.assert_not_called()
        self.store.close.assert_called_once_with()

    def test_unreadable_dem_is_an_explicit_error(self) -> None:
        with patch(
            "api.application.LocalDemStore", side_effect=OSError("index missing")
        ):
            with self.assertRaises(ApiError) as caught:
                evaluate_location(35.6812, 139.7671, dem_root=Path("missing"))

        self.assertEqual(caught.exception.code, ApiErrorCode.DEM_UNAVAILABLE)
        self.assertEqual(
            caught.exception.reason, ApiErrorReason.DEM_DATA_UNAVAILABLE
        )
        self.assertIn("再試行", str(caught.exception))

    def test_corrupt_tile_index_during_lookup_is_dem_data_unavailable(self) -> None:
        complete_tile = {
            "mesh_code": "demo",
            "file": "tiles/demo.dem",
            "south": 35.0,
            "west": 139.0,
            "north": 36.0,
            "east": 140.0,
            "rows": 1,
            "columns": 1,
        }
        for missing_key in ("south", "rows"):
            with self.subTest(missing_key=missing_key):
                with tempfile.TemporaryDirectory() as temporary_directory:
                    root = Path(temporary_directory)
                    tile = {**complete_tile}
                    del tile[missing_key]
                    (root / "index.json").write_text(
                        json.dumps(
                            {
                                "format_version": 1,
                                "missing_value": -32768,
                                "tiles": [tile],
                            }
                        ),
                        encoding="utf-8",
                    )

                    with self.assertRaises(ApiError) as caught:
                        evaluate_location(
                            35.6812,
                            139.7671,
                            dem_root=root,
                            weather_evaluator=Mock(),
                        )

                self.assertEqual(caught.exception.code, ApiErrorCode.DEM_UNAVAILABLE)
                self.assertEqual(
                    caught.exception.reason, ApiErrorReason.DEM_DATA_UNAVAILABLE
                )
                self.assertIsInstance(caught.exception.__cause__, KeyError)

    def test_dem_sampling_failures_have_stable_reasons_and_guidance(self) -> None:
        cases = (
            (
                DemNoElevationError,
                DemSampleRole.OBSERVER,
                ApiErrorReason.OBSERVER_NO_ELEVATION,
                "少し離れた地点",
            ),
            (
                DemOutOfCoverageError,
                DemSampleRole.OBSERVER,
                ApiErrorReason.OBSERVER_OUT_OF_COVERAGE,
                "別の地点",
            ),
            (
                DemNoElevationError,
                DemSampleRole.RAY,
                ApiErrorReason.RAY_NO_ELEVATION,
                "別の地点",
            ),
            (
                DemOutOfCoverageError,
                DemSampleRole.RAY,
                ApiErrorReason.RAY_OUT_OF_COVERAGE,
                "別の地点",
            ),
        )
        for error_class, role, expected_reason, guidance in cases:
            with self.subTest(reason=expected_reason):
                dem_error = error_class("DEM failure")
                dem_error.sample_context = DemSampleContext(role, 35.0, 139.0)

                with self.assertRaises(ApiError) as caught:
                    self.evaluate(
                        horizon_calculator=Mock(side_effect=dem_error)
                    )

                self.assertEqual(caught.exception.code, ApiErrorCode.DEM_UNAVAILABLE)
                self.assertEqual(caught.exception.reason, expected_reason)
                self.assertIn(guidance, str(caught.exception))
                self.assertIs(caught.exception.__cause__, dem_error)

    def test_weather_failure_never_returns_a_partial_result(self) -> None:
        weather_error = WeatherEvaluationError(
            WeatherEvaluationErrorCode.FORECAST_FETCH_FAILED, "offline"
        )

        with self.assertRaises(ApiError) as caught:
            self.evaluate(weather_evaluator=Mock(side_effect=weather_error))

        self.assertEqual(caught.exception.code, ApiErrorCode.WEATHER_UNAVAILABLE)
        self.assertIs(caught.exception.__cause__, weather_error)

    def test_unexpected_terrain_failure_is_retryable_without_partial_result(self) -> None:
        weather = Mock()

        with self.assertRaises(ApiError) as caught:
            self.evaluate(
                weather_evaluator=weather,
                horizon_calculator=Mock(side_effect=ValueError("invalid profile")),
            )

        self.assertEqual(caught.exception.code, ApiErrorCode.DEM_UNAVAILABLE)
        self.assertEqual(
            caught.exception.reason, ApiErrorReason.TERRAIN_CALCULATION_FAILED
        )
        self.assertIn("再試行", str(caught.exception))
        weather.assert_not_called()


if __name__ == "__main__":
    unittest.main()
