from flask import Flask, jsonify, request, render_template
from db_helper import query_all, query_one, execute
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from scripts.init_db import init_db
from scripts.seed_regions import seed_regions

app = Flask(__name__)

init_db()
from db_helper import query_one, execute as _execute
if query_one("SELECT COUNT(*) AS c FROM region_stats")["c"] == 0:
    seed_regions()
_execute("DELETE FROM region_stats WHERE ward IS NULL AND city IS NULL")


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


ASSET_V = _asset_stamp()
app.jinja_env.globals["asset_v"] = ASSET_V


# ADMIN_TOKEN を設定した環境でのみ要求する(未設定ならローカル開発として素通し)。
ADMIN_TOKEN = os.getenv("ADMIN_TOKEN", "")

_PROTECTED = (
    ("POST", "/api/pool/clear"),
    ("POST", "/api/import/csv"),
    ("POST", "/api/scrape"),
    ("POST", "/api/scores/recalculate"),
    ("PUT", "/api/preferences"),
)


def _needs_admin():
    p, m = request.path, request.method
    if (m, p) in _PROTECTED:
        return True
    if m == "DELETE" and p.startswith("/api/listings/"):
        return True
    if p.startswith("/api/sources") and m in ("POST", "PUT", "DELETE"):
        return True
    return False


@app.before_request
def _guard_admin():
    if not ADMIN_TOKEN or not _needs_admin():
        return None
    import hmac
    sent = request.headers.get("X-Admin-Token", "")
    if hmac.compare_digest(sent, ADMIN_TOKEN):
        return None
    return jsonify({"error": "この操作には管理トークンが必要です。"}), 401


def _refresh_initial_costs():
    """保存済みの初期費用を現在の係数で計算し直す(表示箇所ごとの食い違いを防ぐ)。"""
    from core.initial_cost import estimate_initial_cost
    from db_helper import get_conn
    conn = get_conn()
    pref = conn.execute("SELECT * FROM user_preferences WHERE id=1").fetchone()
    if not pref:
        conn.close()
        return
    for l in conn.execute("SELECT id, rent, deposit, key_money, initial_cost_estimate "
                          "FROM rental_listings WHERE is_active=1").fetchall():
        initial = estimate_initial_cost(
            l["rent"], l["deposit"], l["key_money"],
            broker_fee_rate=pref["broker_fee_rate"],
            prepaid_rent_months=pref["prepaid_rent_months"],
            misc_cost=pref["misc_cost"])
        if initial is not None and initial != l["initial_cost_estimate"]:
            conn.execute("UPDATE rental_listings SET initial_cost_estimate=? WHERE id=?",
                         (initial, l["id"]))
    conn.commit()
    conn.close()


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


def _score_single(listing_id):
    """只给一条房源评分(避免全量重算超时)。"""
    import sqlite3
    from config import DB_PATH
    from core.scoring import calculate_scores, ScoreInput, Weights
    from core.commute import get_commute_minutes
    from datetime import datetime
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    pref = conn.execute("SELECT * FROM user_preferences WHERE id=1").fetchone()
    l = conn.execute("SELECT * FROM rental_listings WHERE id=?", (listing_id,)).fetchone()
    if not l:
        conn.close()
        return
    w = Weights(budget=pref["budget_weight"], area=pref["area_weight"],
        commute=pref["commute_weight"], floor=pref["floor_weight"],
        pet=pref["pet_weight"], station=pref["station_weight"],
        age=pref["age_weight"], initial_cost=pref["initial_cost_weight"])
    commute_minutes = None
    if pref["target_station"] and l["nearest_station"]:
        commute_minutes = get_commute_minutes(l["nearest_station"], pref["target_station"])
    inp = ScoreInput(total_monthly_cost=l["total_monthly_cost"], area_m2=l["area_m2"],
        floor=l["floor"], pet_allowed=l["pet_allowed"], walk_minutes=l["walk_minutes"],
        building_age=l["building_age"], deposit=l["deposit"], key_money=l["key_money"], rent=l["rent"])
    r = calculate_scores(inp, w, max_cost=pref["max_total_monthly_cost"],
        ideal_area=pref["ideal_area_m2"], min_floor=pref["min_floor"],
        max_walk=pref["max_walk_minutes"], max_age=pref["max_building_age"],
        broker_rate=pref["broker_fee_rate"], prepaid=pref["prepaid_rent_months"],
        misc=pref["misc_cost"], commute_minutes=commute_minutes,
        min_area=pref["min_area_m2"])
    conn.execute("DELETE FROM listing_scores WHERE listing_id=?", (listing_id,))
    conn.execute("""INSERT INTO listing_scores
        (listing_id, budget_score, area_score, commute_score, floor_score, pet_score,
         station_score, age_score, initial_cost_score, feature_score, total_score,
         score_reason, commute_minutes, commute_resolved, calculated_at)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (listing_id, r.budget_score, r.area_score, r.commute_score, r.floor_score,
         r.pet_score, r.station_score, r.age_score, r.initial_cost_score, r.feature_score,
         r.total_score, r.score_reason, commute_minutes, r.commute_resolved, datetime.now().isoformat()))
    conn.commit()
    conn.close()


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


@app.route("/import")
def page_import():
    return render_template("import.html")


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
    rented = [r for r in regions if r.get("avg_rent") and r.get("prefecture") in ("東京都", "神奈川県")]
    cheapest = min(rented, key=lambda x: x["avg_rent"]) if rented else None
    priciest = max(rented, key=lambda x: x["avg_rent"]) if rented else None
    best_value = max(rented, key=lambda x: x["overall_score"] * 100000 - x["avg_rent"]) if rented else None
    area_summary = {
        "cheapest": {"ward": cheapest["ward"], "rent": cheapest["avg_rent"]} if cheapest else None,
        "priciest": {"ward": priciest["ward"], "rent": priciest["avg_rent"]} if priciest else None,
        "best_value": {"ward": best_value["ward"], "rent": best_value["avg_rent"], "score": best_value["overall_score"]} if best_value else None,
        "rent_min": cheapest["avg_rent"] if cheapest else None,
        "rent_max": priciest["avg_rent"] if priciest else None,
    }
    tokyo_regions = query_all("SELECT ward AS name, avg_rent AS value FROM region_stats WHERE prefecture='東京都' ORDER BY value DESC")
    yokohama_regions = query_all("SELECT ward AS name, avg_rent AS value FROM region_stats WHERE city='横浜市' ORDER BY value DESC")

    user_ward_dist = query_all(
        "SELECT ward AS name, COUNT(*) AS value FROM rental_listings WHERE is_active=1 AND ward IS NOT NULL GROUP BY ward ORDER BY value DESC")

    user_scatter = query_all("""SELECT l.area_m2 AS x, l.total_monthly_cost AS y,
        l.title, l.ward, l.layout, r.avg_rent AS region_avg
        FROM rental_listings l LEFT JOIN region_stats r ON l.ward = r.ward
        WHERE l.is_active=1""")

    platform_dist = query_all(
        "SELECT platform AS name, COUNT(*) AS value FROM rental_listings WHERE is_active=1 GROUP BY platform")

    price_drop = query_one("""SELECT COUNT(*) AS c FROM listing_price_history h
        JOIN rental_listings l ON h.listing_id=l.id
        WHERE l.is_active=1 AND l.total_monthly_cost < h.total_monthly_cost""")["c"]

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
    row = query_one("SELECT * FROM region_stats WHERE ward=?", (ward,))
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
        r.avg_rent AS region_avg_rent, r.avg_area AS region_avg_area,
        r.avg_building_age AS region_avg_age,
        st.id AS fav_status_id, st.status AS fav_status
        FROM rental_listings l
        LEFT JOIN listing_scores s ON s.listing_id=l.id
        LEFT JOIN region_stats r ON l.ward = r.ward
        LEFT JOIN listing_status st ON st.listing_id=l.id
        WHERE l.is_active=1 ORDER BY s.total_score DESC""")

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
        "ward": l.get("ward"), "total_monthly_cost": l.get("total_monthly_cost"),
        "rent": l.get("rent"), "management_fee": l.get("management_fee"),
        "initial_cost_estimate": l.get("initial_cost_estimate"),
        "area_m2": l.get("area_m2"), "price_per_m2": l.get("price_per_m2"),
        "layout": l.get("layout"), "floor": l.get("floor"),
        "nearest_station": l.get("nearest_station"), "walk_minutes": l.get("walk_minutes"),
        "building_age": l.get("building_age"), "pet_allowed": l.get("pet_allowed"),
        "deposit": l.get("deposit"), "key_money": l.get("key_money"),
        "commute_minutes": l.get("commute_minutes"), "commute_resolved": l.get("commute_resolved"),
        "total_score": l.get("total_score"), "score_reason": l.get("score_reason"),
        "budget_score": l.get("budget_score"), "area_score": l.get("area_score"),
        "commute_score": l.get("commute_score"), "floor_score": l.get("floor_score"),
        "pet_score": l.get("pet_score"), "station_score": l.get("station_score"),
        "age_score": l.get("age_score"), "initial_cost_score": l.get("initial_cost_score"),
        "region_avg_rent": l.get("region_avg_rent"),
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
        if l.get("total_monthly_cost") and l.get("region_avg_rent") and l["total_monthly_cost"] < l["region_avg_rent"]:
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
        "deviation_pct": round((l["total_monthly_cost"] - l["region_avg_rent"]) / l["region_avg_rent"] * 100, 1)
                        if l.get("total_monthly_cost") and l.get("region_avg_rent") else None,
    } for l in listings if l.get("total_monthly_cost") and l.get("region_avg_rent")]

    status_progress = query_all("""SELECT status, COUNT(*) AS value FROM listing_status GROUP BY status""")

    price_history = query_all("""SELECT l.title, l.id, h.total_monthly_cost, h.checked_at
        FROM listing_price_history h JOIN rental_listings l ON h.listing_id=l.id
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


@app.route("/api/listings")
def api_listings():
    args = request.args
    sql = """SELECT l.*, s.total_score, s.score_reason, s.commute_resolved,
             s.commute_minutes AS score_commute_minutes,
             st.status AS fav_status
             FROM rental_listings l
             LEFT JOIN listing_scores s ON s.listing_id=l.id
             LEFT JOIN listing_status st ON st.listing_id=l.id
             WHERE l.is_active=1"""
    clauses = []
    params = []
    if args.get("max_total_cost"):
        clauses.append("l.total_monthly_cost <= ?")
        params.append(int(args["max_total_cost"]))
    if args.get("min_area"):
        clauses.append("l.area_m2 >= ?")
        params.append(float(args["min_area"]))
    if args.get("min_floor"):
        clauses.append("l.floor >= ?")
        params.append(int(args["min_floor"]))
    if args.get("pet_allowed") == "1":
        clauses.append("l.pet_allowed = 1")
    if args.get("max_walk_minutes"):
        clauses.append("l.walk_minutes <= ?")
        params.append(int(args["max_walk_minutes"]))
    if args.get("max_building_age"):
        clauses.append("l.building_age <= ?")
        params.append(int(args["max_building_age"]))
    if args.get("layout"):
        layouts = args["layout"].split(",")
        clauses.append("l.layout IN (%s)" % ",".join("?" * len(layouts)))
        params.extend(layouts)
    if args.get("platform"):
        plats = args["platform"].split(",")
        clauses.append("l.platform IN (%s)" % ",".join("?" * len(plats)))
        params.extend(plats)
    if args.get("ward"):
        wards = args["ward"].split(",")
        clauses.append("l.ward IN (%s)" % ",".join("?" * len(wards)))
        params.extend(wards)
    if args.get("min_score"):
        clauses.append("s.total_score >= ?")
        params.append(int(args["min_score"]))
    if args.get("status"):
        clauses.append("st.status = ?")
        params.append(args["status"])
    if clauses:
        sql += " AND " + " AND ".join(clauses)

    sort_map = {
        "score_desc": "s.total_score DESC",
        "price_asc": "l.total_monthly_cost ASC",
        "area_desc": "l.area_m2 DESC",
        "walk_asc": "l.walk_minutes ASC",
        "age_asc": "l.building_age ASC",
        "newest": "l.first_seen_at DESC",
        "price_per_m2_asc": "l.price_per_m2 ASC",
        "initial_cost_asc": "l.initial_cost_estimate ASC",
    }
    sql += " ORDER BY " + sort_map.get(args.get("sort", "score_desc"), sort_map["score_desc"])
    return jsonify(query_all(sql, params))


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


@app.route("/api/rankings")
def api_rankings():
    limit = int(request.args.get("limit", 20))
    min_score = request.args.get("min_score")
    sql = """SELECT l.id, l.title, l.platform, l.ward, l.total_monthly_cost,
        l.area_m2, l.layout, l.floor, l.pet_allowed, l.detail_url,
        s.total_score, s.score_reason
        FROM listing_scores s JOIN rental_listings l ON s.listing_id=l.id
        WHERE l.is_active=1"""
    params = []
    if min_score:
        sql += " AND s.total_score >= ?"
        params.append(int(min_score))
    sql += " ORDER BY s.total_score DESC LIMIT ?"
    params.append(limit)
    return jsonify(query_all(sql, params))


@app.route("/api/status", methods=["GET", "POST"])
def api_status():
    if request.method == "GET":
        return jsonify(query_all("""SELECT st.*, l.title, l.platform, l.ward,
            l.total_monthly_cost, l.area_m2, l.layout, l.detail_url, s.total_score
            FROM listing_status st
            JOIN rental_listings l ON st.listing_id=l.id
            LEFT JOIN listing_scores s ON s.listing_id=l.id
            ORDER BY st.updated_at DESC"""))
    data = request.json
    sid = execute("""INSERT INTO listing_status
        (listing_id, status, priority, memo, contacted)
        VALUES (?,?,?,?,?)""",
        (data["listing_id"], data.get("status"), data.get("priority"),
         data.get("memo"), data.get("contacted", 0)))
    return jsonify({"id": sid}), 201


@app.route("/api/status/<int:sid>", methods=["PUT", "DELETE"])
def api_status_modify(sid):
    if request.method == "DELETE":
        execute("DELETE FROM listing_status WHERE id=?", (sid,))
        return jsonify({"ok": True})
    data = request.json or {}
    allowed = ["status", "priority", "memo", "contacted", "viewing_date", "decision"]
    fields = [k for k in allowed if k in data]
    if not fields:
        return jsonify({"ok": True})
    set_clause = ", ".join(f"{k}=?" for k in fields) + ", updated_at=CURRENT_TIMESTAMP"
    params = [data[k] for k in fields] + [sid]
    execute(f"UPDATE listing_status SET {set_clause} WHERE id=?", params)
    return jsonify({"ok": True})


@app.route("/api/compare")
def api_compare():
    ids = request.args.get("ids", "")
    id_list = [int(x) for x in ids.split(",") if x]
    if not id_list:
        return jsonify([])
    placeholders = ",".join("?" * len(id_list))
    rows = query_all(f"""SELECT l.*, s.total_score, s.score_reason, s.commute_resolved,
        s.budget_score, s.area_score, s.commute_score, s.floor_score, s.pet_score,
        s.station_score, s.age_score, s.initial_cost_score
        FROM rental_listings l LEFT JOIN listing_scores s ON s.listing_id=l.id
        WHERE l.id IN ({placeholders})""", id_list)
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


@app.route("/api/import/csv", methods=["POST"])
def api_import_csv():
    return jsonify({"total_rows": 0, "inserted_count": 0, "updated_count": 0,
                    "duplicate_count": 0, "error_count": 0, "message": "csv import optional"})


@app.route("/api/import/detail", methods=["POST"])
def api_import_detail():
    """粘贴单个房源详情页 URL,自动解析入库 + 评分。支持4平台。"""
    from scrapers.base import fetch_html
    from scripts.run_scrape import normalize, upsert_listing
    from scripts.recalculate_scores import recalculate
    from db_helper import get_conn

    data = request.json or {}
    url = data.get("url", "").strip()
    if not url:
        return jsonify({"error": "URL is required"}), 400

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

    conn = get_conn()
    prefs = query_one("SELECT * FROM user_preferences WHERE id=1")
    status, listing_id = upsert_listing(conn, normalize(raw, prefs))
    conn.commit()
    conn.close()

    _score_single(listing_id)

    try:
        from scrapers.machimusubi import get_station_review
        if raw.nearest_station:
            get_station_review(raw.nearest_station)
    except Exception:
        pass

    return jsonify({
        "status": status,
        "id": listing_id,
        "title": raw.title,
        "message": f"「{raw.title}」を{'追加' if status == 'inserted' else '更新'}しました"
    })


@app.route("/api/listings/<int:lid>/refresh", methods=["POST"])
def api_listing_refresh(lid):
    """重新抓取某房源(更新价格,写历史),重算评分。"""
    from scrapers.base import fetch_html
    from scripts.run_scrape import normalize, upsert_listing
    from scripts.recalculate_scores import recalculate
    from db_helper import get_conn

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

    conn = get_conn()
    prefs = query_one("SELECT * FROM user_preferences WHERE id=1")
    status, _ = upsert_listing(conn, normalize(raw, prefs))
    conn.commit()
    conn.close()

    _score_single(lid)

    new_listing = query_one("SELECT total_monthly_cost FROM rental_listings WHERE id=?", (lid,))
    new_cost = new_listing["total_monthly_cost"] if new_listing else None
    price_changed = old_cost != new_cost

    return jsonify({
        "ok": True,
        "title": raw.title,
        "old_cost": old_cost,
        "new_cost": new_cost,
        "price_changed": price_changed,
        "message": f"「{raw.title}」を更新しました" + (f" 価格変動: {old_cost}→{new_cost}円" if price_changed else " 価格変動なし"),
    })


@app.route("/api/scrape", methods=["POST"])
def api_scrape():
    from scripts.run_scrape import run_scrape
    data = request.json or {}
    source_ids = data.get("source_ids")
    run_scrape(source_ids)
    log = query_all("SELECT * FROM import_logs ORDER BY id DESC LIMIT 1")
    return jsonify(log[0] if log else {})


@app.route("/api/sources")
def api_sources():
    return jsonify(query_all("SELECT * FROM source_configs ORDER BY id"))


@app.route("/api/sources", methods=["POST"])
def api_source_create():
    data = request.json
    sid = execute("INSERT INTO source_configs (name, platform, source_url, max_pages) VALUES (?,?,?,?)",
                  (data["name"], data["platform"], data["source_url"], data.get("max_pages", 2)))
    return jsonify({"id": sid}), 201


@app.route("/api/sources/<int:sid>", methods=["PUT", "DELETE"])
def api_source_modify(sid):
    if request.method == "DELETE":
        execute("DELETE FROM source_configs WHERE id=?", (sid,))
        return jsonify({"ok": True})
    data = request.json
    execute("UPDATE source_configs SET name=?, platform=?, source_url=?, max_pages=?, updated_at=CURRENT_TIMESTAMP WHERE id=?",
            (data["name"], data["platform"], data["source_url"], data.get("max_pages", 2), sid))
    return jsonify({"ok": True})


@app.route("/api/preferences")
def api_preferences():
    return jsonify(query_one("SELECT * FROM user_preferences WHERE id=1"))


@app.route("/api/preferences", methods=["PUT"])
def api_preferences_update():
    data = request.json
    fields = ["max_total_monthly_cost", "min_area_m2", "ideal_area_m2", "min_floor",
              "require_pet_allowed", "max_walk_minutes", "ideal_walk_minutes",
              "max_building_age", "target_station", "budget_weight", "area_weight",
              "commute_weight", "floor_weight", "pet_weight", "station_weight",
              "age_weight", "initial_cost_weight", "broker_fee_rate",
              "prepaid_rent_months", "misc_cost"]
    present = [f for f in fields if f in data]
    if present:
        sets = ", ".join(f"{f}=?" for f in present)
        params = [data[f] for f in present] + ["1"]
        execute(f"UPDATE user_preferences SET {sets}, updated_at=CURRENT_TIMESTAMP WHERE id=?", params)

    if any(f in data for f in ("broker_fee_rate", "prepaid_rent_months", "misc_cost")):
        _refresh_initial_costs()
    return jsonify({"ok": True})


@app.route("/api/scores/recalculate", methods=["POST"])
def api_recalculate():
    from scripts.recalculate_scores import recalculate
    recalculate()
    return jsonify({"ok": True})


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", "5000")),
            debug=os.getenv("FLASK_DEBUG") == "1")