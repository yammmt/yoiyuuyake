import type { Coordinates } from "./forecast";

export type PlaceDetails = {
  displayName?: string | null;
  formattedAddress?: string | null;
  location?: { lat(): number; lng(): number } | null;
};

export type SelectedPlace = {
  name: string;
  coordinates: Coordinates;
};

export function selectedPlaceFromDetails(place: PlaceDetails): SelectedPlace {
  if (!place.location) {
    throw new Error("選択した場所の位置を取得できませんでした。別の候補を選んでください。");
  }

  return {
    name: place.displayName || place.formattedAddress || "検索した地点",
    coordinates: { lat: place.location.lat(), lng: place.location.lng() },
  };
}
