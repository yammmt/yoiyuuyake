# Webアプリ

Google Maps の地図クリックまたは Place Autocomplete で地点を選び、統合 API から今日の夕焼け評価を取得して表示する静的 Web アプリである。
Vite で `dist/` を生成し、Firebase Hosting から配信する。
Cloudflare Worker やサーバーサイドレンダリングは使用しない。

## 必要な環境変数

| 変数 | 内容 | ローカル開発の既定値 | 静的ビルド |
| --- | --- | --- | --- |
| `VITE_GOOGLE_MAPS_API_KEY` | Maps JavaScript API / Places API (New) 用のブラウザキー | なし | 必須 |
| `VITE_FORECAST_API_URL` | 統合 API のオリジン。例: `https://forecast.example.com` | `http://127.0.0.1:8787` | 必須 |

`VITE_` で始まる値はビルド時に JavaScript へ埋め込まれ、ブラウザから閲覧できる。
サーバー用の秘密情報は指定しない。
Maps キーは Git へコミットせず、利用する Web サイトと API を Google Cloud 側で制限する。

Vite は用途ごとに `.env.[mode].local` を読み込む。
これらのファイルは Git 管理外であるが、ローカルのプロセスやツールからの読み取りは防げない。
開発用の Maps キーは `.env.development.local` に保存せず、地図と地点検索を手動確認するときだけ 1Password CLI から渡す。
Maps キーを設定しない場合は、地図と地点検索を除く UI の表示だけを確認できる。
統合 API との連携を確認するには、Maps キーを設定して地点を選択する。

統合 API の接続先を既定値から変える場合だけ、サンプルをコピーして値を編集する。

```bash
cd site
cp .env.development.example .env.development.local
```

地図と地点検索を確認する場合は、1Password CLI にサインインし、保管先を実際の Secret Reference に置き換えて起動する。

```bash
cd site
VITE_GOOGLE_MAPS_API_KEY='op://VAULT/ITEM/FIELD' \
  op run -- npm run dev
```

この方法はキーの平文ファイルへの保存を避けるが、起動中のプロセスと配信されたブラウザ用 JavaScript からキーを隠すものではない。
キーを扱う起動操作は信頼できるターミナルで行い、手動確認後は開発サーバーを停止する。

本番用には `.env.production.example` を `.env.production.local` へコピーし、実際の値に置き換える。
ステージング用には `.env.staging.local` を使える。
値をシェルや CI の環境変数として渡した場合、環境変数が `.env` ファイルより優先される。

## ローカル開発

Node.js 22.13 以降を使用する。
先にリポジトリ直下から統合 API を起動する。

```bash
python3 api/server.py --data gsi/derived-dem10b-v1
```

別のターミナルで Web アプリを起動する。

```bash
cd site
npm ci
npm run dev
```

既定 URL は <http://localhost:3000> である。
ポート 3000 が使用中の場合は、別ポートへ移動せず起動に失敗する。

## 静的成果物

本番用の設定を渡してビルドする。

```bash
cd site
npm ci
npm run build
```

必要な 2 変数が未設定、API URL が絶対 HTTP(S) URL でない、または本番・ステージングビルドの API URL が HTTPS でない場合、ビルドは失敗する。
成功すると、Firebase Hosting へそのまま配置できる静的成果物が `site/dist/` に生成される。
別環境向けの Vite mode を使う場合は、次のように指定する。

```bash
npm run build -- --mode staging
```

成果物だけをローカル確認する場合は、ビルド後に次を実行する。

```bash
npm run preview
```

## Firebase Hosting での確認と配信

リポジトリ直下の `firebase.json` は `site/dist/` だけを配信する。
Firebase プロジェクト ID はリポジトリへ保存せず、コマンドごとに運用記録の値を指定する。

先に静的成果物を生成する。
Firebase Local Emulator Suite で確認する場合:

```bash
firebase emulators:start --only hosting --project PROJECT_ID
```

本番へ配信する場合:

```bash
firebase deploy --only hosting --project PROJECT_ID
```

配信前に Firebase Hosting の公開 URL を Maps キーの許可する参照元へ追加する。
例は `https://SITE_ID.web.app/*` と `https://SITE_ID.firebaseapp.com/*` であり、実際のサイト ID へ置き換える。

## Google Maps API キー

Google Cloud で `Maps JavaScript API` と `Places API (New)` を有効化したブラウザ用キーを作り、環境ごとに次の制限を設定する。

```text
アプリケーションの制限: ウェブサイト
許可する参照元（ローカル開発）: http://localhost:3000/*
                                  http://127.0.0.1:3000/*
許可する参照元（本番）:           https://SITE_ID.web.app/*
                                  https://SITE_ID.firebaseapp.com/*
API の制限: Maps JavaScript API
             Places API (New)
```

開発用と本番用のキーは分離する。
Firebase の共用ドメイン全体を許可するワイルドカードは使わない。
通常の開発ではキーなしで起動し、地図と地点検索の手動確認時だけ開発用キーを注入する。
開発用キーにも低い割り当て上限を設定し、利用量を監視する。詳しい運用は [Google Cloud の基盤準備](../docs/cloud-setup.md#開発用-maps-キーの運用) を参照する。

## 検証

```bash
npm test
npm run lint
```

`npm test` は型検査を実行し、テスト用のダミー設定で静的成果物を再生成する。
続いて、UI、API クライアント、環境変数、Firebase Hosting 設定を検証する。
