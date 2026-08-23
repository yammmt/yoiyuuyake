# 夕焼け予報

きれいな夕焼けを拝めそうな場所を探し、行き、気分をよくする。

## やりたいこと

いい感じの夕焼けが見れそうかを予測する。
特に、 "いい感じ" とは、日没後にきれいなグラデーションが見えるものと、高彩度で力強い空が見えるものとを指す。

## 夕焼けの例

こんな感じの夕焼けを見たい。

### グラデーションがきれいに出るもの

快晴の冬の日に見えがち

![グラデーション例 1](./fig/example_grad_01.jpg)
![グラデーション例 2](./fig/example_grad_02.jpg)

### 高彩度でドラマチックなもの

夏の日に見えがち

![高彩度例 1](./fig/example_dramatic_01.jpg)
![高彩度例 1](./fig/example_dramatic_02.jpg)

## 現在の構成

MVPに向けて、地点の夕焼けを評価するための部品を次のように分けている。

```text
site/       React / Cloudflare Worker のWebアプリ基盤（Google Mapでの地点指定まで実装済み）
terrain/    国土地理院DEM、日没の天文計算、地形視界のローカル検証
weather/    Open-Meteoの時間別予報の取得・検証
docs/       MVP仕様、判断記録、UI参照
gsi/        Git管理外の国土地理院DEM元データ・変換済みタイル
```

`terrain/`は、緯度・経度・対象日から日没時刻と方位を計算し、DEM上の西空の地平線を評価する。建物・樹木は考慮しない。`weather/`は、JMA系モデルを優先してOpen-Meteoから低・中・高層雲量、視程、湿度、降水、風速を取得する。日没前後の抽出と`Gradient` / `Dramatic`の採点、ならびに地形・気象処理のReactアプリへの統合はこれから行う。

## ローカルでの確認

### 地形視界のローカル診断

Python 3.13以降を用いる。国土地理院のDEM10Bを`gsi/`へ置き、初回だけ変換する。

```bash
python3 terrain/scripts/convert_dem.py \
  gsi/20260816184830972-001.zip \
  --output gsi/derived-v1m
```

次のコマンドで、外部サービスを使わない地形確認画面を起動する。これはDEM・天文計算を切り分けて検証するための開発用サーバーであり、MVPの利用画面ではない。

```bash
python3 terrain/scripts/serve_terrain.py --data gsi/derived-v1m
```

ブラウザで <http://127.0.0.1:8787> を開き、緯度・経度・日付を入力する。日没方位と日没10分前の太陽高度は天文計算により自動で求められる。

### MVPのWebアプリ

Node.js 22.13以降を用いる。

```bash
read -s "VITE_GOOGLE_MAPS_API_KEY?Google Maps API key: "
echo
export VITE_GOOGLE_MAPS_API_KEY

cd site
npm ci
npm run dev
```

表示先のURLは起動時に表示される。Google Mapをクリックすると、予報対象の緯度・経度を選択できる。公開時は`npm run build`の成果物をWorkerへデプロイする。地形・気象処理とは未接続である。

Google Cloudでは、`Maps JavaScript API`だけを有効化したブラウザ用キーを作る。キーには次の制限を設定する。

```text
アプリケーションの制限: ウェブサイト
許可する参照元: http://localhost:3000/*
                 http://127.0.0.1:3000/*
APIの制限: Maps JavaScript API のみ
```

`npm run dev`はポート3000へ固定している。ポートが使用中の場合は別の番号へ移動せず起動に失敗するため、既存の開発サーバーを終了してから再実行する。

キーはGit管理せず、上記コマンドで起動したターミナルにだけ渡す。終了後は`unset VITE_GOOGLE_MAPS_API_KEY`で削除する。

## 検証

```bash
python3 -m unittest discover -s terrain/tests
python3 -m unittest discover -s weather/tests

cd site
npm run build
```

`gsi/`内の元データと変換済みタイル、`site/node_modules/`、`site/.next/`、`site/dist/`などの生成物はGit管理しない。
