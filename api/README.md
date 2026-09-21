# 統合 API

site が地点指定後に一度の呼び出しで今日の夕焼け評価を取得するための Python API である。
天文計算、Open-Meteo の気象評価、ローカル DEM の地形評価がすべて成功した場合にだけ結果を返す。

## ローカル起動

Python 3.13 以降と、変換済みの国土地理院 DEM が必要である。

```bash
python3 api/server.py --data gsi/derived-dem10b-v1
```

サーバーは既定で `127.0.0.1:8787` だけで待ち受ける。`--host`、`--port`、`--data` で変更できる。
同じ値を `HOST`、`PORT`、`DEM_ROOT` でも指定でき、コマンドライン引数を指定した場合はそちらを優先する。

```bash
HOST=0.0.0.0 PORT=8080 DEM_ROOT=gsi/derived-dem10b-v1 \
  python3 -m api.server
```

起動時に DEM の `index.json` を読み、利用できなければ待受を開始せず終了コード 1 で停止する。
ローカルサーバーは開発確認用であり、公開コンテナでは Gunicorn を使用する。

## Cloud Run 用コンテナ

採用構成は Cloud Run（東京）から Cloud Storage の DEM を読み取り専用でマウントする構成である。
コンテナは Cloud Run が設定する `PORT` を Gunicorn で待ち受け、`DEM_ROOT` を変換済み DEM のディレクトリに設定する。
依存は Gunicorn のみで、API の評価ロジックはローカル起動と共有する。

ローカルでコンテナを確認する場合は、リポジトリルートで次を実行する。

```bash
docker build --file api/Dockerfile --tag yoiyuuyake-api:local .

docker run --rm \
  --publish 8080:8080 \
  --env PORT=8080 \
  --env DEM_ROOT=/dem \
  --volume "$PWD/gsi/derived-dem10b-v1:/dem:ro" \
  yoiyuuyake-api:local
```

別ターミナルから正常系を確認する。

```bash
curl --fail-with-body --silent --show-error \
  'http://127.0.0.1:8080/api/forecast?lat=35.6812&lng=139.7671'
```

### ビルド

事前に東京リージョンへ Docker 形式の Artifact Registry リポジトリ `yoiyuuyake` と、Cloud Build のソース用バケットを用意する。
`PROJECT_ID`、`BUILD_SOURCE_BUCKET`、`BUILD_SERVICE_ACCOUNT` は実環境の値へ置き換える。

```bash
gcloud builds submit . \
  --project=PROJECT_ID \
  --region=asia-northeast1 \
  --config=api/cloudbuild.yaml \
  --ignore-file=api/source.gcloudignore \
  --gcs-source-staging-dir=gs://BUILD_SOURCE_BUCKET/source \
  --service-account=projects/PROJECT_ID/serviceAccounts/BUILD_SERVICE_ACCOUNT \
  --machine-type=e2-standard-2 \
  --timeout=10m
```

送信対象と Docker のビルド対象は許可リストで制限しており、`gsi/` の DEM、認証情報、site の生成物を含めない。
ビルドはイメージ内で Gunicorn 設定の読み込みも検証する。

### 配置

次は Issue #36 の検証で採用した 1 CPU・512 MiB・同時実行 1・ファイルキャッシュ 128 MiB の設定例である。
`IMAGE_URL` はビルドしたイメージのタグまたはダイジェスト、`DEM_BUCKET` は全国 DEM を配置したバケット、`RUNTIME_SERVICE_ACCOUNT` はバケットに `roles/storage.objectViewer` だけを持つ実行用サービスアカウントへ置き換える。

```bash
gcloud run deploy yoiyuuyake-api \
  --project=PROJECT_ID \
  --region=asia-northeast1 \
  --image=IMAGE_URL \
  --service-account=RUNTIME_SERVICE_ACCOUNT \
  --execution-environment=gen2 \
  --cpu=1 \
  --memory=512Mi \
  --concurrency=1 \
  --min=0 \
  --max=1 \
  --cpu-throttling \
  --no-cpu-boost \
  --timeout=60s \
  --allow-unauthenticated \
  --invoker-iam-check \
  --set-env-vars=DEM_ROOT=/dem/derived-dem10b-v1 \
  --add-volume=name=dem-cache,type=in-memory,size-limit=160Mi \
  --add-volume-mount=volume=dem-cache,mount-path=/dem-cache \
  --add-volume='name=dem,type=cloud-storage,bucket=DEM_BUCKET,readonly=true,mount-options=cache-dir=cr-volume:dem-cache;file-cache-max-size-mb=128;file-cache-cache-file-for-range-read=true' \
  --add-volume-mount=volume=dem,mount-path=/dem
```

ブラウザの site が直接呼び出すため未認証アクセスを許可する。書き込み API はなく、DEM マウントと Storage 権限は読み取り専用とする。
`PORT` は Cloud Run の予約済み環境変数なのでデプロイ時に設定しない。

### 起動・API 契約の確認

Gunicorn はリクエストを受け付ける前に DEM インデックスを検証する。デプロイ完了後はサービス URL を確認し、正常系と入力不正をそれぞれ確認する。

```bash
gcloud run services describe yoiyuuyake-api \
  --project=PROJECT_ID \
  --region=asia-northeast1 \
  --format='value(status.url)'

curl --fail-with-body --silent --show-error --max-time 65 \
  'SERVICE_URL/api/forecast?lat=35.6812&lng=139.7671'

curl --silent --show-error --include \
  'SERVICE_URL/api/forecast?lat=0&lng=0'
```

一つ目は HTTP 200 と完全な評価、二つ目は HTTP 400 と `invalid_input` だけを返すことを確認する。
気象取得失敗は HTTP 502、DEM の欠損・範囲外・障害は HTTP 503 となり、既存のエラー本文を維持する。

### ログ

起動、終了、リクエスト完了、評価失敗を 1 行 JSON で標準出力へ記録する。
緯度・経度とクエリ文字列はアプリケーションログへ記録しない。
起動失敗と API エラーは次のように確認できる。

```bash
gcloud logging read \
  'resource.type="cloud_run_revision"
   AND resource.labels.service_name="yoiyuuyake-api"
   AND (jsonPayload.event="startup_failed"
        OR jsonPayload.event="forecast_failed")' \
  --project=PROJECT_ID \
  --freshness=1h \
  --order=desc \
  --limit=30 \
  --format=json
```

Cloud Run からの `SIGTERM` は Gunicorn が処理し、処理中のリクエストを 9 秒まで待って終了する。
Cloud Run の 10 秒の終了猶予内に収める設定である。

関連する公式資料:

- [Cloud Run のコンテナ ランタイム契約](https://docs.cloud.google.com/run/docs/container-contract)
- [Cloud Storage ボリュームのマウント](https://docs.cloud.google.com/run/docs/configuring/services/cloud-storage-volume-mounts)
- [Cloud Run の Python アプリ最適化](https://docs.cloud.google.com/run/docs/tips/python)

## API 契約

```http
GET /api/forecast?lat=35.6812&lng=139.7671
```

`lat` と `lng` はそれぞれ一つだけ必要である。対象は日本国内、日付は API 実行時の日本時間における今日に固定している。

正常時は HTTP 200 と次の形の JSON を返す。

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

時刻は JST の ISO 8601 形式である。地形と太陽高度の比較には日没 10 分前を使用する。

失敗時は評価結果を一切含めず、次の共通形式を返す。

```json
{
  "error": {
    "code": "dem_unavailable",
    "reason": "ray_out_of_coverage",
    "message": "日没方向が地形データ対象範囲を越えるため、見晴らしを評価できません。別の地点を選択してください。"
  }
}
```

`reason` は `dem_unavailable` の場合に付加し、利用者向けメッセージより詳細な原因を安定した値で示す。

| HTTP | `code` | 意味 |
| ---: | --- | --- |
| 400 | `invalid_input` | 座標の欠落・重複・形式・日本国内の範囲が不正 |
| 502 | `weather_unavailable` | Open-Meteo の取得、必要時間の不足、採点のいずれかに失敗 |
| 503 | `dem_unavailable` | DEM の未配置、破損、範囲外、標高欠損のいずれか |

| `reason` | 意味 | 利用者への案内 |
| --- | --- | --- |
| `observer_no_elevation` | 観測地点の標高が欠損 | 少し離れた地点を選択 |
| `observer_out_of_coverage` | 観測地点が準備済みDEM範囲外 | 別地点を選択 |
| `ray_no_elevation` | レイ途中の標高が欠損 | 別地点を選択 |
| `ray_out_of_coverage` | レイが準備済みDEM範囲外へ出る | 別地点を選択 |
| `dem_data_unavailable` | DEMの未配置・インデックス異常・タイル欠落または破損 | 時間をおいて再試行 |
| `terrain_calculation_failed` | 地形計算自体が失敗 | 時間をおいて再試行 |

DEM10Bでは海上と陸上のデータ欠損を区別できないため、どちらも `observer_no_elevation` または `ray_no_elevation` として扱う。

レスポンスはキャッシュされず、ローカルで起動した site から呼べるよう GET と OPTIONS に CORS ヘッダーを付けている。

## テスト

外部 API や実際の DEM に依存せず、正常系、入力不正、気象失敗、DEM 失敗、ローカル HTTP と公開 WSGI の契約を検証する。

```bash
python3 -m unittest discover -s api/tests
```
