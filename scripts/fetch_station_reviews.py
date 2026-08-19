"""Phase C: 物件プール内の全最寄駅について まちむすび 住民評価を取得。

駅 URL は sitemap-station.xml (1リクエスト) + ローマ字照合で解決するため
バルククロールは発生しない。レビュー取得は 1駅 = 1リクエスト。

Run: python scripts/fetch_station_reviews.py [駅名...]
  引数なし → rental_listings の nearest_station 全部 (表記ゆれは自動抽出)
  引数あり → 指定駅のみ (例: python scripts/fetch_station_reviews.py 東神奈川 横浜)
"""
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from scripts.init_db import init_db
from db_helper import query_all, query_one
from scrapers.machimusubi import ensure_station_map, get_station_review, extract_station


def main():
    init_db()
    print("building station map (sitemap 1リクエスト)...")
    n = ensure_station_map(build=True, debug=True)
    print(f"station map: {n} 駅")
    if n == 0:
        print("NG: sitemap を取得できませんでした (上のログを確認して再実行)")
        return

    args = [a for a in sys.argv[1:] if not a.startswith("-")]
    if args:
        stations = [extract_station(a) for a in args]
    else:
        stations = sorted({extract_station(r["nearest_station"])
                           for r in query_all("SELECT DISTINCT nearest_station FROM rental_listings "
                                              "WHERE nearest_station IS NOT NULL")} - {None})
    print(f"target stations: {stations or '(なし: 物件プールが空)'}")

    ok = miss = 0
    for st in stations:
        r = get_station_review(st)
        if r:
            ok += 1
            print(f"  {st}: 交通{r['transport']} 治安{r['safety']} 買物{r['shopping']} "
                  f"子育{r['childcare']} 自然{r['nature']} → avg {r['avg_score']}")
        else:
            miss += 1
            hit = query_one("SELECT url FROM machimusubi_stations WHERE station=?", (st,))
            print(f"  {st}: 取得できず ({'URLあり=解析失敗' if hit else 'まちむすび未収録駅'})")
    print(f"done: {ok} ok / {miss} miss")


if __name__ == "__main__":
    main()
