"""Seed region_stats table with real average rent data from SUUMO 家賃相場 pages.

Data source: https://suumo.jp/chintai/soba/{prefecture}/sc_{ward_romaji}/
抓取各区的1LDK平均租金(最适合1-2人居住的间取り)。
Safety/convenience/environment 保持手动分级(基于公开统计的简化)。
Run: python scripts/seed_regions.py
"""
import sqlite3
import sys
import os
import re
from bs4 import BeautifulSoup

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import DB_PATH

TOKYO_WARDS = [
    ("千代田区", "chiyoda", "高", "高", "中"), ("中央区", "chuo", "高", "高", "中"),
    ("港区", "minato", "高", "高", "中"), ("新宿区", "shinjuku", "中", "高", "中"),
    ("文京区", "bunkyo", "高", "高", "高"), ("台東区", "taito", "中", "高", "中"),
    ("墨田区", "sumida", "中", "高", "中"), ("江東区", "koto", "中", "高", "中"),
    ("品川区", "shinagawa", "高", "高", "中"), ("目黒区", "meguro", "高", "高", "高"),
    ("大田区", "ota", "高", "高", "高"), ("世田谷区", "setagaya", "高", "中", "高"),
    ("渋谷区", "shibuya", "中", "高", "中"), ("中野区", "nakano", "中", "高", "中"),
    ("杉並区", "suginami", "高", "中", "高"), ("豊島区", "toshima", "中", "高", "中"),
    ("北区", "kita", "中", "高", "中"), ("荒川区", "arakawa", "中", "中", "中"),
    ("板橋区", "itabashi", "高", "中", "高"), ("練馬区", "nerima", "高", "中", "高"),
    ("足立区", "adachi", "中", "中", "中"), ("葛飾区", "katsushika", "中", "中", "中"),
    ("江戸川区", "edogawa", "中", "中", "高"),
]

YOKOHAMA_WARDS = [
    ("鶴見区", "yokohamashitsurumi", "中", "高", "中"),
    ("神奈川区", "yokohamashikanagawa", "中", "高", "中"),
    ("西区", "yokohamashinishi", "高", "高", "中"),
    ("中区", "yokohamashinaka", "中", "高", "中"),
    ("南区", "yokohamashiminami", "中", "高", "中"),
    ("保土ケ谷区", "yokohamashihodogaya", "中", "中", "高"),
    ("磯子区", "yokohamashiisogo", "中", "中", "高"),
    ("金沢区", "yokohamashikanazawa", "高", "中", "高"),
    ("港北区", "yokohamashikohoku", "高", "高", "高"),
    ("戸塚区", "yokohamashitotsuka", "中", "中", "高"),
    ("港南区", "yokohamashikonan", "中", "中", "高"),
    ("旭区", "yokohamashiasahi", "高", "中", "高"),
    ("緑区", "yokohamashimidori", "高", "中", "高"),
    ("瀬谷区", "yokohamashiseya", "高", "中", "高"),
    ("栄区", "yokohamashisakae", "中", "中", "高"),
    ("泉区", "yokohamashiizumi", "高", "中", "高"),
    ("青葉区", "yokohamashiaoba", "高", "中", "高"),
    ("都筑区", "yokohamashitsuzuki", "高", "中", "高"),
]

KAWASAKI_WARDS = [
    ("川崎区", "kawasakishikawasaki", "中", "高", "中"),
    ("幸区", "kawasakishisaiwai", "中", "高", "中"),
    ("中原区", "kawasakishinakahara", "高", "高", "中"),
    ("高津区", "kawasakishitakatsu", "高", "高", "高"),
    ("多摩区", "kawasakishitama", "高", "中", "高"),
    ("宮前区", "kawasakishimiyamae", "高", "中", "高"),
    ("麻生区", "kawasakishiasao", "高", "中", "高"),
]


def parse_rent_benchmarks(html):
    """Keep each layout separate, including the source's management-fee basis."""
    soup = BeautifulSoup(html, "html.parser")
    text = soup.get_text(" ", strip=True)
    fee_basis = None
    if re.search(r"(?:管理費|共益費).{0,30}(?:含ま(?:ない|ず)|除く|除外)", text):
        fee_basis = 0
    elif re.search(r"(?:管理費|共益費).{0,30}(?:含む|込み)", text):
        fee_basis = 1
    rents = {}
    for tr in soup.select("table tr"):
        cells = tr.select("td")
        if len(cells) < 2:
            continue
        layout = re.sub(r"\s+", "", cells[0].get_text()).upper()
        if layout == "ワンルーム":
            layout = "1R"
        if not re.fullmatch(r"[1-9](?:R|K|DK|LDK|SDK|SLDK)", layout):
            continue
        from core.cleaning import parse_money
        rent = parse_money(cells[1].get_text(strip=True))
        if rent and rent > 0:
            rents[layout] = rent
    return rents, fee_basis


def _regional_rows():
    for pref, city, url_pref, wards in (
        ("東京都", None, "tokyo", TOKYO_WARDS),
        ("神奈川県", "横浜市", "kanagawa", YOKOHAMA_WARDS),
        ("神奈川県", "川崎市", "kanagawa", KAWASAKI_WARDS),
    ):
        for ward, slug, safety, conv, env in wards:
            yield pref, city, ward, safety, conv, env, f"https://suumo.jp/chintai/soba/{url_pref}/sc_{slug}/"


def seed_region_catalog():
    """Fast offline startup: add missing regions without inventing market values."""
    seed_missing_regions()
    with sqlite3.connect(DB_PATH) as conn:
        for pref, city, ward, safety, conv, env, _ in _regional_rows():
            if not conn.execute("SELECT 1 FROM region_stats WHERE prefecture=? AND city IS ? AND ward=?",
                                (pref, city, ward)).fetchone():
                _insert(conn, pref, city, ward, None, safety, conv, env)


def seed_regions():
    """Explicit CLI refresh. Failed fetches preserve previous rents and public data."""
    from scripts.init_db import init_db
    from scrapers.base import fetch_html
    from datetime import datetime
    init_db(DB_PATH)
    seed_region_catalog()
    for pref, city, ward, safety, conv, env, url in _regional_rows():
        html = fetch_html(url)
        if not html:
            print(f"{ward}: unavailable; keeping previous data")
            continue
        rents, fee_basis = parse_rent_benchmarks(html)
        if not rents:
            continue
        now = datetime.now().isoformat()
        with sqlite3.connect(DB_PATH) as conn:
            rid = conn.execute("SELECT id FROM region_stats WHERE prefecture=? AND city IS ? AND ward=?",
                               (pref, city, ward)).fetchone()[0]
            for layout, rent in rents.items():
                conn.execute("""INSERT INTO region_rent_benchmarks
                    (region_id, layout, rent, includes_management_fee, source_url, fetched_at)
                    VALUES (?,?,?,?,?,?) ON CONFLICT(region_id,layout) DO UPDATE SET
                    rent=excluded.rent, includes_management_fee=excluded.includes_management_fee,
                    source_url=excluded.source_url, fetched_at=excluded.fetched_at""",
                    (rid, layout, rent, fee_basis, url, now))
            if "1LDK" in rents:
                conn.execute("UPDATE region_stats SET avg_rent=?, rent_layout='1LDK', "
                             "rent_source=?, rent_fetched_at=? WHERE id=?", (rents["1LDK"], url, now, rid))
        print(f"{ward}: {len(rents)} layouts updated")


def _insert(conn, pref, city, ward, rent, safety, conv, env):
    conn.execute("""INSERT INTO region_stats
        (prefecture, city, ward, avg_rent, avg_area, avg_building_age,
         safety_level, convenience_level, environment_level, rent_source, stats_method)
        VALUES (?,?,?,?,NULL,NULL,?,?,?,?,?)""",
        (pref, city, ward, rent, safety, conv, env, "manual_estimate" if rent else "unverified", "manual_levels"))


def _major_rows():
    """主要都市は相場を直書きしているので、取得なしで投入できる。"""
    return [
        ("大阪府", None, "大阪市", 95000, "中", "高", "中"),
        ("京都府", None, "京都市", 92000, "高", "高", "高"),
        ("兵庫県", None, "神戸市", 98000, "高", "高", "高"),
        ("愛知県", None, "名古屋市", 85000, "中", "高", "中"),
        ("北海道", None, "札幌市", 72000, "高", "高", "高"),
        ("福岡県", None, "福岡市", 82000, "中", "高", "中"),
        ("宮城県", None, "仙台市", 75000, "高", "高", "高"),
        ("広島県", None, "広島市", 78000, "中", "高", "高"),
    ]


def seed_missing_regions():
    """一覧に増えたエリアのうち、まだ無いものだけを足す。

    既存の相場・公的データには触れず、手動概算の主要都市を補充する。
    区単位の空行は seed_region_catalog() が通信なしで追加する。
    """
    conn = sqlite3.connect(DB_PATH)
    # 同じ都市が (city=大阪市, ward=NULL) と (city=NULL, ward=大阪市) の
    # 両方の形で保存されている環境があるため、表示名で照合する。
    # タプル完全一致で見ると既存行を見落として重複を作ってしまう。
    have = {(r[0], r[1] or r[2]) for r in
            conn.execute("SELECT prefecture, ward, city FROM region_stats")}
    added = []
    for pref, city, ward, rent, safety, conv, env in _major_rows():
        label = ward or city
        if (pref, label) not in have:
            _insert(conn, pref, city, ward, rent, safety, conv, env)
            have.add((pref, label))
            added.append(label)
    conn.commit()
    conn.close()
    if added:
        print(f"Added {len(added)} missing regions: {', '.join(added)}")
    return added


def dedupe_regions():
    """同じ都道府県・表示名の行が複数あれば1件に寄せる。

    表示名で照合していなかった頃の補充で、大阪市・京都市のように
    行の形が違うだけの重複が生まれた環境がある。
    公的データを持つ行を優先し、無ければ古い方(id小)を残す。
    """
    conn = sqlite3.connect(DB_PATH)
    rows = conn.execute(
        "SELECT id, prefecture, COALESCE(ward, city) AS label, trade_price_per_m2, hazard_level "
        "FROM region_stats ORDER BY id").fetchall()
    seen, drop = {}, []
    for rid, pref, label, trade, hazard in rows:
        key = (pref, label)
        score = (trade is not None) + (hazard is not None)
        if key not in seen:
            seen[key] = (rid, score)
            continue
        keep_id, keep_score = seen[key]
        if score > keep_score:          # 新しい方が情報を持つなら入れ替える
            drop.append(keep_id)
            seen[key] = (rid, score)
        else:
            drop.append(rid)
    for rid in drop:
        conn.execute("DELETE FROM region_stats WHERE id=?", (rid,))
    conn.commit()
    conn.close()
    if drop:
        print(f"Removed {len(drop)} duplicate region rows")
    return drop


if __name__ == "__main__":
    seed_regions()