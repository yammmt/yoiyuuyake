# ローカル DEM 地形視界エンジン

国土地理院の基盤地図情報（数値標高モデル）DEM10Bをローカル形式へ変換し、指定地点から日没方向の地形見上げ角を計算する。

データの取得、出典・利用条件、実測容量、全国カバレッジの詳細は[全国DEM10Bの準備](../docs/dem10b-setup.md)を参照する。

## 変換と検証

以下の期待タイル数は、[2026-09-02検証スナップショット](../docs/dem10b-setup.md#検証対象スナップショット)に対する値である。

```bash
python3 terrain/scripts/convert_dem.py \
  gsi/FG-GML-*-DEM10-*.zip \
  --output gsi/derived-dem10b-v1

python3 terrain/scripts/validate_dataset.py \
  --data gsi/derived-dem10b-v1 \
  --expected-tiles 4885

python3 terrain/scripts/validate_locations.py \
  --data gsi/derived-dem10b-v1
```

変換器はDEM10Bだけを対象とし、同一内容の重複メッシュをまとめる。競合する重複または既存の出力先がある場合は失敗し、変換途中のデータを最終出力として公開しない。

## タイル形式

2次メッシュ1枚を`tiles/`直下の1ファイルへ変換する。

```text
gsi/derived-dem10b-v1/
├── index.json
└── tiles/
    ├── 303650.dem
    └── ...
```

- 750行 × 1125列
- 1m単位の signed 16-bit little-endian整数
- 欠損値は`-32768`
- メッシュ番号、ファイル、地理範囲、行列数、元データ名は`index.json`に保持

## 標高と地平線の照会

```bash
python3 terrain/scripts/query_dem.py \
  --data gsi/derived-dem10b-v1 \
  --latitude 35.6812 \
  --longitude 139.7671
```

```bash
python3 terrain/scripts/query_horizon.py \
  --data gsi/derived-dem10b-v1 \
  --latitude 35.6812 \
  --longitude 139.7671 \
  --azimuth 270 \
  --sun-altitude 1
```

地平線計算は日没方位を中心に9本（±20°）のレイを飛ばし、50mごとに最大50kmまで標高を読む。最大地形見上げ角が1°以下なら`広い`、1°超から4°以下なら`一部遮られる`、4°超なら`遮られやすい`とする。

観測地点またはレイ途中で標高欠損・準備範囲外を検出した場合は、途中までの結果から視界を推測せず、計算全体を失敗させる。このため、沿岸部や島嶼部では全国DEMを準備していても評価できない場合がある。

## ローカル診断画面

```bash
python3 terrain/scripts/serve_terrain.py --data gsi/derived-dem10b-v1
```

<http://127.0.0.1:8787>を開くと、外部APIなしで座標と日没方位から地形視界を確認できる。日没方位を省略した場合は、JSTの日付と緯度経度から日没時刻・方位を計算する。

## 出典

> 出典：[国土地理院「基盤地図情報（数値標高モデル）DEM10B」](https://service.gsi.go.jp/kiban/app/help/)
>
> [国土地理院「基盤地図情報（数値標高モデル）DEM10B」](https://service.gsi.go.jp/kiban/app/help/)を加工して作成

公開・配布前の利用条件と申請要否は[詳細文書](../docs/dem10b-setup.md#出典と利用条件)で確認する。
