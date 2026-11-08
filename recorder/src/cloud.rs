//! Google REST APIs use access tokens from ADC/Cloud Run metadata, never key files in the repo.
use crate::{
    service::{Backend, Location, Record, Reservation},
    weather::{self, Forecast},
};
use anyhow::{Context, Result, bail, ensure};
use async_trait::async_trait;
use base64::{Engine, engine::general_purpose::STANDARD};
use chrono::{DateTime, Utc};
use reqwest::{Client, Method, StatusCode};
use serde_json::{Value, json};
use sha2::{Digest, Sha256};
use std::{sync::Arc, time::Duration};

pub struct Cloud {
    client: Client,
    auth: Arc<dyn gcp_auth::TokenProvider>,
    pub config: Config,
    firestore: String,
    tasks: String,
    meteo: String,
}

#[derive(Clone)]
pub struct Config {
    pub project: String,
    pub region: String,
    pub queue: String,
    pub service_url: String,
    pub trigger_account: String,
}
impl Config {
    pub fn from_env() -> Result<Self> {
        let required = |key: &str| std::env::var(key).with_context(|| format!("missing {key}"));
        let result = Self {
            project: required("PROJECT_ID")?,
            region: required("TASKS_REGION")?,
            queue: required("TASKS_QUEUE")?,
            service_url: required("RECORDER_URL")?.trim_end_matches('/').into(),
            trigger_account: required("TRIGGER_SERVICE_ACCOUNT")?,
        };
        for part in [&result.project, &result.region, &result.queue] {
            ensure!(
                !part.is_empty() && part.bytes().all(|c| c.is_ascii_alphanumeric() || c == b'-'),
                "invalid resource identifier"
            );
        }
        let url = reqwest::Url::parse(&result.service_url)?;
        ensure!(
            url.scheme() == "https"
                && url.host_str().is_some_and(|h| h.ends_with(".run.app"))
                && url.path() == "/"
                && url.query().is_none()
                && url.fragment().is_none()
                && url.username().is_empty()
                && url.password().is_none(),
            "RECORDER_URL must be canonical HTTPS run.app origin"
        );
        ensure!(
            result
                .trigger_account
                .ends_with(&format!("@{}.iam.gserviceaccount.com", result.project)),
            "trigger account must belong to project"
        );
        Ok(result)
    }
}

impl Cloud {
    pub async fn new(config: Config) -> Result<Self> {
        Ok(Self {
            client: Client::builder()
                .timeout(Duration::from_secs(15))
                .redirect(reqwest::redirect::Policy::none())
                .build()?,
            auth: gcp_auth::provider().await?,
            config,
            firestore: "https://firestore.googleapis.com/v1".into(),
            tasks: "https://cloudtasks.googleapis.com/v2".into(),
            meteo: "https://api.open-meteo.com/v1/forecast".into(),
        })
    }
    fn documents(&self) -> String {
        format!(
            "{}/projects/{}/databases/(default)/documents",
            self.firestore, self.config.project
        )
    }
    async fn request(
        &self,
        method: Method,
        url: &str,
        body: Option<Value>,
    ) -> Result<reqwest::Response> {
        let token = self
            .auth
            .token(&["https://www.googleapis.com/auth/cloud-platform"])
            .await
            .context("google authentication failed")?;
        let mut request = self.client.request(method, url).bearer_auth(token.as_str());
        if let Some(body) = body {
            request = request.json(&body);
        }
        request
            .send()
            .await
            .map_err(|_| anyhow::anyhow!("google request transport failure"))
    }
    async fn weather_payload(
        &self,
        location: &Location,
        model: &str,
    ) -> Result<(Value, DateTime<Utc>)> {
        let response = self
            .client
            .get(&self.meteo)
            .query(&[
                ("latitude", location.latitude.to_string()),
                ("longitude", location.longitude.to_string()),
                ("timezone", "Asia/Tokyo".into()),
                ("forecast_days", "1".into()),
                ("hourly", weather::VARIABLES.join(",")),
                ("models", model.into()),
                ("wind_speed_unit", "kmh".into()),
                ("precipitation_unit", "mm".into()),
            ])
            .send()
            .await
            .map_err(|_| anyhow::anyhow!("weather request transport failure"))?;
        let status = response.status();
        ensure!(status == StatusCode::OK, "weather HTTP {status}");
        let payload = response
            .json()
            .await
            .map_err(|_| anyhow::anyhow!("invalid weather JSON"))?;
        Ok((payload, Utc::now()))
    }
}

#[async_trait]
impl Backend for Cloud {
    async fn location(&self) -> Result<Location> {
        let response = self
            .request(
                Method::GET,
                &format!("{}/locations/home", self.documents()),
                None,
            )
            .await?;
        ensure!(
            response.status() == StatusCode::OK,
            "location read HTTP {}",
            response.status()
        );
        let doc: Value = response.json().await?;
        let fields = &doc["fields"];
        let number = |key: &str| -> Result<f64> {
            fields[key]["doubleValue"]
                .as_f64()
                .or_else(|| {
                    fields[key]["integerValue"]
                        .as_str()
                        .and_then(|s| s.parse().ok())
                })
                .context("invalid location number")
        };
        Ok(Location {
            name: fields["name"]["stringValue"]
                .as_str()
                .context("missing location name")?
                .into(),
            latitude: number("latitude")?,
            longitude: number("longitude")?,
            enabled: fields["enabled"]["booleanValue"]
                .as_bool()
                .context("missing enabled flag")?,
        })
    }
    async fn exists(&self, id: &str) -> Result<bool> {
        let response = self
            .request(
                Method::GET,
                &format!("{}/records/{id}", self.documents()),
                None,
            )
            .await?;
        match response.status() {
            StatusCode::OK => Ok(true),
            StatusCode::NOT_FOUND => Ok(false),
            status => bail!("record read HTTP {status}"),
        }
    }
    async fn reserve(&self, reservation: &Reservation) -> Result<bool> {
        let parent = format!(
            "projects/{}/locations/{}/queues/{}",
            self.config.project, self.config.region, self.config.queue
        );
        // Hash prefix avoids sequential task IDs; same location/day always has same name.
        let hash = format!(
            "{:x}",
            Sha256::digest(format!("home_{}", reservation.target_date))
        );
        let body = json!({"task": {"name": format!("{parent}/tasks/{}-home-{}", &hash[..16], reservation.target_date),
            "scheduleTime": reservation.sunset_at.to_rfc3339(), "dispatchDeadline": "120s",
            "httpRequest": {"httpMethod": "POST", "url": format!("{}/collect", self.config.service_url),
                "headers": {"Content-Type": "application/json"}, "body": STANDARD.encode(serde_json::to_vec(reservation)?),
                "oidcToken": {"serviceAccountEmail": self.config.trigger_account, "audience": self.config.service_url}}}});
        let response = self
            .request(
                Method::POST,
                &format!("{}/{parent}/tasks", self.tasks),
                Some(body),
            )
            .await?;
        match response.status() {
            StatusCode::OK => Ok(true),
            StatusCode::CONFLICT => Ok(false),
            status => bail!("reservation create HTTP {status}"),
        }
    }
    async fn forecast(&self, location: &Location, sunset: DateTime<Utc>) -> Result<Forecast> {
        let (payload, fetched_at) = self.weather_payload(location, "jma_seamless").await?;
        if weather::has_nulls(&payload) {
            let (payload, fetched_at) = self.weather_payload(location, "best_match").await?;
            weather::evaluate(payload, sunset, fetched_at, "best_match")
        } else {
            weather::evaluate(payload, sunset, fetched_at, "jma_seamless")
        }
    }
    async fn create(&self, id: &str, record: &Record) -> Result<bool> {
        let record = serde_json::to_value(record)?;
        let fields = record
            .as_object()
            .unwrap()
            .iter()
            .map(|(key, value)| (key.clone(), firestore_value(value, Some(key))))
            .collect::<serde_json::Map<_, _>>();
        let response = self
            .request(
                Method::POST,
                &format!("{}/records?documentId={id}", self.documents()),
                Some(json!({"fields": fields})),
            )
            .await?;
        match response.status() {
            StatusCode::OK => Ok(true),
            StatusCode::CONFLICT => Ok(false),
            status => bail!("record create HTTP {status}"),
        }
    }
}

/// Firestore REST values are typed. Date-only strings stay strings; instants are timestamps.
pub fn firestore_value(value: &Value, key: Option<&str>) -> Value {
    match value {
        Value::Null => json!({"nullValue": null}),
        Value::Bool(v) => json!({"booleanValue": v}),
        Value::Number(v) if v.is_u64() || v.is_i64() => json!({"integerValue": v.to_string()}),
        Value::Number(v) => json!({"doubleValue": v}),
        Value::String(v) => {
            let timestamp = matches!(
                key,
                Some("sunsetAt" | "fetchedAt" | "startsAt" | "endsAt" | "time")
            );
            if timestamp {
                json!({"timestampValue": v})
            } else {
                json!({"stringValue": v})
            }
        }
        Value::Array(values) => {
            json!({"arrayValue": {"values": values.iter().map(|v| firestore_value(v, None)).collect::<Vec<_>>()}})
        }
        Value::Object(values) => {
            json!({"mapValue": {"fields": values.iter().map(|(k,v)| (k.clone(), firestore_value(v, Some(k)))).collect::<serde_json::Map<_,_>>()}})
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn encodes_firestore_types_without_turning_dates_into_timestamps() {
        let encoded = firestore_value(
            &json!({"schemaVersion": 1, "observation": null, "targetDate": "2026-11-08", "sunsetAt": "2026-11-08T08:00:00Z", "hours": [{"time": "2026-11-08T08:00:00Z", "cloud": 0.5}]}),
            None,
        );
        let f = &encoded["mapValue"]["fields"];
        assert_eq!(f["schemaVersion"]["integerValue"], "1");
        assert_eq!(f["targetDate"]["stringValue"], "2026-11-08");
        assert!(f["sunsetAt"]["timestampValue"].is_string());
        assert!(f["observation"].get("nullValue").is_some());
        assert_eq!(
            f["hours"]["arrayValue"]["values"][0]["mapValue"]["fields"]["cloud"]["doubleValue"],
            0.5
        );
    }
}

#[cfg(test)]
mod transport_tests {
    use super::*;
    use wiremock::{
        Mock, MockServer, ResponseTemplate,
        matchers::{body_partial_json, header, method, path, query_param},
    };
    struct TestAuth;
    #[async_trait]
    impl gcp_auth::TokenProvider for TestAuth {
        async fn token(&self, _: &[&str]) -> Result<Arc<gcp_auth::Token>, gcp_auth::Error> {
            Ok(Arc::new(
                serde_json::from_value(
                    json!({"access_token": "offline-test-token", "expires_in": 3600}),
                )
                .unwrap(),
            ))
        }
        async fn project_id(&self) -> Result<Arc<str>, gcp_auth::Error> {
            Ok("test-project".into())
        }
    }
    async fn cloud(server: &MockServer) -> Cloud {
        Cloud {
            client: Client::builder()
                .timeout(Duration::from_secs(2))
                .build()
                .unwrap(),
            auth: Arc::new(TestAuth),
            config: Config {
                project: "test-project".into(),
                region: "asia-northeast1".into(),
                queue: "forecast-fetch".into(),
                service_url: "https://recorder.run.app".into(),
                trigger_account: "forecast-trigger@test-project.iam.gserviceaccount.com".into(),
            },
            firestore: server.uri(),
            tasks: server.uri(),
            meteo: format!("{}/forecast", server.uri()),
        }
    }
    fn reservation() -> Reservation {
        let location = Location {
            name: "test".into(),
            latitude: 35.6812,
            longitude: 139.7671,
            enabled: true,
        };
        let target_date = chrono::NaiveDate::from_ymd_opt(2026, 8, 16).unwrap();
        Reservation {
            sunset_at: crate::astronomy::sunset(target_date, location.latitude, location.longitude)
                .unwrap(),
            target_date,
            location,
        }
    }
    #[tokio::test]
    async fn task_has_stable_name_timestamp_and_oidc_and_conflict_is_success() {
        let server = MockServer::start().await;
        let cloud = cloud(&server).await;
        let r = reservation();
        Mock::given(method("POST")).and(path("/projects/test-project/locations/asia-northeast1/queues/forecast-fetch/tasks"))
            .and(header("authorization", "Bearer offline-test-token"))
            .and(body_partial_json(json!({"task": {"scheduleTime": r.sunset_at.to_rfc3339(), "httpRequest": {"url": "https://recorder.run.app/collect", "oidcToken": {"audience": "https://recorder.run.app", "serviceAccountEmail": cloud.config.trigger_account}}}})))
            .respond_with(ResponseTemplate::new(409)).expect(2).mount(&server).await;
        assert!(!cloud.reserve(&r).await.unwrap());
        assert!(!cloud.reserve(&r).await.unwrap());
        let requests = server.received_requests().await.unwrap();
        let first: Value = serde_json::from_slice(&requests[0].body).unwrap();
        assert_eq!(
            first,
            serde_json::from_slice::<Value>(&requests[1].body).unwrap()
        );
        let decoded = STANDARD
            .decode(first["task"]["httpRequest"]["body"].as_str().unwrap())
            .unwrap();
        assert_eq!(
            serde_json::from_slice::<Value>(&decoded).unwrap()["targetDate"],
            "2026-08-16"
        );
    }
    #[tokio::test]
    async fn firestore_uses_create_only_and_never_patch() {
        let server = MockServer::start().await;
        let cloud = cloud(&server).await;
        let r = reservation();
        let payload = serde_json::from_str(include_str!(
            "../../weather/tests/fixtures/open_meteo_forecast.json"
        ))
        .unwrap();
        let record = Record {
            schema_version: 1,
            location_id: "home",
            location: r.location,
            target_date: r.target_date,
            sunset_at: r.sunset_at,
            forecast: weather::evaluate(payload, r.sunset_at, r.sunset_at, "jma_seamless").unwrap(),
            observation: None,
        };
        Mock::given(method("POST")).and(path("/projects/test-project/databases/(default)/documents/records"))
            .and(query_param("documentId", "home_2026-08-16"))
            .and(body_partial_json(json!({"fields": {"observation": {"nullValue": null}, "schemaVersion": {"integerValue": "1"}}})))
            .respond_with(ResponseTemplate::new(409)).expect(1).mount(&server).await;
        assert!(!cloud.create("home_2026-08-16", &record).await.unwrap());
    }
    #[tokio::test]
    async fn only_explicit_nulls_trigger_best_match_fallback() {
        let server = MockServer::start().await;
        let cloud = cloud(&server).await;
        let r = reservation();
        let payload: Value = serde_json::from_str(include_str!(
            "../../weather/tests/fixtures/open_meteo_forecast.json"
        ))
        .unwrap();
        let mut missing = payload.clone();
        missing["hourly"]["visibility"][0] = Value::Null;
        Mock::given(method("GET"))
            .and(path("/forecast"))
            .and(query_param("models", "jma_seamless"))
            .respond_with(ResponseTemplate::new(200).set_body_json(missing))
            .expect(1)
            .mount(&server)
            .await;
        Mock::given(method("GET"))
            .and(path("/forecast"))
            .and(query_param("models", "best_match"))
            .respond_with(ResponseTemplate::new(200).set_body_json(payload))
            .expect(1)
            .mount(&server)
            .await;
        let result = cloud.forecast(&r.location, r.sunset_at).await.unwrap();
        assert_eq!(result.model, "best_match");
        server.reset().await;
        Mock::given(method("GET"))
            .and(query_param("models", "jma_seamless"))
            .respond_with(ResponseTemplate::new(503))
            .expect(1)
            .mount(&server)
            .await;
        assert!(cloud.forecast(&r.location, r.sunset_at).await.is_err());
        assert_eq!(server.received_requests().await.unwrap().len(), 1);
    }
    #[tokio::test]
    async fn read_failure_is_not_treated_as_missing_record() {
        let server = MockServer::start().await;
        let cloud = cloud(&server).await;
        Mock::given(method("GET"))
            .respond_with(ResponseTemplate::new(403))
            .mount(&server)
            .await;
        assert!(cloud.exists("home_2026-08-16").await.is_err());
    }
}
