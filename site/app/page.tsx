"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { LatestForecastLoader, type Coordinates, type Forecast, type Score } from "./forecast";

type MapClickEvent = {
  latLng?: { lat(): number; lng(): number };
};

type GoogleMap = {
  addListener(eventName: "click", handler: (event: MapClickEvent) => void): void;
};

type GoogleMarker = {
  setMap(map: GoogleMap | null): void;
  setPosition(position: Coordinates): void;
};

type GoogleMapsApi = {
  Map: new (
    element: HTMLElement,
    options: {
      center: Coordinates;
      zoom: number;
      minZoom: number;
      maxZoom: number;
      clickableIcons: boolean;
      streetViewControl: boolean;
      mapTypeControl: boolean;
      fullscreenControl: boolean;
      restriction: {
        latLngBounds: { north: number; south: number; east: number; west: number };
        strictBounds: boolean;
      };
    },
  ) => GoogleMap;
  Marker: new (options: { map: GoogleMap; position: Coordinates; title: string }) => GoogleMarker;
};

declare global {
  interface Window {
    google?: { maps: GoogleMapsApi };
  }
}

const GOOGLE_MAPS_SCRIPT_ID = "google-maps-javascript-api";
const INITIAL_CENTER = { lat: 35.681236, lng: 139.767125 };
const JAPAN_BOUNDS = { north: 46.2, south: 20.1, east: 154.0, west: 122.4 };
const GOOGLE_MAPS_API_KEY = import.meta.env.VITE_GOOGLE_MAPS_API_KEY;
const FORECAST_API_URL = import.meta.env.VITE_FORECAST_API_URL ?? "http://127.0.0.1:8787";

function loadGoogleMaps(apiKey: string): Promise<GoogleMapsApi> {
  if (window.google?.maps) {
    return Promise.resolve(window.google.maps);
  }

  const existingScript = document.getElementById(GOOGLE_MAPS_SCRIPT_ID);
  if (existingScript) {
    return new Promise((resolve, reject) => {
      existingScript.addEventListener(
        "load",
        () => {
          if (window.google?.maps) {
            resolve(window.google.maps);
            return;
          }
          existingScript.remove();
          reject(new Error("地図の初期化に失敗しました。"));
        },
        { once: true },
      );
      existingScript.addEventListener(
        "error",
        () => {
          existingScript.remove();
          reject(new Error("Google Mapsを読み込めませんでした。"));
        },
        { once: true },
      );
    });
  }

  return new Promise((resolve, reject) => {
    const script = document.createElement("script");
    script.id = GOOGLE_MAPS_SCRIPT_ID;
    script.async = true;
    script.src = `https://maps.googleapis.com/maps/api/js?key=${encodeURIComponent(apiKey)}&v=weekly&language=ja&region=JP`;
    script.onload = () => {
      if (window.google?.maps) {
        resolve(window.google.maps);
        return;
      }
      script.remove();
      reject(new Error("地図の初期化に失敗しました。"));
    };
    script.onerror = () => {
      script.remove();
      reject(new Error("Google Mapsを読み込めませんでした。"));
    };
    document.head.append(script);
  });
}

function formatCoordinate(value: number) {
  return value.toFixed(6);
}

function formatTime(value: string) {
  return new Intl.DateTimeFormat("ja-JP", {
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
    timeZone: "Asia/Tokyo",
  }).format(new Date(value));
}

function ScoreCard({ kind, label, score }: { kind: "gradient" | "dramatic"; label: string; score: Score }) {
  const factors = [...score.positive_factors, ...score.negative_factors];
  return (
    <article className={`score-card ${kind}`}>
      <div className="score-heading"><h3>{label}</h3><strong>{score.score}<small> / 100</small></strong></div>
      {factors.length > 0 && <p>{factors.join(" ・ ")}</p>}
    </article>
  );
}

function ForecastResult({ forecast }: { forecast: Forecast }) {
  return (
    <section className="forecast-result" aria-label="今日の夕焼け評価">
      <div className="sunset-summary">
        <div><p className="section-label">今日の日没</p><strong>{formatTime(forecast.sunset.time)}</strong></div>
        <div><p className="section-label">見頃の目安</p><strong>{formatTime(forecast.sunset.viewing_window.starts_at)}〜{formatTime(forecast.sunset.viewing_window.ends_at)}</strong></div>
      </div>
      <div className="score-grid">
        <ScoreCard kind="gradient" label="Gradient" score={forecast.weather.gradient} />
        <ScoreCard kind="dramatic" label="Dramatic" score={forecast.weather.dramatic} />
      </div>
      <article className="terrain-result">
        <p className="section-label">地形上の西空の視界</p>
        <strong>{forecast.terrain.visibility}</strong>
        <p>{forecast.terrain.description}</p>
      </article>
      <p className="terrain-notice">{forecast.notice}</p>
    </section>
  );
}

export default function Home() {
  const mapElement = useRef<HTMLDivElement>(null);
  const marker = useRef<GoogleMarker | null>(null);
  const [coordinates, setCoordinates] = useState<Coordinates | null>(null);
  const [mapStatus, setMapStatus] = useState<"loading" | "ready" | "error" | "missing-key">(
    GOOGLE_MAPS_API_KEY ? "loading" : "missing-key",
  );
  const [forecast, setForecast] = useState<Forecast | null>(null);
  const [forecastStatus, setForecastStatus] = useState<"idle" | "loading" | "success" | "error">("idle");
  const [forecastError, setForecastError] = useState("");
  const forecastLoader = useRef<LatestForecastLoader | null>(null);
  if (forecastLoader.current === null) {
    forecastLoader.current = new LatestForecastLoader(FORECAST_API_URL);
  }

  const requestForecast = useCallback((nextCoordinates: Coordinates) => {
    setCoordinates(nextCoordinates);
    setForecast(null);
    setForecastError("");
    setForecastStatus("loading");

    forecastLoader.current?.request(nextCoordinates, {
      onSuccess(result) {
        setForecast(result);
        setForecastStatus("success");
      },
      onError(error) {
        setForecastError(error instanceof Error ? error.message : "予報を取得できませんでした。");
        setForecastStatus("error");
      },
    });
  }, []);

  useEffect(() => {
    if (!GOOGLE_MAPS_API_KEY) return;
    if (!mapElement.current) return;

    let cancelled = false;
    void loadGoogleMaps(GOOGLE_MAPS_API_KEY)
      .then((maps) => {
        if (cancelled || !mapElement.current) return;
        const map = new maps.Map(mapElement.current, {
          center: INITIAL_CENTER,
          zoom: 8,
          minZoom: 4,
          maxZoom: 18,
          clickableIcons: false,
          streetViewControl: false,
          mapTypeControl: false,
          fullscreenControl: false,
          restriction: { latLngBounds: JAPAN_BOUNDS, strictBounds: true },
        });
        map.addListener("click", (event) => {
          if (!event.latLng) return;
          const nextCoordinates = { lat: event.latLng.lat(), lng: event.latLng.lng() };
          if (marker.current) {
            marker.current.setPosition(nextCoordinates);
          } else {
            marker.current = new maps.Marker({ map, position: nextCoordinates, title: "予報する地点" });
          }
          requestForecast(nextCoordinates);
        });
        setMapStatus("ready");
      })
      .catch(() => {
        if (!cancelled) setMapStatus("error");
      });

    return () => {
      cancelled = true;
      marker.current?.setMap(null);
      marker.current = null;
      forecastLoader.current?.abort();
    };
  }, [requestForecast]);

  return (
    <main className="app-shell">
      <header className="app-header">
        <div>
          <p className="eyebrow">Yūyake Finder</p>
          <h1>今夜の空を、指定地点で確かめる。</h1>
        </div>
        <p className="today">今日の日没を対象にします</p>
      </header>

      <section className="picker-layout" aria-label="予報する地点の指定">
        <aside className="instructions">
          <p className="step">1 / 1 地点を指定</p>
          <h2>地図をクリックしてください</h2>
          <p>予報したい場所をクリックすると、緯度・経度を確定します。施設名や住所での検索は、次の段階で追加します。</p>

          <section className="selected-place" aria-live="polite">
            <p className="section-label">選択した地点</p>
            {coordinates ? (
              <>
                <strong>地図上の指定地点</strong>
                <dl>
                  <div><dt>緯度</dt><dd>{formatCoordinate(coordinates.lat)}</dd></div>
                  <div><dt>経度</dt><dd>{formatCoordinate(coordinates.lng)}</dd></div>
                </dl>
              </>
            ) : <p className="empty-state">まだ地点が選択されていません。</p>}
          </section>

          <div className="forecast-panel" aria-live="polite" aria-busy={forecastStatus === "loading"}>
            {forecastStatus === "idle" && <p className="forecast-prompt">地点を選ぶと、今日の夕焼け評価を表示します。</p>}
            {forecastStatus === "loading" && <p className="forecast-loading" role="status">気象と地形を評価しています…</p>}
            {forecastStatus === "error" && (
              <div className="forecast-error" role="alert">
                <strong>予報を表示できません</strong>
                <p>{forecastError}</p>
                <button type="button" onClick={() => coordinates && requestForecast(coordinates)}>再試行</button>
              </div>
            )}
            {forecastStatus === "success" && forecast && <ForecastResult forecast={forecast} />}
          </div>

          {!(forecastStatus === "success" && forecast) && (
            <p className="terrain-notice">見晴らしは地形を考慮した推定です。建物・樹木などの遮蔽物は考慮していません。</p>
          )}
        </aside>

        <section className="map-card" aria-label="日本地図">
          <div className="map-heading"><span>予報する地点</span><small>日本国内</small></div>
          <div className="map-canvas">
            <div className="google-map" ref={mapElement} />
            {mapStatus === "loading" && <p className="map-message">地図を準備しています…</p>}
            {mapStatus === "missing-key" && <p className="map-message map-error">Google Maps APIキーが設定されていません。ローカル起動時に<code>VITE_GOOGLE_MAPS_API_KEY</code>を渡してください。</p>}
            {mapStatus === "error" && <p className="map-message map-error">地図を読み込めませんでした。APIキーの参照元・API制限とブラウザの開発者ツールを確認してください。</p>}
          </div>
        </section>
      </section>
    </main>
  );
}
