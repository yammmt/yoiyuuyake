"""Select the complete hourly forecast window used for sunset scoring."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, replace
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from .open_meteo import WeatherHour

JST = ZoneInfo("Asia/Tokyo")
WINDOW_BEFORE_SUNSET = timedelta(minutes=20)
WINDOW_AFTER_SUNSET = timedelta(minutes=25)
FORECAST_INTERVAL = timedelta(hours=1)


class SunsetWindowError(ValueError):
    """Raised when a complete sunset forecast window cannot be selected."""


@dataclass(frozen=True)
class SunsetWeatherWindow:
    """The viewing period and hourly samples that completely cover it."""

    sunset: datetime
    starts_at: datetime
    ends_at: datetime
    hours: tuple[WeatherHour, ...]


def select_sunset_window(
    sunset: datetime, forecast: Sequence[WeatherHour]
) -> SunsetWeatherWindow:
    """Select each hourly sample needed to cover 20 min before to 25 min after sunset.

    Datetimes must be timezone-aware. They are compared in Asia/Tokyo, and no
    missing hourly samples are interpolated or otherwise inferred.
    """
    sunset_jst = _as_jst(sunset, "日没時刻")
    starts_at = sunset_jst - WINDOW_BEFORE_SUNSET
    ends_at = sunset_jst + WINDOW_AFTER_SUNSET
    first_hour = _floor_hour(starts_at)
    last_hour = _ceil_hour(ends_at)

    by_time: dict[datetime, WeatherHour] = {}
    for hour in forecast:
        timestamp = _as_jst(hour.time, "時間別予報の時刻")
        if timestamp.minute or timestamp.second or timestamp.microsecond:
            raise SunsetWindowError("時間別予報が正時ではありません")
        if timestamp in by_time:
            raise SunsetWindowError("時間別予報の時刻が重複しています")
        by_time[timestamp] = replace(hour, time=timestamp)

    required_times = _hour_range(first_hour, last_hour)
    missing_times = [
        timestamp for timestamp in required_times if timestamp not in by_time
    ]
    if missing_times:
        formatted = ", ".join(
            timestamp.strftime("%Y-%m-%d %H:%M") for timestamp in missing_times
        )
        raise SunsetWindowError(f"日没前後の時間別予報が不足しています: {formatted}")

    return SunsetWeatherWindow(
        sunset=sunset_jst,
        starts_at=starts_at,
        ends_at=ends_at,
        hours=tuple(by_time[timestamp] for timestamp in required_times),
    )


def _as_jst(value: datetime, label: str) -> datetime:
    if not isinstance(value, datetime) or value.tzinfo is None:
        raise SunsetWindowError(f"{label}にタイムゾーンがありません")
    try:
        offset = value.utcoffset()
    except (OverflowError, ValueError) as error:
        raise SunsetWindowError(f"{label}が不正です") from error
    if offset is None:
        raise SunsetWindowError(f"{label}にタイムゾーンがありません")
    return value.astimezone(JST)


def _floor_hour(value: datetime) -> datetime:
    return value.replace(minute=0, second=0, microsecond=0)


def _ceil_hour(value: datetime) -> datetime:
    floored = _floor_hour(value)
    return floored if value == floored else floored + FORECAST_INTERVAL


def _hour_range(first: datetime, last: datetime) -> tuple[datetime, ...]:
    count = int((last - first) / FORECAST_INTERVAL)
    return tuple(first + index * FORECAST_INTERVAL for index in range(count + 1))
