"""Phase C: LIFULL HOME'S「まちむすび」駅ページから住民アンケートの集計スコアを取得。

取得するのは 5 カテゴリの数値スコアのみ (口コミ本文は保存しない):
  交通の利便性 / 治安の良さ / 買い物のしやすさ / 子育てのしやすさ / 自然の多さ

robots.txt は /machimusubi/ を許可 (sitemap にも掲載)。fetch_html 経由で
robots チェック + UA + 礼儀スリープを適用。表示専用でスコア対象外。

駅名(漢字) → URL の対応は都道府県インデックスページのアンカーから構築し
machimusubi_stations にキャッシュする。
"""
import re
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from scrapers.base import fetch_html
from db_helper import query_all, query_one, execute

BASE = "https://www.homes.co.jp"
INDEX_PAGES = [f"{BASE}/machimusubi/tokyo/", f"{BASE}/machimusubi/kanagawa/"]

# カテゴリ名 → DB列。ページ上の表記ゆれに regex で対応。
CATEGORIES = [
    ("transport", r"交通の利便性"),
    ("safety", r"治安の良さ"),
    ("shopping", r"買い物のしやすさ"),
    ("childcare", r"子育てのしやすさ"),
    ("nature", r"自然の多さ"),
]
_ANCHOR_RE = re.compile(r'href="(/machimusubi/[a-z]+/[a-z0-9_]+-st/)"[^>]*>([^<]{1,30}?)駅?\s*<', re.S)


def normalize_station(name):
    """「東神奈川駅」「東神奈川」→「東神奈川」。"""
    if not name:
        return None
    return re.sub(r"駅$", "", name.strip()) or None


_map_failed = False  # プロセス内で index 取得に失敗したら以後スキップ (ローカル開発で import を遅くしない)


def ensure_station_map(force=False, debug=False):
    """駅名→URL マップを index ページから構築 (空のときのみ)。件数を返す。"""
    global _map_failed
    n = query_one("SELECT COUNT(*) AS c FROM machimusubi_stations")["c"]
    if n > 0 and not force:
        return n
    if _map_failed and not force:
        return 0
    total = 0
    for idx_url in INDEX_PAGES:
        html = fetch_html(idx_url)
        if not html:
            print(f"  machimusubi index fetch failed: {idx_url}")
            continue
        pairs = _ANCHOR_RE.findall(html)
        if debug:
            print(f"  {idx_url}: {len(pairs)} anchors, sample: {pairs[:5]}")
        for path, name in pairs:
            name = normalize_station(re.sub(r"<[^>]+>", "", name))
            if not name:
                continue
            execute("INSERT OR REPLACE INTO machimusubi_stations (station, url) VALUES (?,?)",
                    (name, BASE + path))
            total += 1
    n = query_one("SELECT COUNT(*) AS c FROM machimusubi_stations")["c"]
    if n == 0:
        _map_failed = True
    return n


def parse_station_scores(html):
    """ページテキストからカテゴリ別スコアを抽出 (構造非依存: 見出し語の近傍の数値)。"""
    text = re.sub(r"<script[^>]*>.*?</script>|<style[^>]*>.*?</style>", " ", html, flags=re.S)
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"\s+", " ", text)
    scores = {}
    for col, pat in CATEGORIES:
        m = re.search(pat + r"\D{0,40}?([0-5](?:\.[0-9])?)", text)
        if m:
            v = float(m.group(1))
            if 0 < v <= 5:
                scores[col] = v
    return scores


def get_station_review(station, max_age_days=90):
    """キャッシュ優先で駅の住民評価を返す。無ければ取得を試みる (失敗時 None)。"""
    station = normalize_station(station)
    if not station:
        return None
    row = query_one(
        "SELECT * FROM station_reviews WHERE station=? AND fetched_at > datetime('now', ?)",
        (station, f"-{max_age_days} days"))
    if row:
        return row if row.get("avg_score") else None  # 取得失敗もキャッシュ(再攻撃防止)
    if ensure_station_map() == 0:
        return None
    hit = query_one("SELECT url FROM machimusubi_stations WHERE station=?", (station,))
    if not hit:
        return None
    html = fetch_html(hit["url"])
    scores = parse_station_scores(html) if html else {}
    if len(scores) >= 3:
        avg = round(sum(scores.values()) / len(scores), 2)
        execute("""INSERT OR REPLACE INTO station_reviews
            (station, url, transport, safety, shopping, childcare, nature, avg_score, fetched_at)
            VALUES (?,?,?,?,?,?,?,?,CURRENT_TIMESTAMP)""",
            (station, hit["url"], scores.get("transport"), scores.get("safety"),
             scores.get("shopping"), scores.get("childcare"), scores.get("nature"), avg))
        return query_one("SELECT * FROM station_reviews WHERE station=?", (station,))
    # 失敗も記録して連打を防ぐ (avg_score NULL)
    execute("INSERT OR REPLACE INTO station_reviews (station, url, avg_score, fetched_at) "
            "VALUES (?,?,NULL,CURRENT_TIMESTAMP)", (station, hit["url"]))
    return None
