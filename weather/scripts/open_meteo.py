"""Fetch and validate today's hourly sunset-weather inputs from Open-Meteo."""
from __future__ import annotations
import json
from dataclasses import dataclass
from datetime import datetime
from typing import Callable
from urllib.parse import urlencode
from urllib.request import urlopen

ENDPOINT = "https://api.open-meteo.com/v1/forecast"
HOURLY_VARIABLES = ("cloud_cover_low", "cloud_cover_mid", "cloud_cover_high", "cloud_cover", "visibility", "relative_humidity_2m", "precipitation", "wind_speed_10m")

class OpenMeteoError(RuntimeError): pass

@dataclass(frozen=True)
class WeatherHour:
    time: datetime
    cloud_cover_low: float; cloud_cover_mid: float; cloud_cover_high: float; cloud_cover: float
    visibility: float; relative_humidity: float; precipitation: float; wind_speed: float

def build_forecast_url(latitude: float, longitude: float, *, model: str | None = "jma_seamless") -> str:
    parameters={"latitude":latitude,"longitude":longitude,"timezone":"Asia/Tokyo","forecast_days":1,"hourly":",".join(HOURLY_VARIABLES)}
    if model: parameters["models"]=model
    query=urlencode(parameters)
    return f"{ENDPOINT}?{query}"

def fetch_today_forecast(latitude: float, longitude: float, *, opener: Callable = urlopen, timeout: float = 10) -> tuple[WeatherHour,...]:
    if not -90 <= latitude <= 90 or not -180 <= longitude <= 180: raise ValueError("緯度・経度が不正です")
    try:
        payload=_request(latitude,longitude,"jma_seamless",opener,timeout)
        if _has_missing_values(payload): payload=_request(latitude,longitude,None,opener,timeout)
    except OpenMeteoError: raise
    except Exception as error: raise OpenMeteoError("Open-Meteoの取得に失敗しました") from error
    hourly=payload.get("hourly")
    if not isinstance(hourly,dict): raise OpenMeteoError("Open-Meteoの時間別予報がありません")
    values={name:hourly.get(name) for name in ("time",)+HOURLY_VARIABLES}
    if any(not isinstance(value,list) for value in values.values()): raise OpenMeteoError("必要な時間別予報が欠けています")
    length=len(values["time"])
    if length == 0 or any(len(value)!=length for value in values.values()): raise OpenMeteoError("時間別予報の配列長が不正です")
    try:
        return tuple(WeatherHour(datetime.fromisoformat(values["time"][i]), *[float(values[name][i]) for name in HOURLY_VARIABLES]) for i in range(length))
    except (TypeError,ValueError) as error: raise OpenMeteoError("時間別予報の値が不正です") from error

def _request(latitude, longitude, model, opener, timeout):
    with opener(build_forecast_url(latitude,longitude,model=model), timeout=timeout) as response:
        if response.status != 200: raise OpenMeteoError(f"Open-Meteo HTTP {response.status}")
        return json.load(response)
def _has_missing_values(payload):
    hourly=payload.get("hourly",{});
    return any(any(value is None for value in hourly.get(name,[])) for name in HOURLY_VARIABLES)
