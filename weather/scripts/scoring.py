"""Calculate explainable Gradient and Dramatic sunset-weather scores."""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass

from .open_meteo import WeatherHour


class WeatherScoringError(ValueError):
    """Raised when weather inputs cannot be scored without inference."""


@dataclass(frozen=True)
class NormalizedWeather:
    """Sunset-window weather values normalized to the 0..1 range."""

    low_cloud_clear: float
    mid_cloud: float
    high_cloud: float
    total_cloud_clear: float
    visibility: float
    dry_air: float
    precipitation_free: float
    calm_wind: float


@dataclass(frozen=True)
class ScoreFactor:
    """One explainable component of a score."""

    key: str
    positive_label: str
    negative_label: str
    points: float
    max_points: float


@dataclass(frozen=True)
class ScoreBreakdown:
    """A bounded score and the factors from which it was calculated."""

    score: int
    factors: tuple[ScoreFactor, ...]
    positive_factors: tuple[str, ...]
    negative_factors: tuple[str, ...]


@dataclass(frozen=True)
class WeatherScores:
    """The two independent MVP scores for one sunset weather window."""

    gradient: ScoreBreakdown
    dramatic: ScoreBreakdown
    normalized: NormalizedWeather


def score_weather(hours: Sequence[WeatherHour]) -> WeatherScores:
    """Score complete hourly inputs without filling in missing observations.

    Each weather variable is averaged across the selected sunset window before
    normalization. Callers are responsible for selecting a complete window.
    """
    normalized = normalize_weather(hours)
    gradient = _breakdown(
        (
            _factor(
                "low_cloud_clear",
                "低層雲が少ない",
                "低層雲が多い",
                normalized.low_cloud_clear,
                30,
            ),
            _factor(
                "total_cloud_clear",
                "総雲量が少ない",
                "総雲量が多い",
                normalized.total_cloud_clear,
                15,
            ),
            _factor("visibility", "視程が良い", "視程が悪い", normalized.visibility, 20),
            _factor("dry_air", "湿度が低い", "湿度が高い", normalized.dry_air, 10),
            _factor(
                "precipitation_free",
                "降水がない",
                "降水がある",
                normalized.precipitation_free,
                20,
            ),
            _factor(
                "calm_wind", "風が強くない", "風が強い", normalized.calm_wind, 5
            ),
        )
    )
    dramatic = _breakdown(
        (
            _factor(
                "low_cloud_clear",
                "低層雲が少ない",
                "低層雲が多い",
                normalized.low_cloud_clear,
                20,
            ),
            _factor(
                "mid_cloud_optimal",
                "中層雲が適量",
                "中層雲が適量でない",
                _optimal_band(normalized.mid_cloud, 0.05, 0.30, 0.60, 0.95),
                20,
            ),
            _factor(
                "high_cloud_optimal",
                "高層雲が適量",
                "高層雲が適量でない",
                _optimal_band(normalized.high_cloud, 0.05, 0.35, 0.70, 0.95),
                20,
            ),
            _factor(
                "total_cloud_optimal",
                "総雲量が適量",
                "総雲量が適量でない",
                _optimal_band(
                    1 - normalized.total_cloud_clear, 0.10, 0.30, 0.70, 0.95
                ),
                10,
            ),
            _factor("visibility", "視程が良い", "視程が悪い", normalized.visibility, 10),
            _factor(
                "precipitation_free",
                "降水がない",
                "降水がある",
                normalized.precipitation_free,
                15,
            ),
            _factor("dry_air", "湿度が低い", "湿度が高い", normalized.dry_air, 3),
            _factor(
                "calm_wind", "風が強くない", "風が強い", normalized.calm_wind, 2
            ),
        )
    )
    return WeatherScores(
        gradient=gradient,
        dramatic=dramatic,
        normalized=normalized,
    )


def normalize_weather(hours: Sequence[WeatherHour]) -> NormalizedWeather:
    """Average and normalize all required weather inputs to 0..1."""
    if not hours:
        raise WeatherScoringError("採点対象の時間別予報がありません")

    for hour in hours:
        _validate_hour(hour)

    count = len(hours)

    def average(attribute: str) -> float:
        return sum(getattr(hour, attribute) for hour in hours) / count

    return NormalizedWeather(
        low_cloud_clear=1 - average("cloud_cover_low") / 100,
        mid_cloud=average("cloud_cover_mid") / 100,
        high_cloud=average("cloud_cover_high") / 100,
        total_cloud_clear=1 - average("cloud_cover") / 100,
        visibility=_ramp(average("visibility"), 5_000, 25_000),
        dry_air=1 - _ramp(average("relative_humidity"), 40, 90),
        precipitation_free=1 - _ramp(average("precipitation"), 0, 1),
        calm_wind=1 - _ramp(average("wind_speed"), 5, 15),
    )


def _validate_hour(hour: WeatherHour) -> None:
    if not isinstance(hour, WeatherHour):
        raise WeatherScoringError("時間別予報の形式が不正です")

    ranges = (
        ("cloud_cover_low", 0, 100),
        ("cloud_cover_mid", 0, 100),
        ("cloud_cover_high", 0, 100),
        ("cloud_cover", 0, 100),
        ("visibility", 0, None),
        ("relative_humidity", 0, 100),
        ("precipitation", 0, None),
        ("wind_speed", 0, None),
    )
    for name, minimum, maximum in ranges:
        value = getattr(hour, name)
        if (
            isinstance(value, bool)
            or not isinstance(value, (int, float))
            or not math.isfinite(value)
            or value < minimum
            or (maximum is not None and value > maximum)
        ):
            raise WeatherScoringError(f"時間別予報の値が不正です: {name}")


def _ramp(value: float, minimum: float, maximum: float) -> float:
    return _clamp((value - minimum) / (maximum - minimum))


def _optimal_band(
    value: float,
    zero_below: float,
    full_from: float,
    full_to: float,
    zero_above: float,
) -> float:
    """Return a trapezoid: zero outside, one in the preferred middle band."""
    if value <= zero_below or value >= zero_above:
        return 0.0
    if value < full_from:
        return (value - zero_below) / (full_from - zero_below)
    if value <= full_to:
        return 1.0
    return (zero_above - value) / (zero_above - full_to)


def _factor(
    key: str,
    positive_label: str,
    negative_label: str,
    normalized: float,
    weight: float,
) -> ScoreFactor:
    return ScoreFactor(
        key=key,
        positive_label=positive_label,
        negative_label=negative_label,
        points=_clamp(normalized) * weight,
        max_points=weight,
    )


def _breakdown(factors: tuple[ScoreFactor, ...]) -> ScoreBreakdown:
    score = min(
        100, max(0, math.floor(sum(factor.points for factor in factors) + 0.5))
    )
    positive = tuple(
        factor.positive_label
        for factor in sorted(factors, key=lambda factor: factor.points, reverse=True)
        if factor.points / factor.max_points >= 0.7
    )
    negative = tuple(
        factor.negative_label
        for factor in sorted(
            factors,
            key=lambda factor: factor.max_points - factor.points,
            reverse=True,
        )
        if factor.points / factor.max_points <= 0.3
    )
    return ScoreBreakdown(
        score=score,
        factors=factors,
        positive_factors=positive,
        negative_factors=negative,
    )


def _clamp(value: float) -> float:
    return min(1.0, max(0.0, value))
