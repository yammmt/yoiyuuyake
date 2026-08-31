from __future__ import annotations

import json
import threading
import unittest
from http.server import ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from api.application import ApiError, ApiErrorCode
from api.server import make_handler


class ApiServerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.server = ThreadingHTTPServer(
            ("127.0.0.1", 0), make_handler(Path("unused"))
        )
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        host, port = self.server.server_address
        self.base_url = f"http://{host}:{port}"

    def tearDown(self) -> None:
        self.server.shutdown()
        self.server.server_close()
        self.thread.join()

    def get(self, path: str):
        try:
            response = urlopen(self.base_url + path, timeout=2)
        except HTTPError as error:
            response = error
        with response:
            return response.status, response.headers, json.load(response)

    def test_success_is_json_and_allows_local_site_requests(self) -> None:
        expected = {"weather": {"gradient": {"score": 80}}}
        with patch("api.server.evaluate_location", return_value=expected) as evaluate:
            status, headers, body = self.get(
                "/api/forecast?lat=35.6812&lng=139.7671"
            )

        self.assertEqual(status, 200)
        self.assertEqual(body, expected)
        self.assertEqual(headers["Access-Control-Allow-Origin"], "*")
        self.assertEqual(headers["Cache-Control"], "no-store")
        evaluate.assert_called_once_with(35.6812, 139.7671, dem_root=Path("unused"))

    def test_missing_or_duplicate_coordinates_are_bad_requests(self) -> None:
        for query in ("", "?lat=35", "?lat=35&lat=36&lng=139"):
            with self.subTest(query=query):
                status, _headers, body = self.get("/api/forecast" + query)
                self.assertEqual(status, 400)
                self.assertEqual(body["error"]["code"], "invalid_input")

    def test_application_errors_have_stable_http_statuses(self) -> None:
        cases = (
            (ApiErrorCode.INVALID_INPUT, 400),
            (ApiErrorCode.WEATHER_UNAVAILABLE, 502),
            (ApiErrorCode.DEM_UNAVAILABLE, 503),
        )
        for code, expected_status in cases:
            with self.subTest(code=code):
                with patch(
                    "api.server.evaluate_location",
                    side_effect=ApiError(code, "失敗しました"),
                ):
                    status, _headers, body = self.get("/api/forecast?lat=35&lng=139")
                self.assertEqual(status, expected_status)
                self.assertEqual(
                    body, {"error": {"code": code.value, "message": "失敗しました"}}
                )

    def test_options_supports_browser_preflight(self) -> None:
        request = Request(self.base_url + "/api/forecast", method="OPTIONS")
        with urlopen(request, timeout=2) as response:
            self.assertEqual(response.status, 204)
            self.assertEqual(response.headers["Access-Control-Allow-Methods"], "GET, OPTIONS")


if __name__ == "__main__":
    unittest.main()
