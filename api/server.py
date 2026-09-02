#!/usr/bin/env python3
"""Serve the local integrated sunset forecast API."""

from __future__ import annotations

import argparse
import json
import sys
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).parents[1]))

from api.application import ApiError, ApiErrorCode, evaluate_location

ERROR_STATUSES = {
    ApiErrorCode.INVALID_INPUT: HTTPStatus.BAD_REQUEST,
    ApiErrorCode.WEATHER_UNAVAILABLE: HTTPStatus.BAD_GATEWAY,
    ApiErrorCode.DEM_UNAVAILABLE: HTTPStatus.SERVICE_UNAVAILABLE,
}


def make_handler(dem_root: Path) -> type[BaseHTTPRequestHandler]:
    """Create an HTTP handler bound to one local DEM directory."""

    class ForecastHandler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            parsed = urlparse(self.path)
            if parsed.path != "/api/forecast":
                self._send_error(
                    HTTPStatus.NOT_FOUND, "not_found", "APIが見つかりません"
                )
                return

            try:
                latitude, longitude = _parse_coordinates(parsed.query)
                result = evaluate_location(latitude, longitude, dem_root=dem_root)
            except ApiError as error:
                payload = {"code": error.code.value, "message": str(error)}
                if error.reason is not None:
                    payload["reason"] = error.reason.value
                self._send_json(ERROR_STATUSES[error.code], {"error": payload})
                return

            self._send_json(HTTPStatus.OK, result)

        def do_OPTIONS(self) -> None:
            if urlparse(self.path).path != "/api/forecast":
                self._send_error(
                    HTTPStatus.NOT_FOUND, "not_found", "APIが見つかりません"
                )
                return
            self.send_response(HTTPStatus.NO_CONTENT)
            self._send_common_headers()
            self.send_header("Content-Length", "0")
            self.end_headers()

        def _send_error(self, status: HTTPStatus, code: str, message: str) -> None:
            self._send_json(status, {"error": {"code": code, "message": message}})

        def _send_json(self, status: HTTPStatus, payload: dict[str, Any]) -> None:
            body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            self.send_response(status)
            self._send_common_headers()
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def _send_common_headers(self) -> None:
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("Access-Control-Allow-Methods", "GET, OPTIONS")
            self.send_header("Access-Control-Allow-Headers", "Content-Type")
            self.send_header("Cache-Control", "no-store")

    return ForecastHandler


def _parse_coordinates(query: str) -> tuple[float, float]:
    parameters = parse_qs(query, keep_blank_values=True)
    try:
        latitude_values = parameters["lat"]
        longitude_values = parameters["lng"]
        if len(latitude_values) != 1 or len(longitude_values) != 1:
            raise ValueError
        return float(latitude_values[0]), float(longitude_values[0])
    except (KeyError, ValueError) as error:
        raise ApiError(
            ApiErrorCode.INVALID_INPUT, "lat と lng を1つずつ指定してください"
        ) from error


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data", required=True, type=Path, help="変換済みDEMのパス")
    parser.add_argument("--port", type=int, default=8787)
    args = parser.parse_args()

    server = ThreadingHTTPServer(("127.0.0.1", args.port), make_handler(args.data))
    print(f"http://127.0.0.1:{args.port}/api/forecast?lat=35.6812&lng=139.7671")
    try:
        server.serve_forever()
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
