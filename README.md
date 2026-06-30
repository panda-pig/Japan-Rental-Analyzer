# Tokyo/Yokohama Rental Intelligence Dashboard

東京・横浜エリアの賃貸物件データを SUUMO / LIFULL HOME'S / athome から自動収集し、標準化・スコアリング・可視化を行うダッシュボード。

---

**🌐 言語切替 / 语言切换**

| 日本語 | [中文](#中文版) |

---

## 日本語版

### 概要

複数の賃貸プラットフォームにまたがる物件情報を一元管理し、予算・面積・階数・ペット可否・駅徒歩・築年数などの条件に基づいて物件を評価・比較できるツールです。物件詳細は各プラットフォームへ遷移する設計で、意思決定支援に特化しています。

### 機能

- **3プラットフォーム自動収集** — SUUMO / LIFULL HOME'S / athome の検索結果から物件摘要を取得
- **データ標準化** — 「12.8万円」「徒歩8分」「築12年」などの日本語表記を数値に変換
- **8次元スコアリング** — 予算 / 面積 / 通勤 / 階数 / ペット / 駅距離 / 築年数 / 初期費用 の加重評価（自動正規化、0〜100点）
- **通勤時間計算** — NAVITIME Transfer API で実乗換時間を算出（API未設定時は駅距離で自動降格）
- **初期費用見積** — 敷金 + 礼金 + 仲介手数料 + 前家賃 + 固定雑費（係数調整可能）
- **ダッシュボード可視化** — 10指標カード + 9種類のグラフ（ECharts）
- **物件管理** — お気に入り / 内見予定 / 申込状況の進捗管理、最大4件の比較機能
- **価格履歴** — 複数回取得時の価格変動を記録

### 技術スタック

| レイヤー | 技術 |
|---|---|
| バックエンド | Python 3.14 / Flask |
| データベース | SQLite（7テーブル） |
| スクレイピング | requests / BeautifulSoup4 |
| 評価ロジック | 自作 8次元加重正規化アルゴリズム |
| 通勤計算 | NAVITIME Transfer API（オプション） |
| フロントエンド | Jinja2 / Vanilla JS / ECharts 5 |
| テスト | pytest（58テスト） |

### データベース構成

| テーブル | 用途 |
|---|---|
| `rental_listings` | 物件マスタ（標準化済みデータ） |
| `listing_scores` | 評価結果（8次元スコア + 総合点 + 理由） |
| `listing_status` | お気に入り・進捗状態 |
| `listing_price_history` | 価格履歴 |
| `source_configs` | データソース設定（URL / プラットフォーム / 状態） |
| `import_logs` | 取得・インポートログ |
| `user_preferences` | ユーザー設定（条件 / ウェイト / 費用係数） |

### セットアップ

```bash
# 1. 仮想環境作成 + 依存インストール
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt -r requirements-dev.txt

# 2. NAVITIME API（任意、未設定時は通勤分を自動降格）
cp .env.example .env
# .env に NAVITIME_CLIENT_KEY=your_key を記入

# 3. データベース初期化
python scripts/init_db.py

# 4. データソース設定
# /import ページで検索URLを追加、または直接DBにINSERT

# 5. データ取得 + スコアリング
python scripts/run_scrape.py
python scripts/recalculate_scores.py

# 6. 起動
python app.py
# http://127.0.0.1:5000 を開く
```

### テスト

```bash
.venv/bin/pytest tests/ -v
```

### プロジェクト構成

```
├── app.py                  # Flask 入口 + API ルート
├── config.py               # 環境変数 + デフォルト係数
├── schema.sql              # DBスキーマ
├── db_helper.py            # DB接続ヘルパー
├── core/                   # 業務ロジック
│   ├── cleaning.py         # 金額/面積/徒歩/階/築年/ペット/設備の標準化
│   ├── address.py          # 住所正規表現解析
│   ├── scoring.py          # 8次元加重正規化スコアリング
│   ├── commute.py          # NAVITIME API + 降格処理
│   ├── initial_cost.py     # 初期費用見積
│   └── dedup.py            # 重複排除ハッシュ
├── scrapers/               # プラットフォーム別スクレイパー
│   ├── base.py             # robots確認 + HTTP取得
│   ├── suumo.py / homes.py / athome.py
│   └── models.py           # RawListing データクラス
├── scripts/                # 実行スクリプト
│   ├── init_db.py
│   ├── run_scrape.py
│   └── recalculate_scores.py
├── templates/              # 7ページ
├── static/css|js/          # スタイル + ページJS
└── tests/                  # pytest + HTML fixtures
```

### 利用規約・コンプライアンス

本プロジェクトは個人学習・意思決定支援目的です。

- 検索結果ページの**摘要情報のみ**取得（詳細ページ本文は取得しない）
- スクレイピング前に robots.txt を確認、Disallow の場合はスキップ
- 手動トリガー、低頻度アクセス（1リクエスト毎に2.5秒待機）
- 連絡先等の個人情報は保存しない
- 商用再配布しない
- 各プラットフォームの利用規約を遵守してください

### Render へのデプロイ

1. Render で New → Web Service → GitHub リポジトリを接続
2. ビルドコマンド: `pip install -r requirements.txt`
3. 起動コマンド: `gunicorn app:app --bind 0.0.0.0:$PORT --workers 1`（Procfile から自動読み取り）
4. Persistent Disk 追加: 1GB / Mount Path `db`
5. 環境変数 `DB_PATH` = `/opt/render/project/src/db/database.db` を設定
6. オプション: `NAVITIME_CLIENT_KEY` を設定（未設定時は通勤分を自動降格）
7. デプロイ実行 → 公開URL（`https://xxx.onrender.com`）でアクセス可能

---

## 中文版

### 概述

聚合多个租房平台的房源信息进行统一管理，根据预算、面积、楼层、宠物可否、车站徒步、築年数等条件评估和比较房源。房源详情跳转至原始平台，专注于辅助决策。

### 功能

- **三平台自动抓取** — 从 SUUMO / LIFULL HOME'S / athome 搜索结果页获取房源摘要
- **数据标准化** — 将「12.8万円」「徒歩8分」「築12年」等日文表述转换为数值
- **8维度评分** — 预算 / 面积 / 通勤 / 楼层 / 宠物 / 车站距离 / 築年数 / 初期费用 的加权评估（自动归一化，0~100分）
- **通勤时间计算** — 通过 NAVITIME Transfer API 计算实际换乘时间（未配置时自动降级为车站距离）
- **初期费用估算** — 敷金 + 礼金 + 仲介手续费 + 预付房租 + 固定杂费（系数可调）
- **Dashboard 可视化** — 10个指标卡片 + 9种图表（ECharts）
- **房源管理** — 收藏 / 内见计划 / 申请状态管理，最多4件横向对比
- **价格历史** — 多次抓取时记录价格变动

### 技术栈

| 层级 | 技术 |
|---|---|
| 后端 | Python 3.14 / Flask |
| 数据库 | SQLite（7张表） |
| 抓取 | requests / BeautifulSoup4 |
| 评分逻辑 | 自研 8维度加权归一化算法 |
| 通勤计算 | NAVITIME Transfer API（可选） |
| 前端 | Jinja2 / 原生 JS / ECharts 5 |
| 测试 | pytest（58个测试） |

### 数据库构成

| 表 | 用途 |
|---|---|
| `rental_listings` | 房源主表（标准化数据） |
| `listing_scores` | 评分结果（8维度分数 + 总分 + 理由） |
| `listing_status` | 收藏与进度状态 |
| `listing_price_history` | 价格历史 |
| `source_configs` | 数据源配置（URL / 平台 / 状态） |
| `import_logs` | 抓取与导入日志 |
| `user_preferences` | 用户设置（条件 / 权重 / 费用系数） |

### 安装步骤

```bash
# 1. 创建虚拟环境 + 安装依赖
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt -r requirements-dev.txt

# 2. NAVITIME API（可选，未配置时通勤分自动降级）
cp .env.example .env
# 在 .env 中填写 NAVITIME_CLIENT_KEY=your_key

# 3. 初始化数据库
python scripts/init_db.py

# 4. 配置数据源
# 在 /import 页面添加搜索URL，或直接INSERT到数据库

# 5. 抓取数据 + 评分
python scripts/run_scrape.py
python scripts/recalculate_scores.py

# 6. 启动
python app.py
# 打开 http://127.0.0.1:5000
```

### 测试

```bash
.venv/bin/pytest tests/ -v
```

### 项目结构

```
├── app.py                  # Flask 入口 + API 路由
├── config.py               # 环境变量 + 默认系数
├── schema.sql              # 数据库schema
├── db_helper.py            # 数据库连接封装
├── core/                   # 业务逻辑
│   ├── cleaning.py         # 金额/面积/徒步/楼层/築年/宠物/设备标准化
│   ├── address.py          # 地址正则解析
│   ├── scoring.py          # 8维度加权归一化评分
│   ├── commute.py          # NAVITIME API + 降级处理
│   ├── initial_cost.py     # 初期费用估算
│   └── dedup.py            # 去重hash生成
├── scrapers/               # 平台抓取器
│   ├── base.py             # robots检查 + HTTP请求
│   ├── suumo.py / homes.py / athome.py
│   └── models.py           # RawListing 数据类
├── scripts/                # 运行脚本
│   ├── init_db.py
│   ├── run_scrape.py
│   └── recalculate_scores.py
├── templates/              # 7个页面
├── static/css|js/          # 样式 + 页面JS
└── tests/                  # pytest + HTML fixtures
```

### 合规说明

本项目仅用于个人学习与决策辅助。

- 仅抓取搜索结果页的**摘要信息**（不抓取详情页正文）
- 抓取前检查 robots.txt，Disallow 时跳过
- 手动触发，低频访问（每次请求间隔2.5秒）
- 不保存联系方式等个人信息
- 不做商业再发布
- 请遵守各平台的使用条款

### 部署到 Render

1. 在 Render 上 New → Web Service → 连接 GitHub 仓库
2. 构建命令: `pip install -r requirements.txt`
3. 启动命令: `gunicorn app:app --bind 0.0.0.0:$PORT --workers 1`（Procfile 自动读取）
4. 添加 Persistent Disk: 1GB / Mount Path `db`
5. 环境变量 `DB_PATH` = `/opt/render/project/src/db/database.db`
6. 可选: `NAVITIME_CLIENT_KEY`（未设置时通勤分自动降级）
7. 部署后通过公开URL（`https://xxx.onrender.com`）访问

---

**🌐 言語切替 / 语言切换**

| [日本語](#日本語版) | 中文 |