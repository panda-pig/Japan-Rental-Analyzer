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
    parse_money, parse_deposit_key_money, parse_area, parse_walk_minutes,
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


def normalize(raw: RawListing):
    """RawListing -> rental_listings 列 dict。"""
    rent = parse_money(raw.rent_raw)
    mgmt = parse_money(raw.management_fee_raw) if raw.management_fee_raw else None
    total = (rent or 0) + (mgmt or 0) if rent else None
    deposit = parse_deposit_key_money(raw.deposit_raw, rent)
    key_money = parse_deposit_key_money(raw.key_money_raw, rent)
    area = parse_area(raw.area_raw)
    floor, total_floors = parse_floor(raw.floor_raw)
    age = parse_building_age(raw.age_raw)
    walk = parse_walk_minutes(raw.walk_raw)
    addr = parse_address(raw.address_raw)
    feats = parse_features(raw.features_raw)
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
        "nearest_station": raw.nearest_station,
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
    """detail_url 存在则更新,否则插入。返回 ('inserted'|'updated', id)"""
    cur = conn.execute("SELECT id, rent, total_monthly_cost FROM rental_listings WHERE detail_url=?",
                       (data["detail_url"],))
    row = cur.fetchone()
    now = datetime.now().isoformat()
    if row:
        listing_id, old_rent, old_total = row
        conn.execute("""UPDATE rental_listings SET rent=?, management_fee=?, total_monthly_cost=?,
            deposit=?, key_money=?, initial_cost_estimate=?, area_m2=?, price_per_m2=?,
            floor=?, building_age=?, walk_minutes=?, last_seen_at=?, updated_at=?
            WHERE id=?""",
            (data["rent"], data["management_fee"], data["total_monthly_cost"],
             data["deposit"], data["key_money"], data["initial_cost_estimate"],
             data["area_m2"], data["price_per_m2"], data["floor"], data["building_age"],
             data["walk_minutes"], now, now, listing_id))
        if old_total != data["total_monthly_cost"]:
            conn.execute("""INSERT INTO listing_price_history
                (listing_id, rent, management_fee, total_monthly_cost, checked_at)
                VALUES (?,?,?,?,?)""",
                (listing_id, old_rent, None, old_total, now))
        return ("updated", listing_id)
    cur = conn.execute("SELECT listing_hash FROM rental_listings WHERE listing_hash=?",
                       (data["listing_hash"],))
    dup_group = None
    if cur.fetchone():
        dup_group = data["listing_hash"][:8]
    cur = conn.execute("""INSERT INTO rental_listings
        (platform, detail_url, title, rent, management_fee, total_monthly_cost,
         deposit, key_money, initial_cost_estimate, layout, area_m2, price_per_m2,
         floor, total_floors, building_age, walk_minutes, nearest_station,
         address, prefecture, city, ward, pet_allowed,
         bath_toilet_separate, auto_lock, delivery_box, south_facing, aircon,
         two_person_allowed, image_url, listing_hash, duplicate_group_id,
         first_seen_at, last_seen_at)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (data["platform"], data["detail_url"], data["title"], data["rent"],
         data["management_fee"], data["total_monthly_cost"], data["deposit"],
         data["key_money"], data["initial_cost_estimate"], data["layout"],
         data["area_m2"], data["price_per_m2"], data["floor"], data["total_floors"],
         data["building_age"], data["walk_minutes"], data["nearest_station"],
         data["address"], data["prefecture"], data["city"], data["ward"],
         data["pet_allowed"], data["bath_toilet_separate"], data["auto_lock"],
         data["delivery_box"], data["south_facing"], data["aircon"],
         data["two_person_allowed"], data["image_url"], data["listing_hash"],
         dup_group, now, now))
    return ("inserted", cur.lastrowid)


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