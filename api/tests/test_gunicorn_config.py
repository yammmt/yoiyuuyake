from __future__ import annotations

import io
import json
import runpy
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from types import SimpleNamespace


class GunicornLoggingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        config_path = Path(__file__).parents[1] / "gunicorn.conf.py"
        cls.config = runpy.run_path(str(config_path))

    def test_request_log_is_one_complete_json_event(self) -> None:
        request = SimpleNamespace(method="GET", path="/unsafe\n\x1b[31m")
        response = SimpleNamespace(status_code=200)

        output = io.StringIO()
        with redirect_stdout(output):
            self.config["pre_request"](None, request)
            self.config["post_request"](None, request, {}, response)

        lines = output.getvalue().splitlines()
        self.assertEqual(len(lines), 1)
        event = json.loads(lines[0])
        duration_ms = event.pop("duration_ms")
        self.assertEqual(
            event,
            {
                "severity": "INFO",
                "event": "request_completed",
                "method": "GET",
                "path": "/unsafe\n\x1b[31m",
                "status": 200,
            },
        )
        self.assertIsInstance(duration_ms, int)
        self.assertGreaterEqual(duration_ms, 0)


if __name__ == "__main__":
    unittest.main()
