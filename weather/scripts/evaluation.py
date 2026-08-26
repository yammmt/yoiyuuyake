"""Integrate forecast retrieval, sunset-window selection, and weather scoring."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import date, datetime
from enum import Enum
from typing import Any
from urllib.request import urlopen

from .open_meteo import JST, OpenMeteoError, fetch_today_forecast
from .scoring import ScoreBreakdown, WeatherScoringError, score_weather
from .sunset_window import SunsetWindowError, select_sunset_window


class WeatherEvaluationErrorCode(str, Enum):
    """Stable failure categories for callers of the integrated evaluator."""

    INVALID_INPUT = "invalid_input"
    FORECAST_FETCH_FAILED = "forecast_fetch_failed"
    FORECAST_DATA_INSUFFICIENT = "forecast_data_insufficient"
    SCORING_FAILED = "scoring_failed"


class WeatherEvaluationError(RuntimeError):
    """Raised instead of returning a guessed or partially calculated result."""

    def __init__(self, code: WeatherEvaluationErrorCode, message: str):
        super().__init__(message)
        self.code = code


@dataclass(frozen=True)
class SunsetWeatherEvaluation:
    """Public weather-evaluation result for one location and sunset."""

    latitude: float
    longitude: float
    sunset: datetime
    starts_at: datetime
    ends_at: datetime
    gradient: ScoreBreakdown
    dramatic: ScoreBreakdown


def evaluate_sunset_weather(
    latitude: float,
    longitude: float,
    sunset: datetime,
    *,
    opener: Callable[..., Any] = urlopen,
    timeout: float = 10,
) -> SunsetWeatherEvaluation:
    """Fetch and score the complete forecast window around a given sunset.

    The returned result is complete. Acquisition, missing-window, and scoring
    failures raise ``WeatherEvaluationError`` and never produce inferred scores.
    ``opener`` is injectable so integration tests and local callers can avoid a
    real network request.
    """
    _validate_sunset(sunset)

    try:
        forecast = fetch_today_forecast(
            latitude, longitude, opener=opener, timeout=timeout
        )
    except ValueError as error:
        raise WeatherEvaluationError(
            WeatherEvaluationErrorCode.INVALID_INPUT, str(error)
        ) from error
    except OpenMeteoError as error:
        raise WeatherEvaluationError(
            WeatherEvaluationErrorCode.FORECAST_FETCH_FAILED, str(error)
        ) from error

    try:
        window = select_sunset_window(sunset, forecast)
    except SunsetWindowError as error:
        raise WeatherEvaluationError(
            WeatherEvaluationErrorCode.FORECAST_DATA_INSUFFICIENT, str(error)
        ) from error

    try:
        scores = score_weather(window.hours)
    except WeatherScoringError as error:
        raise WeatherEvaluationError(
            WeatherEvaluationErrorCode.SCORING_FAILED, str(error)
        ) from error

    return SunsetWeatherEvaluation(
        latitude=float(latitude),
        longitude=float(longitude),
        sunset=window.sunset,
        starts_at=window.starts_at,
        ends_at=window.ends_at,
        gradient=scores.gradient,
        dramatic=scores.dramatic,
    )


def _validate_sunset(sunset: datetime) -> None:
    if not isinstance(sunset, datetime) or sunset.tzinfo is None:
        raise WeatherEvaluationError(
            WeatherEvaluationErrorCode.INVALID_INPUT,
            "日没時刻にタイムゾーンがありません",
        )
    try:
        offset = sunset.utcoffset()
    except (OverflowError, ValueError) as error:
        raise WeatherEvaluationError(
            WeatherEvaluationErrorCode.INVALID_INPUT, "日没時刻が不正です"
        ) from error
    if offset is None:
        raise WeatherEvaluationError(
            WeatherEvaluationErrorCode.INVALID_INPUT,
            "日没時刻にタイムゾーンがありません",
        )
    if sunset.astimezone(JST).date() != _today_in_jst():
        raise WeatherEvaluationError(
            WeatherEvaluationErrorCode.INVALID_INPUT,
            "日没時刻は日本時間の今日の日付を指定してください",
        )


def _today_in_jst() -> date:
    return datetime.now(JST).date()
