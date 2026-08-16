# ADR 001: MVPのデータ源

## 状態

採用

## 決定

MVPでは、以下の三つのデータ源を利用する。

| 用途 | 採用するデータ源 |
| --- | --- |
| 地点指定・地図 | Google Maps Platform（Maps JavaScript API、Places Autocomplete） |
| 今日の夕焼け気象予報 | Open-Meteo Forecast API |
| 地形による見晴らし | 国土地理院の数値標高モデル（DEM） |

## 理由

- Open-Meteoは、夕焼けスコアに必要な低層・中層・高層の雲量、視程、湿度、降水などを取得できる。
- Google Maps Platformは、日本国内の地名・施設名・住所の検索と地図上の地点指定を一つのUIで提供できる。
- 国土地理院DEMは、全国の山・丘・谷による日没方向の遮蔽を計算する基礎データになる。

## 採用しないもの

- PLATEAU: 建物遮蔽の精度向上には有効だが、地域ごとのデータ差があり、MVPの必須要件ではない。
- OpenStreetMap: 将来の候補地点探索や建物データの補助には有用だが、MVPで扱う地形判定には不要である。
- 経路検索API: MVPは指定地点予報のみであり、移動時間を扱わない。

## 結果

MVPは日本全国で動作する。ただし見晴らしは地形のみを考慮し、都市部の建物や樹木は未考慮であることをUIで明示する。

## 参照

- Open-Meteo Forecast API: <https://open-meteo.com/en/docs>
- Google Place Autocomplete: <https://developers.google.com/maps/documentation/javascript/place-autocomplete-overview>
- 国土地理院 基盤地図情報: <https://www.gsi.go.jp/kiban/>

