use anyhow::{Result, bail};
use async_trait::async_trait;
use chrono::{DateTime, Duration, NaiveDate, Utc};
use forecast_recorder::{
    astronomy,
    service::{self, Backend, Location, Record, Reservation},
    weather::{self, Forecast},
};
use std::sync::Mutex;

#[derive(Default)]
struct State {
    reservation: Option<Reservation>,
    record: Option<serde_json::Value>,
    fetches: usize,
    fail_fetch: bool,
    lose_save_response: bool,
}
struct Fake {
    location: Location,
    state: Mutex<State>,
}
impl Fake {
    fn new() -> Self {
        Self {
            location: Location {
                name: "test location".into(),
                latitude: 35.6812,
                longitude: 139.7671,
                enabled: true,
            },
            state: Mutex::new(State::default()),
        }
    }
}
#[async_trait]
impl Backend for Fake {
    async fn location(&self) -> Result<Location> {
        Ok(self.location.clone())
    }
    async fn exists(&self, _: &str) -> Result<bool> {
        Ok(self.state.lock().unwrap().record.is_some())
    }
    async fn reserve(&self, r: &Reservation) -> Result<bool> {
        let mut state = self.state.lock().unwrap();
        if state.reservation.is_some() {
            return Ok(false);
        }
        state.reservation = Some(r.clone());
        Ok(true)
    }
    async fn forecast(&self, _: &Location, sunset: DateTime<Utc>) -> Result<Forecast> {
        let mut state = self.state.lock().unwrap();
        state.fetches += 1;
        if state.fail_fetch {
            bail!("simulated weather failure");
        }
        let payload = serde_json::from_str(include_str!(
            "../../weather/tests/fixtures/open_meteo_forecast.json"
        ))?;
        weather::evaluate(
            payload,
            sunset,
            sunset + Duration::seconds(2),
            "jma_seamless",
        )
    }
    async fn create(&self, _: &str, record: &Record) -> Result<bool> {
        let mut state = self.state.lock().unwrap();
        if state.record.is_some() {
            return Ok(false);
        }
        state.record = Some(serde_json::to_value(record)?);
        if state.lose_save_response {
            bail!("simulated lost response");
        }
        Ok(true)
    }
}
fn reservation(fake: &Fake) -> Reservation {
    let day = NaiveDate::from_ymd_opt(2026, 8, 16).unwrap();
    Reservation {
        target_date: day,
        sunset_at: astronomy::sunset(day, fake.location.latitude, fake.location.longitude).unwrap(),
        location: fake.location.clone(),
    }
}
#[tokio::test]
async fn reservations_are_idempotent_and_stop_after_sunset() {
    let fake = Fake::new();
    let r = reservation(&fake);
    let morning = r.sunset_at - Duration::hours(10);
    assert_eq!(
        service::schedule(&fake, morning).await.unwrap(),
        "scheduled"
    );
    assert_eq!(
        service::schedule(&fake, morning + Duration::minutes(30))
            .await
            .unwrap(),
        "already_scheduled"
    );
    assert_eq!(
        service::schedule(&fake, r.sunset_at).await.unwrap(),
        "reservation_expired"
    );
}
#[tokio::test]
async fn lost_success_response_does_not_overwrite_or_refetch() {
    let fake = Fake::new();
    let r = reservation(&fake);
    fake.state.lock().unwrap().lose_save_response = true;
    assert!(
        service::collect(&fake, r.clone(), r.sunset_at)
            .await
            .is_err()
    );
    let before = fake.state.lock().unwrap().record.clone().unwrap();
    assert_eq!(
        service::collect(&fake, r.clone(), r.sunset_at + Duration::minutes(10))
            .await
            .unwrap(),
        "already_saved"
    );
    let state = fake.state.lock().unwrap();
    assert_eq!(state.fetches, 1);
    assert_eq!(state.record.as_ref().unwrap(), &before);
    assert_eq!(before["observation"], serde_json::Value::Null);
    assert_eq!(before["location"]["name"], "test location");
    assert!(before["forecast"]["weather"]["hours"].is_array());
}
#[tokio::test]
async fn failed_fetch_leaves_no_partial_record_and_can_retry() {
    let fake = Fake::new();
    let r = reservation(&fake);
    fake.state.lock().unwrap().fail_fetch = true;
    assert!(
        service::collect(&fake, r.clone(), r.sunset_at)
            .await
            .is_err()
    );
    assert!(fake.state.lock().unwrap().record.is_none());
    fake.state.lock().unwrap().fail_fetch = false;
    assert_eq!(
        service::collect(&fake, r.clone(), r.sunset_at + Duration::minutes(10))
            .await
            .unwrap(),
        "saved"
    );
}
#[tokio::test]
async fn rejects_early_invalid_and_stale_tasks_and_honors_disabled_locations() {
    let mut fake = Fake::new();
    let r = reservation(&fake);
    assert!(
        service::collect(&fake, r.clone(), r.sunset_at - Duration::seconds(1))
            .await
            .is_err()
    );
    let mut bad = r.clone();
    bad.sunset_at += Duration::minutes(1);
    assert!(service::collect(&fake, bad, r.sunset_at).await.is_err());
    assert_eq!(
        service::collect(&fake, r.clone(), r.sunset_at + Duration::days(1))
            .await
            .unwrap(),
        "expired_date"
    );
    fake.location.enabled = false;
    assert_eq!(
        service::schedule(&fake, r.sunset_at - Duration::hours(10))
            .await
            .unwrap(),
        "disabled"
    );
    assert_eq!(
        service::collect(&fake, r.clone(), r.sunset_at)
            .await
            .unwrap(),
        "disabled"
    );
    fake.location.enabled = true;
    fake.location.latitude += 0.1;
    assert_eq!(
        service::collect(&fake, r.clone(), r.sunset_at)
            .await
            .unwrap(),
        "location_changed"
    );
    assert_eq!(fake.state.lock().unwrap().fetches, 0);
}
