"""Small Cloud Run-oriented Gunicorn configuration."""

from __future__ import annotations

import os
import time
from pathlib import Path
from typing import Any

from api.server import log_event, validate_dem_root

bind = f"0.0.0.0:{os.environ.get('PORT', '8080')}"
workers = 1
threads = 1
timeout = 0
graceful_timeout = 9
control_socket_disable = True
accesslog = None
errorlog = "-"


def pre_request(_worker: Any, request: Any) -> None:
    request._yuyake_started_at = time.monotonic()


def post_request(
    _worker: Any,
    request: Any,
    _environ: dict[str, Any],
    response: Any,
) -> None:
    started_at = request._yuyake_started_at
    log_event(
        "INFO",
        "request_completed",
        method=request.method,
        path=request.path,
        status=response.status_code,
        duration_ms=round((time.monotonic() - started_at) * 1000),
    )


def on_starting(_server: Any) -> None:
    dem_root = os.environ.get("DEM_ROOT")
    if dem_root is None:
        log_event("CRITICAL", "startup_failed", reason="dem_root_not_configured")
        raise RuntimeError("DEM_ROOT is required")
    try:
        validate_dem_root(Path(dem_root))
    except (KeyError, OSError, TypeError, ValueError) as error:
        log_event(
            "CRITICAL",
            "startup_failed",
            reason="dem_data_unavailable",
            error_type=type(error).__name__,
        )
        raise


def when_ready(_server: Any) -> None:
    log_event(
        "INFO",
        "server_started",
        host="0.0.0.0",
        port=int(os.environ.get("PORT", "8080")),
        dem_root=os.environ["DEM_ROOT"],
    )


def on_exit(_server: Any) -> None:
    log_event("INFO", "server_stopped")
