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

時刻は必ず `Asia/Tokyo` で取得し、JMA Seamlessモデルを優先指定します。APIがエラーを返す、または必要な時間別変数が欠ける場合は、予測値を作らず例外を返します。
