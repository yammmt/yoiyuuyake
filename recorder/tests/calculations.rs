use chrono::{DateTime, NaiveDate};
use forecast_recorder::{astronomy::sunset, weather};
use serde_json::{Value, json};

fn fixture() -> Value {
    serde_json::from_str(include_str!(
        "../../weather/tests/fixtures/open_meteo_forecast.json"
    ))
    .unwrap()
}

#[test]
fn rejects_missing_invalid_and_duplicate_inputs() {
    let moment = DateTime::parse_from_rfc3339("2026-03-21T18:00:00+09:00")
        .unwrap()
        .to_utc();
    for mode in 0..5 {
        let mut input = fixture();
        match mode {
            0 => input["hourly"]["cloud_cover_low"][0] = Value::Null,
            1 => input["hourly"]["cloud_cover_low"][0] = json!(101),
            2 => input["hourly_units"]["wind_speed_10m"] = json!("m/s"),
            3 => input["hourly"]["time"][1] = input["hourly"]["time"][0].clone(),
            _ => input["hourly"]["time"] = json!([]),
        }
        assert!(weather::evaluate(input, moment, moment, "jma_seamless").is_err());
    }
}

#[test]
fn agrees_with_python_reference_cases() {
    let cases: Value =
        serde_json::from_str(include_str!("fixtures/python-reference.json")).unwrap();
    for case in cases["sunsets"].as_array().unwrap() {
        let day = NaiveDate::parse_from_str(case["date"].as_str().unwrap(), "%Y-%m-%d").unwrap();
        let actual = sunset(
            day,
            case["latitude"].as_f64().unwrap(),
            case["longitude"].as_f64().unwrap(),
        )
        .unwrap();
        let expected = DateTime::parse_from_rfc3339(case["sunset"].as_str().unwrap())
            .unwrap()
            .to_utc();
        assert!((actual - expected).num_microseconds().unwrap().abs() < 1000);
    }
    for case in cases["weather"].as_array().unwrap() {
        let moment = DateTime::parse_from_rfc3339(case["sunset"].as_str().unwrap())
            .unwrap()
            .to_utc();
        let forecast =
            weather::evaluate(case["payload"].clone(), moment, moment, "jma_seamless").unwrap();
        assert_eq!(forecast.gradient, case["gradient"].as_u64().unwrap() as u32);
        assert_eq!(forecast.dramatic, case["dramatic"].as_u64().unwrap() as u32);
        assert_eq!(
            forecast.weather.hours.len(),
            case["count"].as_u64().unwrap() as usize
        );
    }
}
