export type Coordinates = { lat: number; lng: number };

export type Score = {
  score: number;
  positive_factors: string[];
  negative_factors: string[];
};

export type Forecast = {
  location: { latitude: number; longitude: number };
  sunset: {
    time: string;
    azimuth_degrees: number;
    viewing_window: { starts_at: string; ends_at: string };
  };
  weather: { gradient: Score; dramatic: Score };
  terrain: {
    visibility: "広い" | "一部遮られる" | "遮られやすい";
    description: string;
  };
  notice: string;
};

type Fetcher = typeof fetch;
type ForecastFetcher = typeof fetchForecast;

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null;
}

function isFiniteNumber(value: unknown): value is number {
  return typeof value === "number" && Number.isFinite(value);
}

function isStringArray(value: unknown): value is string[] {
  return Array.isArray(value) && value.every((item) => typeof item === "string");
}

function isDateTime(value: unknown): value is string {
  return typeof value === "string" && !Number.isNaN(Date.parse(value));
}

function isScore(value: unknown): value is Score {
  if (!isRecord(value)) return false;
  return (
    isFiniteNumber(value.score) &&
    value.score >= 0 &&
    value.score <= 100 &&
    isStringArray(value.positive_factors) &&
    isStringArray(value.negative_factors)
  );
}

export function isForecast(value: unknown): value is Forecast {
  if (!isRecord(value)) return false;
  const { location, sunset, weather, terrain, notice } = value;
  if (!isRecord(location) || !isRecord(sunset) || !isRecord(weather) || !isRecord(terrain)) {
    return false;
  }
  const window = sunset.viewing_window;
  return (
    isFiniteNumber(location.latitude) &&
    isFiniteNumber(location.longitude) &&
    isDateTime(sunset.time) &&
    isFiniteNumber(sunset.azimuth_degrees) &&
    isRecord(window) &&
    isDateTime(window.starts_at) &&
    isDateTime(window.ends_at) &&
    isScore(weather.gradient) &&
    isScore(weather.dramatic) &&
    ["広い", "一部遮られる", "遮られやすい"].includes(
      terrain.visibility as string,
    ) &&
    typeof terrain.description === "string" &&
    typeof notice === "string"
  );
}

function errorMessage(value: unknown): string | null {
  if (!isRecord(value) || !isRecord(value.error)) return null;
  return typeof value.error.message === "string" ? value.error.message : null;
}

export async function fetchForecast(
  apiBaseUrl: string,
  coordinates: Coordinates,
  signal: AbortSignal,
  fetcher: Fetcher = fetch,
): Promise<Forecast> {
  const url = new URL("/api/forecast", apiBaseUrl);
  url.searchParams.set("lat", String(coordinates.lat));
  url.searchParams.set("lng", String(coordinates.lng));

  const response = await fetcher(url, { signal, headers: { Accept: "application/json" } });
  let payload: unknown;
  try {
    payload = await response.json();
  } catch {
    throw new Error("予報APIから正しい応答を取得できませんでした。");
  }

  if (!response.ok) {
    throw new Error(errorMessage(payload) ?? "予報を取得できませんでした。");
  }
  if (!isForecast(payload)) {
    throw new Error("予報APIの応答が不完全です。");
  }
  return payload;
}

export class LatestForecastLoader {
  private controller: AbortController | null = null;
  private sequence = 0;
  private readonly apiBaseUrl: string;
  private readonly loader: ForecastFetcher;

  constructor(apiBaseUrl: string, loader: ForecastFetcher = fetchForecast) {
    this.apiBaseUrl = apiBaseUrl;
    this.loader = loader;
  }

  request(
    coordinates: Coordinates,
    handlers: {
      onSuccess(forecast: Forecast): void;
      onError(error: unknown): void;
    },
  ): void {
    this.controller?.abort();
    const controller = new AbortController();
    const sequence = ++this.sequence;
    this.controller = controller;

    void this.loader(this.apiBaseUrl, coordinates, controller.signal)
      .then((forecast) => {
        if (sequence === this.sequence) handlers.onSuccess(forecast);
      })
      .catch((error: unknown) => {
        if (!controller.signal.aborted && sequence === this.sequence) handlers.onError(error);
      });
  }

  abort(): void {
    this.sequence += 1;
    this.controller?.abort();
    this.controller = null;
  }
}
