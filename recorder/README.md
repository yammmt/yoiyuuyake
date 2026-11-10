# 日没予報の収集サービス

Issue #54 の予約・取得・保存を行う Rust サービス。
[実装方針](../docs/forecast-recording-plan.md) と [ADR 002](../docs/decisions/002-sunset-forecast-evaluation-records.md) に従う。
画面用の Python API は呼び出さず、日没計算と気象評価を Rust に移植している。地形データは不要。
配置後の結果と確認範囲は [配置・確認記録](../docs/forecast-recording-deployment.md) を参照する。

## 担当と呼び出し

| 担当 | 処理 |
| --- | --- |
| Cloud Scheduler | 日本時間の毎朝6:00に `POST /schedule` を呼ぶ |
| Rust の `/schedule` | 地点を読み、日没を計算し、Cloud Tasks に予約する |
| Cloud Tasks | 日没時刻に、予約内容を本文として `POST /collect` を呼ぶ |
| Rust の `/collect` | 予報の取得・検証・採点を行い、Firestore に新規保存する |
| Cloud Run | 上記2つの HTTP 処理の実行環境 |

HTTP 200 の `status` が処理結果。依存サービスの障害や検証失敗は HTTP 503 とし、呼び出し元の再試行に任せる。
アプリ内で HTTP リクエストの自動再試行は行わない。JMA の値が明示的に `null` の場合だけ、既存処理と同じく自動モデル選択に切り替える。

## 設定と認証

ルートの管理者所有 `.env` に環境固有値を記録する。認証情報は保存しない。
プログラムは `.env` を自動で読み込まない。Cloud Run へは環境変数として渡す。

| 環境変数 | 内容 |
| --- | --- |
| `PROJECT_ID` | 対象プロジェクトID |
| `TASKS_REGION` | `asia-northeast1` |
| `TASKS_QUEUE` | `forecast-fetch` |
| `RECORDER_URL` | このサービス自身の HTTPS `run.app` URL。パスを含めない |
| `TRIGGER_SERVICE_ACCOUNT` | 呼び出し用 `forecast-trigger` のメールアドレス |
| `PORT` | 待受ポート。既定値は `8080` |

実行主体は `forecast-recorder`。Cloud Run のメタデータ経由で認証し、キーファイルは使わない。
ローカル実行には ADC を利用できるが、接続先は実データベースになる。テストには認証もクラウド接続も不要。

| 身分 | 必要な権限と対象 |
| --- | --- |
| `forecast-recorder` | プロジェクトの `roles/datastore.user` |
| 同上 | `forecast-fetch` キューの `roles/cloudtasks.enqueuer` |
| 同上 | `forecast-trigger` に対する `roles/iam.serviceAccountUser` |
| `forecast-trigger` | 収集用 Cloud Run サービスの `roles/run.invoker` |
| 配置・Scheduler設定を行う本人 | 配置・設定の権限に加え、それぞれ指定するサービスアカウントの `iam.serviceAccounts.actAs` |

Cloud Tasks と Scheduler の Google 管理サービスエージェントには、それぞれ標準のサービスエージェントロールが必要。
通常は API の有効化時に設定されるが、作成や呼び出しが拒否された場合は確認する。
`forecast-trigger` に Firestore の権限やトークン作成者ロールを追加しない。

Cloud Run の IAM 認証を必須とする。アプリ独自の認証は設けておらず、ローカルの待受も外部公開しない。
Firestore のサーバーアクセスは IAM で制御され、ブラウザ用 Security Rules では制限されない。
`roles/datastore.user` は更新・削除も許可する。上書き防止は新規作成 API の使用で実現する。

## 記録形式と実行時の扱い

- 地点は `locations/home` の `name`（文字列）、`latitude`・`longitude`（数値）、`enabled`（真偽値）。
- 記録IDは日本時間の `home_YYYY-MM-DD`。`records/{記録ID}` が存在すれば取得・保存済みとする。
- 型は `schemaVersion` とスコアが整数、座標と気象値が数値、`targetDate` が `YYYY-MM-DD` 文字列、日時が Firestore Timestamp。`locationId` は `home`。
- `forecast.weather` は `startsAt`、`endsAt`、`units`、`hours`。各時間の気象変数名は Open-Meteo に合わせる。
- 対象時間帯は日没20分前から25分後。前端を正時に切り下げ、後端を切り上げた全時間を採点に使う。
- `forecast.fetchedAt` は採用した HTTP 応答の読み取り完了時刻。実測や気象モデル更新時刻ではない。
- `forecast.model` は `jma_seamless` または `best_match` という要求時の選択。`best_match` では実際に選択されたモデルを特定できない。
- `forecast.scoreVersion` は `weather-rules-v1`。既存 `weather/scripts/scoring.py` の初期ルールと同じ係数・閾値・丸め。式の変更時は識別子も更新する。
- 取得・検証・採点が成功した記録だけを `createDocument` で保存する。既存時の409は処理済みとし、更新APIは呼ばない。`observation` は `null`。
- 同じ地点・対象日の予約IDも固定し、予約作成の409を登録済みとして扱う。
- 地点は予約時の情報を本文に保持する。予約後に地点の名前・座標が変更された場合や無効化された場合は取得を見送る。変更は翌朝の予約から反映される。
- 日没以降に届いた朝の予約処理は予約を作らない。取得処理も日本時間の対象日を過ぎたら終了する。
- 日没直後や再試行の正確な実行時刻は保証しない。20分後を厳密な打ち切り時刻にはせず、同日内でキューの最大3試行に従う。
- 失敗時は記録を作らずログに理由を残す。全試行失敗と未実行は、記録の不在だけでは区別できないためログも確認する。

地点名、座標、認証情報、HTTP 本文はアプリログに出さない。Cloud Tasks の予約本文には地点情報があるため、タスク閲覧権限も本人と必要な処理に限定する。

## 手元での検証

```bash
cd recorder
cargo fmt --all -- --check
cargo test --locked
cargo clippy --locked --all-targets -- -D warnings
```

`rust-toolchain.toml` と `Cargo.lock` でコンパイラと依存を固定する。
固定データによるテストはクラウド・実際の Open-Meteo に接続しない。
`tests/fixtures/python-reference.json` は既存 Python から生成した日没12ケースと気象12ケースの期待値を含む。
リポジトリルートで `PYTHONPATH=. python3 recorder/tests/generate_reference.py` を実行すると期待値を再生成できる。計算の変更時は Python 側との差異も確認する。収集サービスの本番実行には Python は不要。

## ビルド・配置

以下は利用者本人が実行する手順であり、実施済みの記録ではない。
既存のビルド用アカウント、ソース保存バケット、Artifact Registry を利用する。
ビルド、イメージ保存、Cloud Run の実行、Firestore の読み書き・保存、Cloud Tasks、Scheduler、ログ・通信は費用の対象。
無料枠や最大インスタンス数は支出の強制上限ではない。
料金は [Cloud Run](https://cloud.google.com/run/pricing)、[Firestore](https://cloud.google.com/firestore/pricing)、[Cloud Tasks](https://cloud.google.com/tasks/pricing)、[Scheduler](https://cloud.google.com/scheduler/pricing) を作成前に確認する。

ルートで既存 `.env` を読み込み、`TASKS_REGION`、`TASKS_QUEUE`、`TRIGGER_SERVICE_ACCOUNT` を上表どおり追加する。
`RECORDER_IMAGE_URL` は以下のビルドが生成したイメージURLを記録する。既存 API の `IMAGE_URL` を置き換えない。

```bash
gcloud builds submit . \
  --project="$PROJECT_ID" --region=asia-northeast1 \
  --config=recorder/cloudbuild.yaml \
  --ignore-file=recorder/source.gcloudignore \
  --gcs-source-staging-dir="gs://${BUILD_SOURCE_BUCKET}/source" \
  --service-account="projects/${PROJECT_ID}/serviceAccounts/${BUILD_SERVICE_ACCOUNT}" \
  --timeout=20m
```

ビルド内で Rust のテストとリリースビルドを実行する。ソース送信・Docker の両方で許可リストを使い、`.env`、認証情報、DEM、生成物を含めない。

配置前に、[既定URLの形式](https://docs.cloud.google.com/run/docs/custom-urls) `https://サービス名-プロジェクト番号.リージョン.run.app` から収集用の `RECORDER_URL` を定める。
プロジェクト番号はプロジェクトの概要で確認し、完成したURLを `.env` に保存する。配置後に設定とURLへの応答を確認する。

```bash
gcloud run deploy forecast-recorder \
  --project="$PROJECT_ID" --region=asia-northeast1 \
  --image="$RECORDER_IMAGE_URL" \
  --service-account="forecast-recorder@${PROJECT_ID}.iam.gserviceaccount.com" \
  --no-allow-unauthenticated --invoker-iam-check \
  --ingress=all --cpu=1 --memory=256Mi --concurrency=1 \
  --min=0 --max=1 --cpu-throttling --timeout=120s \
  --set-env-vars="PROJECT_ID=${PROJECT_ID},TASKS_REGION=${TASKS_REGION},TASKS_QUEUE=${TASKS_QUEUE},RECORDER_URL=${RECORDER_URL},TRIGGER_SERVICE_ACCOUNT=${TRIGGER_SERVICE_ACCOUNT}"

gcloud run services add-iam-policy-binding forecast-recorder \
  --project="$PROJECT_ID" --region=asia-northeast1 \
  --member="serviceAccount:${TRIGGER_SERVICE_ACCOUNT}" --role=roles/run.invoker
```

`--ingress=all` は外部から到達できる入口を設けるが、IAM 認証により許可した主体だけが呼び出せる。`allUsers` や `allAuthenticatedUsers` の許可は付けない。
配置後は `gcloud run services describe` と `get-iam-policy` で、イメージ・実行アカウント・環境変数・IAM 認証設定・公開許可がないことを照合する。
認証なしの `POST /schedule` が拒否されること、許可された本人の認証付き呼び出しでは処理が通ることも確認する。本人にもサービス単位の呼び出し権限が必要。

## 予約から保存までの確認

1. 日没前に、権限を持つ本人が認証付きで `POST /schedule` を呼ぶ。Cloud Tasks の予約名、日時、URL、OIDC の主体と audience を確認する。
2. 同じ呼び出しを繰り返し、`already_scheduled` となり予約が増えないことを確認する。
3. 日没後、`records/home_対象日` を開く。地点情報、`sunsetAt` と `fetchedAt`、気象値・単位、スコアとバージョン、`observation: null` を確認する。
4. 同じ予約本文で `/collect` を再実行し、`already_saved` となり記録の `updateTime` と内容が変わらないことを確認する。
5. 障害時の再試行は別の検証用キューとテスト用データで確認し、本番データの破壊や本番用権限の一時解除で再現しない。

朝の処理を日没後に手動実行しても、その日の収集は開始しない。日没前の `/collect` 実行も保存せず失敗する。
強制実行で試行枠を消費しないよう、本番キューの「今すぐ実行」は通常の確認に使わない。

## 定期実行の有効化

手動で一連の動作を確認してから、Cloud Scheduler API を有効にして作成する。
キュー設定は `maxAttempts: 3`、`minBackoff: 600s`、`maxBackoff: 600s`、`maxRetryDuration: 0s` と照合する。

```bash
gcloud scheduler jobs create http forecast-reserve \
  --project="$PROJECT_ID" --location=asia-northeast1 \
  --schedule='0 6 * * *' --time-zone=Asia/Tokyo \
  --uri="${RECORDER_URL}/schedule" --http-method=POST \
  --oidc-service-account-email="$TRIGGER_SERVICE_ACCOUNT" \
  --oidc-token-audience="$RECORDER_URL" \
  --attempt-deadline=120s \
  --max-retry-attempts=2 --min-backoff=1800s --max-backoff=1800s \
  --max-doublings=0 --max-retry-duration=0s
```

作成後は Scheduler の設定を取得し、朝6:00・日本時間・最大2再試行・30分間隔を確認する。
翌日以降は実際の予約・保存とログまで確認し、設定成功だけで日没時の自動収集が成功したとは扱わない。
アプリログは `jsonPayload.fields.event="recorder_failed"` と `recorder_completed`、同じ `fields` 内の `operation` と `outcome` を確認する。

## 停止と削除

1. Scheduler の `forecast-reserve` を一時停止して、新しい予約作成を止める。
2. Cloud Tasks の `forecast-fetch` を一時停止して、登録済み予約の呼び出しも止める。不要なタスクを削除する。再開時に古い予約を残さない。
3. 必要に応じて Cloud Run の呼び出し権限を解除する。Firestore の `enabled: false` は対象除外であり、Scheduler 自体の停止ではない。
4. 終了する場合は記録を取り出してから、収集用サービス・キュー・Scheduler ジョブ・不要なイメージやビルドソースを削除する。共有の保存先や既存 API は削除しない。
5. データ保存を終えるなら Firestore のデータを削除する。他用途がないことを確認した場合のみデータベース自体を削除する。アクセスの遮断だけでは保存費用はなくならない。

一時停止中の Scheduler ジョブも料金計算の対象。不要になったら削除する。
削除後も請求レポートで残る保存資源・利用量を確認する。サービスアカウント無効化だけで全資源が停止・削除されるわけではない。

気象データ: [Open-Meteo](https://open-meteo.com/)（[利用条件](https://open-meteo.com/en/terms)、CC BY 4.0）。非商用の個人学習として無料APIを使う。データの公開・出力時にも出典を付ける。
