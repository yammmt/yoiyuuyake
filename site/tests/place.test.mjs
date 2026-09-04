import assert from "node:assert/strict";
import test from "node:test";
import { selectedPlaceFromDetails } from "../app/place.ts";

const location = { lat: () => 35.681236, lng: () => 139.767125 };

test("builds the shared selected-place state from an autocomplete result", () => {
  assert.deepEqual(
    selectedPlaceFromDetails({
      displayName: "東京駅",
      formattedAddress: "東京都千代田区丸の内1丁目",
      location,
    }),
    {
      name: "東京駅",
      coordinates: { lat: 35.681236, lng: 139.767125 },
    },
  );
});

test("uses the address as the name and rejects a result without coordinates", () => {
  assert.equal(
    selectedPlaceFromDetails({ formattedAddress: "東京都千代田区", location }).name,
    "東京都千代田区",
  );
  assert.throws(
    () => selectedPlaceFromDetails({ displayName: "位置なし" }),
    /位置を取得できませんでした/,
  );
});
