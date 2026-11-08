"""Regenerate reference fixtures from repository root; not used at runtime or in CI.

Run: PYTHONPATH=. python3 recorder/tests/generate_reference.py
"""
import copy
import json
from datetime import date, datetime
from pathlib import Path

from terrain.scripts.astronomy import sunset_on
from weather.scripts.open_meteo import _parse_hourly
from weather.scripts.scoring import score_weather
from weather.scripts.sunset_window import select_sunset_window

sunsets = []
for latitude, longitude in [(35.6812, 139.7671), (43.0687, 141.3508), (26.2124, 127.6809)]:
    for day in ["2026-01-01", "2026-03-21", "2026-06-21", "2026-11-08"]:
        sunsets.append({
            "date": day,
            "latitude": latitude,
            "longitude": longitude,
            "sunset": sunset_on(date.fromisoformat(day), latitude, longitude).time.isoformat(),
        })

fixture = Path("weather/tests/fixtures/open_meteo_forecast.json")
payload = json.loads(fixture.read_text())
weather = []
for case in range(12):
    sample = copy.deepcopy(payload)
    for name, values in sample["hourly"].items():
        if name == "time":
            continue
        for index in range(len(values)):
            if "cloud" in name or "humidity" in name:
                values[index] = (case * 19 + index * 7) % 101
            elif name == "visibility":
                values[index] = (case * 3900 + index * 1000) % 40000
            elif name == "precipitation":
                values[index] = (case % 4) * 0.3
            else:
                values[index] = case * 1.5
    day = sample["hourly"]["time"][0][:10]
    minute = [0, 20, 35, 34][case % 4]
    moment = datetime.fromisoformat(day + f"T18:{minute:02}:00+09:00")
    window = select_sunset_window(moment, _parse_hourly(sample))
    scores = score_weather(window.hours)
    weather.append({
        "sunset": moment.isoformat(),
        "payload": sample,
        "gradient": scores.gradient.score,
        "dramatic": scores.dramatic.score,
        "count": len(window.hours),
    })

Path("recorder/tests/fixtures/python-reference.json").write_text(
    json.dumps({"sunsets": sunsets, "weather": weather}, ensure_ascii=False, indent=2) + "\n"
)
