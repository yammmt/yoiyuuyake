//! Input selection and scores match weather/scripts; this is not observed weather.
use crate::astronomy::jst;
use anyhow::{Context, Result, bail, ensure};
use chrono::{DateTime, Duration, NaiveDateTime, TimeZone, Timelike, Utc};
use serde::{Deserialize, Serialize};
use serde_json::Value;
use std::collections::{BTreeMap, BTreeSet};

pub const SCORE_VERSION: &str = "weather-rules-v1";
pub const VARIABLES: [&str; 8] = [
    "cloud_cover_low",
    "cloud_cover_mid",
    "cloud_cover_high",
    "cloud_cover",
    "visibility",
    "relative_humidity_2m",
    "precipitation",
    "wind_speed_10m",
];
pub const UNITS: [&str; 8] = ["%", "%", "%", "%", "m", "%", "mm", "km/h"];

#[derive(Clone, Debug, Serialize, Deserialize)]
pub struct WeatherHour {
    pub time: DateTime<Utc>,
    #[serde(flatten)]
    pub values: BTreeMap<String, f64>,
}

#[derive(Clone, Debug, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct Forecast {
    pub fetched_at: DateTime<Utc>,
    pub source: String,
    /// Requested selection, not a claim about the actual grid model used by best_match.
    pub model: String,
    pub weather: WeatherWindow,
    pub score_version: String,
    pub gradient: u32,
    pub dramatic: u32,
}

#[derive(Clone, Debug, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct WeatherWindow {
    pub starts_at: DateTime<Utc>,
    pub ends_at: DateTime<Utc>,
    pub units: BTreeMap<String, String>,
    pub hours: Vec<WeatherHour>,
}

pub fn has_nulls(payload: &Value) -> bool {
    VARIABLES.iter().any(|key| {
        payload["hourly"][key]
            .as_array()
            .is_some_and(|a| a.iter().any(Value::is_null))
    })
}

pub fn evaluate(
    payload: Value,
    sunset: DateTime<Utc>,
    fetched_at: DateTime<Utc>,
    model: &str,
) -> Result<Forecast> {
    ensure!(
        payload["utc_offset_seconds"].as_i64() == Some(32400),
        "unexpected forecast timezone"
    );
    let times = payload["hourly"]["time"]
        .as_array()
        .context("missing forecast times")?;
    ensure!(!times.is_empty(), "empty forecast");
    let mut units = BTreeMap::new();
    for (key, expected) in VARIABLES.iter().zip(UNITS) {
        ensure!(
            payload["hourly"][key]
                .as_array()
                .is_some_and(|a| a.len() == times.len()),
            "invalid forecast array: {key}"
        );
        ensure!(
            payload["hourly_units"][key].as_str() == Some(expected),
            "unexpected unit: {key}"
        );
        units.insert(key.to_string(), expected.to_string());
    }
    let mut hours = BTreeMap::new();
    let mut seen = BTreeSet::new();
    for (i, time) in times.iter().enumerate() {
        let local = NaiveDateTime::parse_from_str(
            time.as_str().context("invalid time")?,
            "%Y-%m-%dT%H:%M",
        )?;
        ensure!(local.minute() == 0, "forecast time is not on hour");
        let time = jst()
            .from_local_datetime(&local)
            .unwrap()
            .with_timezone(&Utc);
        ensure!(seen.insert(time), "duplicate forecast hour");
        let mut values = BTreeMap::new();
        for (index, key) in VARIABLES.iter().enumerate() {
            let value = payload["hourly"][key][i]
                .as_f64()
                .context("non-numeric weather value")?;
            ensure!(
                value.is_finite()
                    && value >= 0.0
                    && (!(index <= 3 || index == 5) || value <= 100.0),
                "out of range weather value: {key}"
            );
            values.insert(key.to_string(), value);
        }
        hours.insert(time, WeatherHour { time, values });
    }
    let starts_at = sunset - Duration::minutes(20);
    let ends_at = sunset + Duration::minutes(25);
    let floor = |t: DateTime<Utc>| {
        t.with_minute(0)
            .unwrap()
            .with_second(0)
            .unwrap()
            .with_nanosecond(0)
            .unwrap()
    };
    let mut cursor = floor(starts_at);
    let last = if ends_at == floor(ends_at) {
        ends_at
    } else {
        floor(ends_at) + Duration::hours(1)
    };
    let mut selected = Vec::new();
    while cursor <= last {
        match hours.remove(&cursor) {
            Some(hour) => selected.push(hour),
            None => bail!("incomplete sunset window"),
        }
        cursor += Duration::hours(1);
    }
    let (gradient, dramatic) = score(&selected);
    Ok(Forecast {
        fetched_at,
        source: "Open-Meteo".into(),
        model: model.into(),
        weather: WeatherWindow {
            starts_at,
            ends_at,
            units,
            hours: selected,
        },
        score_version: SCORE_VERSION.into(),
        gradient,
        dramatic,
    })
}

fn score(hours: &[WeatherHour]) -> (u32, u32) {
    let average = |key: &str| hours.iter().map(|h| h.values[key]).sum::<f64>() / hours.len() as f64;
    let ramp = |value: f64, min: f64, max: f64| ((value - min) / (max - min)).clamp(0.0, 1.0);
    let low = 1.0 - average("cloud_cover_low") / 100.0;
    let mid = average("cloud_cover_mid") / 100.0;
    let high = average("cloud_cover_high") / 100.0;
    let total = 1.0 - average("cloud_cover") / 100.0;
    let visibility = ramp(average("visibility"), 5000.0, 25000.0);
    let dry = 1.0 - ramp(average("relative_humidity_2m"), 40.0, 90.0);
    let rain = 1.0 - ramp(average("precipitation"), 0.0, 1.0);
    let wind = 1.0 - ramp(average("wind_speed_10m"), 5.0, 15.0);
    let gradient =
        low * 30.0 + total * 15.0 + visibility * 20.0 + dry * 10.0 + rain * 20.0 + wind * 5.0;
    let dramatic = low * 20.0
        + band(mid, 0.05, 0.30, 0.60, 0.95) * 20.0
        + band(high, 0.05, 0.35, 0.70, 0.95) * 20.0
        + band(1.0 - total, 0.10, 0.30, 0.70, 0.95) * 10.0
        + visibility * 10.0
        + rain * 15.0
        + dry * 3.0
        + wind * 2.0;
    (
        gradient.round().clamp(0.0, 100.0) as u32,
        dramatic.round().clamp(0.0, 100.0) as u32,
    )
}

fn band(value: f64, below: f64, from: f64, to: f64, above: f64) -> f64 {
    if value <= below || value >= above {
        0.0
    } else if value < from {
        (value - below) / (from - below)
    } else if value <= to {
        1.0
    } else {
        (above - value) / (above - to)
    }
}
