# Hosting の配置記録

Issue #40 の画面配置と、#41 の受入確認を記録する。
記載内容は開発者の操作結果とブラウザでの確認報告に基づく。
API と全国 DEM の配置は [#39 の記録](cloud-deployment.md) を参照する。

## 実施内容

- 既存の Google Cloud プロジェクトへ Firebase を追加した。
- デフォルトサイトの配信を停止し、同じプロジェクトに別の Hosting サイトを作成した。
- 公開用 Maps キーを開発用と分離し、参照元を `https://${HOSTING_SITE_ID}.web.app/*`、API を Maps JavaScript API と Places API (New) に制限した。
- ページタイトルと画面上の名前を「Yoiyuuyake」、見出しを「夕焼け予報」に変更した。
- 新サイトへ静的ファイルを配置し、Cloud Run API に接続した。

## 再配置

環境固有の値はリポジトリ直下の Git 管理外の `.env` に保存する。
`PROJECT_ID`、`SERVICE_URL`、`HOSTING_SITE_ID` と、`VITE_FORECAST_API_URL="${SERVICE_URL}"` を定義する。
API キーやトークンは `.env` に保存しない。

リポジトリ直下で、配置先を指定したローカル用の設定ファイルを生成する。
元の `firebase.json` にはサイト ID の指定がなく、デフォルトサイトに配信するため、以降の配信コマンドでは生成した設定ファイルを指定する。
Node.js 22.13 以降を使用する。

```sh
node --env-file=.env --input-type=module <<'JS'
import fs from "node:fs";
import path from "node:path";

const site = process.env.HOSTING_SITE_ID;
if (!site) throw new Error("HOSTING_SITE_ID が未設定です");
const config = JSON.parse(fs.readFileSync("firebase.json", "utf8"));
config.hosting.site = site;
config.hosting.public = path.resolve("site/dist");
fs.mkdirSync(".firebase", { recursive: true });
fs.writeFileSync(".firebase/hosting.local.json", JSON.stringify(config, null, 2) + "\n");
console.log(`配置先: ${site}`);
JS
```

Zsh で自身が管理する `.env` を読み込み、公開用 Maps キーを画面に表示せずに入力してビルドする。
キーは生成後の JavaScript に含まれ、ブラウザから確認できる。

```zsh
source ./.env
cd site
npm ci
read -r -s "VITE_GOOGLE_MAPS_API_KEY?Maps Hosting API key: "
echo
export VITE_GOOGLE_MAPS_API_KEY VITE_FORECAST_API_URL
npm run build
unset VITE_GOOGLE_MAPS_API_KEY
```

ビルドが成功したことを確認してから配信する。

```sh
cd ..
firebase deploy --only hosting \
  --config .firebase/hosting.local.json \
  --project "$PROJECT_ID"
```

## 確認結果

開発者が新サイトの HTTPS URL で次を確認した。

- Google マップの表示と、東京駅の検索による地点選択。
- 地図をクリックすると地点が変わり、予報が更新されること。
- API の接続先が `SERVICE_URL` と一致し、認証なしアクセスを許可する前は HTTP 403 が返ること。
- `allUsers` に `roles/run.invoker` を付与すると予報が表示されること。
- 東京湾の海上付近での DEM 不足の案内と、直前のスコアが残らないこと。
- 東京駅を再選択すると予報が正常に表示されること。

途中で `RefererNotAllowedMapError` が発生したため、ビルドに渡す Maps キーを修正して再配置した。
キーを変更した場合は再ビルドが必要になる。
表示文言はローカルプレビューでも確認し、静的ビルドの関連テスト 2 件が成功した。

## #41 の受入確認

2026-10-27 に、開発者からの報告に基づいて確認結果を整理した。
各操作の実施日時は記録していない。

- モバイル回線のスマートフォンから利用できた。PC の電源を切った状態での確認は明示されていない。
- ログ確認の報告では、予報可能地点の選択で HTTP 200 と予報結果、海上の選択で HTTP 503 と `ray_no_elevation`、外国の選択で HTTP 503 と `observer_out_of_coverage` を確認した。
- 開発者は確認した使用量を少ないと判断した。対象期間、具体的な使用量、請求額は記録しておらず、今後の費用を保証するものではない。

上記のログ確認は、予期しない例外が一切ないことや、すべての外国・海上地点で同じ応答になることを示すものではない。
直前のスコアの消去と正常地点への復帰は、前節の #40 の確認結果を参照する。

## #41 の範囲

開発者は、1 日に最大 1 回しか検証用データを取得できない #33 の情報収集を優先し、#41 を確認結果の記録と既存手順の整理に縮小する。
PC 停止条件の明示的な確認、気象取得失敗の意図的な再現、費用の詳細確認、切り戻し・削除の詳細手順、新規チェックアウトからの配置再現確認は、低優先度の後続 Issue #52 へ移管する。
これらを実施済みとは扱わず、追加のクラウド操作は行わない。

初回公開では、DEM 欠損時に評価結果を出さない仕様を維持する。
海側の欠損対応は #26、包括的な高速化は #29、Maps の App Check は #46 に残す。
予報保存・主観評価は #33 の後続機能であり、#41 では実装しない。

## 運用手順

- 画面の配置・更新：[再配置](#再配置)
- API の配置・更新：[Cloud Run の配置](cloud-deployment.md#cloud-run-の配置)
- ログ調査：[ログの確認](cloud-deployment.md#ログの確認)
- API の公開アクセス遮断と再開：[学習中の公開アクセス管理](cloud-deployment.md#学習中の公開アクセス管理)

### 配信停止

画面の配信を停止するには次のコマンドを実行する。
API の認証なしアクセスを遮断するには [#39 の手順](cloud-deployment.md#作業終了時) を使う。
どちらの操作でも保存データやリソースは削除されず、保存費用は残る。

```sh
firebase hosting:disable --site "$HOSTING_SITE_ID" --project "$PROJECT_ID"
```
