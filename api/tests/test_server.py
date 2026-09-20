from __future__ import annotations

import json
import threading
import unittest
from http.server import ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from api.application import ApiError, ApiErrorCode, ApiErrorReason
from api.server import ServerConfig, make_handler, parse_server_config, validate_dem_root


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

    def request(self, path: str, *, method: str = "GET"):
        try:
            response = urlopen(
                Request(self.base_url + path, method=method), timeout=2
            )
        except HTTPError as error:
            response = error
        with response:
            return response.status, response.headers, json.load(response)

    def get(self, path: str):
        return self.request(path)

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

    def test_unsupported_method_matches_hosted_api_contract(self) -> None:
        status, headers, body = self.request("/api/forecast", method="POST")

        self.assertEqual(status, 405)
        self.assertEqual(headers["Allow"], "GET, OPTIONS")
        self.assertEqual(headers["Access-Control-Allow-Methods"], "GET, OPTIONS")
        self.assertEqual(
            body,
            {
                "error": {
                    "code": "method_not_allowed",
                    "message": "GET または OPTIONS を使用してください",
                }
            },
        )

    def test_head_unknown_path_preserves_404_headers_without_body(self) -> None:
        request = Request(self.base_url + "/unknown", method="HEAD")
        try:
            response = urlopen(request, timeout=2)
        except HTTPError as error:
            response = error

        with response:
            self.assertEqual(response.status, 404)
            self.assertEqual(
                response.headers["Content-Type"], "application/json; charset=utf-8"
            )
            self.assertEqual(response.headers["Access-Control-Allow-Origin"], "*")
            self.assertEqual(response.headers["Cache-Control"], "no-store")
            self.assertGreater(int(response.headers["Content-Length"]), 0)
            self.assertEqual(response.read(), b"")

    def test_dem_error_includes_diagnostic_reason(self) -> None:
        error = ApiError(
            ApiErrorCode.DEM_UNAVAILABLE,
            "別の地点を選択してください。",
            reason=ApiErrorReason.RAY_OUT_OF_COVERAGE,
        )
        with patch("api.server.evaluate_location", side_effect=error):
            status, _headers, body = self.get("/api/forecast?lat=35&lng=139")

        self.assertEqual(status, 503)
        self.assertEqual(
            body,
            {
                "error": {
                    "code": "dem_unavailable",
                    "reason": "ray_out_of_coverage",
                    "message": "別の地点を選択してください。",
                }
            },
        )


class ServerConfigurationTests(unittest.TestCase):
    def test_cloud_environment_supplies_runtime_configuration(self) -> None:
        config = parse_server_config(
            [],
            environ={
                "HOST": "0.0.0.0",
                "PORT": "8080",
                "DEM_ROOT": "/dem/derived-dem10b-v1",
            },
        )

        self.assertEqual(
            config,
            ServerConfig("0.0.0.0", 8080, Path("/dem/derived-dem10b-v1")),
        )

    def test_cli_values_override_environment(self) -> None:
        config = parse_server_config(
            ["--host", "127.0.0.2", "--port", "9000", "--data", "custom-dem"],
            environ={"HOST": "0.0.0.0", "PORT": "8080", "DEM_ROOT": "/dem"},
        )

        self.assertEqual(
            config, ServerConfig("127.0.0.2", 9000, Path("custom-dem"))
        )

    def test_startup_validation_opens_and_closes_dem_store(self) -> None:
        with patch("api.server.LocalDemStore") as store_class:
            validate_dem_root(Path("prepared-dem"))

        store_class.assert_called_once_with(Path("prepared-dem"))
        store_class.return_value.close.assert_called_once_with()


if __name__ == "__main__":
    unittest.main()
