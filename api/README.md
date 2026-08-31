# ローカル統合 API

site が地点指定後に一度の呼び出しで今日の夕焼け評価を取得するための、ローカル Python API です。天文計算、Open-Meteo の気象評価、ローカル DEM の地形評価がすべて成功した場合にだけ結果を返します。

## 起動

Python 3.13 以降と、変換済みの国土地理院 DEM が必要です。

```bash
python3 api/server.py --data gsi/derived-v1m
```

サーバーは `127.0.0.1:8787` だけで待ち受けます。別のポートを使う場合は `--port` を指定します。Cloudflare やデータベースなどの外部実行基盤は使用しません。

## API 契約

```http
GET /api/forecast?lat=35.6812&lng=139.7671
```

`lat` と `lng` はそれぞれ一つだけ必要です。対象は日本国内、日付は API 実行時の日本時間における今日に固定しています。

正常時は HTTP 200 と次の形の JSON を返します。

```json
{
  "location": {
    "latitude": 35.6812,
    "longitude": 139.7671
  },
  "sunset": {
    "time": "2026-08-31T18:08:00+09:00",
    "azimuth_degrees": 279.1,
    "viewing_window": {
      "starts_at": "2026-08-31T17:48:00+09:00",
      "ends_at": "2026-08-31T18:33:00+09:00"
    }
  },
  "weather": {
    "gradient": {
      "score": 77,
      "positive_factors": ["視程が良い"],
      "negative_factors": ["低層雲が多い"]
    },
    "dramatic": {
      "score": 94,
      "positive_factors": ["中層雲が適量"],
      "negative_factors": []
    }
  },
  "terrain": {
    "visibility": "広い",
    "description": "日没方向の地形による遮蔽は小さい見込みです。",
    "observer_elevation_meters": 4.0,
    "maximum_horizon_angle_degrees": 0.8,
    "obstructing_azimuth_degrees": 271.5,
    "obstructing_distance_meters": 2000,
    "comparison_sun_altitude_degrees": 1.1,
    "sun_likely_occluded": false
  },
  "notice": "見晴らしは地形を考慮した推定です。建物・樹木などの遮蔽物は考慮していません。"
}
```

時刻は JST の ISO 8601 形式です。地形と太陽高度の比較には日没 10 分前を使います。

失敗時は評価結果を一切含めず、次の共通形式を返します。

```json
{
  "error": {
    "code": "weather_unavailable",
    "message": "気象予報を利用できません"
  }
}
```

| HTTP | `code` | 意味 |
| ---: | --- | --- |
| 400 | `invalid_input` | 座標の欠落・重複・形式・日本国内の範囲が不正 |
| 502 | `weather_unavailable` | Open-Meteo の取得、必要時間の不足、採点のいずれかに失敗 |
| 503 | `dem_unavailable` | DEM の未配置、破損、範囲外、標高欠損のいずれか |

レスポンスはキャッシュされず、ローカルで起動した site から呼べるよう GET と OPTIONS に CORS ヘッダーを付けています。

## テスト

外部 API や実際の DEM に依存せず、正常系、入力不正、気象失敗、DEM 失敗、HTTP 契約を検証します。

```bash
python3 -m unittest discover -s api/tests
```
