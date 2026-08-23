"""Fetch and validate today's hourly sunset-weather inputs from Open-Meteo."""

from __future__ import annotations

import json
import math
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Any
from urllib.error import HTTPError
from urllib.parse import urlencode
from urllib.request import urlopen

ENDPOINT = "https://api.open-meteo.com/v1/forecast"
PREFERRED_MODEL = "jma_seamless"
HOURLY_VARIABLES = (
    "cloud_cover_low",
    "cloud_cover_mid",
    "cloud_cover_high",
    "cloud_cover",
    "visibility",
    "relative_humidity_2m",
    "precipitation",
    "wind_speed_10m",
)


class OpenMeteoError(RuntimeError):
    """Raised when Open-Meteo cannot provide a complete, valid forecast."""


@dataclass(frozen=True)
class WeatherHour:
    time: datetime
    cloud_cover_low: float
    cloud_cover_mid: float
    cloud_cover_high: float
    cloud_cover: float
    visibility: float
    relative_humidity: float
    precipitation: float
    wind_speed: float


def build_forecast_url(
    latitude: float, longitude: float, *, model: str | None = PREFERRED_MODEL
) -> str:
    """Build a one-day, Japan-time forecast URL for the required variables."""
    parameters: dict[str, str | float | int] = {
        "latitude": latitude,
        "longitude": longitude,
        "timezone": "Asia/Tokyo",
        "forecast_days": 1,
        "hourly": ",".join(HOURLY_VARIABLES),
    }
    if model is not None:
        parameters["models"] = model
    return f"{ENDPOINT}?{urlencode(parameters)}"


def fetch_today_forecast(
    latitude: float,
    longitude: float,
    *,
    opener: Callable[..., Any] = urlopen,
    timeout: float = 10,
) -> tuple[WeatherHour, ...]:
    """Fetch a complete forecast, preferring JMA and never imputing missing data.

    Open-Meteo can return ``null`` values for locations/times not covered by the
    explicitly selected JMA model. Only in that case, retry with Open-Meteo's
    automatic model selection. Invalid responses and HTTP failures remain errors.
    """
    _validate_coordinates(latitude, longitude)

    try:
        preferred_payload = _request(
            latitude, longitude, PREFERRED_MODEL, opener, timeout
        )
        if _has_null_hourly_values(preferred_payload):
            fallback_payload = _request(latitude, longitude, None, opener, timeout)
            return _parse_hourly(fallback_payload)
        return _parse_hourly(preferred_payload)
    except OpenMeteoError:
        raise
    except Exception as error:
        raise OpenMeteoError("Open-Meteoの取得に失敗しました") from error


def _validate_coordinates(latitude: float, longitude: float) -> None:
    for value, lower, upper in (
        (latitude, -90, 90),
        (longitude, -180, 180),
    ):
        if (
            isinstance(value, bool)
            or not isinstance(value, (int, float))
            or not math.isfinite(value)
            or not lower <= value <= upper
        ):
            raise ValueError("緯度・経度が不正です")


def _request(
    latitude: float,
    longitude: float,
    model: str | None,
    opener: Callable[..., Any],
    timeout: float,
) -> Any:
    url = build_forecast_url(latitude, longitude, model=model)
    try:
        response_context = opener(url, timeout=timeout)
    except HTTPError as error:
        raise OpenMeteoError(f"Open-Meteo HTTP {error.code}") from error

    with response_context as response:
        status = getattr(response, "status", None)
        if status != 200:
            raise OpenMeteoError(f"Open-Meteo HTTP {status}")
        try:
            return json.load(response)
        except (json.JSONDecodeError, UnicodeDecodeError) as error:
            raise OpenMeteoError("Open-MeteoのJSON応答が不正です") from error


def _has_null_hourly_values(payload: Any) -> bool:
    """Return true only for explicit nulls, not for malformed/missing arrays."""
    if not isinstance(payload, Mapping):
        return False
    hourly = payload.get("hourly")
    if not isinstance(hourly, Mapping):
        return False
    return any(
        isinstance(values, list) and any(value is None for value in values)
        for name in HOURLY_VARIABLES
        if (values := hourly.get(name)) is not None
    )


def _parse_hourly(payload: Any) -> tuple[WeatherHour, ...]:
    if not isinstance(payload, Mapping):
        raise OpenMeteoError("Open-Meteoの応答形式が不正です")
    hourly = payload.get("hourly")
    if not isinstance(hourly, Mapping):
        raise OpenMeteoError("Open-Meteoの時間別予報がありません")

    names = ("time",) + HOURLY_VARIABLES
    values = {name: hourly.get(name) for name in names}
    if any(not isinstance(value, list) for value in values.values()):
        raise OpenMeteoError("必要な時間別予報が欠けています")

    times = values["time"]
    assert isinstance(times, list)
    length = len(times)
    if length == 0 or any(len(value) != length for value in values.values()):
        raise OpenMeteoError("時間別予報の配列長が不正です")

    return tuple(
        WeatherHour(
            time=_parse_time(times[index]),
            cloud_cover_low=_number_at(values, "cloud_cover_low", index, 0, 100),
            cloud_cover_mid=_number_at(values, "cloud_cover_mid", index, 0, 100),
            cloud_cover_high=_number_at(values, "cloud_cover_high", index, 0, 100),
            cloud_cover=_number_at(values, "cloud_cover", index, 0, 100),
            visibility=_number_at(values, "visibility", index, 0),
            relative_humidity=_number_at(
                values, "relative_humidity_2m", index, 0, 100
            ),
            precipitation=_number_at(values, "precipitation", index, 0),
            wind_speed=_number_at(values, "wind_speed_10m", index, 0),
        )
        for index in range(length)
    )


def _parse_time(value: Any) -> datetime:
    if not isinstance(value, str) or "T" not in value:
        raise OpenMeteoError("時間別予報の時刻が不正です")
    try:
        return datetime.fromisoformat(value)
    except ValueError as error:
        raise OpenMeteoError("時間別予報の時刻が不正です") from error


def _number_at(
    values: Mapping[str, Sequence[Any]],
    name: str,
    index: int,
    minimum: float,
    maximum: float | None = None,
) -> float:
    value = values[name][index]
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise OpenMeteoError(f"時間別予報の値が不正です: {name}")
    number = float(value)
    if (
        not math.isfinite(number)
        or number < minimum
        or (maximum is not None and number > maximum)
    ):
        raise OpenMeteoError(f"時間別予報の値が不正です: {name}")
    return number
