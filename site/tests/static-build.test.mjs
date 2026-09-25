import assert from "node:assert/strict";
import { readFile, readdir } from "node:fs/promises";
import test from "node:test";

const siteRoot = new URL("../", import.meta.url);
const outputRoot = new URL("test-dist/", siteRoot);

test("builds a self-contained static entry point", async () => {
  const html = await readFile(new URL("index.html", outputRoot), "utf8");

  assert.match(html, /<html lang="ja">/);
  assert.match(html, /<title>Yūyake Finder<\/title>/);
  assert.match(html, /<div id="root"><\/div>/);
  assert.match(html, /<script type="module" crossorigin src="\/assets\/[^"]+\.js"><\/script>/);
  assert.doesNotMatch(html, /Cloudflare|vinext|\/server\//i);
});

test("embeds the selected build environment in the browser bundle", async () => {
  const assetNames = await readdir(new URL("assets/", outputRoot));
  const scripts = assetNames.filter((name) => name.endsWith(".js"));
  assert.ok(scripts.length > 0);

  const source = (
    await Promise.all(
      scripts.map((name) => readFile(new URL(`assets/${name}`, outputRoot), "utf8")),
    )
  ).join("\n");

  assert.match(source, /test-key/);
  assert.match(source, /https:\/\/forecast\.test\.invalid/);
  assert.doesNotMatch(source, /http:\/\/127\.0\.0\.1:8787/);
  assert.match(source, /今夜の空を、指定地点で確かめる。/);
  assert.match(source, /予報を表示できません/);
});
