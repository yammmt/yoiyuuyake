import sys
import unittest
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

sys.path.insert(0, str(Path(__file__).parents[2]))

from weather.scripts.open_meteo import WeatherHour  # noqa: E402
from weather.scripts.sunset_window import (  # noqa: E402
    SunsetWindowError,
    select_sunset_window,
)

JST = ZoneInfo("Asia/Tokyo")


def weather_hour(hour: int, minute: int = 0) -> WeatherHour:
    return WeatherHour(
        time=datetime(2026, 8, 16, hour, minute, tzinfo=JST),
        cloud_cover_low=10,
        cloud_cover_mid=30,
        cloud_cover_high=40,
        cloud_cover=50,
        visibility=24_000,
        relative_humidity=60,
        precipitation=0,
        wind_speed=3,
    )


class SunsetWindowTests(unittest.TestCase):
    def setUp(self):
        self.forecast = tuple(weather_hour(hour) for hour in range(16, 21))

    def test_selects_hourly_samples_covering_the_viewing_period(self):
        window = select_sunset_window(
            datetime(2026, 8, 16, 18, 24, tzinfo=JST), self.forecast
        )

        self.assertEqual(window.starts_at.isoformat(), "2026-08-16T18:04:00+09:00")
        self.assertEqual(window.ends_at.isoformat(), "2026-08-16T18:49:00+09:00")
        self.assertEqual([hour.time.hour for hour in window.hours], [18, 19])

    def test_exact_hour_sunset_includes_both_outer_bracketing_hours(self):
        window = select_sunset_window(
            datetime(2026, 8, 16, 18, 0, tzinfo=JST), self.forecast
        )

        self.assertEqual([hour.time.hour for hour in window.hours], [17, 18, 19])

    def test_rounding_boundaries_change_only_after_the_period_crosses_an_hour(self):
        cases = (
            (18, 19, [17, 18, 19]),
            (18, 20, [18, 19]),
            (18, 35, [18, 19]),
            (18, 36, [18, 19, 20]),
        )
        for hour, minute, expected in cases:
            with self.subTest(sunset=f"{hour:02d}:{minute:02d}"):
                window = select_sunset_window(
                    datetime(2026, 8, 16, hour, minute, tzinfo=JST), self.forecast
                )
                self.assertEqual(
                    [forecast_hour.time.hour for forecast_hour in window.hours],
                    expected,
                )

    def test_converts_sunset_to_asia_tokyo(self):
        window = select_sunset_window(
            datetime(2026, 8, 16, 9, 24, tzinfo=timezone.utc), self.forecast
        )

        self.assertEqual(window.sunset.isoformat(), "2026-08-16T18:24:00+09:00")
        self.assertEqual([hour.time.hour for hour in window.hours], [18, 19])

    def test_accepts_forecast_timestamps_with_an_equivalent_timezone(self):
        utc_forecast = tuple(
            replace(hour, time=hour.time.astimezone(timezone.utc))
            for hour in self.forecast
        )

        window = select_sunset_window(
            datetime(2026, 8, 16, 18, 24, tzinfo=JST), utc_forecast
        )

        self.assertEqual(
            [hour.time.isoformat() for hour in window.hours],
            ["2026-08-16T18:00:00+09:00", "2026-08-16T19:00:00+09:00"],
        )

    def test_missing_required_hour_is_an_error(self):
        forecast = tuple(hour for hour in self.forecast if hour.time.hour != 19)

        with self.assertRaisesRegex(SunsetWindowError, "2026-08-16 19:00"):
            select_sunset_window(
                datetime(2026, 8, 16, 18, 24, tzinfo=JST), forecast
            )

    def test_does_not_use_nearby_non_hourly_data_as_a_substitute(self):
        forecast = self.forecast + (weather_hour(19, 30),)

        with self.assertRaisesRegex(SunsetWindowError, "正時"):
            select_sunset_window(
                datetime(2026, 8, 16, 18, 24, tzinfo=JST), forecast
            )

    def test_duplicate_forecast_hour_is_an_error(self):
        forecast = self.forecast + (weather_hour(19),)

        with self.assertRaisesRegex(SunsetWindowError, "重複"):
            select_sunset_window(
                datetime(2026, 8, 16, 18, 24, tzinfo=JST), forecast
            )

    def test_naive_datetime_is_rejected(self):
        with self.assertRaisesRegex(SunsetWindowError, "タイムゾーン"):
            select_sunset_window(datetime(2026, 8, 16, 18, 24), self.forecast)

        naive_forecast = (
            replace(self.forecast[0], time=self.forecast[0].time.replace(tzinfo=None)),
        )
        with self.assertRaisesRegex(SunsetWindowError, "タイムゾーン"):
            select_sunset_window(
                datetime(2026, 8, 16, 18, 24, tzinfo=JST), naive_forecast
            )


if __name__ == "__main__":
    unittest.main()
