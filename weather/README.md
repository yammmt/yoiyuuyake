# 気象予報モジュール

Open-Meteoから、夕焼け評価に必要な今日の時間別予報を取得します。API通信、日没前後の抽出、スコア計算は分離します。

```text
open_meteo.py  → API通信とレスポンス検証
sunset_window.py → 日没前後の時間を選ぶ（次段階）
scoring.py → Gradient / Dramaticを採点（次段階）
```

## 取得する変数

- 低層・中層・高層・総雲量
- 視程、相対湿度、降水量、風速

## 取得と検証のルール

時刻は必ず `Asia/Tokyo`、対象期間は今日の1日分として取得し、JMA Seamlessモデル（`jma_seamless`）を優先指定します。JMAモデルの応答に明示的な `null` が含まれる場合に限り、Open-Meteoの自動モデル選択（`models`指定なし）で一度だけ再取得します。

次の場合は値の補完や推測をせず、`OpenMeteoError`を返します。

- HTTPエラー、通信失敗、不正なJSON
- 必須変数の欠落、空配列、配列長の不一致
- ISO 8601でない時刻
- 数値でない値、`null`（フォールバック後を含む）、非有限値
- 雲量・湿度の0〜100%範囲外、または視程・降水量・風速の負値

このフォールバックは欠損値を補間するものではありません。自動選択モデルでも完全な値を取得できなければ、評価不能として失敗します。また、JMA指定時のHTTPエラーや不正応答はモデルカバレッジ不足とは区別し、そのまま失敗させます。

## 利用方法

```python
from weather.scripts.open_meteo import OpenMeteoError, fetch_today_forecast

try:
    hours = fetch_today_forecast(35.6812, 139.7671)
except OpenMeteoError as error:
    # スコアを推測せず、呼び出し側で再試行可能なエラーとして扱う
    print(error)
```

テストは`weather/tests/fixtures/open_meteo_forecast.json`を使用し、実際のOpen-Meteo APIへ接続しません。

```bash
python3 -m unittest discover -s weather/tests
```
