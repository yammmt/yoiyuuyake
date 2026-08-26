import io
import json
import sys
import unittest
from copy import deepcopy
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import patch
from zoneinfo import ZoneInfo

sys.path.insert(0, str(Path(__file__).parents[2]))

from weather.scripts.evaluation import (  # noqa: E402
    SunsetWeatherEvaluation,
    WeatherEvaluationError,
    WeatherEvaluationErrorCode,
    evaluate_sunset_weather,
)
from weather.scripts.open_meteo import OpenMeteoError  # noqa: E402
from weather.scripts.scoring import WeatherScoringError  # noqa: E402
from weather.scripts.sunset_window import SunsetWindowError  # noqa: E402

FIXTURE_PATH = Path(__file__).parent / "fixtures" / "open_meteo_forecast.json"
JST = ZoneInfo("Asia/Tokyo")


class Response(io.BytesIO):
    def __init__(self, payload):
        super().__init__(json.dumps(payload).encode())
        self.status = 200

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False


class WeatherEvaluationTests(unittest.TestCase):
    def setUp(self):
        self.fixture = json.loads(FIXTURE_PATH.read_text())
        self.sunset = datetime(2026, 8, 16, 18, 24, tzinfo=JST)
        today = patch(
            "weather.scripts.evaluation._today_in_jst",
            return_value=self.sunset.date(),
        )
        today.start()
        self.addCleanup(today.stop)

    def evaluate(self, payload=None):
        forecast = self.fixture if payload is None else payload
        return evaluate_sunset_weather(
            35.625,
            139.75,
            self.sunset,
            opener=lambda *_args, **_kwargs: Response(forecast),
        )

    def test_fixture_runs_through_fetch_window_selection_and_scoring(self):
        result = self.evaluate()

        self.assertIsInstance(result, SunsetWeatherEvaluation)
        self.assertEqual(result.latitude, 35.625)
        self.assertEqual(result.longitude, 139.75)
        self.assertEqual(result.sunset.isoformat(), "2026-08-16T18:24:00+09:00")
        self.assertEqual(result.starts_at.isoformat(), "2026-08-16T18:04:00+09:00")
        self.assertEqual(result.ends_at.isoformat(), "2026-08-16T18:49:00+09:00")
        self.assertEqual(result.gradient.score, 77)
        self.assertEqual(result.dramatic.score, 94)
        self.assertIn("降水がない", result.gradient.positive_factors)
        self.assertIn("中層雲が適量", result.dramatic.positive_factors)

    def test_invalid_input_is_rejected_before_fetching(self):
        requested = False

        def opener(*_args, **_kwargs):
            nonlocal requested
            requested = True
            return Response(self.fixture)

        with self.assertRaises(WeatherEvaluationError) as caught:
            evaluate_sunset_weather(
                35.625,
                139.75,
                datetime(2026, 8, 16, 18, 24),
                opener=opener,
            )

        self.assertEqual(caught.exception.code, WeatherEvaluationErrorCode.INVALID_INPUT)
        self.assertFalse(requested)

    def test_non_today_sunset_is_rejected_before_fetching(self):
        requested = False

        def opener(*_args, **_kwargs):
            nonlocal requested
            requested = True
            return Response(self.fixture)

        with self.assertRaises(WeatherEvaluationError) as caught:
            evaluate_sunset_weather(
                35.625,
                139.75,
                self.sunset + timedelta(days=1),
                opener=opener,
            )

        self.assertEqual(caught.exception.code, WeatherEvaluationErrorCode.INVALID_INPUT)
        self.assertIn("今日", str(caught.exception))
        self.assertFalse(requested)

    def test_fetch_failure_has_a_stable_error_code_and_preserves_cause(self):
        def fail(*_args, **_kwargs):
            raise OSError("offline")

        with self.assertRaises(WeatherEvaluationError) as caught:
            evaluate_sunset_weather(35.625, 139.75, self.sunset, opener=fail)

        self.assertEqual(
            caught.exception.code,
            WeatherEvaluationErrorCode.FORECAST_FETCH_FAILED,
        )
        self.assertIsInstance(caught.exception.__cause__, OpenMeteoError)

    def test_missing_sunset_hour_does_not_return_a_score(self):
        incomplete = deepcopy(self.fixture)
        for values in incomplete["hourly"].values():
            values.pop()

        with self.assertRaises(WeatherEvaluationError) as caught:
            self.evaluate(incomplete)

        self.assertEqual(
            caught.exception.code,
            WeatherEvaluationErrorCode.FORECAST_DATA_INSUFFICIENT,
        )
        self.assertIsInstance(caught.exception.__cause__, SunsetWindowError)

    def test_scoring_failure_does_not_return_a_partial_result(self):
        with patch(
            "weather.scripts.evaluation.score_weather",
            side_effect=WeatherScoringError("採点不能"),
        ):
            with self.assertRaises(WeatherEvaluationError) as caught:
                self.evaluate()

        self.assertEqual(
            caught.exception.code, WeatherEvaluationErrorCode.SCORING_FAILED
        )
        self.assertIsInstance(caught.exception.__cause__, WeatherScoringError)


if __name__ == "__main__":
    unittest.main()
