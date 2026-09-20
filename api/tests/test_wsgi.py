from __future__ import annotations

import json
import os
import unittest
from pathlib import Path
from unittest.mock import patch

from api.application import ApiError, ApiErrorCode
from api.wsgi import application


def invoke(path: str, query: str = "", method: str = "GET"):
    response: dict[str, object] = {}

    def start_response(status, headers):
        response["status"] = status
        response["headers"] = dict(headers)

    with patch.dict(os.environ, {"DEM_ROOT": "/dem"}):
        body = b"".join(
            application(
                {
                    "REQUEST_METHOD": method,
                    "PATH_INFO": path,
                    "QUERY_STRING": query,
                },
                start_response,
            )
        )
    response["body"] = body
    return response


class WsgiApplicationTests(unittest.TestCase):
    def test_success_preserves_json_and_cors_contract(self) -> None:
        expected = {"weather": {"gradient": {"score": 80}}}
        with patch("api.server.evaluate_location", return_value=expected) as evaluate:
            response = invoke(
                "/api/forecast", "lat=35.6812&lng=139.7671"
            )

        self.assertEqual(response["status"], "200 OK")
        self.assertEqual(json.loads(response["body"]), expected)
        self.assertEqual(response["headers"]["Access-Control-Allow-Origin"], "*")
        self.assertEqual(response["headers"]["Cache-Control"], "no-store")
        evaluate.assert_called_once_with(35.6812, 139.7671, dem_root=Path("/dem"))

    def test_application_error_preserves_status_and_error_shape(self) -> None:
        with patch(
            "api.server.evaluate_location",
            side_effect=ApiError(ApiErrorCode.WEATHER_UNAVAILABLE, "利用不可"),
        ):
            response = invoke("/api/forecast", "lat=35&lng=139")

        self.assertEqual(response["status"], "502 Bad Gateway")
        self.assertEqual(
            json.loads(response["body"]),
            {
                "error": {
                    "code": "weather_unavailable",
                    "message": "利用不可",
                }
            },
        )

    def test_options_returns_empty_preflight_response(self) -> None:
        response = invoke("/api/forecast", method="OPTIONS")

        self.assertEqual(response["status"], "204 No Content")
        self.assertEqual(response["body"], b"")
        self.assertEqual(response["headers"]["Content-Length"], "0")

    def test_unsupported_method_returns_stable_error(self) -> None:
        response = invoke("/api/forecast", method="POST")

        self.assertEqual(response["status"], "405 Method Not Allowed")
        self.assertEqual(response["headers"]["Allow"], "GET, OPTIONS")
        self.assertEqual(
            response["headers"]["Access-Control-Allow-Methods"], "GET, OPTIONS"
        )
        self.assertEqual(
            json.loads(response["body"]),
            {
                "error": {
                    "code": "method_not_allowed",
                    "message": "GET または OPTIONS を使用してください",
                }
            },
        )

    def test_unknown_path_is_not_found(self) -> None:
        response = invoke("/unknown")

        self.assertEqual(response["status"], "404 Not Found")
        self.assertEqual(json.loads(response["body"])["error"]["code"], "not_found")


if __name__ == "__main__":
    unittest.main()
