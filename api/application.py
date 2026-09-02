"""Combine astronomy, weather, and terrain into one complete API result."""

from __future__ import annotations

import math
from collections.abc import Callable
from datetime import datetime, timedelta
from enum import Enum
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from terrain.scripts.astronomy import solar_position, sunset_on
from terrain.scripts.dem_store import (
    DemError,
    DemNoElevationError,
    DemOutOfCoverageError,
    DemSampleRole,
    LocalDemStore,
)
from terrain.scripts.horizon import HorizonProfile, calculate_horizon
from terrain.scripts.visibility import VisibilityAssessment, assess_visibility
from weather.scripts.evaluation import (
    SunsetWeatherEvaluation,
    WeatherEvaluationError,
    evaluate_sunset_weather,
)
from weather.scripts.scoring import ScoreBreakdown

JST = ZoneInfo("Asia/Tokyo")
JAPAN_BOUNDS = {"north": 46.2, "south": 20.1, "east": 154.0, "west": 122.4}
COMPARISON_BEFORE_SUNSET = timedelta(minutes=10)
TERRAIN_NOTICE = (
    "見晴らしは地形を考慮した推定です。"
    "建物・樹木などの遮蔽物は考慮していません。"
)


class ApiErrorCode(str, Enum):
    """Stable failure categories exposed to site clients."""

    INVALID_INPUT = "invalid_input"
    WEATHER_UNAVAILABLE = "weather_unavailable"
    DEM_UNAVAILABLE = "dem_unavailable"


class ApiErrorReason(str, Enum):
    """Stable diagnostic reasons for unavailable terrain evaluations."""

    OBSERVER_NO_ELEVATION = "observer_no_elevation"
    OBSERVER_OUT_OF_COVERAGE = "observer_out_of_coverage"
    RAY_NO_ELEVATION = "ray_no_elevation"
    RAY_OUT_OF_COVERAGE = "ray_out_of_coverage"
    DEM_DATA_UNAVAILABLE = "dem_data_unavailable"
    TERRAIN_CALCULATION_FAILED = "terrain_calculation_failed"


class ApiError(RuntimeError):
    """Raised when a complete integrated result cannot be returned."""

    def __init__(
        self,
        code: ApiErrorCode,
        message: str,
        *,
        reason: ApiErrorReason | None = None,
    ):
        super().__init__(message)
        self.code = code
        self.reason = reason


def evaluate_location(
    latitude: float,
    longitude: float,
    *,
    dem_root: Path,
    weather_evaluator: Callable[..., SunsetWeatherEvaluation] = evaluate_sunset_weather,
    horizon_calculator: Callable[..., HorizonProfile] = calculate_horizon,
) -> dict[str, Any]:
    """Return today's complete sunset assessment for one point in Japan.

    No result is returned unless astronomy, weather, and terrain all succeed.
    Injectable evaluators keep tests deterministic and offline.
    """
    latitude, longitude = _validate_coordinates(latitude, longitude)
    today = datetime.now(JST).date()

    try:
        sunset = sunset_on(today, latitude, longitude)
        comparison_sun = solar_position(
            sunset.time - COMPARISON_BEFORE_SUNSET, latitude, longitude
        )
    except (OverflowError, ValueError) as error:
        raise ApiError(ApiErrorCode.INVALID_INPUT, "日没を計算できません") from error

    store: LocalDemStore | None = None
    try:
        store = LocalDemStore(Path(dem_root))
    except (KeyError, OSError, TypeError, ValueError) as error:
        raise _terrain_api_error(
            ApiErrorReason.DEM_DATA_UNAVAILABLE,
            "地形データを利用できません。時間をおいて再試行してください。",
        ) from error

    try:
        profile = horizon_calculator(
            store, latitude, longitude, sunset.azimuth_degrees
        )
        visibility = assess_visibility(profile, comparison_sun.altitude_degrees)
    except DemError as error:
        raise _dem_api_error(error) from error
    except (KeyError, OSError) as error:
        raise _terrain_api_error(
            ApiErrorReason.DEM_DATA_UNAVAILABLE,
            "地形データを利用できません。時間をおいて再試行してください。",
        ) from error
    except (TypeError, ValueError) as error:
        raise _terrain_api_error(
            ApiErrorReason.TERRAIN_CALCULATION_FAILED,
            "地形評価中にエラーが発生しました。時間をおいて再試行してください。",
        ) from error
    finally:
        if store is not None:
            store.close()

    try:
        weather = weather_evaluator(latitude, longitude, sunset.time)
    except WeatherEvaluationError as error:
        raise ApiError(
            ApiErrorCode.WEATHER_UNAVAILABLE, "気象予報を利用できません"
        ) from error

    return _result_to_dict(
        latitude, longitude, sunset.azimuth_degrees, weather, profile, visibility
    )


def _dem_api_error(error: DemError) -> ApiError:
    role = error.sample_context.role if error.sample_context is not None else None
    if isinstance(error, DemNoElevationError):
        if role == DemSampleRole.OBSERVER:
            return _terrain_api_error(
                ApiErrorReason.OBSERVER_NO_ELEVATION,
                "選択地点の標高データがないため、地形を評価できません。少し離れた地点を選択してください。",
            )
        if role == DemSampleRole.RAY:
            return _terrain_api_error(
                ApiErrorReason.RAY_NO_ELEVATION,
                "日没方向の地形データが不足しているため、見晴らしを評価できません。別の地点を選択してください。",
            )
    if isinstance(error, DemOutOfCoverageError):
        if role == DemSampleRole.OBSERVER:
            return _terrain_api_error(
                ApiErrorReason.OBSERVER_OUT_OF_COVERAGE,
                "選択地点は現在の地形データ対象範囲外です。別の地点を選択してください。",
            )
        if role == DemSampleRole.RAY:
            return _terrain_api_error(
                ApiErrorReason.RAY_OUT_OF_COVERAGE,
                "日没方向が地形データ対象範囲を越えるため、見晴らしを評価できません。別の地点を選択してください。",
            )
    return _terrain_api_error(
        ApiErrorReason.DEM_DATA_UNAVAILABLE,
        "地形データを利用できません。時間をおいて再試行してください。",
    )


def _terrain_api_error(reason: ApiErrorReason, message: str) -> ApiError:
    return ApiError(ApiErrorCode.DEM_UNAVAILABLE, message, reason=reason)


def _validate_coordinates(latitude: float, longitude: float) -> tuple[float, float]:
    coordinates = (
        (latitude, JAPAN_BOUNDS["south"], JAPAN_BOUNDS["north"]),
        (longitude, JAPAN_BOUNDS["west"], JAPAN_BOUNDS["east"]),
    )
    if any(
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not math.isfinite(value)
        or not lower <= value <= upper
        for value, lower, upper in coordinates
    ):
        raise ApiError(
            ApiErrorCode.INVALID_INPUT, "日本国内の緯度・経度を指定してください"
        )
    return float(latitude), float(longitude)


def _result_to_dict(
    latitude: float,
    longitude: float,
    sunset_azimuth_degrees: float,
    weather: SunsetWeatherEvaluation,
    profile: HorizonProfile,
    visibility: VisibilityAssessment,
) -> dict[str, Any]:
    return {
        "location": {"latitude": latitude, "longitude": longitude},
        "sunset": {
            "time": weather.sunset.isoformat(),
            "azimuth_degrees": sunset_azimuth_degrees,
            "viewing_window": {
                "starts_at": weather.starts_at.isoformat(),
                "ends_at": weather.ends_at.isoformat(),
            },
        },
        "weather": {
            "gradient": _score_to_dict(weather.gradient),
            "dramatic": _score_to_dict(weather.dramatic),
        },
        "terrain": {
            "visibility": visibility.label,
            "description": visibility.description,
            "observer_elevation_meters": profile.observer_elevation_meters,
            "maximum_horizon_angle_degrees": (
                visibility.maximum_horizon_angle_degrees
            ),
            "obstructing_azimuth_degrees": visibility.obstructing_azimuth_degrees,
            "obstructing_distance_meters": visibility.obstructing_distance_meters,
            "comparison_sun_altitude_degrees": visibility.sun_altitude_degrees,
            "sun_likely_occluded": visibility.sun_likely_occluded,
        },
        "notice": TERRAIN_NOTICE,
    }


def _score_to_dict(score: ScoreBreakdown) -> dict[str, Any]:
    return {
        "score": score.score,
        "positive_factors": list(score.positive_factors),
        "negative_factors": list(score.negative_factors),
    }
