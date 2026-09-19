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

地点別の経過時間を表示するには、`validate_locations.py` に `--timing` を付ける。
`TIME store_init` はインデックスの読み込みを含むストア初期化時間、各地点の
`elapsed` は地形計算・視界判定・期待値との比較にかかった時間で、出力時間を含まない。
通常の検証と同じく全地点で一つのストアを共有するため、地点ごとにストアを作る
APIの応答時間とは異なる。OSのファイルキャッシュはリセットしない。
ローカルの初期計測は[クラウド配置の検証記録](../docs/cloud-benchmark.md)を参照する。

## 検証用の範囲抽出

全国DEMを残したまま、指定矩形に重なるタイルを別フォルダへコピーする。
境界に接するタイルも丸ごと保持し、インデックスには選択したタイルだけを残す。
標高値・欠損値は変更しない。出力先が既に存在する場合は上書きせず終了する。

```bash
python3 terrain/scripts/subset_dem.py \
  --data gsi/derived-dem10b-v1 \
  --output gsi/derived-dem10b-kanto-v1 \
  --south 35 --north 36.5 --west 138.5 --east 140.5
```

これは関東全域を保証する範囲ではなく、東京周辺のクラウド検証用の範囲である。
2026-09-02検証スナップショットでは330タイル、タイル容量は約531 MiB。
タイル単位で選ぶため実際の外接範囲は指定矩形より広くなるが、海上等の欠損は残る。
正常評価用の地点では最大50kmのレイが収まることを別途確認する。
インデックス縮小で検索時間が変わり得るため、同じ抽出データでローカル計測を取り直す。

抽出後は専用のケースで検証する。正常3地点で三段階の視界、鎌倉と東京湾で
レイ上・観測地点の欠損、西端付近と範囲外でレイ上・観測地点の範囲外を確認する。
全国用のケースをそのまま使うと対象外地点で失敗する。

```bash
python3 terrain/scripts/validate_locations.py \
  --data gsi/derived-dem10b-kanto-v1 \
  --cases terrain/validation/locations-kanto.json \
  --timing
```

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
