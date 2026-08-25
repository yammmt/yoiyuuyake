# 気象予報モジュール

Open-Meteoから、夕焼け評価に必要な今日の時間別予報を取得します。API通信、日没前後の抽出、スコア計算は分離し、外部からは一つの統合関数として利用できます。

```text
open_meteo.py  → API通信とレスポンス検証
sunset_window.py → 日没前後の時間を選ぶ
scoring.py → Gradient / Dramaticを採点
evaluation.py → 取得・抽出・採点を統合する外部インターフェース
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

## 日没前後の抽出ルール

採点の対象期間は、MVPの見頃の目安と同じ「日没20分前から日没25分後まで」です。Open-Meteoの1時間ごとの予報から、この期間の両端を覆う正時の値をすべて選びます。

- 日没18:24の場合: 対象18:04〜18:49、選択する予報18:00・19:00
- 日没18:00の場合: 対象17:40〜18:25、選択する予報17:00・18:00・19:00

日没時刻と予報時刻はタイムゾーン付きで受け取り、`Asia/Tokyo`に変換して比較・出力します。Open-Meteoが返すJSTのローカル時刻には取得時に`Asia/Tokyo`を付与します。必要な正時の予報が1つでもない場合、重複する場合、正時でない値が混じる場合は、補間や代用をせず`SunsetWindowError`を返します。

## 採点ルール

選択済みの日没時間帯に含まれる各時間の値を変数ごとに算術平均し、次のルールで0〜1に正規化します。閾値の外側は0または1に収めます。

| 気象要素 | 正規化方法 | 0になる条件 | 1になる条件 |
| --- | --- | ---: | ---: |
| 低層雲量 | `(100 − 雲量) / 100` | 100% | 0% |
| 中層雲量 | `雲量 / 100` | 0% | 100% |
| 高層雲量 | `雲量 / 100` | 0% | 100% |
| 総雲量 | `(100 − 雲量) / 100` | 100% | 0% |
| 視程 | `(視程 − 5 km) / 20 km` | 5 km以下 | 25 km以上 |
| 相対湿度 | `(90 − 湿度) / 50` | 90%以上 | 40%以下 |
| 降水量 | `1 − 降水量 / 1 mm` | 1 mm以上 | 0 mm |
| 風速 | `(15 − 風速) / 10` | 15 km/h以上 | 5 km/h以下 |

正規化値が大きいことは、必ずしも高得点を意味しません。`Dramatic`の中層雲・高層雲・総雲量には、適量で最大となり、少なすぎても多すぎても低下する評価を適用します。

`Gradient`は雲が少なく透明感のある空を評価します。各正規化値に以下の最大点を掛け、合計を四捨五入します。

| 要因 | 最大点 |
| --- | ---: |
| 低層雲が少ない | 30 |
| 総雲量が少ない | 15 |
| 視程が良い | 20 |
| 湿度が低い | 10 |
| 降水がない | 20 |
| 風が強くない | 5 |

`Dramatic`は中層・高層雲が適量ある空を評価します。雲量は、少なすぎても多すぎても点が下がる台形型のルールです。中層雲は30〜60%、高層雲は35〜70%、総雲量は30〜70%で満点になります。中層・高層雲は5%以下または95%以上、総雲量は10%以下または95%以上で0点となり、その間は線形に変化します。

| 要因 | 最大点 |
| --- | ---: |
| 低層雲が少ない | 20 |
| 中層雲が適量 | 20 |
| 高層雲が適量 | 20 |
| 総雲量が適量 | 10 |
| 視程が良い | 10 |
| 降水がない | 15 |
| 湿度が低い | 3 |
| 風が強くない | 2 |

両スコアとも0〜100に制限します。要因ごとの実得点と最大点を`ScoreFactor`として保持し、最大点の70%以上を得た要因を主な加点要因、30%以下の要因を主な減点要因として結果に含めます。これにより、快晴は`Gradient`には有利ですが、中層・高層雲の点が得られないため`Dramatic`が常に高得点にはなりません。

## 利用方法

日没時刻は、天文計算を担当する呼び出し側から、日本時間で今日の日付となるタイムゾーン付きの`datetime`として渡します。

```python
from datetime import datetime
from zoneinfo import ZoneInfo

from terrain.scripts.astronomy import sunset_on
from weather.scripts.evaluation import (
    WeatherEvaluationError,
    evaluate_sunset_weather,
)

latitude = 35.625
longitude = 139.75
today_jst = datetime.now(ZoneInfo("Asia/Tokyo")).date()
sunset = sunset_on(today_jst, latitude, longitude).time

try:
    result = evaluate_sunset_weather(latitude, longitude, sunset)
    print(result.gradient.score, result.dramatic.score)
except WeatherEvaluationError as error:
    # codeで入力不正・取得失敗・データ不足・採点不能を区別できる
    print(error.code.value, error)
```

`SunsetWeatherEvaluation`は、地点、JSTに正規化した日没時刻と見頃の開始・終了、`Gradient` / `Dramatic`の点数・加減点要因を返します。エラー時は結果を返さず、`WeatherEvaluationError.code`が次のいずれかになります。

- `invalid_input`: 緯度・経度または日没日時が不正
- `forecast_fetch_failed`: Open-Meteoの通信・応答・値の検証に失敗
- `forecast_data_insufficient`: 日没前後に必要な正時の予報が不足・重複
- `scoring_failed`: 完全な採点結果を計算できない

テストは`weather/tests/fixtures/open_meteo_forecast.json`を使用し、実際のOpen-Meteo APIへ接続しません。

```bash
python3 -m unittest discover -s weather/tests
```
