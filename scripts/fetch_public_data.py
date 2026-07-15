"""Phase B: 国土交通省 不動産情報ライブラリ API から公的データを取得して region_stats に反映。

対象:
  - XIT001 不動産取引価格情報 (東京都13 + 神奈川県14, 直近4四半期)
    → 区ごとの 中古マンション等 取引件数 + ㎡単価中央値
  - XKT026 洪水浸水想定区域(想定最大規模, z=14 区役所周辺タイル)
    → 区中心部の最大浸水深ランク (A31a_205: 1=~0.5m ... 6=20m~)
  - XKT029 土砂災害警戒区域 (z=12 タイル, A33_006 の市区名で区別集計)
    → 区ごとの警戒区域数 + 特別警戒区域数 (A33_002=2)
  → region_public_data にキャッシュ + region_stats の各列を更新
  → hazard_level (低/中/高) は表示用の目安 (スコア対象外)

Run: python scripts/fetch_public_data.py
"""
import sys
import os
import re
import json
import math
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

# 各区の代表座標(区役所付近)。ハザードタイルのサンプリング中心。
WARD_COORDS = {
    # 東京23区
    "千代田区": (35.694, 139.754), "中央区": (35.671, 139.772), "港区": (35.658, 139.752),
    "新宿区": (35.694, 139.703), "文京区": (35.708, 139.752), "台東区": (35.713, 139.780),
    "墨田区": (35.711, 139.802), "江東区": (35.673, 139.817), "品川区": (35.609, 139.730),
    "目黒区": (35.641, 139.698), "大田区": (35.561, 139.716), "世田谷区": (35.646, 139.653),
    "渋谷区": (35.664, 139.698), "中野区": (35.707, 139.664), "杉並区": (35.699, 139.636),
    "豊島区": (35.726, 139.716), "北区": (35.753, 139.734), "荒川区": (35.736, 139.783),
    "板橋区": (35.751, 139.709), "練馬区": (35.735, 139.652), "足立区": (35.775, 139.804),
    "葛飾区": (35.743, 139.847), "江戸川区": (35.707, 139.868),
    # 横浜市
    "鶴見区": (35.508, 139.685), "神奈川区": (35.477, 139.629), "西区": (35.457, 139.622),
    "中区": (35.444, 139.642), "南区": (35.428, 139.608), "保土ケ谷区": (35.463, 139.592),
    "磯子区": (35.402, 139.618), "金沢区": (35.337, 139.624), "港北区": (35.518, 139.632),
    "戸塚区": (35.395, 139.529), "港南区": (35.399, 139.591), "旭区": (35.473, 139.546),
    "緑区": (35.512, 139.538), "瀬谷区": (35.463, 139.492), "栄区": (35.365, 139.554),
    "泉区": (35.417, 139.489), "青葉区": (35.552, 139.537), "都筑区": (35.545, 139.571),
    # 川崎市
    "川崎区": (35.531, 139.703), "幸区": (35.544, 139.697), "中原区": (35.577, 139.657),
    "高津区": (35.602, 139.611), "多摩区": (35.614, 139.562), "宮前区": (35.586, 139.579),
    "麻生区": (35.602, 139.507),
}
FLOOD_LABELS = {0: "想定なし", 1: "~0.5m", 2: "0.5~3m", 3: "3~5m", 4: "5~10m", 5: "10~20m", 6: "20m~"}
SLEEP_TILE = 0.6


def _api_get(path, params):
    r = requests.get(f"{BASE}/{path}", params=params, headers=HEADERS, timeout=60)
    r.raise_for_status()
    return r.json()


def _api_get_retry(path, params, attempts=3):
    """限流/瞬断に強い版。404 は「データなし」として None を返す。"""
    for i in range(attempts):
        try:
            return _api_get(path, params)
        except requests.HTTPError as e:
            code = e.response.status_code if e.response is not None else 0
            if code == 404:
                return None  # タイルにデータなし
            if i == attempts - 1:
                raise
            time.sleep(2 * (i + 1))  # 429/5xx: バックオフして再試行
        except requests.RequestException:
            if i == attempts - 1:
                raise
            time.sleep(2 * (i + 1))


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


def _tile_xy(lat, lon, z):
    n = 2 ** z
    x = int((lon + 180) / 360 * n)
    lat_r = math.radians(lat)
    y = int((1 - math.log(math.tan(lat_r) + 1 / math.cos(lat_r)) / math.pi) / 2 * n)
    return x, y


def fetch_hazards():
    """洪水(区中心 z14 タイルの最大浸水深ランク) + 土砂(z12, 市区名で集計)。

    戻り値: (flood, sed, known_wards)
      取得に失敗したタイルの区は known_wards に含めない = DB を更新しない
      (失敗を「低リスク」と偽装しないため)。404/空タイルは正当な「データなし」。
    """
    # --- 土砂災害 XKT029: 区中心のユニーク z12 タイルを取得し, A33_006 で区別集計 ---
    name_to_ward = {}
    for w in WARD_COORDS:
        for cand in (w, "横浜市" + w, "川崎市" + w):
            name_to_ward[cand] = w
    tiles12 = {}
    for w, (lat, lon) in WARD_COORDS.items():
        tiles12.setdefault(_tile_xy(lat, lon, 12), []).append(w)
    sed = {}           # ward -> [警戒区域数, 特別警戒区域数]
    sed_ok = set()     # 中心タイル取得成功の区
    seen_zones = set()
    for (x, y), center_wards in tiles12.items():
        try:
            d = _api_get_retry("XKT029", {"response_format": "geojson", "z": 12, "x": x, "y": y})
        except Exception as e:
            print(f"  XKT029 tile({x},{y}) failed after retries: {e}")
            time.sleep(SLEEP_TILE)
            continue
        sed_ok.update(center_wards)
        for f in (d.get("features") if d else None) or []:
            p = f.get("properties", {})
            zid = p.get("A33_004") or p.get("_id")
            if zid in seen_zones:
                continue
            seen_zones.add(zid)
            ward = name_to_ward.get((p.get("A33_006") or "").strip())
            if not ward:
                continue
            t = sed.setdefault(ward, [0, 0])
            t[0] += 1
            if str(p.get("A33_002")) == "2":
                t[1] += 1
        time.sleep(SLEEP_TILE)

    # --- 洪水 XKT026: 区中心 z14 タイルの最大浸水深ランク ---
    tiles14 = {}
    for w, (lat, lon) in WARD_COORDS.items():
        tiles14.setdefault(_tile_xy(lat, lon, 14), []).append(w)
    flood = {}         # ward -> max rank (取得成功の区のみ)
    for (x, y), wards in tiles14.items():
        try:
            d = _api_get_retry("XKT026", {"response_format": "geojson", "z": 14, "x": x, "y": y})
        except Exception as e:
            print(f"  XKT026 tile({x},{y}) failed after retries: {e}")
            time.sleep(SLEEP_TILE)
            continue
        rank = 0
        for f in (d.get("features") if d else None) or []:
            try:
                rank = max(rank, int(f.get("properties", {}).get("A31a_205") or 0))
            except (TypeError, ValueError):
                pass
        for w in wards:
            flood[w] = max(flood.get(w, 0), rank)
        time.sleep(SLEEP_TILE)

    known = sed_ok & set(flood.keys())
    return flood, sed, known


def _hazard_level(flood_rank, sed_total, sed_special):
    """表示用の目安 (スコア対象外)。

    注: 洪水は「想定最大規模(≒千年に一度)シナリオで区役所周辺タイル内の最大浸水深」
    のため関東低地はほぼ 3m+ になる。相対的な区別がつくよう閾値は高めに設定。
    """
    if flood_rank >= 5 or sed_special >= 20:
        return "高"
    if flood_rank >= 3 or sed_total >= 100:
        return "中"
    return "低"


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
    for col, typ in [("trade_price_per_m2", "INTEGER"), ("trade_count", "INTEGER"),
                     ("flood_rank", "INTEGER"), ("sediment_count", "INTEGER"),
                     ("hazard_level", "TEXT")]:
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
    print(f"region_stats updated: {updated} wards matched, {total} with ㎡単価")

    # --- ハザード (洪水 + 土砂) ---
    print("Fetching hazard tiles (XKT026 洪水 z14 / XKT029 土砂 z12)...")
    flood, sed, known = fetch_hazards()
    if len(known) < len(WARD_COORDS):
        print(f"  WARNING: {len(WARD_COORDS) - len(known)} wards のタイル取得に失敗 → その区は更新しない")
    conn.execute("DELETE FROM region_public_data WHERE data_type='hazard'")
    hz_updated = 0
    levels = []
    for w in sorted(known):
        fr = flood.get(w, 0)
        st, sp = sed.get(w, [0, 0])
        level = _hazard_level(fr, st, sp)
        levels.append(level)
        conn.execute(
            "INSERT INTO region_public_data (ward, data_type, payload, source) VALUES (?,?,?,?)",
            (w, "hazard",
             json.dumps({"flood_rank": fr, "flood_label": FLOOD_LABELS.get(fr, "?"),
                         "sediment_total": st, "sediment_special": sp,
                         "hazard_level": level}, ensure_ascii=False),
             "reinfolib XKT026/XKT029"))
        cur = conn.execute(
            "UPDATE region_stats SET flood_rank=?, sediment_count=?, hazard_level=?, updated_at=CURRENT_TIMESTAMP WHERE ward=?",
            (fr, st, level, w))
        hz_updated += cur.rowcount
    conn.commit()
    conn.close()
    from collections import Counter
    print(f"hazard updated: {hz_updated}/{len(WARD_COORDS)} wards, levels: {dict(Counter(levels))}")


if __name__ == "__main__":
    main()
