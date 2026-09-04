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
![高彩度例 2](./fig/example_dramatic_02.jpg)

## 動くもの

![大きめ画面 GUI](./fig/gui_deskop.png)

## 構成

```text
site/       地点指定と夕焼け評価を表示するWebアプリ
api/        日没・気象・地形をまとめるローカルPython API
terrain/    DEM変換、天文計算、地形視界
weather/    Open-Meteoの取得と夕焼けスコア
docs/       MVP仕様、データ準備、判断記録
gsi/        Git管理外のDEM元データと変換済みタイル
```

## ローカル起動

Python 3.13以降とNode.js 22.13以降を使用する。

初回だけ、[全国DEM10Bの準備](docs/dem10b-setup.md#検証対象スナップショット)に記載した2026-09-02検証スナップショットの地方区分ZIPを11個取得し、全国データへ変換する。取得、利用条件、容量、検証の詳細も同文書を参照する。

```bash
python3 terrain/scripts/convert_dem.py \
  gsi/FG-GML-*-DEM10-*.zip \
  --output gsi/derived-dem10b-v1

python3 terrain/scripts/validate_dataset.py \
  --data gsi/derived-dem10b-v1 \
  --expected-tiles 4885
```

ターミナル1で統合APIを起動する。

```bash
python3 api/server.py --data gsi/derived-dem10b-v1
```

ターミナル2でGoogle Maps APIキーを渡し、Webアプリを起動する。

```bash
cd site
npm ci
read -r -s -p "Google Maps API key: " VITE_GOOGLE_MAPS_API_KEY
echo
export VITE_GOOGLE_MAPS_API_KEY
npm run dev
```

Webアプリの既定URLは <http://localhost:3000>、統合APIは <http://127.0.0.1:8787> である。APIキーの制限と別ポートの指定方法は[siteのREADME](site/README.md)を参照する。

## 開発と検証

- [地形エンジン](terrain/README.md)
- [統合API契約](api/README.md)
- [Webアプリ](site/README.md)
- [気象取得とスコア](weather/README.md)

```bash
python3 -m unittest discover -s api/tests
python3 -m unittest discover -s terrain/tests
python3 -m unittest discover -s weather/tests

cd site
npm test
```

`gsi/`内の元データと変換済みタイル、`site/node_modules/`、`site/.next/`、`site/dist/`などの生成物はGit管理しない。

## データ出典

標高データは国土地理院のものを使用する。

> 出典：[国土地理院「基盤地図情報（数値標高モデル）DEM10B」](https://service.gsi.go.jp/kiban/app/help/)
>
> [国土地理院「基盤地図情報（数値標高モデル）DEM10B」](https://service.gsi.go.jp/kiban/app/help/)を加工して作成
