<div align="center">

# Japan Rental Analyzer

**物件URLを貼るだけ。相場・災害リスク・住民評価が1枚のレポートに。**

東京・横浜・川崎の賃貸意思決定ツール

[English](README.md) · **日本語** · [简体中文](README.zh-CN.md)

</div>

![ホーム](screenshots/hero.png)

<sub>スクリーンショットの物件はサンプルです。エリア相場・取引価格・災害リスクは実データです。</sub>

---

部屋探しでは、同じ物件を4つのサイトで開き直し、この家賃が妥当なのか、その
エリアは浸水するのか、その駅の周りは実際どうなのかを、結局は勘で判断すること
になります。このツールは、URLを1本貼るだけでその3つに答えます。

## できること

### 1. URLを貼るだけで、レポートが1枚

SUUMO / LIFULL HOME'S / athome / Yahoo!不動産 の物件詳細ページに対応。賃料・
管理費・敷金・礼金・面積・間取り・階数・築年数・駅徒歩・設備を自動で読み取り
ます。

![レポート](screenshots/report.png)

- **8次元スコア** — 予算・面積・通勤・階数・ペット・駅距離・築年数・初期費用を
  自分の重み付けで評価し、0〜100に正規化
- **エリア相場との偏差** — 相場より何円・何パーセント高いか安いか
- **初期費用の内訳** — 敷金・礼金・仲介手数料・前家賃・諸費用をドーナツで概算
- **条件クリア** — 8つの条件のうちどれを満たすか。未達も隠さずグレーで並べる
- **価格履歴** — 再取得すると価格の変動を折れ線で記録

### 2. 公的データと住民評価

物件と並べて表示しますが、**スコアには算入しません**。物件そのものではなく、
エリアの性質を示す情報だからです。

- **取引価格** — 国土交通省 不動産情報ライブラリによる中古マンションの㎡単価
  中央値と取引件数（関東48区・直近4四半期）
- **災害リスク** — 洪水浸水想定の最大浸水深と土砂災害警戒区域数から、低・中・高
  の目安を表示
- **駅の住民評価** — LIFULL HOME'S「まちむすび」の住民アンケート集計値
  （交通・治安・買い物・子育て・自然）を最寄駅ごとに

### 3. 貼るほど貯まる物件プール

![プール](screenshots/pool.png)

解析した物件はプールに残ります。行をクリックすれば上のレポートが切り替わり、
スコア・月額・面積・㎡単価・エリア偏差で並び替えられます。2〜4件にチェックを
入れれば横断比較へ。

![比較](screenshots/compare.png)

8次元レーダーを重ね合わせ、全項目を表で並べます。取得できなかった値は
0円ではなく「未取得」と表示します。

### 4. お気に入りと検討状況

![お気に入り](screenshots/favorites.png)

★を付けた物件を、気になる → 内見 → 申込 の流れでメモ付きで管理できます。

### 5. 物件がゼロでも使えるエリアデータ

![エリアデータ](screenshots/area.png)

相場×総合評価の散布図（左上ほど「安くて評価が高い」）、東京23区・横浜市の相場
ランキング、2エリアの比較レーダー、全56エリアの並び替え可能なテーブル。

## データソースと出典

| データ | 出典 | 取得方法 |
|---|---|---|
| 物件情報 | ユーザーが貼った詳細ページのみ | 単発取得・一括クロールなし |
| エリア平均賃料 | SUUMO 家賃相場 | 低頻度・手動シード |
| 不動産取引価格 | 国土交通省 不動産情報ライブラリ (XIT001) | 公式API（キー必要） |
| 災害リスク | 同上 (XKT026 洪水 / XKT029 土砂) | 公式APIタイル |
| 駅の住民評価 | LIFULL HOME'S まちむすび | 集計値のみ・口コミ本文は保存しない |

## 技術スタック

| レイヤー | 技術 |
|---|---|
| バックエンド | Python 3.14 / Flask |
| データベース | SQLite・11テーブル |
| スクレイピング | requests / BeautifulSoup4（robots.txt遵守・礼儀スリープ） |
| 公的データ | 不動産情報ライブラリAPI + XYZタイル座標計算 |
| 駅名照合 | pykakasi（漢字→ローマ字）+ 正規化 + 近似マッチ |
| 通勤計算 | NAVITIME Transfer API（任意） |
| フロントエンド | Jinja2 / Vanilla JS / ECharts 5 / wordcloud2.js |
| テスト | pytest・98テスト |

取得先はホスト名を解析した上で許可リストと照合し、プライベートアドレスは拒否、
リダイレクトも1ホップごとに再検査します。スクレイプした文字列はDOMに入れる前に
必ずエスケープします。破壊的操作と設定変更は `ADMIN_TOKEN` を設定した環境では
トークンを要求します。

UIは WCAG 2.1 AA を目標にしています。キーボードで操作できる表、全グラフの代替
テキスト、フォーム結果のライブリージョン、AA基準のコントラスト、44pxのタップ
領域、`prefers-reduced-motion` への対応。

## セットアップ

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt -r requirements-dev.txt

cp .env.example .env
#   REINFOLIB_API_KEY   : 不動産情報ライブラリ（任意）
#   NAVITIME_CLIENT_KEY : 通勤時間（無ければ通勤軸は自動で除外）
#   ADMIN_TOKEN         : 設定すると破壊的操作にトークンが必要になる

python scripts/init_db.py
python scripts/seed_regions.py
python scripts/fetch_public_data.py   # REINFOLIB_API_KEY がある場合のみ

python app.py    # http://127.0.0.1:5000
```

```bash
.venv/bin/pytest tests/ -q
```

## Render デプロイ

1. New → Web Service → このリポジトリを接続
2. Build `pip install -r requirements.txt`、
   Start `gunicorn app:app --bind 0.0.0.0:$PORT --workers 1`
3. Persistent Disk 1GB、マウントパス `db`
4. 環境変数 `DB_PATH=/opt/render/project/src/db/database.db`、
   `REINFOLIB_API_KEY`、`ADMIN_TOKEN`
5. デプロイ後にShellで一度:
   `python scripts/fetch_public_data.py && python scripts/fetch_station_reviews.py`

## コンプライアンス方針

- 解析するのはユーザーが明示的に貼った物件ページのみ。サイト横断クロールはしない
- 取得の前に robots.txt を確認し Disallow はスキップ。リクエスト間に礼儀スリープ
- CAPTCHA等のbot対策は迂回しない。bot対策のあるソースは採用しない
- 住民評価は集計数値のみ保存し、口コミ本文・個人情報は保存しない
- 公的データと住民評価は出典をUIに明示し、物件スコアには算入しない
- 個人の学習・意思決定支援が目的。データの商用再配布はしない
