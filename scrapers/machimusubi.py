"""Phase C: LIFULL HOME'S「まちむすび」駅ページから住民アンケートの集計スコアを取得。

取得するのは 5 カテゴリの数値スコアのみ (口コミ本文は保存しない):
  交通の利便性 / 治安の良さ / 買い物のしやすさ / 子育てのしやすさ / 自然の多さ

robots.txt は /machimusubi/ を許可 (sitemap にも掲載)。fetch_html 経由で
robots チェック + UA + 礼儀スリープを適用。表示専用でスコア対象外。

駅名(漢字) → URL の対応:
  /machimusubi/{pref}/line/ (路線一覧) → 各路線ページ → 駅アンカー(漢字, 駅なし)
  の2段階で構築し machimusubi_stations にキャッシュ。構築は重い(~90リクエスト)
  ため batch スクリプトからのみ実行 (build=True)。import フックは既存マップのみ参照。
"""
import re
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from scrapers.base import fetch_html
from db_helper import query_all, query_one, execute

BASE = "https://www.homes.co.jp"
LINE_INDEX_PAGES = [f"{BASE}/machimusubi/tokyo/line/", f"{BASE}/machimusubi/kanagawa/line/"]

# カテゴリ名 → DB列
CATEGORIES = [
    ("transport", r"交通の利便性"),
    ("safety", r"治安の良さ"),
    ("shopping", r"買い物のしやすさ"),
    ("childcare", r"子育てのしやすさ"),
    ("nature", r"自然の多さ"),
]
_LINE_RE = re.compile(r'href="(?:https://www\.homes\.co\.jp)?(/machimusubi/[a-z]+/[a-z0-9_]+-line/)"')
_ST_ANCHOR_RE = re.compile(
    r'<a[^>]+href="(?:https://www\.homes\.co\.jp)?(/machimusubi/[a-z]+/[a-z0-9_]+-st/)"[^>]*>'
    r'\s*(?:<[^>]+>\s*)*([^<>]{1,15}?)\s*(?:駅)?\s*(?:<|$)', re.S)


def normalize_station(name):
    """「東神奈川駅」「東神奈川」→「東神奈川」。"""
    if not name:
        return None
    return re.sub(r"駅$", "", str(name).strip()) or None


def extract_station(raw):
    """nearest_station の表記ゆれから最寄駅名を1つ取り出す。

    例: 'ＪＲ山手線/東京駅 歩10分東京メトロ日比谷線/八丁堀駅 歩3分' → '八丁堀' (徒歩最短)
        '東神奈川' → '東神奈川'
    """
    if not raw:
        return None
    s = str(raw).strip()
    if "駅" not in s:
        return normalize_station(s)
    # (駅名, 徒歩分) を列挙して徒歩最短を選ぶ
    pairs = re.findall(r"([^/\s線]{1,12}?)駅\s*(?:歩|徒歩)?\s*(\d{1,3})\s*分", s)
    if pairs:
        return min(pairs, key=lambda p: int(p[1]))[0]
    m = re.search(r"([^/\s線]{1,12}?)駅", s)
    return m.group(1) if m else normalize_station(s)


_map_failed = False  # プロセス内で構築失敗したら以後スキップ


def ensure_station_map(build=False, debug=False):
    """駅名→URL マップ件数を返す。build=True のときのみ未構築なら構築 (重い)。"""
    global _map_failed
    n = query_one("SELECT COUNT(*) AS c FROM machimusubi_stations")["c"]
    if n > 0 or not build or _map_failed:
        return n
    line_urls = []
    for idx in LINE_INDEX_PAGES:
        html = fetch_html(idx)
        if not html:
            print(f"  machimusubi line index fetch failed: {idx}")
            continue
        found = sorted(set(_LINE_RE.findall(html)))
        if debug:
            print(f"  {idx}: {len(found)} lines")
        line_urls.extend(found)
    if not line_urls:
        _map_failed = True
        return 0
    for i, path in enumerate(line_urls):
        html = fetch_html(BASE + path)
        if not html:
            continue
        pairs = _ST_ANCHOR_RE.findall(html)
        for st_path, name in pairs:
            name = normalize_station(name)
            if name and re.search(r"[぀-ヿ一-鿿]", name):  # 和文の駅名のみ
                execute("INSERT OR REPLACE INTO machimusubi_stations (station, url) VALUES (?,?)",
                        (name, BASE + st_path))
        if debug and i % 10 == 0:
            c = query_one("SELECT COUNT(*) AS c FROM machimusubi_stations")["c"]
            print(f"  lines {i + 1}/{len(line_urls)} ... {c} 駅")
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


def get_station_review(station, max_age_days=90, build_map=False):
    """キャッシュ優先で駅の住民評価を返す。無ければ取得を試みる (失敗時 None)。"""
    station = extract_station(station)
    if not station:
        return None
    row = query_one(
        "SELECT * FROM station_reviews WHERE station=? AND fetched_at > datetime('now', ?)",
        (station, f"-{max_age_days} days"))
    if row:
        return row if row.get("avg_score") else None  # 取得失敗もキャッシュ(再攻撃防止)
    if ensure_station_map(build=build_map) == 0:
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
