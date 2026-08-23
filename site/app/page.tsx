"use client";

import { useEffect, useRef, useState } from "react";

type Coordinates = { lat: number; lng: number };

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

export default function Home() {
  const mapElement = useRef<HTMLDivElement>(null);
  const marker = useRef<GoogleMarker | null>(null);
  const [coordinates, setCoordinates] = useState<Coordinates | null>(null);
  const [mapStatus, setMapStatus] = useState<"loading" | "ready" | "error" | "missing-key">(
    GOOGLE_MAPS_API_KEY ? "loading" : "missing-key",
  );

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
          setCoordinates(nextCoordinates);
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
    };
  }, []);

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

          <p className="terrain-notice">見晴らしは地形を考慮した推定です。建物・樹木などの遮蔽物は考慮していません。</p>
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
