from flask import Flask, jsonify, request, render_template
from db_helper import query_all, query_one, execute
from core.validation import preferences as validate_preferences, status_fields
from services.regions import attach_benchmarks
from werkzeug.exceptions import HTTPException
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from scripts.init_db import init_db
from scripts.seed_regions import seed_region_catalog, dedupe_regions

app = Flask(__name__)

init_db()
dedupe_regions()
seed_region_catalog()


_COMPRESSIBLE = ("application/json", "text/css", "application/javascript",
                 "text/javascript", "text/html")
_MIN_COMPRESS_BYTES = 1024


@app.after_request
def _compress(resp):
    if resp.status_code >= 300:
        return resp
    if "gzip" not in request.headers.get("Accept-Encoding", "").lower():
        return resp
    if resp.headers.get("Content-Encoding"):
        return resp
    if not resp.mimetype or not resp.mimetype.startswith(_COMPRESSIBLE):
        return resp
    resp.direct_passthrough = False
    data = resp.get_data()
    if len(data) < _MIN_COMPRESS_BYTES:
        return resp
    import gzip as _gzip
    packed = _gzip.compress(data, 6)
    if len(packed) >= len(data):
        return resp
    resp.set_data(packed)
    resp.headers["Content-Encoding"] = "gzip"
    resp.headers["Content-Length"] = str(len(packed))
    resp.headers.add("Vary", "Accept-Encoding")
    return resp


app.config["SEND_FILE_MAX_AGE_DEFAULT"] = 31536000


def _asset_stamp():
    """static/ 配下で最も新しい mtime。デプロイで何か変われば値が変わる。"""
    newest = 0
    for root, _dirs, files in os.walk(app.static_folder):
        for name in files:
            try:
                newest = max(newest, os.path.getmtime(os.path.join(root, name)))
            except OSError:
                pass
    return int(newest)


_ASSET_V = _asset_stamp()


def asset_v():
    # 本番は起動時の値で十分(デプロイで再起動する)。開発中は JS/CSS を書き換えても
    # リローダが走らず、1年キャッシュされた古い版が残るので毎回見に行く。
    return _asset_stamp() if app.debug else _ASSET_V


app.jinja_env.globals["asset_v"] = asset_v


# ADMIN_TOKEN を設定した環境でのみ要求する(未設定ならローカル開発として素通し)。
ADMIN_TOKEN = os.getenv("ADMIN_TOKEN", "")

def _needs_admin():
    return (request.url_rule is not None and request.path.startswith("/api/")
            and request.method in ("POST", "PUT", "PATCH", "DELETE"))


@app.before_request
def _guard_admin():
    if not ADMIN_TOKEN or not _needs_admin():
        return None
    import hmac
    sent = request.headers.get("X-Admin-Token", "")
    if hmac.compare_digest(sent, ADMIN_TOKEN):
        return None
    return jsonify({"error": "この操作には管理トークンが必要です。"}), 401


def _json_object():
    data = request.get_json()
    if not isinstance(data, dict):
        raise ValueError("JSONオブジェクトを送信してください")
    return data


@app.errorhandler(ValueError)
def _invalid_input(error):
    return jsonify({"error": str(error)}), 400


@app.errorhandler(HTTPException)
def _http_error(error):
    if request.path.startswith("/api/"):
        return jsonify({"error": error.description}), error.code
    return error


def _detail_parser(url):
    """許可ドメインを厳密に判定して解析器を返す。未対応なら None。"""
    from scrapers.base import allowed_domain
    domain = allowed_domain(url)
    if domain == "suumo.jp":
        from scrapers.suumo_detail import parse_suumo_detail
        return parse_suumo_detail
    if domain == "homes.co.jp":
        from scrapers.homes_detail import parse_homes_detail
        return parse_homes_detail
    if domain == "athome.jp":
        from scrapers.athome_detail import parse_athome_detail
        return parse_athome_detail
    if domain == "yahoo.co.jp":
        from scrapers.yahoo_detail import parse_yahoo_detail
        return parse_yahoo_detail
    return None


def _score_single(listing_id, resolve_commute=True):
    from services.scoring import score_listing
    return score_listing(listing_id, resolve_commute)


def _enqueue_enrichment(listing_id):
    if app.testing:
        return "idle"
    from services.enrichment import enqueue
    return enqueue(listing_id)


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/my-list")
def page_my_list():
    return render_template("my-list.html")


@app.route("/favorites")
def page_favorites():
    return render_template("favorites.html")


@app.route("/compare")
def page_compare():
    return render_template("compare.html")


@app.route("/settings")
def page_settings():
    return render_template("settings.html")


LEVEL_SCORE = {"高": 85, "中": 60, "低": 35}


def _enrich_region(r):
    """给 region_stats 行补 0~100 展示分 + 総合評価。"""
    safety = LEVEL_SCORE.get(r.get("safety_level"), 50)
    conv = LEVEL_SCORE.get(r.get("convenience_level"), 50)
    env = LEVEL_SCORE.get(r.get("environment_level"), 50)
    r["safety_score"] = safety
    r["convenience_score"] = conv
    r["environment_score"] = env
    r["overall_score"] = round((safety + conv + env) / 3)
    if r.get("stats_method") != "measured":
        r["avg_area"] = None
        r["avg_building_age"] = None
    r["levels_note"] = "治安・便利・住環境は手動の参考評価です"
    return r


@app.route("/api/dashboard")
def api_dashboard():
    total = query_one("SELECT COUNT(*) AS c FROM rental_listings WHERE is_active=1")["c"]
    pref = query_one("SELECT * FROM user_preferences WHERE id=1")
    budget_match = query_one(
        "SELECT COUNT(*) AS c FROM rental_listings WHERE is_active=1 AND total_monthly_cost <= ?",
        (pref["max_total_monthly_cost"],))["c"]
    pet_count = query_one(
        "SELECT COUNT(*) AS c FROM rental_listings WHERE is_active=1 AND pet_allowed=1")["c"]
    avg_cost = query_one(
        "SELECT AVG(total_monthly_cost) AS a FROM rental_listings WHERE is_active=1")["a"] or 0
    avg_area = query_one(
        "SELECT AVG(area_m2) AS a FROM rental_listings WHERE is_active=1")["a"] or 0
    avg_score = query_one(
        "SELECT AVG(s.total_score) AS a FROM listing_scores s JOIN rental_listings l ON s.listing_id=l.id WHERE l.is_active=1")["a"] or 0
    fav_count = query_one("SELECT COUNT(*) AS c FROM listing_status")["c"]

    regions = [_enrich_region(r) for r in query_all("SELECT * FROM region_stats ORDER BY avg_rent DESC")]
    rented = [r for r in regions if r.get("avg_rent") and r.get("rent_layout") == "1LDK"
              and r.get("rent_fetched_at") and r.get("prefecture") in ("東京都", "神奈川県")]
    cheapest = min(rented, key=lambda x: x["avg_rent"]) if rented else None
    priciest = max(rented, key=lambda x: x["avg_rent"]) if rented else None
    best_value = max(rented, key=lambda x: x["overall_score"] / x["avg_rent"]) if rented else None
    area_summary = {
        "cheapest": {"ward": cheapest["ward"], "rent": cheapest["avg_rent"]} if cheapest else None,
        "priciest": {"ward": priciest["ward"], "rent": priciest["avg_rent"]} if priciest else None,
        "best_value": {"ward": best_value["ward"], "rent": best_value["avg_rent"], "score": best_value["overall_score"]} if best_value else None,
        "rent_min": cheapest["avg_rent"] if cheapest else None,
        "rent_max": priciest["avg_rent"] if priciest else None,
    }
    tokyo_regions = [{"name": r["ward"], "value": r["avg_rent"]} for r in rented if r["prefecture"] == "東京都"]
    yokohama_regions = [{"name": r["ward"], "value": r["avg_rent"]} for r in rented if r["city"] == "横浜市"]

    user_ward_dist = query_all(
        "SELECT ward AS name, COUNT(*) AS value FROM rental_listings WHERE is_active=1 AND ward IS NOT NULL GROUP BY ward ORDER BY value DESC")

    user_scatter = query_all("""SELECT l.area_m2 AS x, l.total_monthly_cost AS y,
        l.title, l.ward, l.layout
        FROM rental_listings l
        WHERE l.is_active=1""")

    platform_dist = query_all(
        "SELECT platform AS name, COUNT(*) AS value FROM rental_listings WHERE is_active=1 GROUP BY platform")

    price_drop = query_one("""SELECT COUNT(DISTINCT l.id) AS c FROM listing_price_history h
        JOIN rental_listings l ON h.listing_id=l.id
        WHERE l.is_active=1 AND h.observation_kind='observed' AND l.total_monthly_cost < h.total_monthly_cost""")["c"]

    status_dist = query_all(
        "SELECT status AS name, COUNT(*) AS value FROM listing_status GROUP BY status")

    return jsonify({
        "total_listings": total, "budget_match_count": budget_match,
        "pet_allowed_count": pet_count,
        "average_total_cost": int(avg_cost), "average_area": round(avg_area, 1),
        "average_score": round(avg_score, 1),
        "favorite_count": fav_count, "price_drop_count": price_drop,
        "region_count": len(regions),
        "area_summary": area_summary,
        "regions": regions,
        "tokyo_region_rent": tokyo_regions,
        "yokohama_region_rent": yokohama_regions,
        "user_ward_distribution": user_ward_dist,
        "user_scatter": user_scatter,
        "platform_distribution": platform_dist,
        "status_distribution": status_dist,
    })


@app.route("/api/regions")
def api_regions():
    return jsonify([_enrich_region(r) for r in query_all("SELECT * FROM region_stats ORDER BY prefecture, city, ward")])


@app.route("/api/regions/<ward>")
def api_region_detail(ward):
    rows = query_all("SELECT * FROM region_stats WHERE ward=?", (ward,))
    if not rows:
        return jsonify({"error": "not found"}), 404
    if len(rows) != 1:
        return jsonify({"error": "同名の地域があります。地域IDを指定してください"}), 409
    return jsonify(_enrich_region(rows[0]))


@app.route("/api/regions/id/<int:rid>")
def api_region_by_id(rid):
    row = query_one("SELECT * FROM region_stats WHERE id=?", (rid,))
    if not row:
        return jsonify({"error": "not found"}), 404
    return jsonify(_enrich_region(row))


@app.route("/api/my-list")
def api_my_list():
    """我的关注分析:导入房源 + 区域基准对比 + 雷达数据 + 价格历史 + 状态进度。"""
    pref = query_one("SELECT * FROM user_preferences WHERE id=1")
    max_cost = pref["max_total_monthly_cost"] if pref else 140000

    listings = query_all("""SELECT l.*, s.total_score, s.score_reason, s.commute_resolved,
        s.budget_score, s.area_score, s.commute_score, s.floor_score, s.pet_score,
        s.station_score, s.age_score, s.initial_cost_score,
        st.id AS fav_status_id, st.status AS fav_status
        FROM rental_listings l
        LEFT JOIN listing_scores s ON s.listing_id=l.id
        LEFT JOIN listing_status st ON st.listing_id=l.id
        WHERE l.is_active=1 ORDER BY s.total_score DESC""")

    attach_benchmarks(listings)
    from scrapers.machimusubi import extract_station
    st_keys = {l["id"]: extract_station(l.get("nearest_station")) for l in listings}
    uniq_sts = sorted({k for k in st_keys.values() if k})
    reviews = {}
    if uniq_sts:
        ph = ",".join("?" * len(uniq_sts))
        for r in query_all(
                f"SELECT * FROM station_reviews WHERE avg_score IS NOT NULL AND station IN ({ph})",
                uniq_sts):
            reviews[r["station"]] = r
    for l in listings:
        rv = reviews.get(st_keys[l["id"]])
        # 生の nearest_station は路線名や複数駅が繋がった塊のことがあるので、
        # 表示にはここで取り出した最寄駅名を使う。
        l["station_name"] = st_keys[l["id"]]
        l["st_station"] = st_keys[l["id"]] if rv else None
        for col in ("transport", "safety", "shopping", "childcare", "nature"):
            l["st_" + col] = rv[col] if rv else None
        l["st_avg"] = rv["avg_score"] if rv else None

    total = len(listings)
    budget_match = len([l for l in listings if l.get("total_monthly_cost") and l["total_monthly_cost"] <= max_cost])
    avg_cost = sum(l.get("total_monthly_cost") or 0 for l in listings) / total if total else 0
    avg_score = sum(l.get("total_score") or 0 for l in listings) / total if total else 0
    uncontacted = len([l for l in listings if not l.get("fav_status")])

    scatter_data = [{"x": l.get("area_m2"), "y": l.get("total_monthly_cost"),
                     "name": l.get("title"), "ward": l.get("ward"),
                     "region_avg": l.get("region_avg_rent")} for l in listings if l.get("area_m2") and l.get("total_monthly_cost")]

    radar_indicators = [
        {"name": "予算", "max": 20}, {"name": "面積", "max": 15},
        {"name": "通勤", "max": 15}, {"name": "階数", "max": 10},
        {"name": "ペット", "max": 15}, {"name": "駅距離", "max": 10},
        {"name": "築年数", "max": 10}, {"name": "初期費用", "max": 5},
    ]
    radar_series = [{
        "value": [l.get("budget_score") or 0, l.get("area_score") or 0,
                  l.get("commute_score") or 0, l.get("floor_score") or 0,
                  l.get("pet_score") or 0, l.get("station_score") or 0,
                  l.get("age_score") or 0, l.get("initial_cost_score") or 0],
        "name": l.get("title", "?")[:20],
    } for l in listings[:8]]

    compare_rows = [{
        "id": l["id"], "title": l.get("title"), "platform": l.get("platform"),
        "ward": l.get("ward"), "prefecture": l.get("prefecture"), "city": l.get("city"),
        "region_id": l.get("region_id"), "total_monthly_cost": l.get("total_monthly_cost"),
        "rent": l.get("rent"), "management_fee": l.get("management_fee"),
        "initial_cost_estimate": l.get("initial_cost_estimate"),
        "area_m2": l.get("area_m2"), "price_per_m2": l.get("price_per_m2"),
        "layout": l.get("layout"), "floor": l.get("floor"),
        "nearest_station": l.get("nearest_station"),
        "station_name": l.get("station_name"), "walk_minutes": l.get("walk_minutes"),
        "building_age": l.get("building_age"), "pet_allowed": l.get("pet_allowed"),
        "deposit": l.get("deposit"), "key_money": l.get("key_money"),
        "commute_minutes": l.get("commute_minutes"), "commute_resolved": l.get("commute_resolved"),
        "total_score": l.get("total_score"), "score_reason": l.get("score_reason"),
        "budget_score": l.get("budget_score"), "area_score": l.get("area_score"),
        "commute_score": l.get("commute_score"), "floor_score": l.get("floor_score"),
        "pet_score": l.get("pet_score"), "station_score": l.get("station_score"),
        "age_score": l.get("age_score"), "initial_cost_score": l.get("initial_cost_score"),
        "region_avg_rent": l.get("region_avg_rent"),
        "region_comparison_cost": l.get("region_comparison_cost"),
        "benchmark_source": l.get("benchmark_source"), "benchmark_fetched_at": l.get("benchmark_fetched_at"),
        "benchmark_note": l.get("benchmark_note"),
        "region_avg_area": l.get("region_avg_area"), "region_avg_age": l.get("region_avg_age"),
        "st_station": l.get("st_station"),
        "st_transport": l.get("st_transport"), "st_safety": l.get("st_safety"),
        "st_shopping": l.get("st_shopping"), "st_childcare": l.get("st_childcare"),
        "st_nature": l.get("st_nature"), "st_avg": l.get("st_avg"),
        "total_floors": l.get("total_floors"), "structure": l.get("structure"),
        "two_person_allowed": l.get("two_person_allowed"),
        "bath_toilet_separate": l.get("bath_toilet_separate"), "auto_lock": l.get("auto_lock"),
        "delivery_box": l.get("delivery_box"), "south_facing": l.get("south_facing"),
        "aircon": l.get("aircon"),
        "fav_status": l.get("fav_status"), "fav_status_id": l.get("fav_status_id"),
        "detail_url": l.get("detail_url"),
    } for l in listings]

    feature_labels = [
        ("bath_toilet_separate", "バストイレ別"), ("auto_lock", "オートロック"),
        ("delivery_box", "宅配ボックス"), ("south_facing", "南向き"),
        ("aircon", "エアコン"), ("pet_allowed", "ペット可"),
        ("two_person_allowed", "2人入居可"),
    ]
    ideal_area = pref["ideal_area_m2"] if pref else 40
    cloud = {}

    def bump(label):
        cloud[label] = cloud.get(label, 0) + 1

    for l in listings:
        for col, label in feature_labels:
            if l.get(col):
                bump(label)
        if l.get("total_monthly_cost") and l["total_monthly_cost"] <= max_cost:
            bump("予算内")
        if l.get("total_monthly_cost") and l.get("region_avg_rent") and l["region_comparison_cost"] < l["region_avg_rent"]:
            bump("コスパ良")
        if l.get("area_m2") and l["area_m2"] >= ideal_area:
            bump("広め")
        if l.get("building_age") is not None and l["building_age"] <= 10:
            bump("築浅")
        if l.get("walk_minutes") is not None and l["walk_minutes"] <= 10:
            bump("駅徒歩10分以内")
        if l.get("floor") is not None and l["floor"] >= 3:
            bump("3階以上")
        if l.get("key_money") == 0:
            bump("礼金なし")
        if l.get("deposit") == 0:
            bump("敷金なし")
    feature_cloud = sorted(
        [{"name": k, "value": v} for k, v in cloud.items()],
        key=lambda x: x["value"], reverse=True)

    layout_counts = {}
    for l in listings:
        if l.get("layout"):
            layout_counts[l["layout"]] = layout_counts.get(l["layout"], 0) + 1
    layout_dist = sorted(
        [{"name": k, "value": v} for k, v in layout_counts.items()],
        key=lambda x: x["value"], reverse=True)

    deviations = [{
        "name": l.get("title", "?")[:20],
        "ward": l.get("ward"),
        "total_monthly_cost": l.get("total_monthly_cost"),
        "region_avg_rent": l.get("region_avg_rent"),
        "deviation_pct": round((l["region_comparison_cost"] - l["region_avg_rent"]) / l["region_avg_rent"] * 100, 1)
                        if l.get("total_monthly_cost") and l.get("region_avg_rent") else None,
    } for l in listings if l.get("total_monthly_cost") and l.get("region_avg_rent")]

    status_progress = query_all("""SELECT status, COUNT(*) AS value FROM listing_status GROUP BY status""")

    price_history = query_all("""SELECT l.title, l.id, h.total_monthly_cost, h.checked_at
        FROM listing_price_history h JOIN rental_listings l ON h.listing_id=l.id
        WHERE h.observation_kind='observed' AND h.total_monthly_cost IS NOT NULL
        ORDER BY l.id, h.checked_at""")

    return jsonify({
        "total": total, "budget_match": budget_match,
        "avg_cost": int(avg_cost), "avg_score": round(avg_score, 1),
        "uncontacted": uncontacted,
        "scatter_data": scatter_data,
        "radar_indicators": radar_indicators,
        "radar_series": radar_series,
        "compare_rows": compare_rows,
        "deviations": deviations,
        "status_progress": status_progress,
        "price_history": price_history,
        "feature_cloud": feature_cloud,
        "layout_dist": layout_dist,
        "prefs": {
            "broker_fee_rate": pref["broker_fee_rate"] if pref else 0.55,
            "prepaid_rent_months": pref["prepaid_rent_months"] if pref else 1,
            "misc_cost": pref["misc_cost"] if pref else 40000,
            "max_total_monthly_cost": max_cost,
            "ideal_area_m2": pref["ideal_area_m2"] if pref else 40,
        },
    })


@app.route("/api/listings/<int:lid>", methods=["GET", "DELETE"])
def api_listing_detail(lid):
    if request.method == "DELETE":
        if not query_one("SELECT id FROM rental_listings WHERE id=?", (lid,)):
            return jsonify({"error": "not found"}), 404
        from db_helper import transaction
        with transaction() as conn:
            conn.execute("DELETE FROM listing_price_history WHERE listing_id=?", (lid,))
            conn.execute("DELETE FROM listing_status WHERE listing_id=?", (lid,))
            conn.execute("DELETE FROM listing_scores WHERE listing_id=?", (lid,))
            conn.execute("DELETE FROM rental_listings WHERE id=?", (lid,))
        return jsonify({"ok": True})
    row = query_one("""SELECT l.*, s.total_score, s.score_reason, s.commute_resolved,
        s.commute_minutes AS score_commute, st.status, st.memo, st.priority
        FROM rental_listings l
        LEFT JOIN listing_scores s ON s.listing_id=l.id
        LEFT JOIN listing_status st ON st.listing_id=l.id
        WHERE l.id=?""", (lid,))
    if not row:
        return jsonify({"error": "not found"}), 404
    return jsonify(row)


@app.route("/api/status", methods=["GET", "POST"])
def api_status():
    if request.method == "GET":
        return jsonify(query_all("""SELECT st.*, l.title, l.platform, l.ward,
            l.total_monthly_cost, l.area_m2, l.layout, l.detail_url, s.total_score
            FROM listing_status st
            JOIN rental_listings l ON st.listing_id=l.id
            LEFT JOIN listing_scores s ON s.listing_id=l.id
            ORDER BY st.updated_at DESC"""))
    data = status_fields(_json_object(), creating=True)
    from db_helper import transaction
    with transaction(immediate=True) as conn:
        if not conn.execute("SELECT id FROM rental_listings WHERE id=?", (data["listing_id"],)).fetchone():
            return jsonify({"error": "listing not found"}), 404
        data.setdefault("priority", 1)
        data.setdefault("contacted", 0)
        fields = list(data)
        inserted = conn.execute(f"INSERT INTO listing_status ({','.join(fields)}) "
            f"VALUES ({','.join('?' for _ in fields)}) ON CONFLICT(listing_id) DO NOTHING RETURNING id",
            list(data.values())).fetchone()
        sid = inserted[0] if inserted else conn.execute(
            "SELECT id FROM listing_status WHERE listing_id=?", (data["listing_id"],)).fetchone()[0]
    return jsonify({"id": sid}), 201 if inserted else 200


@app.route("/api/status/<int:sid>", methods=["PUT", "DELETE"])
def api_status_modify(sid):
    if not query_one("SELECT id FROM listing_status WHERE id=?", (sid,)):
        return jsonify({"error": "not found"}), 404
    if request.method == "DELETE":
        execute("DELETE FROM listing_status WHERE id=?", (sid,))
        return jsonify({"ok": True})
    data = status_fields(_json_object())
    if data:
        sets = ", ".join(f"{key}=?" for key in data)
        execute(f"UPDATE listing_status SET {sets}, updated_at=CURRENT_TIMESTAMP WHERE id=?",
                [*data.values(), sid])
    return jsonify({"ok": True})


@app.route("/api/compare")
def api_compare():
    ids = request.args.get("ids", "")
    if not ids:
        return jsonify([])
    parts = ids.split(",")
    if len(parts) > 4 or any(not x.isascii() or not x.isdigit() or len(x) > 19 for x in parts):
        raise ValueError("ids: 1〜4件の正の物件IDを指定してください")
    id_list = list(dict.fromkeys(int(x) for x in parts))
    if any(x < 1 or x > 2**63 - 1 for x in id_list):
        raise ValueError("ids: 正の物件IDを指定してください")
    placeholders = ",".join("?" * len(id_list))
    rows = query_all(f"""SELECT l.*, s.total_score, s.score_reason, s.commute_resolved,
        s.budget_score, s.area_score, s.commute_score, s.floor_score, s.pet_score,
        s.station_score, s.age_score, s.initial_cost_score
        FROM rental_listings l LEFT JOIN listing_scores s ON s.listing_id=l.id
        WHERE l.is_active=1 AND l.id IN ({placeholders})""", id_list)
    rows.sort(key=lambda r: id_list.index(r["id"]))
    from scrapers.machimusubi import extract_station
    for r in rows:
        r["station_name"] = extract_station(r.get("nearest_station"))
    return jsonify(rows)


@app.route("/api/pool/clear", methods=["POST"])
def api_pool_clear():
    """物件プールを全てクリア(履歴的な一括抓取データのリセット用)。"""
    from db_helper import transaction
    n = query_one("SELECT COUNT(*) AS c FROM rental_listings")["c"]
    with transaction() as conn:
        conn.execute("DELETE FROM listing_price_history")
        conn.execute("DELETE FROM listing_status")
        conn.execute("DELETE FROM listing_scores")
        conn.execute("DELETE FROM rental_listings")
    return jsonify({"ok": True, "deleted": n})


@app.route("/api/import/detail", methods=["POST"])
def api_import_detail():
    """粘贴单个房源详情页 URL,自动解析入库 + 评分。支持4平台。"""
    from scrapers.base import fetch_html
    from scripts.run_scrape import normalize, upsert_listing
    from db_helper import transaction

    data = _json_object()
    url = data.get("url")
    if not isinstance(url, str) or not url.strip() or len(url) > 4096:
        raise ValueError("URL: 4096文字以内の物件URLを入力してください")
    url = url.strip()

    # 根据 URL 判断平台和解析器(ホスト名を厳密に照合)
    parser = _detail_parser(url)
    if parser is None:
        return jsonify({"error": "サポートされていないURLです。SUUMO/HOMES/athome/Yahoo!不動産の物件詳細URLを入力してください。"}), 400

    html = fetch_html(url)
    if html is None:
        return jsonify({"error": "ページの取得に失敗しました。robots.txtまたはネットワークエラーの可能性があります。"}), 500

    try:
        raw = parser(html, url)
        if not raw.title:
            return jsonify({"error": "物件情報の解析に失敗しました。詳細ページのURLが正しいか確認してください。"}), 500
    except Exception as e:
        return jsonify({"error": f"解析エラー: {str(e)}"}), 500

    prefs = query_one("SELECT * FROM user_preferences WHERE id=1")
    normalized = normalize(raw, prefs)
    if not normalized["rent"] or normalized["rent"] < 0:
        return jsonify({"error": "家賃を解析できませんでした。物件詳細ページを確認してください"}), 422
    with transaction(immediate=True) as conn:
        status, listing_id = upsert_listing(conn, normalized)
    _score_single(listing_id, resolve_commute=False)
    enrichment = _enqueue_enrichment(listing_id)

    return jsonify({
        "status": status,
        "enrichment_status": enrichment,
        "id": listing_id,
        "title": raw.title,
        "message": f"「{raw.title}」を{'追加' if status == 'inserted' else '更新'}しました"
    })


@app.route("/api/listings/<int:lid>/refresh", methods=["POST"])
def api_listing_refresh(lid):
    """重新抓取某房源(更新价格,写历史),重算评分。"""
    from scrapers.base import fetch_html
    from scripts.run_scrape import normalize, upsert_listing
    from db_helper import transaction

    listing = query_one("SELECT * FROM rental_listings WHERE id=?", (lid,))
    if not listing:
        return jsonify({"error": "物件が見つかりません"}), 404

    url = listing["detail_url"]
    old_cost = listing["total_monthly_cost"]

    html = fetch_html(url)
    if html is None:
        return jsonify({"error": "ページの取得に失敗しました"}), 500

    # 根据URL选择解析器(ホスト名を厳密に照合)
    parser = _detail_parser(url)
    if parser is None:
        return jsonify({"error": "サポートされていないURL"}), 400

    try:
        raw = parser(html, url)
    except Exception as e:
        return jsonify({"error": f"解析エラー: {str(e)}"}), 500

    raw.detail_url = url
    prefs = query_one("SELECT * FROM user_preferences WHERE id=1")
    normalized = normalize(raw, prefs)
    if not raw.title or not normalized["rent"] or normalized["rent"] < 0:
        return jsonify({"error": "物件情報を解析できませんでした。保存済みデータは変更していません"}), 422
    with transaction(immediate=True) as conn:
        upsert_listing(conn, normalized)
    _score_single(lid, resolve_commute=False)
    enrichment = _enqueue_enrichment(lid)

    new_listing = query_one("SELECT total_monthly_cost FROM rental_listings WHERE id=?", (lid,))
    new_cost = new_listing["total_monthly_cost"] if new_listing else None
    price_changed = old_cost != new_cost

    return jsonify({
        "ok": True,
        "title": raw.title,
        "old_cost": old_cost,
        "new_cost": new_cost,
        "price_changed": price_changed,
        "enrichment_status": enrichment,
        "message": f"「{raw.title}」を更新しました" + (f" 価格変動: {old_cost}→{new_cost}円" if price_changed else " 価格変動なし"),
    })


@app.route("/api/preferences")
def api_preferences():
    return jsonify(query_one("SELECT * FROM user_preferences WHERE id=1"))


@app.route("/api/preferences", methods=["PUT"])
def api_preferences_update():
    data = _json_object()
    from db_helper import transaction
    from services.scoring import recalculate
    with transaction(immediate=True) as conn:
        pref = dict(conn.execute("SELECT * FROM user_preferences WHERE id=1").fetchone())
        clean = validate_preferences(data, pref)
        if clean:
            sets = ", ".join(f"{key}=?" for key in clean)
            conn.execute(f"UPDATE user_preferences SET {sets}, updated_at=CURRENT_TIMESTAMP WHERE id=1",
                         list(clean.values()))
    if clean:
        recalculate(resolve_commute=False)
    return jsonify({"ok": True})


@app.route("/api/scores/recalculate", methods=["POST"])
def api_recalculate():
    from services.scoring import recalculate
    count = recalculate(resolve_commute=False)
    states = [_enqueue_enrichment(r["id"]) for r in query_all("SELECT id FROM rental_listings WHERE is_active=1")]
    return jsonify({"ok": True, "count": count, "pending": states.count("pending"), "deferred": states.count("deferred")})


@app.route("/api/listings/<int:lid>/enrichment")
def api_enrichment_status(lid):
    if not query_one("SELECT id FROM rental_listings WHERE id=?", (lid,)):
        return jsonify({"error": "not found"}), 404
    from services.enrichment import status
    return jsonify({"status": status(lid)})


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", "5000")),
            debug=os.getenv("FLASK_DEBUG") == "1")
