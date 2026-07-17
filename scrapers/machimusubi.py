"""Phase C: LIFULL HOME'S「まちむすび」駅ページから住民アンケートの集計スコアを取得。

取得するのは 5 カテゴリの数値スコアのみ (口コミ本文は保存しない):
  交通の利便性 / 治安の良さ / 買い物のしやすさ / 子育てのしやすさ / 自然の多さ

robots.txt は /machimusubi/ を許可 (sitemap にも掲載)。fetch_html 経由で
robots チェック + UA + 礼儀スリープを適用。表示専用でスコア対象外。

駅 URL の解決 (バルククロールなし):
  sitemap-station.xml を1リクエスト取得 → slug (ローマ字) を machimusubi_stations
  にキャッシュ → 漢字駅名は pykakasi でローマ字化し正規化して slug と照合。
  レビュー取得は 1駅 = 1リクエストのオンデマンドのみ (レート制限に強い)。
"""
import re
import sys
import os
import time
import difflib

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from scrapers.base import fetch_html
from db_helper import query_all, query_one, execute

BASE = "https://www.homes.co.jp"
SITEMAP_URL = f"{BASE}/machimusubi/sitemap-station.xml"
_ST_URL_RE = re.compile(r"https://www\.homes\.co\.jp/machimusubi/(tokyo|kanagawa)/([a-z0-9]+)_(\d+)-st/")

# カテゴリ名 → DB列
CATEGORIES = [
    ("transport", r"交通の利便性"),
    ("safety", r"治安の良さ"),
    ("shopping", r"買い物のしやすさ"),
    ("childcare", r"子育てのしやすさ"),
    ("nature", r"自然の多さ"),
]

MIN_MAP_SIZE = 150   # 東京+神奈川で数百駅のはず。これ未満は不完全とみなす
_map_failed = False  # プロセス内で構築失敗したら以後スキップ
_kks = None          # pykakasi は初回のみ初期化
_slug_index = None   # {正規化slug: url} のメモリキャッシュ


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
    pairs = re.findall(r"([^/\s線]{1,12}?)駅\s*(?:歩|徒歩)?\s*(\d{1,3})\s*分", s)
    if pairs:
        return min(pairs, key=lambda p: int(p[1]))[0]
    m = re.search(r"([^/\s線]{1,12}?)駅", s)
    return m.group(1) if m else normalize_station(s)


def _normalize_romaji(s):
    """ローマ字表記ゆれの正規化 (長音のばし・撥音・促音を slug 流儀に揃える)。"""
    s = re.sub(r"[^a-z]", "", s.lower())
    for a, b in (("ou", "o"), ("uu", "u"), ("oo", "o"), ("aa", "a"), ("ee", "e"),
                 ("nb", "mb"), ("np", "mp"), ("cch", "tch")):
        s = s.replace(a, b)
    return s


def _romaji(name):
    global _kks
    if _kks is None:
        import pykakasi
        _kks = pykakasi.kakasi()
    return _normalize_romaji("".join(x["hepburn"] for x in _kks.convert(name)))


def _fetch_retry(url, retries=2, backoff=6):
    """fetch_html + 失敗時バックオフ再試行 (レート制限/瞬断対策)。"""
    for i in range(retries + 1):
        html = fetch_html(url)
        if html:
            return html
        if i < retries:
            time.sleep(backoff * (i + 1))
    return None


def ensure_station_map(build=False, debug=False):
    """駅 slug→URL マップ件数を返す。build=True のとき未構築なら sitemap から構築 (1リクエスト)。"""
    global _map_failed, _slug_index
    n = query_one("SELECT COUNT(*) AS c FROM machimusubi_stations")["c"]
    if n >= MIN_MAP_SIZE or not build or _map_failed:
        return n
    xml = _fetch_retry(SITEMAP_URL)
    if not xml:
        print(f"  machimusubi sitemap fetch failed: {SITEMAP_URL}")
        _map_failed = True
        return n
    if n > 0:
        execute("DELETE FROM machimusubi_stations")  # 旧形式(漢字キー等)を一掃
    found = _ST_URL_RE.findall(xml)
    for pref, slug, sid in found:
        execute("INSERT OR REPLACE INTO machimusubi_stations (station, url) VALUES (?,?)",
                (slug, f"{BASE}/machimusubi/{pref}/{slug}_{sid}-st/"))
    _slug_index = None
    n = query_one("SELECT COUNT(*) AS c FROM machimusubi_stations")["c"]
    if debug:
        print(f"  sitemap: {len(found)} 駅URL (東京/神奈川) → map {n} 駅")
    if n == 0:
        _map_failed = True
    return n


def _resolve_url(station_kanji):
    """漢字駅名 → まちむすび駅ページ URL (ローマ字化 + 正規化 + 近似照合)。"""
    global _slug_index
    if _slug_index is None:
        _slug_index = {}
        for r in query_all("SELECT station, url FROM machimusubi_stations"):
            _slug_index.setdefault(_normalize_romaji(r["station"]), r["url"])
    if not _slug_index:
        return None
    cand = _romaji(station_kanji)
    if not cand:
        return None
    if cand in _slug_index:
        return _slug_index[cand]
    close = difflib.get_close_matches(cand, _slug_index.keys(), n=1, cutoff=0.86)
    return _slug_index[close[0]] if close else None


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
        return row if row.get("avg_score") else None  # スコア無し駅もキャッシュ(連打防止)
    if ensure_station_map(build=build_map) == 0:
        return None
    url = _resolve_url(station)
    if not url:
        return None
    html = _fetch_retry(url)
    if html is None:
        return None  # ネットワーク/レート制限: キャッシュせず次回再試行
    scores = parse_station_scores(html)
    if len(scores) >= 3:
        avg = round(sum(scores.values()) / len(scores), 2)
        execute("""INSERT OR REPLACE INTO station_reviews
            (station, url, transport, safety, shopping, childcare, nature, avg_score, fetched_at)
            VALUES (?,?,?,?,?,?,?,?,CURRENT_TIMESTAMP)""",
            (station, url, scores.get("transport"), scores.get("safety"),
             scores.get("shopping"), scores.get("childcare"), scores.get("nature"), avg))
        return query_one("SELECT * FROM station_reviews WHERE station=?", (station,))
    # ページは取れたがスコアが無い駅 (アンケート未実施等) → 記録して連打を防ぐ
    execute("INSERT OR REPLACE INTO station_reviews (station, url, avg_score, fetched_at) "
            "VALUES (?,?,NULL,CURRENT_TIMESTAMP)", (station, url))
    return None
