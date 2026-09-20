#!/usr/bin/env python3
"""Serve the local integrated sunset forecast API."""

from __future__ import annotations

import argparse
import json
import os
import signal
import sys
import threading
import time
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).parents[1]))

from api.application import ApiError, ApiErrorCode, evaluate_location
from terrain.scripts.dem_store import LocalDemStore

ERROR_STATUSES = {
    ApiErrorCode.INVALID_INPUT: HTTPStatus.BAD_REQUEST,
    ApiErrorCode.WEATHER_UNAVAILABLE: HTTPStatus.BAD_GATEWAY,
    ApiErrorCode.DEM_UNAVAILABLE: HTTPStatus.SERVICE_UNAVAILABLE,
}
ALLOWED_METHODS = "GET, OPTIONS"


@dataclass(frozen=True)
class ServerConfig:
    """Runtime values shared by local and Cloud Run execution."""

    host: str
    port: int
    dem_root: Path


def log_event(severity: str, event: str, **details: Any) -> None:
    """Write one Cloud Logging-compatible structured event to stdout."""
    print(
        json.dumps(
            {"severity": severity, "event": event, **details},
            ensure_ascii=False,
            separators=(",", ":"),
        ),
        flush=True,
    )


def make_handler(dem_root: Path) -> type[BaseHTTPRequestHandler]:
    """Create an HTTP handler bound to one local DEM directory."""

    class ForecastHandler(BaseHTTPRequestHandler):
        def handle_one_request(self) -> None:
            self._request_started_at = time.monotonic()
            super().handle_one_request()

        def do_GET(self) -> None:
            parsed = urlparse(self.path)
            if parsed.path != "/api/forecast":
                self._send_error(
                    HTTPStatus.NOT_FOUND, "not_found", "APIが見つかりません"
                )
                return

            try:
                status, payload = forecast_response(parsed.query, dem_root)
            except Exception:
                log_event("ERROR", "forecast_unexpected_failure")
                raise

            self._send_json(status, payload)

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

        def _method_not_allowed(self) -> None:
            if urlparse(self.path).path != "/api/forecast":
                self._send_error(
                    HTTPStatus.NOT_FOUND,
                    "not_found",
                    "APIが見つかりません",
                    include_body=self.command != "HEAD",
                )
                return
            status, payload = method_not_allowed_response()
            self._send_json(
                status,
                payload,
                include_body=self.command != "HEAD",
                extra_headers=(("Allow", ALLOWED_METHODS),),
            )

        do_CONNECT = _method_not_allowed
        do_DELETE = _method_not_allowed
        do_HEAD = _method_not_allowed
        do_PATCH = _method_not_allowed
        do_POST = _method_not_allowed
        do_PUT = _method_not_allowed
        do_TRACE = _method_not_allowed

        def _send_error(
            self,
            status: HTTPStatus,
            code: str,
            message: str,
            *,
            include_body: bool = True,
        ) -> None:
            self._send_json(
                status,
                {"error": {"code": code, "message": message}},
                include_body=include_body,
            )

        def _send_json(
            self,
            status: HTTPStatus,
            payload: dict[str, Any],
            *,
            include_body: bool = True,
            extra_headers: Sequence[tuple[str, str]] = (),
        ) -> None:
            body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            self.send_response(status)
            self._send_common_headers()
            for name, value in extra_headers:
                self.send_header(name, value)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            if include_body:
                self.wfile.write(body)

        def _send_common_headers(self) -> None:
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("Access-Control-Allow-Methods", ALLOWED_METHODS)
            self.send_header("Access-Control-Allow-Headers", "Content-Type")
            self.send_header("Cache-Control", "no-store")

        def log_request(self, code: int | str = "-", size: int | str = "-") -> None:
            started_at = getattr(self, "_request_started_at", time.monotonic())
            log_event(
                "INFO",
                "request_completed",
                method=getattr(self, "command", None),
                path=urlparse(getattr(self, "path", "")).path,
                status=int(code) if isinstance(code, (int, HTTPStatus)) else code,
                duration_ms=round((time.monotonic() - started_at) * 1000, 1),
            )

        def log_error(self, format: str, *args: Any) -> None:
            log_event("ERROR", "http_server_error", message=format % args)

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


def forecast_response(query: str, dem_root: Path) -> tuple[HTTPStatus, dict[str, Any]]:
    """Evaluate one query and preserve the public success/error contract."""
    try:
        latitude, longitude = _parse_coordinates(query)
        return (
            HTTPStatus.OK,
            evaluate_location(latitude, longitude, dem_root=dem_root),
        )
    except ApiError as error:
        payload = {"code": error.code.value, "message": str(error)}
        if error.reason is not None:
            payload["reason"] = error.reason.value
        log_event(
            "WARNING",
            "forecast_failed",
            code=error.code.value,
            reason=error.reason.value if error.reason is not None else None,
        )
        return ERROR_STATUSES[error.code], {"error": payload}


def method_not_allowed_response() -> tuple[HTTPStatus, dict[str, Any]]:
    """Return the stable response shared by local and hosted entrypoints."""
    return HTTPStatus.METHOD_NOT_ALLOWED, {
        "error": {
            "code": "method_not_allowed",
            "message": "GET または OPTIONS を使用してください",
        }
    }


def parse_server_config(
    argv: Sequence[str] | None = None,
    *,
    environ: Mapping[str, str] | None = None,
) -> ServerConfig:
    """Read CLI flags with environment-variable defaults for hosted execution."""
    environment = os.environ if environ is None else environ
    parser = argparse.ArgumentParser(description=__doc__)
    dem_root = environment.get("DEM_ROOT")
    parser.add_argument(
        "--data",
        default=dem_root,
        required=dem_root is None,
        type=Path,
        help="変換済みDEMのパス（既定: DEM_ROOT）",
    )
    parser.add_argument(
        "--host",
        default=environment.get("HOST", "127.0.0.1"),
        help="待受アドレス（既定: HOST または 127.0.0.1）",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=environment.get("PORT", "8787"),
        help="待受ポート（既定: PORT または 8787）",
    )
    args = parser.parse_args(argv)
    if not args.host:
        parser.error("host は空にできません")
    if not 1 <= args.port <= 65535:
        parser.error("port は1から65535の範囲で指定してください")
    return ServerConfig(args.host, args.port, args.data)


def validate_dem_root(dem_root: Path) -> None:
    store = LocalDemStore(dem_root)
    store.close()


def serve(config: ServerConfig) -> None:
    """Validate runtime data, serve requests, and stop cleanly on signals."""
    try:
        validate_dem_root(config.dem_root)
    except (KeyError, OSError, TypeError, ValueError) as error:
        log_event(
            "CRITICAL",
            "startup_failed",
            reason="dem_data_unavailable",
            error_type=type(error).__name__,
        )
        raise SystemExit(1) from error

    server = ThreadingHTTPServer(
        (config.host, config.port), make_handler(config.dem_root)
    )
    shutdown_started = threading.Event()

    def request_shutdown(signum: int, _frame: Any) -> None:
        if shutdown_started.is_set():
            return
        shutdown_started.set()
        log_event(
            "INFO",
            "shutdown_requested",
            signal=signal.Signals(signum).name,
        )
        threading.Thread(target=server.shutdown, daemon=True).start()

    signal.signal(signal.SIGINT, request_shutdown)
    signal.signal(signal.SIGTERM, request_shutdown)

    log_event(
        "INFO",
        "server_started",
        host=config.host,
        port=server.server_port,
        dem_root=str(config.dem_root),
    )
    try:
        server.serve_forever()
    finally:
        server.server_close()
        log_event("INFO", "server_stopped")


def main() -> None:
    config = parse_server_config()
    serve(config)


if __name__ == "__main__":
    main()
