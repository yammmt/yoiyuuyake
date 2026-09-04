import assert from "node:assert/strict";
import test from "node:test";

async function render() {
  const workerUrl = new URL("../dist/server/index.js", import.meta.url);
  workerUrl.searchParams.set("test", `${process.pid}-${Date.now()}`);
  const { default: worker } = await import(workerUrl.href);

  return worker.fetch(
    new Request("http://localhost/", {
      headers: { accept: "text/html" },
    }),
    {
      ASSETS: {
        fetch: async () => new Response("Not found", { status: 404 }),
      },
    },
    {
      waitUntil() {},
      passThroughOnException() {},
    },
  );
}

test("server-renders the Yuyake Finder point picker", async () => {
  const response = await render();
  assert.equal(response.status, 200);
  assert.match(response.headers.get("content-type") ?? "", /^text\/html\b/i);

  const html = await response.text();
  assert.match(html, /<title>Yūyake Finder<\/title>/i);
  assert.match(html, /今夜の空を、指定地点で確かめる。/);
  assert.match(html, /場所を検索、または地図をクリック/);
  assert.match(html, /日本国内の地名・施設名・住所を検索/);
  assert.match(html, /場所を検索/);
  assert.match(html, /class="place-search-mount"><\/div>/);
  assert.match(html, /まだ地点が選択されていません。/);
  assert.match(html, /地点を選ぶと、今日の夕焼け評価を表示します。/);
  assert.doesNotMatch(html, /\/ 100/);
});

test("shows a safe fallback when the Google Maps key is absent", async () => {
  const response = await render();
  const html = await response.text();

  assert.match(
    html,
    /Google Maps APIキーが設定されていません。/,
  );
  assert.match(html, /検索にはGoogle Maps APIキーが必要です。/);
  assert.match(html, /見晴らしは地形を考慮した推定です。/);
  assert.match(html, /建物・樹木などの遮蔽物は考慮していません。/);
  assert.doesNotMatch(html, /maps\.googleapis\.com\/maps\/api\/js\?key=/);
});
