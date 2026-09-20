# 地形読み取りの検証コンテナ

Issue #36専用の固定ケース実行サーバー。本番の予報APIとは別に使用する。
Python標準ライブラリのみで動く。Cloud Runでは認証必須、同時実行数1で配置する。
採用判断・測定結果・費用は[検証記録](../../docs/cloud-benchmark.md)を参照。

## ローカル確認

リポジトリのルートで起動する。

```bash
python3 terrain/scripts/benchmark_server.py --data gsi/derived-dem10b-kanto-v1
```

別のターミナルから実行する。

```bash
curl --fail-with-body --silent --show-error http://127.0.0.1:8080/benchmark
```

終了はサーバー側でCtrl+C。1リクエストで固定7地点を順番に評価し、期待値と
比較する。期待するDEM欠損・範囲外は検証成功と扱い、全ケース成功ならHTTP 200、
不一致や予期しない障害はHTTP 500。これは診断応答であり、予報APIの契約ではない。

本番APIに合わせ、地点ごとにDEMストアを生成・破棄する。
既存のvalidate_locations.pyはストアを全地点で共有するため、厳密な比較には
ローカル・クラウドともこのサーバーを使用する。
OSやマウントのキャッシュは維持する。

- `process_id` / `request_sequence`: 同じプロセスの初回・再アクセスを区別する。
  初回番号だけでOS・マウントキャッシュが空であるとは断定しない。
- `store_init_seconds`: 地点ごとのインデックス読み込み・ストア初期化時間。
- `evaluation_seconds`: 地形計算・視界判定・期待値比較時間。
- 地点の`total_seconds`: 初期化からファイルを閉じるまで。
- 応答全体の`total_seconds`: 7地点の実行時間。起動待ち・通信・JSON生成は含まない。
  利用者側の応答時間は別途測定する。
- `process_peak_rss_bytes`: Pythonプロセスの起動以来の最大RSS。
  マウント側やコンテナ全体の使用メモリはCloud Monitoringで別途確認する。

## Cloud Build でのビルド

以下は作成済みの検証環境で再現する手順。コマンドはリポジトリのルートから実行する。
DEM の抽出は[範囲抽出手順](../README.md#検証用の範囲抽出)を参照。

| 前提リソース | 権限・設定 |
| --- | --- |
| DEM バケット `mapsproduction-507807-dem-benchmark` | 東京・Standard、関東版 DEM を配置済み。`maps-python-api` に `roles/storage.objectViewer` |
| ソースバケット `mapsproduction-507807-build-source` | 東京・Standard、ビルド用アカウントに `roles/storage.objectViewer` |
| Artifact Registry `dem-benchmark` | 東京・Docker 形式、ビルド用アカウントに `roles/artifactregistry.writer` |
| ビルド用アカウント `903647380527-compute@developer.gserviceaccount.com` | プロジェクトに `roles/logging.logWriter` |

両バケットは uniform bucket-level access、public access prevention を有効、soft delete を無効にした。
Cloud Build、Artifact Registry、Cloud Run、Storage、IAM 関連 API は有効化済み。
実行者にはビルド・デプロイと各サービスアカウントを使用する権限が必要。

ソース送信は `source.gcloudignore`、イメージ内のファイルは Dockerfile で制限し、DEM・認証情報を含めない。
ビルドではコンテナ内の `--help` 実行を確認し、ビルド ID をタグとしてイメージを保存する。

```bash
gcloud builds submit . \
  --project=mapsproduction-507807 \
  --region=asia-northeast1 \
  --config=terrain/benchmark/cloudbuild.yaml \
  --ignore-file=terrain/benchmark/source.gcloudignore \
  --gcs-source-staging-dir=gs://mapsproduction-507807-build-source/source \
  --service-account=projects/mapsproduction-507807/serviceAccounts/903647380527-compute@developer.gserviceaccount.com \
  --machine-type=e2-standard-2 \
  --timeout=10m
```

ビルド設定は `--config` で別途送信するため、ソースの許可リストには含めない。
再ビルドした場合は `gcloud builds describe BUILD_ID --project=mapsproduction-507807 --region=asia-northeast1 --format="yaml(results.images)"` でダイジェストを確認する。

## Cloud Run への配置

以下は検証済みイメージを使い、採用したキャッシュ設定を含めて配置するコマンド。
再ビルドしたイメージを使う場合は `--image` のダイジェストを置き換える。

```bash
gcloud run deploy dem-benchmark \
  --project=mapsproduction-507807 \
  --region=asia-northeast1 \
  --image=asia-northeast1-docker.pkg.dev/mapsproduction-507807/dem-benchmark/terrain@sha256:9e23a9e96d4a6c42d5bc970defb2660ce6f61ecc1acaf4f7c4b74a96c3043e06 \
  --service-account=maps-python-api@mapsproduction-507807.iam.gserviceaccount.com \
  --execution-environment=gen2 \
  --cpu=1 \
  --memory=512Mi \
  --concurrency=1 \
  --min=0 \
  --max=1 \
  --cpu-throttling \
  --no-cpu-boost \
  --timeout=300s \
  --no-allow-unauthenticated \
  --invoker-iam-check \
  --add-volume=name=dem-cache,type=in-memory,size-limit=160Mi \
  --add-volume-mount=volume=dem-cache,mount-path=/dem-cache \
  --add-volume='name=dem,type=cloud-storage,bucket=mapsproduction-507807-dem-benchmark,readonly=true,mount-options=cache-dir=cr-volume:dem-cache;file-cache-max-size-mb=128;file-cache-cache-file-for-range-read=true' \
  --add-volume-mount=volume=dem,mount-path=/dem
```

## 認証付きで測定

```bash
curl --fail-with-body --silent --show-error \
  --max-time 310 \
  --header "Authorization: Bearer $(gcloud auth print-identity-token)" \
  --output /tmp/dem-benchmark.json \
  --write-out 'HTTP %{http_code}\nHTTP total: %{time_total} s\n' \
  https://dem-benchmark-903647380527.asia-northeast1.run.app/benchmark

python3 -m json.tool --no-ensure-ascii /tmp/dem-benchmark.json
```

再アクセスは同じコマンドを実行し、`process_id` が同じで `request_sequence` が増えたことを確認する。
起動待ち込みの測定では、要求到着後に同じインスタンスが起動したことをログで照合する。

```bash
gcloud logging read \
  'resource.type="cloud_run_revision"
   AND resource.labels.service_name="dem-benchmark"
   AND (httpRequest.requestUrl:"/benchmark"
        OR textPayload:"Starting new instance"
        OR textPayload:"Benchmark server listening")' \
  --project=mapsproduction-507807 \
  --freshness=1h --order=desc --limit=30 \
  --format="json(timestamp,httpRequest,labels.instanceId,textPayload)"
```
