#!/usr/bin/env python3
"""Serve fixed terrain regression measurements for an authenticated cloud experiment."""

from __future__ import annotations

import argparse
import json
import os
import resource
import sys
import traceback
import uuid
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from time import perf_counter

from dem_store import LocalDemStore
from validate_locations import _validate_case


def run_benchmark(data: Path, cases: list[dict]) -> dict:
    started = perf_counter()
    measurements = []
    for case in cases:
        case_started = perf_counter()
        store = LocalDemStore(data)
        initialized = perf_counter()
        try:
            passed, message = _validate_case(store, case)
            evaluated = perf_counter()
        finally:
            store.close()
        measurements.append({
            "id": case["id"],
            "passed": passed,
            "result": message,
            "store_init_seconds": initialized - case_started,
            "evaluation_seconds": evaluated - initialized,
            "total_seconds": perf_counter() - case_started,
        })
    peak_rss = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    return {
        "passed": all(item["passed"] for item in measurements),
        "cases": measurements,
        "total_seconds": perf_counter() - started,
        "process_peak_rss_bytes": peak_rss if sys.platform == "darwin" else peak_rss * 1024,
        "python_version": sys.version,
        "store_lifetime": "one_per_case",
    }


def make_handler(data: Path, cases: list[dict]) -> type[BaseHTTPRequestHandler]:
    process_id = str(uuid.uuid4())
    sequence = 0

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            nonlocal sequence
            if self.path != "/benchmark":
                self.send_error(404)
                return
            sequence += 1
            try:
                result = run_benchmark(data, cases)
                status = 200 if result["passed"] else 500
            except Exception:
                traceback.print_exc()
                result = {"passed": False, "error": "benchmark_failed"}
                status = 500
            result.update(process_id=process_id, request_sequence=sequence)
            payload = json.dumps(result, ensure_ascii=False).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(payload)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(payload)

    return Handler


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data", type=Path, default=Path(os.environ.get("DEM_ROOT", "/dem/derived-dem10b-kanto-v1")))
    parser.add_argument("--cases", type=Path, default=Path("terrain/validation/locations-kanto.json"))
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=int(os.environ.get("PORT", "8080")))
    args = parser.parse_args()
    cases = json.loads(args.cases.read_text(encoding="utf-8"))["locations"]
    if not cases:
        parser.error("検証地点が空です")
    server = HTTPServer((args.host, args.port), make_handler(args.data, cases))
    print(f"Benchmark server listening on {args.host}:{server.server_port}", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
