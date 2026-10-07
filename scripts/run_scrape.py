import sqlite3
import sys
import os
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import DB_PATH
from scrapers.base import fetch_html
from scrapers.suumo import parse_suumo
from scrapers.homes import parse_homes
from scrapers.athome import parse_athome
from scrapers.models import RawListing
from core.cleaning import (
    parse_money, parse_deposit_key_money, parse_area, parse_walk_minutes, parse_station_walk,
    parse_floor, parse_building_age, parse_pet_allowed, parse_features,
)
from core.address import parse_address
from core.initial_cost import estimate_initial_cost
from core.dedup import generate_listing_hash

PARSERS = {
    "SUUMO": parse_suumo,
    "HOMES": parse_homes,
    "athome": parse_athome,
}


def normalize(raw: RawListing, prefs=None):
    """RawListing -> rental_listings 列 dict。

    prefs を渡すと初期費用の係数(仲介手数料率/前家賃/雑費)にユーザー設定を使う。
    渡さない場合は config の既定値。以前は常に既定値で保存していたため、
    設定を変えるとレポートのグラフ(ユーザー係数)と保存値がずれていた。
    """
    rent = parse_money(raw.rent_raw)
    mgmt = parse_money(raw.management_fee_raw) if raw.management_fee_raw else None
    total = rent + mgmt if rent is not None and mgmt is not None else None
    deposit = parse_deposit_key_money(raw.deposit_raw, rent)
    key_money = parse_deposit_key_money(raw.key_money_raw, rent)
    area = parse_area(raw.area_raw)
    floor, total_floors = parse_floor(raw.floor_raw)
    age = parse_building_age(raw.age_raw)
    access = parse_station_walk(raw.walk_raw) or parse_station_walk(raw.nearest_station)
    walk = access[1] if access else parse_walk_minutes(raw.walk_raw)
    addr = parse_address(raw.address_raw)
    feats = parse_features(raw.features_raw)
    if prefs:
        initial = estimate_initial_cost(
            rent, deposit, key_money,
            broker_fee_rate=prefs["broker_fee_rate"],
            prepaid_rent_months=prefs["prepaid_rent_months"],
            misc_cost=prefs["misc_cost"])
    else:
        initial = estimate_initial_cost(rent, deposit, key_money)
    price_per_m2 = (total / area) if (total and area) else None
    h = generate_listing_hash(addr.get("address"), raw.title, raw.layout, area, floor, rent)
    return {
        "platform": raw.platform,
        "detail_url": raw.detail_url,
        "title": raw.title,
        "rent": rent,
        "management_fee": mgmt,
        "total_monthly_cost": total,
        "deposit": deposit,
        "key_money": key_money,
        "initial_cost_estimate": initial,
        "layout": raw.layout,
        "area_m2": area,
        "price_per_m2": price_per_m2,
        "floor": floor,
        "total_floors": total_floors,
        "building_age": age,
        "walk_minutes": walk,
        "nearest_station": access[0] if access else raw.nearest_station,
        "address": raw.address_raw,
        "prefecture": addr["prefecture"],
        "city": addr["city"],
        "ward": addr["ward"],
        "pet_allowed": parse_pet_allowed(" ".join(raw.features_raw)),
        "bath_toilet_separate": feats["bath_toilet_separate"],
        "auto_lock": feats["auto_lock"],
        "delivery_box": feats["delivery_box"],
        "south_facing": feats["south_facing"],
        "aircon": feats["aircon"],
        "two_person_allowed": feats["two_person_allowed"],
        "image_url": raw.image_url,
        "listing_hash": h,
    }


def upsert_listing(conn, data):
    """Atomically refresh all parsed fields and record observed price changes."""
    if not conn.in_transaction:
        conn.execute("BEGIN IMMEDIATE")
    cur = conn.execute("SELECT * FROM rental_listings WHERE detail_url=?", (data["detail_url"],))
    values = cur.fetchone()
    old = dict(zip([c[0] for c in cur.description], values)) if values else None
    now = datetime.now().isoformat()
    if old:
        listing_id = old["id"]
        # A legacy listing may not yet have a trustworthy initial observation.
        observed = conn.execute("SELECT 1 FROM listing_price_history WHERE listing_id=? "
                                "AND observation_kind='observed' LIMIT 1", (listing_id,)).fetchone()
        if not observed and old.get("last_seen_at"):
            conn.execute("""INSERT INTO listing_price_history
                (listing_id,rent,management_fee,total_monthly_cost,checked_at,observation_kind)
                VALUES (?,?,?,?,?,'observed')""",
                (listing_id, old["rent"], old["management_fee"], old["total_monthly_cost"], old["last_seen_at"]))
        columns = [key for key in data if key != "detail_url"]
        sets = ", ".join(f"{key}=?" for key in columns)
        conn.execute(f"UPDATE rental_listings SET {sets}, is_active=1, last_seen_at=?, updated_at=? WHERE id=?",
                     [data[key] for key in columns] + [now, now, listing_id])
        status = "updated"
    else:
        duplicate = conn.execute("SELECT 1 FROM rental_listings WHERE listing_hash=?", (data["listing_hash"],)).fetchone()
        columns = list(data) + ["duplicate_group_id", "first_seen_at", "last_seen_at"]
        params = list(data.values()) + [data["listing_hash"][:8] if duplicate else None, now, now]
        cur = conn.execute(f"INSERT INTO rental_listings ({','.join(columns)}) "
                           f"VALUES ({','.join('?' for _ in columns)})", params)
        listing_id, status = cur.lastrowid, "inserted"
    previous = conn.execute("SELECT rent,management_fee,total_monthly_cost FROM listing_price_history "
                            "WHERE listing_id=? AND observation_kind='observed' ORDER BY id DESC LIMIT 1",
                            (listing_id,)).fetchone()
    price = (data["rent"], data["management_fee"], data["total_monthly_cost"])
    if previous is None or tuple(previous) != price:
        conn.execute("""INSERT INTO listing_price_history
            (listing_id,rent,management_fee,total_monthly_cost,checked_at,observation_kind)
            VALUES (?,?,?,?,?,'observed')""", (listing_id, *price, now))
    return status, listing_id


def run_scrape(source_ids=None):
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    if source_ids:
        placeholders = ",".join("?" * len(source_ids))
        sources = conn.execute(f"SELECT * FROM source_configs WHERE id IN ({placeholders}) AND enabled=1",
                               source_ids).fetchall()
    else:
        sources = conn.execute("SELECT * FROM source_configs WHERE enabled=1").fetchall()

    total_inserted = total_updated = total_dup = total_error = 0
    for src in sources:
        parser = PARSERS.get(src["platform"])
        if not parser:
            continue
        html = fetch_html(src["source_url"])
        if html is None:
            conn.execute("UPDATE source_configs SET last_status=?, updated_at=? WHERE id=?",
                         ("robots_disallowed", datetime.now().isoformat(), src["id"]))
            conn.execute("""INSERT INTO import_logs
                (import_type, source_name, total_rows, inserted_count, updated_count,
                 duplicate_count, error_count, message)
                VALUES (?,?,?,?,?,?,?,?)""",
                ("scrape", src["name"], 0, 0, 0, 0, 0, "robots_disallowed"))
            conn.commit()
            continue
        try:
            raws = parser(html, src["source_url"])
        except Exception:
            conn.execute("UPDATE source_configs SET last_status=?, updated_at=? WHERE id=?",
                         ("error", datetime.now().isoformat(), src["id"]))
            conn.execute("""INSERT INTO import_logs
                (import_type, source_name, total_rows, inserted_count, updated_count,
                 duplicate_count, error_count, message)
                VALUES (?,?,?,?,?,?,?,?)""",
                ("scrape", src["name"], 0, 0, 0, 0, 1, "parse_error"))
            conn.commit()
            continue
        ins = upd = dup = err = 0
        for raw in raws:
            try:
                data = normalize(raw)
                status, _ = upsert_listing(conn, data)
                if status == "inserted":
                    ins += 1
                else:
                    upd += 1
            except Exception:
                err += 1
        conn.execute("UPDATE source_configs SET last_scraped_at=?, last_status=? WHERE id=?",
                     (datetime.now().isoformat(), "ok", src["id"]))
        conn.execute("""INSERT INTO import_logs
            (import_type, source_name, total_rows, inserted_count, updated_count,
             duplicate_count, error_count, message)
            VALUES (?,?,?,?,?,?,?,?)""",
            ("scrape", src["name"], len(raws), ins, upd, dup, err, ""))
        total_inserted += ins
        total_updated += upd
        total_dup += dup
        total_error += err
    conn.commit()
    conn.close()
    print(f"Scrape done: inserted={total_inserted} updated={total_updated} "
          f"duplicate={total_dup} error={total_error}")


if __name__ == "__main__":
    run_scrape()
