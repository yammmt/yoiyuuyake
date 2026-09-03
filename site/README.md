# Webアプリ

Google Mapsで地点を選び、ローカル統合APIから今日の夕焼け評価を取得して表示する。

## 起動

Node.js 22.13以降を使用する。先にリポジトリ直下から統合APIを起動する。

```bash
python3 api/server.py --data gsi/derived-dem10b-v1
```

別のターミナルでWebアプリを起動する。

```bash
cd site
npm ci
read -r -s -p "Google Maps API key: " VITE_GOOGLE_MAPS_API_KEY
echo
export VITE_GOOGLE_MAPS_API_KEY
npm run dev
```

既定URLは <http://localhost:3000> である。ポート3000が使用中の場合は、別ポートへ移動せず起動に失敗する。

## Google Maps APIキー

Google Cloudで`Maps JavaScript API`だけを有効化したブラウザ用キーを作り、次の制限を設定する。

```text
アプリケーションの制限: ウェブサイト
許可する参照元: http://localhost:3000/*
                 http://127.0.0.1:3000/*
APIの制限: Maps JavaScript API のみ
```

キーはGit管理しない。終了後は`unset VITE_GOOGLE_MAPS_API_KEY`で削除する。

## 統合APIのURL

既定では <http://127.0.0.1:8787> を呼び出す。APIを別ポートで起動する場合は、Webアプリの起動前にURLを指定する。

```bash
export VITE_FORECAST_API_URL=http://127.0.0.1:8788
npm run dev
```

## 検証

```bash
npm test
npm run lint
```

本番向け成果物は`npm run build`で生成する。
