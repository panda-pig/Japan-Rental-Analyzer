from flask import Flask, jsonify, request, render_template
from db_helper import query_all, query_one, execute

app = Flask(__name__)


# ===== Pages =====

@app.route("/")
def index():
    return render_template("index.html")


@app.route("/listings")
def page_listings():
    return render_template("listings.html")


@app.route("/rankings")
def page_rankings():
    return render_template("rankings.html")


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


# ===== Dashboard API =====

@app.route("/api/dashboard")
def api_dashboard():
    total = query_one("SELECT COUNT(*) AS c FROM rental_listings WHERE is_active=1")["c"]
    pref = query_one("SELECT * FROM user_preferences WHERE id=1")
    budget_match = query_one(
        "SELECT COUNT(*) AS c FROM rental_listings WHERE is_active=1 AND total_monthly_cost <= ?",
        (pref["max_total_monthly_cost"],))["c"]
    floor_2plus = query_one(
        "SELECT COUNT(*) AS c FROM rental_listings WHERE is_active=1 AND floor >= 2")["c"]
    pet_count = query_one(
        "SELECT COUNT(*) AS c FROM rental_listings WHERE is_active=1 AND pet_allowed=1")["c"]
    avg_cost = query_one(
        "SELECT AVG(total_monthly_cost) AS a FROM rental_listings WHERE is_active=1")["a"] or 0
    avg_area = query_one(
        "SELECT AVG(area_m2) AS a FROM rental_listings WHERE is_active=1")["a"] or 0
    avg_score = query_one(
        "SELECT AVG(s.total_score) AS a FROM listing_scores s JOIN rental_listings l ON s.listing_id=l.id WHERE l.is_active=1")["a"] or 0
    new_count = query_one(
        "SELECT COUNT(*) AS c FROM rental_listings WHERE is_active=1 AND first_seen_at >= date('now','-7 days')")["c"]
    price_drop = query_one("""SELECT COUNT(*) AS c FROM listing_price_history h
        JOIN rental_listings l ON h.listing_id=l.id
        WHERE l.is_active=1 AND l.total_monthly_cost < h.total_monthly_cost""")["c"]
    fav_count = query_one("SELECT COUNT(*) AS c FROM listing_status")["c"]

    area_rent = query_all(
        "SELECT ward AS name, AVG(total_monthly_cost) AS value FROM rental_listings WHERE is_active=1 GROUP BY ward ORDER BY value DESC")
    rent_dist = query_all("""SELECT
        CASE WHEN total_monthly_cost < 80000 THEN '8万以下'
             WHEN total_monthly_cost < 100000 THEN '8~10万'
             WHEN total_monthly_cost < 120000 THEN '10~12万'
             WHEN total_monthly_cost < 140000 THEN '12~14万'
             WHEN total_monthly_cost < 160000 THEN '14~16万'
             ELSE '16万以上' END AS name,
        COUNT(*) AS value FROM rental_listings WHERE is_active=1 GROUP BY name""")
    area_dist = query_all("""SELECT
        CASE WHEN area_m2 < 25 THEN '25㎡未満'
             WHEN area_m2 < 35 THEN '25~35㎡'
             WHEN area_m2 < 45 THEN '35~45㎡'
             ELSE '45㎡以上' END AS name,
        COUNT(*) AS value FROM rental_listings WHERE is_active=1 GROUP BY name""")
    scatter = query_all(
        "SELECT area_m2 AS x, total_monthly_cost AS y, title, ward, layout FROM rental_listings WHERE is_active=1")
    top10 = query_all("""SELECT l.title, s.total_score FROM listing_scores s
        JOIN rental_listings l ON s.listing_id=l.id
        WHERE l.is_active=1 ORDER BY s.total_score DESC LIMIT 10""")
    layout_dist = query_all(
        "SELECT layout AS name, COUNT(*) AS value FROM rental_listings WHERE is_active=1 GROUP BY layout")
    platform_dist = query_all(
        "SELECT platform AS name, COUNT(*) AS value FROM rental_listings WHERE is_active=1 GROUP BY platform")
    floor_dist = query_all("""SELECT
        CASE WHEN floor <= 1 THEN '1階' WHEN floor = 2 THEN '2階' WHEN floor = 3 THEN '3階'
             ELSE '4階以上' END AS name,
        COUNT(*) AS value FROM rental_listings WHERE is_active=1 GROUP BY name""")
    age_dist = query_all("""SELECT
        CASE WHEN building_age <= 5 THEN '0~5年' WHEN building_age <= 10 THEN '6~10年'
             WHEN building_age <= 20 THEN '11~20年' ELSE '21年以上' END AS name,
        COUNT(*) AS value FROM rental_listings WHERE is_active=1 GROUP BY name""")
    status_dist = query_all(
        "SELECT status AS name, COUNT(*) AS value FROM listing_status GROUP BY status")

    return jsonify({
        "total_listings": total, "budget_match_count": budget_match,
        "floor_2plus_count": floor_2plus, "pet_allowed_count": pet_count,
        "average_total_cost": int(avg_cost), "average_area": round(avg_area, 1),
        "average_score": round(avg_score, 1), "new_listing_count": new_count,
        "price_drop_count": price_drop, "favorite_count": fav_count,
        "area_rent_data": area_rent, "rent_distribution": rent_dist,
        "area_distribution": area_dist, "scatter_data": scatter,
        "top_score_listings": top10, "layout_distribution": layout_dist,
        "platform_distribution": platform_dist, "floor_distribution": floor_dist,
        "age_distribution": age_dist, "status_distribution": status_dist,
        "price_history_chart": [],
    })


# ===== Listings API =====

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


@app.route("/api/listings/<int:lid>")
def api_listing_detail(lid):
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


# ===== Status / Favorites API =====

@app.route("/api/status", methods=["GET", "POST"])
def api_status():
    if request.method == "GET":
        return jsonify(query_all("""SELECT st.*, l.title, l.platform, l.ward,
            l.total_monthly_cost, l.detail_url FROM listing_status st
            JOIN rental_listings l ON st.listing_id=l.id ORDER BY st.updated_at DESC"""))
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
    data = request.json
    execute("""UPDATE listing_status SET status=?, priority=?, memo=?, contacted=?,
        viewing_date=?, decision=?, updated_at=CURRENT_TIMESTAMP WHERE id=?""",
        (data.get("status"), data.get("priority"), data.get("memo"),
         data.get("contacted", 0), data.get("viewing_date"), data.get("decision"), sid))
    return jsonify({"ok": True})


# ===== Compare API =====

@app.route("/api/compare")
def api_compare():
    ids = request.args.get("ids", "")
    id_list = [int(x) for x in ids.split(",") if x]
    if not id_list:
        return jsonify([])
    placeholders = ",".join("?" * len(id_list))
    rows = query_all(f"""SELECT l.*, s.total_score, s.score_reason, s.commute_resolved
        FROM rental_listings l LEFT JOIN listing_scores s ON s.listing_id=l.id
        WHERE l.id IN ({placeholders})""", id_list)
    return jsonify(rows)


# ===== Import / Scrape API =====

@app.route("/api/import/csv", methods=["POST"])
def api_import_csv():
    return jsonify({"total_rows": 0, "inserted_count": 0, "updated_count": 0,
                    "duplicate_count": 0, "error_count": 0, "message": "csv import optional"})


@app.route("/api/scrape", methods=["POST"])
def api_scrape():
    from scripts.run_scrape import run_scrape
    data = request.json or {}
    source_ids = data.get("source_ids")
    run_scrape(source_ids)
    log = query_all("SELECT * FROM import_logs ORDER BY id DESC LIMIT 1")
    return jsonify(log[0] if log else {})


# ===== Sources API =====

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


# ===== Preferences API =====

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
    sets = ", ".join(f"{f}=?" for f in fields)
    params = [data.get(f) for f in fields]
    params.append("1")
    execute(f"UPDATE user_preferences SET {sets}, updated_at=CURRENT_TIMESTAMP WHERE id=?", params)
    return jsonify({"ok": True})


@app.route("/api/scores/recalculate", methods=["POST"])
def api_recalculate():
    from scripts.recalculate_scores import recalculate
    recalculate()
    return jsonify({"ok": True})


if __name__ == "__main__":
    app.run(debug=os.getenv("FLASK_DEBUG") == "1")