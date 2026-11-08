use axum::{
    Json, Router,
    extract::{DefaultBodyLimit, State},
    http::StatusCode,
    routing::post,
};
use chrono::Utc;
use forecast_recorder::{
    cloud::{Cloud, Config},
    service::{self, Reservation},
};
use serde_json::{Value, json};
use std::{sync::Arc, time::Duration};

type Reply = (StatusCode, Json<Value>);

#[tokio::main]
async fn main() -> anyhow::Result<()> {
    tracing_subscriber::fmt().json().with_target(false).init();
    let cloud = Arc::new(Cloud::new(Config::from_env()?).await?);
    // Cloud Run IAM authenticates callers. Never deploy this service with public invocation.
    let app = Router::new()
        .route("/schedule", post(schedule))
        .route("/collect", post(collect))
        .layer(DefaultBodyLimit::max(8192))
        .with_state(cloud);
    let port: u16 = std::env::var("PORT")
        .unwrap_or_else(|_| "8080".into())
        .parse()?;
    let listener = tokio::net::TcpListener::bind((std::net::Ipv4Addr::UNSPECIFIED, port)).await?;
    tracing::info!(event = "recorder_started");
    axum::serve(listener, app)
        .with_graceful_shutdown(shutdown())
        .await?;
    Ok(())
}

async fn schedule(State(cloud): State<Arc<Cloud>>) -> Reply {
    reply(
        "schedule",
        tokio::time::timeout(
            Duration::from_secs(100),
            service::schedule(cloud.as_ref(), Utc::now()),
        )
        .await,
    )
}
async fn collect(State(cloud): State<Arc<Cloud>>, Json(reservation): Json<Reservation>) -> Reply {
    reply(
        "collect",
        tokio::time::timeout(
            Duration::from_secs(100),
            service::collect(cloud.as_ref(), reservation, Utc::now()),
        )
        .await,
    )
}
fn reply(
    operation: &str,
    result: Result<anyhow::Result<&str>, tokio::time::error::Elapsed>,
) -> Reply {
    match result {
        Ok(Ok(outcome)) => {
            tracing::info!(event = "recorder_completed", operation, outcome);
            (StatusCode::OK, Json(json!({"status": outcome})))
        }
        result => {
            // Do not log payloads, location names, coordinates, tokens or request URLs.
            let reason = match result {
                Ok(Err(error)) => format!("{error:#}"),
                _ => "operation timed out".into(),
            };
            tracing::error!(event = "recorder_failed", operation, reason);
            (
                StatusCode::SERVICE_UNAVAILABLE,
                Json(json!({"status": "failed"})),
            )
        }
    }
}

async fn shutdown() {
    #[cfg(unix)]
    {
        if let Ok(mut terminate) =
            tokio::signal::unix::signal(tokio::signal::unix::SignalKind::terminate())
        {
            tokio::select! {
                _ = tokio::signal::ctrl_c() => {},
                _ = terminate.recv() => {},
            }
            return;
        }
    }
    let _ = tokio::signal::ctrl_c().await;
}
