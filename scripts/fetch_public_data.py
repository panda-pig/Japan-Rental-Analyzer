"""Phase B: 国土交通省 不動産情報ライブラリ API から公的データを取得して region_stats に反映。

現在の対象:
  - XIT001 不動産取引価格情報 (東京都13 + 神奈川県14, 直近4四半期)
    → 区ごとの 中古マンション等 取引件数 + ㎡単価中央値 を集計
    → region_public_data にキャッシュ + region_stats.trade_price_per_m2 / trade_count を更新

次段階 (要タイル座標計算, エンドポイントIDは公式マニュアル確認済み):
  - XKT026 洪水浸水想定区域 / XKT029 土砂災害警戒区域 / XKT010 医療機関 など

Run: python scripts/fetch_public_data.py
"""
import sys
import os
import re
import json
import time
from datetime import date
from statistics import median

import requests

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import DB_PATH, REINFOLIB_API_KEY, REINFOLIB_ENABLED

import sqlite3

BASE = "https://www.reinfolib.mlit.go.jp/ex-api/external"
HEADERS = {"Ocp-Apim-Subscription-Key": REINFOLIB_API_KEY}
PREFS = [("13", "東京都"), ("14", "神奈川県")]
QUARTERS_WANTED = 4          # 直近4四半期分を集計
MIN_TRADES_FOR_PRICE = 5     # 件数がこれ未満の区は㎡単価を採用しない(ノイズ回避)
SLEEP = 1.0                  # リクエスト間隔(礼仪)

# 政令市: Municipality が「横浜市鶴見区」形式で返るため市名を剥がして ward に合わせる
CITY_PREFIXES = ("横浜市", "川崎市", "相模原市")


def _api_get(path, params):
    r = requests.get(f"{BASE}/{path}", params=params, headers=HEADERS, timeout=60)
    r.raise_for_status()
    return r.json()


def _parse_num(s):
    if not s:
        return None
    m = re.search(r"[\d,]+", str(s).replace(",", ""))
    return float(m.group()) if m else None


def _recent_quarters(n=QUARTERS_WANTED, max_probe=10):
    """今日から遡って (year, quarter) を列挙(データ公開ラグがあるため多めに候补)。"""
    today = date.today()
    y, q = today.year, (today.month - 1) // 3 + 1
    out = []
    for _ in range(max_probe):
        q -= 1
        if q == 0:
            y, q = y - 1, 4
        out.append((y, q))
    return out


def fetch_transactions():
    """区ごとの {ward: [price_per_m2, ...]} を直近4四半期分収集。"""
    per_ward = {}
    quarters_used = []
    for (y, q) in _recent_quarters():
        if len(quarters_used) >= QUARTERS_WANTED:
            break
        got_any = False
        for area, pref_name in PREFS:
            try:
                d = _api_get("XIT001", {"year": y, "quarter": q, "area": area})
            except Exception as e:
                print(f"  XIT001 {pref_name} {y}Q{q} failed: {e}")
                continue
            rows = d.get("data") or []
            if rows:
                got_any = True
            for r in rows:
                if r.get("Type") != "中古マンション等":
                    continue
                price = _parse_num(r.get("TradePrice"))
                area_m2 = _parse_num(r.get("Area"))
                if not price or not area_m2 or area_m2 < 10:
                    continue
                muni = (r.get("Municipality") or "").strip()
                ward = muni
                for cp in CITY_PREFIXES:
                    if ward.startswith(cp) and len(ward) > len(cp):
                        ward = ward[len(cp):]
                        break
                if not ward:
                    continue
                per_ward.setdefault(ward, []).append(price / area_m2)
            time.sleep(SLEEP)
        if got_any:
            quarters_used.append(f"{y}Q{q}")
        else:
            print(f"  {y}Q{q}: データ未公開, さらに遡る")
    return per_ward, quarters_used


def main():
    if not REINFOLIB_ENABLED:
        print("REINFOLIB_API_KEY が未設定のためスキップ (public data は種データのまま)")
        return

    from scripts.init_db import init_db
    init_db()  # region_public_data 表を確実に作成

    print("Fetching XIT001 transaction prices (東京都/神奈川県)...")
    per_ward, quarters = fetch_transactions()
    print(f"quarters: {quarters} | wards with trades: {len(per_ward)}")

    conn = sqlite3.connect(DB_PATH)
    # 迁移: region_stats に列がなければ追加
    for col, typ in [("trade_price_per_m2", "INTEGER"), ("trade_count", "INTEGER")]:
        try:
            conn.execute(f"ALTER TABLE region_stats ADD COLUMN {col} {typ}")
        except sqlite3.OperationalError:
            pass  # 既に存在

    conn.execute("DELETE FROM region_public_data WHERE data_type='transaction_price'")

    known_wards = {row[0] for row in conn.execute(
        "SELECT ward FROM region_stats WHERE ward IS NOT NULL")}
    updated = 0
    for ward, prices in sorted(per_ward.items()):
        count = len(prices)
        ppm = int(median(prices)) if count >= MIN_TRADES_FOR_PRICE else None
        conn.execute(
            "INSERT INTO region_public_data (ward, data_type, payload, source) VALUES (?,?,?,?)",
            (ward, "transaction_price",
             json.dumps({"quarters": quarters, "trade_count": count,
                         "median_price_per_m2": ppm}, ensure_ascii=False),
             "reinfolib XIT001"))
        if ward in known_wards:
            conn.execute(
                "UPDATE region_stats SET trade_price_per_m2=?, trade_count=?, updated_at=CURRENT_TIMESTAMP WHERE ward=?",
                (ppm, count, ward))
            updated += 1
    conn.commit()

    total = conn.execute(
        "SELECT COUNT(*) FROM region_stats WHERE trade_price_per_m2 IS NOT NULL").fetchone()[0]
    conn.close()
    print(f"region_stats updated: {updated} wards matched, {total} with ㎡単価")


if __name__ == "__main__":
    main()
