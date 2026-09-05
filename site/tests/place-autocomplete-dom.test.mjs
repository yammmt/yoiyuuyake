import assert from "node:assert/strict";
import test from "node:test";
import { JSDOM } from "jsdom";
import { runnerImport } from "vite";

process.env.VITE_GOOGLE_MAPS_API_KEY = "test-key";

const dom = new JSDOM("<!doctype html><html><body></body></html>", {
  url: "http://localhost:3000/",
});
for (const property of [
  "window",
  "document",
  "navigator",
  "HTMLElement",
  "Event",
  "CustomEvent",
  "KeyboardEvent",
  "Node",
]) {
  Object.defineProperty(globalThis, property, {
    configurable: true,
    value: dom.window[property],
  });
}
globalThis.IS_REACT_ACT_ENVIRONMENT = true;

const { createElement } = await import("react");
const { act } = await import("react");
const { createRoot } = await import("react-dom/client");
const { module: pageModule } = await runnerImport("./app/page.tsx", {
  configFile: false,
  root: process.cwd(),
});
const Home = pageModule.default;

const completeForecast = {
  location: { latitude: 35.681236, longitude: 139.767125 },
  sunset: {
    time: "2026-09-05T17:59:00+09:00",
    azimuth_degrees: 276,
    viewing_window: {
      starts_at: "2026-09-05T17:39:00+09:00",
      ends_at: "2026-09-05T18:24:00+09:00",
    },
  },
  weather: {
    gradient: { score: 70, positive_factors: [], negative_factors: [] },
    dramatic: { score: 60, positive_factors: [], negative_factors: [] },
  },
  terrain: { visibility: "広い", description: "日没方向の地形による遮蔽は小さい見込みです。" },
  notice: "見晴らしは地形を考慮した推定です。建物・樹木などの遮蔽物は考慮していません。",
};

class FakeMap {
  addListener() {}
  setCenter() {}
  setZoom() {}
}

class FakeMarker {
  setMap() {}
  setPosition() {}
  setTitle() {}
}

class FakePlaceAutocompleteElement extends HTMLElement {
  constructor(options) {
    super();
    this.options = options;
    this.place = null;
  }

  connectedCallback() {
    const input = document.createElement("input");
    input.placeholder = this.placeholder;
    input.setAttribute("aria-label", this.description);
    let highlighted = false;
    input.addEventListener("keydown", (event) => {
      if (event.key === "ArrowDown") highlighted = true;
      if (event.key !== "Enter" || !highlighted || !this.place) return;
      const selectEvent = new Event("gmp-select");
      Object.defineProperty(selectEvent, "placePrediction", {
        value: { toPlace: () => this.place },
      });
      this.dispatchEvent(selectEvent);
    });
    this.replaceChildren(input);
  }

  choose(place) {
    this.place = place;
  }

  rejectRequest() {
    this.dispatchEvent(new Event("gmp-error"));
  }
}

dom.window.customElements.define("fake-place-autocomplete", FakePlaceAutocompleteElement);

function installGoogleMaps() {
  window.google = {
    maps: {
      Map: FakeMap,
      Marker: FakeMarker,
      importLibrary: async () => ({ PlaceAutocompleteElement: FakePlaceAutocompleteElement }),
    },
  };
}

async function renderHome() {
  document.body.innerHTML = '<div id="root"></div>';
  installGoogleMaps();
  globalThis.fetch = async () => Response.json(completeForecast);
  const root = createRoot(document.querySelector("#root"));
  await act(async () => {
    root.render(createElement(Home));
  });
  const autocomplete = document.querySelector(".place-search-mount > *");
  assert.ok(autocomplete instanceof FakePlaceAutocompleteElement);
  assert.deepEqual(autocomplete.options.includedRegionCodes, ["jp"]);
  return { root, autocomplete, input: autocomplete.querySelector("input") };
}

async function chooseWithKeyboard(input) {
  await act(async () => {
    input.focus();
    input.dispatchEvent(new KeyboardEvent("keydown", { key: "ArrowDown", bubbles: true }));
    input.dispatchEvent(new KeyboardEvent("keydown", { key: "Enter", bubbles: true }));
  });
}

test("keyboard selection updates the selected place after fetching required fields", async () => {
  const { root, autocomplete, input } = await renderHome();
  let requestedFields;
  autocomplete.choose({
    displayName: "東京駅",
    formattedAddress: "東京都千代田区丸の内1丁目",
    location: { lat: () => 35.681236, lng: () => 139.767125 },
    async fetchFields({ fields }) {
      requestedFields = fields;
    },
  });

  await chooseWithKeyboard(input);

  assert.deepEqual(requestedFields, ["displayName", "formattedAddress", "location"]);
  const selectedPlace = document.querySelector(".selected-place");
  assert.match(selectedPlace.textContent, /東京駅/);
  assert.match(selectedPlace.textContent, /35\.681236/);
  assert.match(selectedPlace.textContent, /139\.767125/);
  await act(async () => root.unmount());
});

test("a place details failure is announced without replacing the selected place", async () => {
  const { root, autocomplete, input } = await renderHome();
  autocomplete.choose({
    displayName: "東京駅",
    formattedAddress: "東京都千代田区丸の内1丁目",
    location: { lat: () => 35.681236, lng: () => 139.767125 },
    async fetchFields() {},
  });
  await chooseWithKeyboard(input);

  autocomplete.choose({
    async fetchFields() {
      throw new Error("場所の詳細を取得できませんでした。");
    },
  });

  await chooseWithKeyboard(input);

  const alert = document.querySelector('.place-search-error[role="alert"]');
  assert.equal(alert?.textContent, "場所の詳細を取得できませんでした。");
  const selectedPlace = document.querySelector(".selected-place").textContent;
  assert.match(selectedPlace, /東京駅/);
  assert.match(selectedPlace, /35\.681236/);
  assert.match(selectedPlace, /139\.767125/);
  await act(async () => root.unmount());
});

test("an autocomplete request rejection is announced", async () => {
  const { root, autocomplete } = await renderHome();

  await act(async () => autocomplete.rejectRequest());

  const alert = document.querySelector('.place-search-error[role="alert"]');
  assert.equal(
    alert?.textContent,
    "場所の候補を取得できませんでした。入力内容を確認して、もう一度お試しください。",
  );
  await act(async () => root.unmount());
});
