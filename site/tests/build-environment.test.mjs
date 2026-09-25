import assert from "node:assert/strict";
import test from "node:test";
import { validateBuildEnvironment } from "../build/environment.ts";

const completeEnvironment = {
  VITE_GOOGLE_MAPS_API_KEY: "test-key",
  VITE_FORECAST_API_URL: "https://forecast.example.test",
};

test("accepts complete browser build settings", () => {
  assert.doesNotThrow(() => validateBuildEnvironment(completeEnvironment));
  assert.doesNotThrow(() =>
    validateBuildEnvironment({
      ...completeEnvironment,
      VITE_FORECAST_API_URL: "http://127.0.0.1:8787",
    }),
  );
  assert.doesNotThrow(() =>
    validateBuildEnvironment(completeEnvironment, { requireHttps: true }),
  );
});

test("rejects missing or unsafe forecast endpoint settings", () => {
  assert.throws(
    () => validateBuildEnvironment({}),
    /VITE_GOOGLE_MAPS_API_KEY, VITE_FORECAST_API_URL/,
  );
  assert.throws(
    () =>
      validateBuildEnvironment({
        ...completeEnvironment,
        VITE_FORECAST_API_URL: "forecast.example.test",
      }),
    /絶対URL/,
  );
  assert.throws(
    () =>
      validateBuildEnvironment({
        ...completeEnvironment,
        VITE_FORECAST_API_URL: "javascript:alert(1)",
      }),
    /http または https/,
  );
  assert.throws(
    () =>
      validateBuildEnvironment(
        {
          ...completeEnvironment,
          VITE_FORECAST_API_URL: "http://forecast.example.test",
        },
        { requireHttps: true },
      ),
    /https のURL/,
  );
});
