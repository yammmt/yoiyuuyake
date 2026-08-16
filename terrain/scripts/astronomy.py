"""Offline solar-position calculations for Japan Standard Time."""
from __future__ import annotations
import math
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

JST = ZoneInfo("Asia/Tokyo")
STANDARD_SUNSET_ZENITH = 90.833  # solar radius + standard refraction

@dataclass(frozen=True)
class SolarPosition:
    time: datetime
    altitude_degrees: float
    azimuth_degrees: float

def sunset_on(day: date, latitude: float, longitude: float) -> SolarPosition:
    """Return conventional sunset (upper limb at -0.833°) in JST."""
    noon = datetime(day.year, day.month, day.day, 12, tzinfo=JST)
    declination, equation = _solar_terms(noon)
    cos_hour_angle = (math.cos(math.radians(STANDARD_SUNSET_ZENITH)) / (math.cos(math.radians(latitude))*math.cos(math.radians(declination))) - math.tan(math.radians(latitude))*math.tan(math.radians(declination)))
    if not -1 <= cos_hour_angle <= 1: raise ValueError("この地点・日付では日没を計算できません")
    hour_angle = math.degrees(math.acos(cos_hour_angle))
    minutes = 720 - 4 * longitude - equation + 9 * 60 + 4 * hour_angle
    moment = datetime(day.year, day.month, day.day, tzinfo=JST) + timedelta(minutes=minutes)
    return solar_position(moment, latitude, longitude)

def solar_position(moment: datetime, latitude: float, longitude: float) -> SolarPosition:
    if moment.tzinfo is None: raise ValueError("時刻にはタイムゾーンが必要です")
    local = moment.astimezone(JST); declination, equation = _solar_terms(local)
    minutes = local.hour*60 + local.minute + local.second/60 + local.microsecond/60_000_000
    hour_angle = (minutes + equation + 4*longitude - 540) / 4 - 180
    if hour_angle > 180: hour_angle -= 360
    lat, dec, hour = map(math.radians, (latitude, declination, hour_angle))
    altitude = math.degrees(math.asin(math.sin(lat)*math.sin(dec)+math.cos(lat)*math.cos(dec)*math.cos(hour)))
    azimuth = (math.degrees(math.atan2(math.sin(hour), math.cos(hour)*math.sin(lat)-math.tan(dec)*math.cos(lat)))+180) % 360
    return SolarPosition(local, altitude, azimuth)

def _solar_terms(moment: datetime) -> tuple[float,float]:
    utc=moment.astimezone(timezone.utc); jd=utc.timestamp()/86400+2440587.5; t=(jd-2451545)/36525
    l=(280.46646+t*(36000.76983+t*.0003032))%360; m=357.52911+t*(35999.05029-.0001537*t); e=.016708634-t*(.000042037+.0000001267*t)
    c=math.sin(math.radians(m))*(1.914602-t*(.004817+.000014*t))+math.sin(math.radians(2*m))*(.019993-.000101*t)+math.sin(math.radians(3*m))*.000289
    omega=125.04-1934.136*t; apparent=l+c-.00569-.00478*math.sin(math.radians(omega)); obliq=23+(26+((21.448-t*(46.815+t*(.00059-t*.001813)))/60))/60+.00256*math.cos(math.radians(omega))
    decl=math.degrees(math.asin(math.sin(math.radians(obliq))*math.sin(math.radians(apparent)))); y=math.tan(math.radians(obliq)/2)**2
    eq=4*math.degrees(y*math.sin(2*math.radians(l))-2*e*math.sin(math.radians(m))+4*e*y*math.sin(math.radians(m))*math.cos(2*math.radians(l))-.5*y*y*math.sin(4*math.radians(l))-1.25*e*e*math.sin(2*math.radians(m)))
    return decl,eq
