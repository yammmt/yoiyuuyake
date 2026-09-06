# Google Cloud の基盤準備

## この文書の範囲

プロジェクト・API・課金・実行権限の設定手順をまとめる。機能範囲の正本は [MVP仕様](mvp-spec.md) とする。

> [!caution]
> 設定手順と公式資料の確認日は 2026-09-06 である。コンソールの項目名や提供機能は変更されることがある。

- 以下の名前は設定例であり、すべて設定済みであることを示すものではない。
- 費用見積もりは、この段階では行わない。

## プロジェクト

- 既存の Google Maps 用プロジェクトは開発用として残し、本番用プロジェクトを分離する。
  - 開発時の API キー・利用量・権限を本番から分け、本番の費用と API キーの使用状況を個別に確認するため。
- 本番用 Maps キー、課金・予算の対象、Cloud Run、DEM 用 Cloud Storage バケット、Artifact Registry、実行用サービスアカウントは、同じ本番用プロジェクトにそろえる。
- 以下の手順では、Google Cloud コンソール上部で本番用プロジェクトを選択する。ローカル確認に使う開発用 Maps キーのみ、既存の開発用プロジェクトで管理する。
- 選択した本番用プロジェクトの ID は、リポジトリ外の運用記録「本番 Google Cloud プロジェクト」に記録し、配置先の正本とする。記録がなければ作成し、保管場所を作業者間で共有する。この記録にはプロジェクト ID・用途・選択理由のみを記載し、API キーや認証情報は含めない。
- 手順中の `PROJECT_ID` は、この運用記録にある本番用プロジェクトの ID を指す。API 一覧の確認や後続のデプロイ・リソース作成コマンドでは、必ず記録値に置き換える。公開文書にはプレースホルダーを残す。

新規作成時に、標準で行われる `cloudapis.googleapis.com` の有効化を省略する場合は、CLI の `gcloud projects create PROJECT_ID --no-enable-cloud-apis` を使える。

参考: [公式リファレンス](https://docs.cloud.google.com/sdk/gcloud/reference/projects/create)

## API の確認と有効化

有効な API は、[「API とサービス」→「有効な API とサービス」](https://console.cloud.google.com/apis/dashboard)で確認する。
グラフの下に一覧がある。API 名を個別に開かずに確認する場合は、次の読み取り専用コマンドも使える。
画面最上部のプロジェクト選択ツールで、選択中のプロジェクト ID が運用記録の値と一致することを確認する。
acOS であれば <kbd>Cmd</kbd> + <kbd>O</kbd> のショートカットキーが使える。

```bash
gcloud services list --enabled --project=PROJECT_ID \
  --format="table(config.name,config.title)"
```

API の追加は「API とサービス」→「ライブラリ」で対象を検索し、「有効にする」を選ぶ。プロジェクト作成時から有効な API もあるため、現在の一覧を先に確認する。[一覧の確認手順](https://docs.cloud.google.com/service-usage/docs/list-services)、[標準で有効になる API](https://docs.cloud.google.com/service-usage/docs/enabled-service)

Cloud Run＋Cloud Storage での小規模検証を第一候補とし、次の用途で API を整理する。

| API | 識別名 | 用途・タイミング |
| --- | --- | --- |
| Maps JavaScript API | `maps-backend.googleapis.com` | 地図表示・クリックによる地点選択。本番用プロジェクトで基盤準備時に有効化し、キー作成は公開ドメイン確定後に行う |
| Places API (New) | `places.googleapis.com` | 地点の入力候補検索・選択地点の詳細取得。本番用プロジェクトで基盤準備時に有効化し、キー作成は公開ドメイン確定後に行う |
| Cloud Run Admin API | `run.googleapis.com` | Python API の実行環境 |
| Artifact Registry API | `artifactregistry.googleapis.com` | コンテナイメージの保管 |
| Cloud Storage API | `storage.googleapis.com` | DEM の保存・読み取り |
| Identity and Access Management (IAM) API | `iam.googleapis.com` | サービスアカウントの作成・管理 |
| Cloud Logging API | `logging.googleapis.com` | 起動失敗やアプリのエラーなどの調査 |
| Cloud Monitoring API | `monitoring.googleapis.com` | 応答時間・メモリなどの検証と監視 |
| Cloud Build API | `cloudbuild.googleapis.com` | Cloud Build でビルドする場合に準備 |
| Cloud Resource Manager API | `cloudresourcemanager.googleapis.com` | Cloud Build を使った配置など、手順で必要な場合に確認 |
| Compute Engine API | `compute.googleapis.com` | データの置き場所として VM と永続ディスクを比較検証する際に準備 |

Cloud Datastore API は今回の構成では使用しない。
Maps の地図・検索に必要なのは Maps JavaScript API と Places API (New) であり、Address Validation API などは今回の機能には含まれない。

API の有効化、認証情報の作成、バケットや実行サービスの作成はそれぞれ別の設定である。
ただし、製品の利用開始画面では複数の設定がまとめて行われる場合がある。
有効な API の一覧だけでは、API キーやリソースの有無は判断できない。

## Google Maps のキー

- ローカル確認には既存の開発用プロジェクトのキーを使う。設定は [フロントエンドの README](../site/README.md#google-maps-apiキー) を参照する。
- 本番用キーは、Firebase Hosting の公開ドメインを確認してから、分離した本番用プロジェクトで作成し、ウェブサイト制限と API 制限を設定する。
- API 制限は Maps JavaScript API と Places API (New) に限定する。
- ウェブサイト制限には実際に使う公開ドメインを登録する。例は `https://SITE_ID.web.app/*`。Firebase の共用ドメイン全体を許可するワイルドカードは使わない。
- キーの確認・削除は [「API とサービス」→「認証情報」](https://console.cloud.google.com/apis/credentials)で行う。

Maps の画面でキーが表示されたことだけでは、新規作成と既存キーの再表示を区別できない。
必要に応じて認証情報の一覧・作成日時を確認する。本番用の参照元設定と公開環境での動作確認は #40 に引き継ぐ。

参考: [Google Maps のセキュリティ指針](https://developers.google.com/maps/api-security-best-practices)

## 課金と予算

以下の「アラートのみ」の予算を作成する前に、操作する範囲に応じた権限を確認する。

- **単一プロジェクトの予算**: 本番用プロジェクト上の `resourcemanager.projects.get`、`billing.resourcebudgets.read`、`billing.resourcebudgets.write` が必要。これらは「オーナー」`roles/owner` または「編集者」`roles/editor` に含まれるため、同じ権限の追加付与は不要。必要な権限を含むカスタムロールでも対応でき、課金アカウント側のロールは必須ではない。費用レポートの閲覧には `billing.resourceCosts.get` も必要。
- **課金アカウント単位の予算**: 課金アカウント上の「請求先アカウント費用管理者」`roles/billing.costsManager` または「請求先アカウント管理者」`roles/billing.admin` など、予算作成に必要な権限を含むロールが必要。プロジェクトの Owner／Editor だけでは、この範囲の権限を満たさない。

参照: [予算作成に必要な権限](https://docs.cloud.google.com/billing/docs/how-to/budgets#permissions_required_to_manage_budgets)、[プロジェクトの予算権限とロール](https://docs.cloud.google.com/billing/docs/how-to/project-owners/setup-multi-project-access#project_permissions)

1. 「お支払い」で本番用プロジェクトに紐付く課金アカウントを確認する。未接続の場合は「課金アカウントをリンク」から利用するアカウントを選択して紐付ける。利用できる課金アカウントがなければ、先に作成する。紐付けには、予算作成とは別にプロジェクト側と課金アカウント側の権限が必要なため、[課金を有効にする手順と必要権限](https://docs.cloud.google.com/billing/docs/how-to/modify-project)を確認する。
2. 接続先の課金アカウントの「概要」で閉鎖・停止の表示がないことを確認し、「お支払いの概要」で未払い・支払い方法の問題も確認する。接続先が有効で正常な状態であることを確認してから、予算作成に進む。有効でなければ問題を解消するか、有効な課金アカウントに接続し直す。[課金状態の確認手順](https://docs.cloud.google.com/billing/docs/how-to/verify-billing-enabled)
3. 「予算とアラート」から予算を作成する。
4. プロジェクト全体の費用通知は「アラートのみ」を選び、範囲を本番用プロジェクト、サービスを「すべて選択」にする。
5. 予算額・通知しきい値・通知先を設定して保存する。
6. 「お支払い」→「レポート」で本番用プロジェクトに絞り、サービス別の費用を確認する。API の利用量は各サービスの指標・割り当て画面で確認する。

通常の予算アラートは **支出を自動停止しない** 。
別機能の「支出上限の適用」は、確認日時点ではプレビューで、単一プロジェクトの Cloud Run、Cloud Run functions、Gemini API、Vertex AI 系サービスが対象である。
4つの候補すべてを設定する必要はなく、Cloud Run に設定する場合は Cloud Run を選ぶ。

> [!caution]
> 支出上限の適用による停止には遅延があり、課金アカウント全体の請求上限を保証する機能ではない。

API キーの利用範囲はキーの API 制限で絞る。Maps の利用量は調整可能な割り当て上限も確認する。これらは予算通知とは別の設定である。

なお、設定確認に利用できる Cloud Shell 自体は無料だが、そこから利用するクラウドサービスの料金は別途発生する。

参考:

- [予算の作成](https://docs.cloud.google.com/billing/docs/how-to/budgets)
- [支出上限の制約](https://docs.cloud.google.com/billing/docs/how-to/budgets-spend-caps)
- [Maps の費用管理](https://developers.google.com/maps/billing-and-pricing/manage-costs)
- [Cloud Shell の料金](https://cloud.google.com/shell/pricing)

## 実行者とサービスアカウント

### 実行者の権限確認

[「IAM と管理」→「IAM」](https://console.cloud.google.com/iam-admin/iam)を開き、対象プロジェクトの「プリンシパル別に表示」で、自分のメールアドレスと同じ行の「ロール」列を見る。
「定義済み／カスタム」が表示される「ロール」の定義一覧とは異なる画面である。

自分に「オーナー」が付いている場合、基盤準備のために重複して権限を追加する必要はない。
ロールが異なる場合は、現在の割り当てと必要な操作を確認して追加権限を決める。
作業者の管理権限を、以下のアプリ実行用アカウントにそのまま付与しない。

### アプリ実行用アカウントの作成

1. 本番用プロジェクトを選択し、[「IAM と管理」→「サービス アカウント」](https://console.cloud.google.com/iam-admin/serviceaccounts)で「サービス アカウントを作成」を選ぶ。
2. 名前・ID を指定する。例: `yoiyuuyake-api`。説明は「夕焼け予報 API の実行用。DEM を読み取る。」とする。
3. 「このサービスアカウントにプロジェクトへのアクセスを許可」は空欄にする。DEM の権限はバケット作成後、そのバケットに付与する。
4. アカウントを Cloud Run に割り当てる作業者には、そのサービスアカウント上の「サービス アカウント ユーザー」`roles/iam.serviceAccountUser` が必要。既存権限で満たしていない場合、作成画面の「サービス アカウント ユーザーのロール」欄に作業者のメールアドレスを指定する。
5. 作成を完了し、発行されたサービスアカウントのメールアドレスを確認する。例: `yoiyuuyake-api@PROJECT_ID.iam.gserviceaccount.com`。

Cloud Run は割り当てられたサービスアカウントで認証するため、JSON キーは作成しない。Cloud Build を使う場合のビルド用アカウント・権限は、ビルド方法を具体化した段階で別途整理する。

参照:

- [IAM の割り当て確認](https://docs.cloud.google.com/iam/docs/granting-changing-revoking-access#view-current-access)
- [サービスアカウント作成](https://docs.cloud.google.com/iam/docs/service-accounts-create)
- [Cloud Run のサービス ID](https://docs.cloud.google.com/run/docs/securing/service-identity)

## リージョンと後続作業

検証先として東京 `asia-northeast1` を用いる。
プロジェクト全体に共通するリージョン設定を行う段階ではなく、本番用プロジェクト内に Cloud Run・DEM 用バケット・Artifact Registry を作成するときに、それぞれ指定する。

現段階では DEM 用バケットと Cloud Run サービスは未作成として扱う。リソース配置先選定時の検証リソース作成時に、次を行う。

1. 検証期間・構成・利用量の前提を定め、費用とリソースの削除手順を整理する。実測後に見積もりを更新する。
2. DEM 用バケットを作成し、そのバケットの「権限」→「アクセス権を付与」で、実行用サービスアカウントに「Storage オブジェクト閲覧者」`roles/storage.objectViewer` を付与する。これにより、対象バケット内の一覧取得・読み取りを許可する。
3. Cloud Run の実行用サービスアカウントに、作成したアカウントを指定する。バケットのマウントも読み取り専用にする。
4. DEM の読み取り性能・メモリ・費用を検証し、Cloud Run＋Cloud Storage と Compute Engine＋永続ディスクを比較して構成を決める。

権限付与はバケット単位で行い、アプリにプロジェクト全体の Storage 管理権限や DEM の書き込み・削除権限を与えない。
Cloud Storage API を有効にしただけでは、このバケット作成や権限付与は完了しない。

削除方法の整理では、API 無効化だけで全リソースと保存費用が消えるとは扱わない。
Cloud Storage のデータは残る一方、Cloud Run API の無効化では関連リソースが削除されるため、採用したリソースごとに削除と残存費用を確認する。

参照:
- [Cloud Run のリージョン](https://docs.cloud.google.com/run/docs/locations)
- [API 無効化の影響](https://docs.cloud.google.com/service-usage/docs/enable-disable#disable)
- [バケットへの権限付与](https://docs.cloud.google.com/storage/docs/access-control/using-iam-permissions)
- [Cloud Run の Cloud Storage マウント](https://docs.cloud.google.com/run/docs/configuring/services/cloud-storage-volume-mounts)

## Git に含める情報

この文書には手順と設定方針を残す。
API キーの値、サービスアカウントの JSON キー、アクセストークン、ローカルの認証設定、生成済み DEM は Git に含めない。
