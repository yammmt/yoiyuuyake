import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

test("keeps the development Maps key out of local configuration examples", async () => {
  const example = await readFile(
    new URL("../.env.development.example", import.meta.url),
    "utf8",
  );
  const readme = await readFile(new URL("../README.md", import.meta.url), "utf8");

  assert.doesNotMatch(example, /VITE_GOOGLE_MAPS_API_KEY/);
  assert.doesNotMatch(example, /AIza[0-9A-Za-z_-]{35}/);
  assert.match(readme, /op run -- npm run dev/);
});
