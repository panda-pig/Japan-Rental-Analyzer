# Tokyo/Yokohama Rental Intelligence Dashboard

东京/横滨租房数据分析 Dashboard。从 SUUMO / LIFULL HOME'S / athome 搜索结果页抓取房源摘要,自动清洗、评分、可视化,辅助租房决策。

## 特徴

- **三平台聚合**:SUUMO、LIFULL HOME'S、athome 搜索结果摘要自动抓取
- **自动清洗**:日文金额(万円/円)、面积(m²)、徒歩分、築年、楼层、设备关键词自动解析
- **智能评分**:8 维度加权评分(预算/面积/通勤/楼层/宠物/车站距离/築年/初期费用),权重可调,自动归一化
- **通勤分**:NAVITIME Transfer API 算真实换乘时间(未配置时自动降级为车站距离近似)
- **初期费用估算**:敷金 + 礼金 + 仲介手数料 + 前家賃 + 固定杂费,系数可调
- **可视化**:10 指标卡 + 9 图表(区域均价、家租分布、面积分布、面积vs费用散点、推荐分Top10、房型/平台/楼层/築年占比)
- **全流程管理**:收藏(気になる→内見→申込)、对比(≤4件)、价格历史追踪

## 技術スタック

| 层 | 技术 |
|---|---|
| 后端 | Python 3.14、Flask |
| 数据库 | SQLite(7 张表) |
| 抓取 | requests + BeautifulSoup4 |
| 评分 | 自研 8 维度加权归一化算法 |
| 通勤 | NAVITIME Transfer API(可选) |
| 前端 | Jinja2 templates + 原生 JS + ECharts 5 |
| 测试 | pytest(56+ 单测) |

## 数据库構成

| 表 | 用途 |
|---|---|
| `rental_listings` | 房源主表(清洗后标准化数据) |
| `listing_scores` | 评分结果(8 维度分 + 总分 + 理由) |
| `listing_status` | 收藏/进度状态(気になる/内見/申込等) |
| `listing_price_history` | 价格历史(多次抓取时记录变化) |
| `source_configs` | 抓取数据源配置(URL、平台、状态) |
| `import_logs` | 抓取/导入日志 |
| `user_preferences` | 用户偏好(找房条件 + 评分权重 + 费用系数) |

## セットアップ

```bash
# 1. 仮想環境作成 + 依存インストール
python3 -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -r requirements.txt -r requirements-dev.txt

# 2. NAVITIME API(任意、未設定時は通勤分自動降格)
cp .env.example .env
# .env に NAVITIME_CLIENT_KEY=your_key を記入

# 3. DB初期化
python scripts/init_db.py

# 4. データソース設定
# /import ページで検索URLを追加、または直接DBにINSERT

# 5. スクレイピング + 採点
python scripts/run_scrape.py
python scripts/recalculate_scores.py

# 6. 起動
python app.py
# http://127.0.0.1:5000 を開く
```

## テスト

```bash
.venv/bin/pytest tests/ -v
```

## 合規について

本プロジェクトは個人学習・意思決定支援目的です。

- 検索結果ページの**要約情報のみ**取得(詳細ページ本文は取得しない)
- スクレイピング前に robots.txt を確認、Disallow の場合はスキップ
- 手動トリガー、低頻度アクセス(1リクエスト毎に2.5秒待機)
- 連絡先等の個人情報は保存しない
- 商用再配布しない
- 詳細は各プラットフォームの利用規約を遵守ください

## プロジェクト構成

```txt
├── app.py                 # Flask 入口 + API 路由
├── config.py              # 環境変数 + デフォルト係数
├── schema.sql             # DBスキーマ
├── db_helper.py           # DB接続ヘルパー
├── core/                  # 業務ロジック(単体テスト可能)
│   ├── cleaning.py        # 金額/面積/徒歩/階/築年/ペット/設備
│   ├── address.py         # 住所正規表現解析
│   ├── scoring.py         # 8次元加重正規化採点
│   ├── commute.py         # NAVITIME API + 降格
│   ├── initial_cost.py    # 初期費用見積
│   └── dedup.py           # 重複排除ハッシュ
├── scrapers/              # プラットフォーム別スクレイパー
│   ├── base.py            # robots確認 + fetch
│   ├── suumo.py / homes.py / athome.py
│   └── models.py          # RawListing データクラス
├── scripts/               # 実行スクリプト
│   ├── init_db.py
│   ├── run_scrape.py
│   └── recalculate_scores.py
├── templates/             # 7ページ
├── static/css|js/         # スタイル + ページJS
└── tests/                 # pytest + fixtures
```