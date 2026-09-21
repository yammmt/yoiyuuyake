"""WSGI adapter for the Cloud Run forecast API."""

from __future__ import annotations

import json
import os
from http import HTTPStatus
from pathlib import Path
from typing import Any

from api.server import (
    ALLOWED_METHODS,
    forecast_response,
    log_event,
    method_not_allowed_response,
)

COMMON_HEADERS = (
    ("Access-Control-Allow-Origin", "*"),
    ("Access-Control-Allow-Methods", ALLOWED_METHODS),
    ("Access-Control-Allow-Headers", "Content-Type"),
    ("Cache-Control", "no-store"),
)


def application(environ: dict[str, Any], start_response: Any) -> list[bytes]:
    """Serve the existing API contract through a production WSGI server."""
    method = environ.get("REQUEST_METHOD", "")
    path = environ.get("PATH_INFO", "")

    if path != "/api/forecast":
        return _json_response(
            start_response,
            HTTPStatus.NOT_FOUND,
            {"error": {"code": "not_found", "message": "APIが見つかりません"}},
        )
    if method == "OPTIONS":
        start_response(
            f"{HTTPStatus.NO_CONTENT.value} {HTTPStatus.NO_CONTENT.phrase}",
            [*COMMON_HEADERS, ("Content-Length", "0")],
        )
        return [b""]
    if method != "GET":
        status, payload = method_not_allowed_response()
        return _json_response(
            start_response,
            status,
            payload,
            extra_headers=(("Allow", ALLOWED_METHODS),),
        )

    try:
        query = environ.get("QUERY_STRING", "")
        status, payload = forecast_response(query, _dem_root())
        return _json_response(start_response, status, payload)
    except Exception:
        log_event("ERROR", "forecast_unexpected_failure")
        raise


def _dem_root() -> Path:
    value = os.environ.get("DEM_ROOT")
    if value is None:
        raise RuntimeError("DEM_ROOT is required")
    return Path(value)


def _json_response(
    start_response: Any,
    status: HTTPStatus,
    payload: dict[str, Any],
    *,
    extra_headers: tuple[tuple[str, str], ...] = (),
) -> list[bytes]:
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    start_response(
        f"{status.value} {status.phrase}",
        [
            *COMMON_HEADERS,
            *extra_headers,
            ("Content-Type", "application/json; charset=utf-8"),
            ("Content-Length", str(len(body))),
        ],
    )
    return [body]
