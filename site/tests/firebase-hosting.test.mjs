import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

test("Firebase Hosting publishes only the static site build", async () => {
  const config = JSON.parse(
    await readFile(new URL("../../firebase.json", import.meta.url), "utf8"),
  );

  assert.equal(config.hosting.public, "site/dist");
  assert.equal(config.hosting.rewrites, undefined);
  assert.equal(config.hosting.redirects, undefined);
  assert.equal(config.emulators.hosting.port, 3000);
});
