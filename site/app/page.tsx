"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { LatestForecastLoader, type Coordinates, type Forecast, type Score } from "./forecast";
import { selectedPlaceFromDetails, type PlaceDetails, type SelectedPlace } from "./place";

type MapClickEvent = {
  latLng?: { lat(): number; lng(): number };
};

type GoogleMap = {
  addListener(eventName: "click", handler: (event: MapClickEvent) => void): void;
  setCenter(position: Coordinates): void;
  setZoom(zoom: number): void;
};

type GoogleMarker = {
  setMap(map: GoogleMap | null): void;
  setPosition(position: Coordinates): void;
  setTitle(title: string): void;
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
  importLibrary(name: "places"): Promise<GooglePlacesLibrary>;
};

type GooglePlace = PlaceDetails & {
  fetchFields(options: { fields: string[] }): Promise<void>;
};

type PlaceSelectEvent = Event & {
  placePrediction: { toPlace(): GooglePlace };
};

type PlaceAutocompleteElement = HTMLElement & {
  description: string;
  placeholder: string;
};

type GooglePlacesLibrary = {
  PlaceAutocompleteElement: new (options: {
    includedRegionCodes: string[];
  }) => PlaceAutocompleteElement;
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
  const searchElement = useRef<HTMLDivElement>(null);
  const marker = useRef<GoogleMarker | null>(null);
  const selectionSequence = useRef(0);
  const [selectedPlace, setSelectedPlace] = useState<SelectedPlace | null>(null);
  const [mapStatus, setMapStatus] = useState<"loading" | "ready" | "error" | "missing-key">(
    GOOGLE_MAPS_API_KEY ? "loading" : "missing-key",
  );
  const [forecast, setForecast] = useState<Forecast | null>(null);
  const [forecastStatus, setForecastStatus] = useState<"idle" | "loading" | "success" | "error">("idle");
  const [forecastError, setForecastError] = useState("");
  const [searchError, setSearchError] = useState("");
  const forecastLoader = useRef<LatestForecastLoader | null>(null);
  if (forecastLoader.current === null) {
    forecastLoader.current = new LatestForecastLoader(FORECAST_API_URL);
  }

  const requestForecast = useCallback((nextCoordinates: Coordinates) => {
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
    if (!searchElement.current) return;

    let cancelled = false;
    const searchContainer = searchElement.current;
    void loadGoogleMaps(GOOGLE_MAPS_API_KEY)
      .then(async (maps) => {
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

        const selectPlace = (nextPlace: SelectedPlace, moveMap: boolean) => {
          setSelectedPlace(nextPlace);
          setSearchError("");
          if (marker.current) {
            marker.current.setPosition(nextPlace.coordinates);
            marker.current.setTitle(nextPlace.name);
          } else {
            marker.current = new maps.Marker({
              map,
              position: nextPlace.coordinates,
              title: nextPlace.name,
            });
          }
          if (moveMap) {
            map.setCenter(nextPlace.coordinates);
            map.setZoom(15);
          }
          requestForecast(nextPlace.coordinates);
        };

        map.addListener("click", (event) => {
          if (!event.latLng) return;
          selectionSequence.current += 1;
          selectPlace({
            name: "地図上の指定地点",
            coordinates: { lat: event.latLng.lat(), lng: event.latLng.lng() },
          }, false);
        });

        const { PlaceAutocompleteElement } = await maps.importLibrary("places");
        if (cancelled) return;
        const autocomplete = new PlaceAutocompleteElement({ includedRegionCodes: ["jp"] });
        autocomplete.placeholder = "地名・施設名・住所を検索";
        autocomplete.description = "日本国内の地名、施設名、住所を入力して候補から選択してください。";
        const handlePlaceSelect = async (event: Event) => {
          const sequence = ++selectionSequence.current;
          setSearchError("");
          try {
            const place = (event as PlaceSelectEvent).placePrediction.toPlace();
            await place.fetchFields({ fields: ["displayName", "formattedAddress", "location"] });
            if (cancelled || sequence !== selectionSequence.current) return;
            selectPlace(selectedPlaceFromDetails(place), true);
          } catch (error) {
            if (cancelled || sequence !== selectionSequence.current) return;
            setSearchError(
              error instanceof Error
                ? error.message
                : "場所の詳細を取得できませんでした。もう一度お試しください。",
            );
          }
        };
        autocomplete.addEventListener("gmp-select", handlePlaceSelect);
        autocomplete.addEventListener("gmp-error", () => {
          setSearchError("場所の候補を取得できませんでした。入力内容を確認して、もう一度お試しください。");
        });
        searchContainer.replaceChildren(autocomplete);
        setMapStatus("ready");
      })
      .catch(() => {
        if (!cancelled) setMapStatus("error");
      });

    return () => {
      cancelled = true;
      marker.current?.setMap(null);
      marker.current = null;
      selectionSequence.current += 1;
      searchContainer.replaceChildren();
      forecastLoader.current?.abort();
    };
  }, [requestForecast]);

  return (
    <div className="app-shell">
      <main>
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
            <h2>場所を検索、または地図をクリック</h2>
            <p>日本国内の地名・施設名・住所を検索して候補を選ぶか、予報したい場所を地図でクリックしてください。</p>

            <div className="place-search">
              <p className="section-label" id="place-search-label">場所を検索</p>
              <div className="place-search-widget" aria-labelledby="place-search-label">
                <div className="place-search-mount" ref={searchElement} />
                {mapStatus === "loading" && <p>検索を準備しています…</p>}
                {mapStatus === "missing-key" && <p>検索にはGoogle Maps APIキーが必要です。</p>}
                {mapStatus === "error" && <p>場所の検索を読み込めませんでした。</p>}
              </div>
              {searchError && <p className="place-search-error" role="alert">{searchError}</p>}
            </div>

            <section className="selected-place" aria-live="polite">
              <p className="section-label">選択した地点</p>
              {selectedPlace ? (
                <>
                  <strong>{selectedPlace.name}</strong>
                  <dl>
                    <div><dt>緯度</dt><dd>{formatCoordinate(selectedPlace.coordinates.lat)}</dd></div>
                    <div><dt>経度</dt><dd>{formatCoordinate(selectedPlace.coordinates.lng)}</dd></div>
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
                  <button type="button" onClick={() => selectedPlace && requestForecast(selectedPlace.coordinates)}>再試行</button>
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

      <footer className="site-footer" aria-labelledby="data-sources-heading">
        <h2 id="data-sources-heading">データ出典</h2>
        <ul className="data-sources">
          <li>気象：<a href="https://open-meteo.com/">Open-Meteo</a>（<a href="https://creativecommons.org/licenses/by/4.0/">CC BY 4.0</a>）</li>
          <li>地形：<a href="https://service.gsi.go.jp/kiban/app/help/">国土地理院「基盤地図情報（数値標高モデル）DEM10B」</a>を加工して作成</li>
          <li>地図・場所検索：<a href="https://mapsplatform.google.com/">Google Maps Platform</a></li>
        </ul>
        <p>夕焼けスコア・地形評価は、上記データを基に当サイトが算出しています。</p>
        <details className="calculation-details">
          <summary>算出方法について</summary>
          <dl>
            <div>
              <dt>夕焼けスコア</dt>
              <dd>日没前後の雲量・視程・湿度・降水などの気象予報を基に、当サイト独自のルールで算出します。Gradient はなめらかなグラデーション、Dramatic は赤や桃色の鮮やかな焼け空への期待度です。実際の夕焼けを保証するものではありません。</dd>
            </div>
            <div>
              <dt>地形上の見晴らし</dt>
              <dd>DEM10B の標高から日没方向の地形による遮蔽を推定します。建物・樹木などの遮蔽物は考慮していません。</dd>
            </div>
            <div>
              <dt>日没時刻・見頃</dt>
              <dd>日没時刻は指定地点と今日の日付を基に天文計算で求めます。見頃は日没20分前から日没25分後までを目安として表示しています。</dd>
            </div>
          </dl>
        </details>
      </footer>
    </div>
  );
}
