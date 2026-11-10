//! Port of terrain/scripts/astronomy.py; no network or terrain data needed.
use anyhow::{Result, ensure};
use chrono::{DateTime, FixedOffset, NaiveDate, TimeZone, Utc};

pub fn jst() -> FixedOffset {
    FixedOffset::east_opt(9 * 3600).expect("valid fixed offset")
}

pub fn sunset(day: NaiveDate, latitude: f64, longitude: f64) -> Result<DateTime<Utc>> {
    ensure!(
        latitude.is_finite() && (20.1..=46.2).contains(&latitude),
        "invalid latitude"
    );
    ensure!(
        longitude.is_finite() && (122.4..=154.0).contains(&longitude),
        "invalid longitude"
    );
    let noon = jst()
        .from_local_datetime(&day.and_hms_opt(12, 0, 0).unwrap())
        .unwrap();
    let (declination, equation) = solar_terms(noon.with_timezone(&Utc));
    let lat = latitude.to_radians();
    let dec = declination.to_radians();
    let cos_hour = 90.833_f64.to_radians().cos() / (lat.cos() * dec.cos()) - lat.tan() * dec.tan();
    ensure!((-1.0..=1.0).contains(&cos_hour), "sunset unavailable");
    let minutes = 720.0 - 4.0 * longitude - equation + 540.0 + 4.0 * cos_hour.acos().to_degrees();
    let midnight = jst()
        .from_local_datetime(&day.and_hms_opt(0, 0, 0).unwrap())
        .unwrap();
    Ok(
        (midnight + chrono::Duration::microseconds((minutes * 60_000_000.0).round() as i64))
            .with_timezone(&Utc),
    )
}

fn solar_terms(moment: DateTime<Utc>) -> (f64, f64) {
    let jd = moment.timestamp() as f64 / 86400.0 + 2440587.5;
    let t = (jd - 2451545.0) / 36525.0;
    let l = (280.46646 + t * (36000.76983 + t * 0.0003032)).rem_euclid(360.0);
    let m = 357.52911 + t * (35999.05029 - 0.0001537 * t);
    let e = 0.016708634 - t * (0.000042037 + 0.0000001267 * t);
    let sin = |x: f64| x.to_radians().sin();
    let cos = |x: f64| x.to_radians().cos();
    let c = sin(m) * (1.914602 - t * (0.004817 + 0.000014 * t))
        + sin(2.0 * m) * (0.019993 - 0.000101 * t)
        + sin(3.0 * m) * 0.000289;
    let omega = 125.04 - 1934.136 * t;
    let apparent = l + c - 0.00569 - 0.00478 * sin(omega);
    let obliq = 23.0
        + (26.0 + (21.448 - t * (46.815 + t * (0.00059 - t * 0.001813))) / 60.0) / 60.0
        + 0.00256 * cos(omega);
    let decl = (sin(obliq) * sin(apparent)).asin().to_degrees();
    let y = (obliq.to_radians() / 2.0).tan().powi(2);
    let eq = 4.0
        * (y * sin(2.0 * l) - 2.0 * e * sin(m) + 4.0 * e * y * sin(m) * cos(2.0 * l)
            - 0.5 * y * y * sin(4.0 * l)
            - 1.25 * e * e * sin(2.0 * m))
        .to_degrees();
    (decl, eq)
}
