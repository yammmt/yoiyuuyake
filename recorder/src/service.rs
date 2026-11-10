//! Orchestration is separated from network calls so retry behavior is testable offline.
use crate::{
    astronomy::{jst, sunset},
    weather::Forecast,
};
use anyhow::{Result, ensure};
use async_trait::async_trait;
use chrono::{DateTime, NaiveDate, Utc};
use serde::{Deserialize, Serialize};

#[derive(Clone, Debug, Serialize, Deserialize, PartialEq)]
#[serde(deny_unknown_fields)]
pub struct Location {
    pub name: String,
    pub latitude: f64,
    pub longitude: f64,
    pub enabled: bool,
}
impl Location {
    pub fn validate(&self, day: NaiveDate) -> Result<()> {
        ensure!(
            !self.name.trim().is_empty() && self.name.len() <= 500,
            "invalid location name"
        );
        sunset(day, self.latitude, self.longitude)?;
        Ok(())
    }
}

#[derive(Clone, Debug, Serialize, Deserialize)]
#[serde(rename_all = "camelCase", deny_unknown_fields)]
pub struct Reservation {
    pub target_date: NaiveDate,
    pub sunset_at: DateTime<Utc>,
    pub location: Location,
}

#[derive(Clone, Debug, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct Record {
    pub schema_version: u32,
    pub location_id: &'static str,
    pub location: Location,
    pub target_date: NaiveDate,
    pub sunset_at: DateTime<Utc>,
    pub forecast: Forecast,
    pub observation: Option<()>,
}

#[async_trait]
pub trait Backend: Send + Sync {
    async fn location(&self) -> Result<Location>;
    async fn exists(&self, id: &str) -> Result<bool>;
    /// Return false on ALREADY_EXISTS, including after a lost success response.
    async fn reserve(&self, reservation: &Reservation) -> Result<bool>;
    async fn forecast(&self, location: &Location, sunset: DateTime<Utc>) -> Result<Forecast>;
    async fn create(&self, id: &str, record: &Record) -> Result<bool>;
}

pub fn record_id(day: NaiveDate) -> String {
    format!("home_{day}")
}

pub async fn schedule(backend: &dyn Backend, now: DateTime<Utc>) -> Result<&'static str> {
    let day = now.with_timezone(&jst()).date_naive();
    let location = backend.location().await?;
    location.validate(day)?;
    if !location.enabled {
        return Ok("disabled");
    }
    if backend.exists(&record_id(day)).await? {
        return Ok("already_saved");
    }
    let sunset_at = sunset(day, location.latitude, location.longitude)?;
    // A delayed morning retry must not turn into an immediate, late forecast fetch.
    if now >= sunset_at {
        return Ok("reservation_expired");
    }
    let reservation = Reservation {
        target_date: day,
        sunset_at,
        location,
    };
    Ok(if backend.reserve(&reservation).await? {
        "scheduled"
    } else {
        "already_scheduled"
    })
}

pub async fn collect(
    backend: &dyn Backend,
    reservation: Reservation,
    now: DateTime<Utc>,
) -> Result<&'static str> {
    ensure!(
        reservation.target_date == reservation.sunset_at.with_timezone(&jst()).date_naive(),
        "inconsistent target date"
    );
    reservation.location.validate(reservation.target_date)?;
    let computed = sunset(
        reservation.target_date,
        reservation.location.latitude,
        reservation.location.longitude,
    )?;
    ensure!(
        (computed - reservation.sunset_at).num_milliseconds().abs() <= 1,
        "inconsistent sunset"
    );
    let id = record_id(reservation.target_date);
    if backend.exists(&id).await? {
        return Ok("already_saved");
    }
    if now.with_timezone(&jst()).date_naive() != reservation.target_date {
        return Ok("expired_date");
    }
    ensure!(now >= reservation.sunset_at, "collection before sunset");
    let current = backend.location().await?;
    // A pending task cannot collect a disabled or changed location; changes apply tomorrow.
    if !current.enabled {
        return Ok("disabled");
    }
    if current != reservation.location {
        return Ok("location_changed");
    }
    let forecast = backend
        .forecast(&reservation.location, reservation.sunset_at)
        .await?;
    ensure!(
        forecast.fetched_at.with_timezone(&jst()).date_naive() == reservation.target_date,
        "forecast fetched on wrong day"
    );
    let record = Record {
        schema_version: 1,
        location_id: "home",
        location: reservation.location,
        target_date: reservation.target_date,
        sunset_at: reservation.sunset_at,
        forecast,
        observation: None,
    };
    Ok(if backend.create(&id, &record).await? {
        "saved"
    } else {
        "already_saved"
    })
}
