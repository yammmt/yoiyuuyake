import assert from "node:assert/strict";
import test from "node:test";
import { fetchForecast, isForecast, LatestForecastLoader } from "../app/forecast.ts";

const completeForecast = {
  location: { latitude: 35.6812, longitude: 139.7671 },
  sunset: {
    time: "2026-08-31T18:08:00+09:00",
    azimuth_degrees: 279.1,
    viewing_window: {
      starts_at: "2026-08-31T17:48:00+09:00",
      ends_at: "2026-08-31T18:33:00+09:00",
    },
  },
  weather: {
    gradient: { score: 77, positive_factors: ["視程が良い"], negative_factors: [] },
    dramatic: { score: 94, positive_factors: ["中層雲が適量"], negative_factors: [] },
  },
  terrain: { visibility: "広い", description: "日没方向の地形による遮蔽は小さい見込みです。" },
  notice: "見晴らしは地形を考慮した推定です。建物・樹木などの遮蔽物は考慮していません。",
};

test("accepts only a complete integrated forecast", () => {
  assert.equal(isForecast(completeForecast), true);
  assert.equal(isForecast({ ...completeForecast, terrain: undefined }), false);
  assert.equal(isForecast({ ...completeForecast, weather: { gradient: completeForecast.weather.gradient } }), false);
  for (const field of ["time", "starts_at", "ends_at"]) {
    const sunset = structuredClone(completeForecast.sunset);
    if (field === "time") sunset.time = "not-a-date";
    else sunset.viewing_window[field] = "not-a-date";
    assert.equal(isForecast({ ...completeForecast, sunset }), false);
  }
});

test("calls the local integrated endpoint with selected coordinates", async () => {
  let requestedUrl;
  const result = await fetchForecast(
    "http://127.0.0.1:8787",
    { lat: 35.6812, lng: 139.7671 },
    new AbortController().signal,
    async (url) => {
      requestedUrl = new URL(url);
      return Response.json(completeForecast);
    },
  );

  assert.equal(requestedUrl.pathname, "/api/forecast");
  assert.equal(requestedUrl.searchParams.get("lat"), "35.6812");
  assert.equal(requestedUrl.searchParams.get("lng"), "139.7671");
  assert.equal(result.weather.dramatic.score, 94);
});

test("does not expose incomplete or failed evaluations", async () => {
  await assert.rejects(
    fetchForecast(
      "http://127.0.0.1:8787",
      { lat: 35, lng: 139 },
      new AbortController().signal,
      async () => Response.json({
        ...completeForecast,
        sunset: { ...completeForecast.sunset, time: "invalid" },
      }),
    ),
    /不完全/,
  );

  await assert.rejects(
    fetchForecast(
      "http://127.0.0.1:8787",
      { lat: 35, lng: 139 },
      new AbortController().signal,
      async () => Response.json({ ...completeForecast, terrain: undefined }),
    ),
    /不完全/,
  );

  await assert.rejects(
    fetchForecast(
      "http://127.0.0.1:8787",
      { lat: 35, lng: 139 },
      new AbortController().signal,
      async () => Response.json({
        error: {
          code: "dem_unavailable",
          reason: "ray_out_of_coverage",
          message: "日没方向が地形データ対象範囲を越えるため、別の地点を選択してください。",
        },
      }, { status: 503 }),
    ),
    /別の地点を選択してください/,
  );
});

test("ignores an older response after the selected point changes", async () => {
  const pending = [];
  const loader = new LatestForecastLoader("http://127.0.0.1:8787", (_base, coordinates, signal) => (
    new Promise((resolve) => pending.push({ coordinates, resolve, signal }))
  ));
  const displayed = [];
  const errors = [];
  const handlers = {
    onSuccess: (forecast) => displayed.push(forecast.location.latitude),
    onError: (error) => errors.push(error),
  };

  loader.request({ lat: 35, lng: 139 }, handlers);
  loader.request({ lat: 36, lng: 140 }, handlers);
  assert.equal(pending[0].signal.aborted, true);

  pending[1].resolve({
    ...completeForecast,
    location: { latitude: 36, longitude: 140 },
  });
  pending[0].resolve({
    ...completeForecast,
    location: { latitude: 35, longitude: 139 },
  });
  await Promise.resolve();
  await Promise.resolve();

  assert.deepEqual(displayed, [36]);
  assert.deepEqual(errors, []);
});
