import io
import json
import sys
import unittest
from copy import deepcopy
from pathlib import Path
from urllib.error import HTTPError
from urllib.parse import parse_qs, urlparse

sys.path.insert(0, str(Path(__file__).parents[1] / "scripts"))

from open_meteo import (  # noqa: E402
    HOURLY_VARIABLES,
    OpenMeteoError,
    build_forecast_url,
    fetch_today_forecast,
)

FIXTURE_PATH = Path(__file__).parent / "fixtures" / "open_meteo_forecast.json"


class Response(io.BytesIO):
    def __init__(self, body: bytes, status: int = 200):
        super().__init__(body)
        self.status = status

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False


def response(payload, status=200):
    return Response(json.dumps(payload).encode(), status)


class RecordingOpener:
    def __init__(self, *responses):
        self.responses = list(responses)
        self.calls = []

    def __call__(self, url, **kwargs):
        self.calls.append((url, kwargs))
        return self.responses.pop(0)


class OpenMeteoTests(unittest.TestCase):
    def setUp(self):
        self.fixture = json.loads(FIXTURE_PATH.read_text())

    def test_url_requests_jst_jma_and_all_required_fields(self):
        query = parse_qs(urlparse(build_forecast_url(35.6, 139.7)).query)

        self.assertEqual(query["timezone"], ["Asia/Tokyo"])
        self.assertEqual(query["forecast_days"], ["1"])
        self.assertEqual(query["models"], ["jma_seamless"])
        self.assertEqual(query["hourly"][0].split(","), list(HOURLY_VARIABLES))

    def test_fixture_becomes_typed_hourly_data(self):
        hours = fetch_today_forecast(
            35.6, 139.7, opener=lambda *_args, **_kwargs: response(self.fixture)
        )

        self.assertEqual(len(hours), 3)
        self.assertEqual(hours[0].time.isoformat(), "2026-08-16T17:00:00")
        self.assertEqual(hours[1].visibility, 24100.0)
        self.assertEqual(hours[2].relative_humidity, 70.0)

    def test_null_jma_values_retry_without_an_explicit_model(self):
        jma_payload = deepcopy(self.fixture)
        jma_payload["hourly"]["cloud_cover_low"][1] = None
        opener = RecordingOpener(response(jma_payload), response(self.fixture))

        hours = fetch_today_forecast(35.6, 139.7, opener=opener)

        self.assertEqual(len(hours), 3)
        self.assertIn("models=jma_seamless", opener.calls[0][0])
        self.assertNotIn("models=", opener.calls[1][0])
        self.assertEqual(opener.calls[0][1]["timeout"], 10)

    def test_fallback_missing_values_remain_an_error(self):
        missing = deepcopy(self.fixture)
        missing["hourly"]["visibility"][0] = None
        opener = RecordingOpener(response(missing), response(missing))

        with self.assertRaises(OpenMeteoError):
            fetch_today_forecast(35.6, 139.7, opener=opener)

    def test_missing_variable_is_an_error_without_fallback(self):
        data = deepcopy(self.fixture)
        del data["hourly"]["visibility"]
        opener = RecordingOpener(response(data))

        with self.assertRaisesRegex(OpenMeteoError, "欠けています"):
            fetch_today_forecast(35.6, 139.7, opener=opener)
        self.assertEqual(len(opener.calls), 1)

    def test_mismatched_array_lengths_are_an_error(self):
        data = deepcopy(self.fixture)
        data["hourly"]["precipitation"].pop()

        with self.assertRaisesRegex(OpenMeteoError, "配列長"):
            fetch_today_forecast(
                35.6, 139.7, opener=lambda *_args, **_kwargs: response(data)
            )

    def test_invalid_hourly_values_are_errors(self):
        cases = (
            ("cloud_cover", 101),
            ("relative_humidity_2m", True),
            ("visibility", "24000"),
            ("precipitation", -0.1),
        )
        for variable, invalid_value in cases:
            with self.subTest(variable=variable, invalid_value=invalid_value):
                data = deepcopy(self.fixture)
                data["hourly"][variable][0] = invalid_value
                with self.assertRaisesRegex(OpenMeteoError, variable):
                    fetch_today_forecast(
                        35.6,
                        139.7,
                        opener=lambda *_args, **_kwargs: response(data),
                    )

    def test_invalid_time_is_an_error(self):
        for invalid_time in ("not-a-time", "2026-08-16", 123):
            with self.subTest(invalid_time=invalid_time):
                data = deepcopy(self.fixture)
                data["hourly"]["time"][0] = invalid_time
                with self.assertRaisesRegex(OpenMeteoError, "時刻"):
                    fetch_today_forecast(
                        35.6,
                        139.7,
                        opener=lambda *_args, **_kwargs: response(data),
                    )

    def test_missing_or_empty_hourly_data_is_an_error(self):
        for hourly in (None, {}):
            with self.subTest(hourly=hourly):
                with self.assertRaises(OpenMeteoError):
                    fetch_today_forecast(
                        35.6,
                        139.7,
                        opener=lambda *_args, **_kwargs: response({"hourly": hourly}),
                    )

    def test_http_error_is_explicit(self):
        def fail(*_args, **_kwargs):
            raise HTTPError(
                "https://api.open-meteo.com/v1/forecast",
                503,
                "Service Unavailable",
                None,
                None,
            )

        with self.assertRaisesRegex(OpenMeteoError, "HTTP 503"):
            fetch_today_forecast(35.6, 139.7, opener=fail)

    def test_non_200_response_is_explicit(self):
        with self.assertRaisesRegex(OpenMeteoError, "HTTP 503"):
            fetch_today_forecast(
                35.6, 139.7, opener=lambda *_args, **_kwargs: response({}, 503)
            )

    def test_invalid_json_is_explicit(self):
        with self.assertRaisesRegex(OpenMeteoError, "JSON"):
            fetch_today_forecast(
                35.6,
                139.7,
                opener=lambda *_args, **_kwargs: Response(b"not json"),
            )

    def test_transport_error_is_wrapped(self):
        def fail(*_args, **_kwargs):
            raise OSError("offline")

        with self.assertRaisesRegex(OpenMeteoError, "取得に失敗"):
            fetch_today_forecast(35.6, 139.7, opener=fail)

    def test_invalid_coordinates_are_rejected_before_request(self):
        for latitude, longitude in ((91, 139.7), (35.6, float("nan")), (True, 139.7)):
            with self.subTest(latitude=latitude, longitude=longitude):
                with self.assertRaises(ValueError):
                    fetch_today_forecast(latitude, longitude)


if __name__ == "__main__":
    unittest.main()
