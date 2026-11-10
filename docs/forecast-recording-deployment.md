# 予報収集サービスの配置・確認記録

Issue #54 の配置と、2026-11-10 の自動保存の確認結果を記録する。
クラウド操作は利用者本人が行った。本書は会話で共有された出力と利用者の確認報告に基づき、設定をこちらで直接取得した記録ではない。
設計は [実装方針](forecast-recording-plan.md) と [ADR 002](decisions/002-sunset-forecast-evaluation-records.md)、汎用的な配置・停止手順は [収集サービスの README](../recorder/README.md) を参照する。

## 配置した構成

| サービス・資源 | 用途・確認した設定 |
| --- | --- |
| Firestore | Standard、Native モード、`(default)`、`asia-northeast1` |
| `locations/home` | 生活拠点1か所。地点名、緯度・経度、有効フラグを登録 |
| Cloud Run `forecast-recorder` | Rust の予約処理と取得・保存処理を実行。IAM 認証を必須とする |
| Cloud Tasks `forecast-fetch` | 日没時刻の取得予約。最大3試行、再試行間隔600秒、最大再試行期間0秒 |
| Cloud Scheduler `forecast-reserve` | 毎朝6:00、日本時間。失敗後1800秒間隔で最大2回再試行 |

実環境のプロジェクトID、URL、イメージURL、アカウントのメールアドレスは、Git 管理外のルート `.env` に保存する。認証情報や生活拠点の座標は公開文書に記載しない。
収集用イメージは `RECORDER_IMAGE_URL`、サービスURLは `RECORDER_URL` として記録した。既存の画面用 API は別サービスとして維持する。

## 権限と非公開設定

| 主体 | 付与先・権限 |
| --- | --- |
| `forecast-recorder` | プロジェクトの `roles/datastore.user` |
| 同上 | `forecast-fetch` キューの `roles/cloudtasks.enqueuer` |
| 同上 | `forecast-trigger` に対する `roles/iam.serviceAccountUser` |
| `forecast-trigger` | 収集用 Cloud Run の `roles/run.invoker` |

各権限は IAM ポリシーの取得結果で確認したと利用者から報告を受けた。
Cloud Run の実行アカウント・イメージ・環境変数を確認し、配置後の Service URL が `.env` の `RECORDER_URL` と一致した。
IAM 認証を無効化する注釈はなく、呼び出しポリシーに `allUsers`・`allAuthenticatedUsers` がないことと、認証なしの `POST /schedule` が HTTP 403 になることを確認した。
Firestore のデータに対する第三者アクセスの拒否は、今回の会話では別途検証していない。

## 動作確認の結果

ローカルの Docker ビルドと、コンテナ内の自動テスト11件は成功した。
Google Cloud 上のビルドも成功し、生成イメージを配置した。クラウドビルドは5分以上かかったが、所要時間の内訳と原因は確認していない。

2026-11-09 の日没後、本人の認証による `/schedule` の呼び出しは HTTP 200 と `reservation_expired` を返した。
Scheduler の手動実行でも、同日22:02（日本時間）の Cloud Run ログに次を確認した。

```text
jsonPayload.fields.event: recorder_completed
jsonPayload.fields.operation: schedule
jsonPayload.fields.outcome: reservation_expired
```

これは Scheduler からの認証付き呼び出しと、日没後に予約を作らない動作の確認である。

2026-11-10 に、利用者が Firestore の日次記録を確認した。
地点情報、対象日、気象データと単位、モデル情報、評価式のバージョン、スコア、`observation: null` は想定どおりとの報告を受けた。
`forecast.fetchedAt` は `sunsetAt` の約2秒後だった。
この結果をもって、当日の日没に合わせた自動取得・保存の正常系を確認した。
朝6:00の実行ログや、日没前のキュー内予約の詳細は、会話では個別に共有されていない。

## 確認範囲と省略事項

上書き防止は実装済み。同じ地点・対象日の記録が存在すれば処理済みとして終了し、保存には新規作成 API のみを使う。
保存成功後に応答だけ失われた場合も、再実行で取得・上書きしないことを自動テストで確認した。
利用者との合意により、クラウド上での再実行による上書き防止の追加確認は省略する。

取得失敗時に不完全な記録を作らず、後の試行で保存できることも自動テストで確認済み。
クラウドで障害を起こした再試行・欠測の確認、停止・削除の実操作、実際の費用・利用量の確認は未実施。
今回の約2秒の取得遅延は1日分の結果であり、毎日の遅延や成功を保証するものではない。

主観評価は未入力であり、PCからの評価入力と分析用出力は #55 で扱う。
