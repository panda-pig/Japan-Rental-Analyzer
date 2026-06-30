import sqlite3
import sys
import os
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import DB_PATH
from core.scoring import calculate_scores, ScoreInput, Weights
from core.commute import get_commute_minutes


def recalculate():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    pref = conn.execute("SELECT * FROM user_preferences WHERE id=1").fetchone()
    if not pref:
        print("No user_preferences found")
        return
    w = Weights(
        budget=pref["budget_weight"], area=pref["area_weight"],
        commute=pref["commute_weight"], floor=pref["floor_weight"],
        pet=pref["pet_weight"], station=pref["station_weight"],
        age=pref["age_weight"], initial_cost=pref["initial_cost_weight"],
    )
    listings = conn.execute("SELECT * FROM rental_listings WHERE is_active=1").fetchall()
    for l in listings:
        commute_minutes = None
        if pref["target_station"] and l["nearest_station"]:
            commute_minutes = get_commute_minutes(l["nearest_station"], pref["target_station"])
            if commute_minutes is not None:
                conn.execute("UPDATE rental_listings SET commute_minutes=?, commute_target_station=? WHERE id=?",
                             (commute_minutes, pref["target_station"], l["id"]))
        inp = ScoreInput(
            total_monthly_cost=l["total_monthly_cost"], area_m2=l["area_m2"],
            floor=l["floor"], pet_allowed=l["pet_allowed"],
            walk_minutes=l["walk_minutes"], building_age=l["building_age"],
            deposit=l["deposit"], key_money=l["key_money"], rent=l["rent"],
        )
        r = calculate_scores(inp, w,
            max_cost=pref["max_total_monthly_cost"], ideal_area=pref["ideal_area_m2"],
            min_floor=pref["min_floor"], max_walk=pref["max_walk_minutes"],
            max_age=pref["max_building_age"],
            broker_rate=pref["broker_fee_rate"], prepaid=pref["prepaid_rent_months"],
            misc=pref["misc_cost"], commute_minutes=commute_minutes)
        conn.execute("DELETE FROM listing_scores WHERE listing_id=?", (l["id"],))
        conn.execute("""INSERT INTO listing_scores
            (listing_id, budget_score, area_score, commute_score, floor_score,
             pet_score, station_score, age_score, initial_cost_score, feature_score,
             total_score, score_reason, commute_minutes, commute_resolved, calculated_at)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (l["id"], r.budget_score, r.area_score, r.commute_score, r.floor_score,
             r.pet_score, r.station_score, r.age_score, r.initial_cost_score,
             r.feature_score, r.total_score, r.score_reason,
             commute_minutes, r.commute_resolved, datetime.now().isoformat()))
    conn.commit()
    conn.close()
    print(f"Recalculated scores for {len(listings)} listings")


if __name__ == "__main__":
    recalculate()