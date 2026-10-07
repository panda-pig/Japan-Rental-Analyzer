"""One scoring path for imports, refreshes and full recalculation."""
import time
from dataclasses import asdict
from datetime import datetime

from core import commute
from core.initial_cost import estimate_initial_cost
from core.scoring import ScoreInput, Weights, calculate_scores
from db_helper import query_one, query_all, transaction
from scrapers.machimusubi import extract_station


def commute_minutes(origin, destination, resolve=True):
    if not origin or not destination:
        return None
    cached = query_one("SELECT minutes FROM commute_cache WHERE origin=? AND destination=? AND expires_at>?",
                       (origin, destination, time.time()))
    if cached:
        return cached["minutes"]
    if not resolve:
        return None
    minutes = commute.get_commute_minutes(origin, destination)
    with transaction() as conn:
        conn.execute("""INSERT INTO commute_cache(origin,destination,minutes,expires_at)
            VALUES (?,?,?,?) ON CONFLICT(origin,destination) DO UPDATE SET
            minutes=excluded.minutes, expires_at=excluded.expires_at""",
            (origin, destination, minutes, time.time() + (86400 if minutes is not None else 300)))
    return minutes


def score_listing(listing_id, resolve_commute=True):
    listing = query_one("SELECT * FROM rental_listings WHERE id=? AND is_active=1", (listing_id,))
    pref = query_one("SELECT * FROM user_preferences WHERE id=1")
    if not listing or not pref:
        return False
    origin = extract_station(listing["nearest_station"])
    destination = pref["target_station"]
    minutes = commute_minutes(origin, destination, resolve_commute)
    # External I/O has finished before acquiring the write lock. Re-read data so
    # a concurrent refresh/settings change cannot be overwritten by an old score.
    with transaction(immediate=True) as conn:
        current = conn.execute("SELECT * FROM rental_listings WHERE id=? AND is_active=1", (listing_id,)).fetchone()
        prefs = conn.execute("SELECT * FROM user_preferences WHERE id=1").fetchone()
        if not current or not prefs:
            return False
        if extract_station(current["nearest_station"]) != origin or prefs["target_station"] != destination:
            # The caller queues a new pass after a refresh/preferences change.
            # This stale lookup must not erase a score already saved for it.
            return False
        weights = Weights(**{name: prefs[name + "_weight"] for name in Weights.__dataclass_fields__})
        inp = ScoreInput(**{name: current[name] for name in ScoreInput.__dataclass_fields__})
        result = calculate_scores(inp, weights,
            max_cost=prefs["max_total_monthly_cost"], ideal_area=prefs["ideal_area_m2"],
            min_floor=prefs["min_floor"], max_walk=prefs["max_walk_minutes"], max_age=prefs["max_building_age"],
            broker_rate=prefs["broker_fee_rate"], prepaid=prefs["prepaid_rent_months"], misc=prefs["misc_cost"],
            commute_minutes=minutes, min_area=prefs["min_area_m2"])
        initial = estimate_initial_cost(current["rent"], current["deposit"], current["key_money"],
            broker_fee_rate=prefs["broker_fee_rate"], prepaid_rent_months=prefs["prepaid_rent_months"], misc_cost=prefs["misc_cost"])
        conn.execute("UPDATE rental_listings SET initial_cost_estimate=?, commute_minutes=?, "
                     "commute_target_station=? WHERE id=?", (initial, minutes, prefs["target_station"], listing_id))
        fields = {**asdict(result), "commute_minutes": minutes, "calculated_at": datetime.now().isoformat()}
        names = list(fields)
        conn.execute(f"INSERT INTO listing_scores(listing_id,{','.join(names)}) "
                     f"VALUES ({','.join('?' for _ in range(len(names)+1))}) "
                     "ON CONFLICT(listing_id) DO UPDATE SET " + ','.join(f"{n}=excluded.{n}" for n in names),
                     [listing_id, *fields.values()])
    return True


def recalculate(listing_ids=None, resolve_commute=True):
    if listing_ids is None:
        listing_ids = [r["id"] for r in query_all("SELECT id FROM rental_listings WHERE is_active=1")]
    return sum(score_listing(lid, resolve_commute) for lid in listing_ids)
