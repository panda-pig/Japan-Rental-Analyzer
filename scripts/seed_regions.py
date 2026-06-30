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
import time
import requests
from bs4 import BeautifulSoup

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import DB_PATH, SCRAPE_USER_AGENT, SCRAPE_SLEEP_SECONDS

# (prefecture, city, ward, suumo_url_slug, safety, convenience, environment)
# slug = URL 中的 sc_xxx 部分
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
    ("高津区", "kawasakshitakatsu", "高", "高", "高"),
    ("多摩区", "kawasakishitama", "高", "中", "高"),
    ("宮前区", "kawasakishimiyamae", "高", "中", "高"),
    ("麻生区", "kawasakishiasao", "高", "中", "高"),
]


def fetch_avg_rent(prefecture, slug):
    """从 SUUMO 家賃相場页抓取1LDK平均租金。"""
    url = f"https://suumo.jp/chintai/soba/{prefecture}/sc_{slug}/"
    try:
        resp = requests.get(url, headers={"User-Agent": SCRAPE_USER_AGENT}, timeout=15)
        if resp.status_code != 200:
            return None, None
        soup = BeautifulSoup(resp.text, "html.parser")
        # 找家賃相場表
        rent_1ldk = None
        rent_1k = None
        for t in soup.select("table"):
            for tr in t.select("tr"):
                tds = tr.select("td")
                if len(tds) >= 2:
                    layout = tds[0].get_text(strip=True)
                    rent_text = tds[1].get_text(strip=True)
                    if layout == "1LDK" and "万円" in rent_text:
                        m = re.search(r"([\d.]+)万円", rent_text)
                        if m:
                            rent_1ldk = int(float(m.group(1)) * 10000)
                    if layout == "1K" and "万円" in rent_text:
                        m = re.search(r"([\d.]+)万円", rent_text)
                        if m:
                            rent_1k = int(float(m.group(1)) * 10000)
        time.sleep(SCRAPE_SLEEP_SECONDS)
        return rent_1ldk, rent_1k
    except Exception:
        return None, None


def seed_regions():
    conn = sqlite3.connect(DB_PATH)
    conn.execute("DELETE FROM region_stats")

    # 东京23区
    for ward, slug, safety, conv, env in TOKYO_WARDS:
        rent_1ldk, rent_1k = fetch_avg_rent("tokyo", slug)
        rent = rent_1ldk or rent_1k
        print(f"東京都 {ward}: 1LDK={rent_1ldk} 1K={rent_1k} -> {rent}")
        _insert(conn, "東京都", None, ward, rent, safety, conv, env)

    # 横浜各区
    for ward, slug, safety, conv, env in YOKOHAMA_WARDS:
        rent_1ldk, rent_1k = fetch_avg_rent("kanagawa", slug)
        rent = rent_1ldk or rent_1k
        print(f"横浜市 {ward}: 1LDK={rent_1ldk} 1K={rent_1k} -> {rent}")
        _insert(conn, "神奈川県", "横浜市", ward, rent, safety, conv, env)

    # 川崎各区
    for ward, slug, safety, conv, env in KAWASAKI_WARDS:
        rent_1ldk, rent_1k = fetch_avg_rent("kanagawa", slug)
        rent = rent_1ldk or rent_1k
        print(f"川崎市 {ward}: 1LDK={rent_1ldk} 1K={rent_1k} -> {rent}")
        _insert(conn, "神奈川県", "川崎市", ward, rent, safety, conv, env)

    # 全国主要城市(手动)
    major = [
        ("大阪府", None, "大阪市", 95000, "中", "高", "中"),
        ("京都府", None, "京都市", 92000, "高", "高", "高"),
        ("兵庫県", None, "神戸市", 98000, "高", "高", "高"),
        ("愛知県", None, "名古屋市", 85000, "中", "高", "中"),
        ("北海道", None, "札幌市", 72000, "高", "高", "高"),
        ("福岡県", None, "福岡市", 82000, "中", "高", "中"),
        ("宮城県", None, "仙台市", 75000, "高", "高", "高"),
        ("広島県", None, "広島市", 78000, "中", "高", "高"),
    ]
    for pref, city, ward, rent, safety, conv, env in major:
        _insert(conn, pref, city, ward, rent, safety, conv, env)

    conn.commit()
    count = conn.execute("SELECT COUNT(*) FROM region_stats").fetchone()[0]
    conn.close()
    print(f"\nSeeded {count} region stats")


def _insert(conn, pref, city, ward, rent, safety, conv, env):
    from datetime import datetime
    conn.execute("""INSERT INTO region_stats
        (prefecture, city, ward, avg_rent, avg_area, avg_building_age,
         safety_level, convenience_level, environment_level, updated_at)
        VALUES (?,?,?,?,?,?,?,?,?,?)""",
        (pref, city, ward, rent, 40.0, 25, safety, conv, env, datetime.now().isoformat()))


if __name__ == "__main__":
    seed_regions()