import os
import sqlite3
import subprocess
import sys
from datetime import datetime, timedelta
from pathlib import Path

import pytest

from core.cleaning import parse_deposit_key_money, parse_money
from core.initial_cost import estimate_initial_cost
from core.scoring import _initial_cost_score
from db_helper import query_all, query_one, execute, transaction
from scripts.init_db import init_db
from scripts.run_scrape import normalize, upsert_listing
from scrapers.models import RawListing
from services.scoring import score_listing


@pytest.fixture
def listing():
    raw = RawListing(platform="SUUMO", detail_url="https://suumo.jp/chintai/test/", title="Test",
                     rent_raw="12万円", management_fee_raw="0円", deposit_raw="なし", key_money_raw="なし",
                     area_raw="40㎡", layout="1LDK", floor_raw="3階", age_raw="築5年", walk_raw="徒歩5分",
                     address_raw="東京都中央区1-1", nearest_station="東京", features_raw=["ペット可"])
    with transaction() as conn:
        _, lid = upsert_listing(conn, normalize(raw))
    return lid, raw


@pytest.mark.parametrize("text,expected", [("0.5ヶ月", 50000), ("1.5か月", 150000),
    ("０．５カ月", 50000), ("0ヶ月", 0), ("2ケ月分", 200000), ("", None), (None, None), ("なし", 0),
    ("-", None), ("―", None)])
def test_fractional_deposit(text, expected):
    assert parse_deposit_key_money(text, 100000) == expected


def test_money_does_not_lose_yen_to_float_rounding():
    assert parse_money("16.4万円") == 164000
    assert parse_money("１．６４万円") == 16400


def test_walking_limit_can_be_lower_than_legacy_ideal(client):
    assert client.put('/api/preferences', json={'max_walk_minutes': 5}).status_code == 200
    assert client.get('/api/preferences').json['max_walk_minutes'] == 5


def test_missing_cost_is_not_zero_or_full_marks():
    assert _initial_cost_score(None, None, 100000) is None
    assert estimate_initial_cost(100000, None, 0) is None
    assert _initial_cost_score(0, 0, 100000) == 5


def test_app_starts_twice_without_network_or_api_keys(tmp_path):
    env = {**os.environ, "DB_PATH": str(tmp_path / "fresh.db")}
    code = "import requests; requests.get=lambda *a,**k: (_ for _ in ()).throw(AssertionError('network on startup')); import app"
    for _ in range(2):
        result = subprocess.run([sys.executable, "-c", code], env=env, capture_output=True, text=True, timeout=15)
        assert result.returncode == 0, result.stderr
    with sqlite3.connect(env["DB_PATH"]) as conn:
        assert conn.execute("SELECT count(*) FROM region_stats").fetchone()[0] == 56


def test_legacy_migration_preserves_notes_and_makes_backup(tmp_path):
    path = tmp_path / "legacy.db"
    with sqlite3.connect(path) as conn:
        conn.executescript((Path(__file__).parent / "fixtures/legacy_schema.sql").read_text())
        conn.execute("INSERT INTO rental_listings(id,detail_url) VALUES (1,'test')")
        conn.execute("INSERT INTO listing_status(listing_id,status,memo) VALUES (1,'気になる','first note')")
        conn.execute("INSERT INTO listing_status(listing_id,status,memo) VALUES (1,'内見済み','second note')")
        conn.execute("INSERT INTO listing_scores(listing_id,total_score) VALUES (1,20),(1,80)")
        conn.execute("INSERT INTO listing_price_history(listing_id,total_monthly_cost) VALUES (1,100000)")
    init_db(path)
    init_db(path)
    with sqlite3.connect(path) as conn:
        columns = {r[1] for r in conn.execute("PRAGMA table_info(region_stats)")}
        assert {"trade_price_per_m2", "hazard_level", "rent_source"} <= columns
        assert conn.execute("SELECT count(*) FROM listing_status").fetchone()[0] == 1
        status, memo = conn.execute("SELECT status,memo FROM listing_status").fetchone()
        assert status == "内見済み"
        assert "first note" in memo and "second note" in memo
        assert conn.execute("SELECT count(*) FROM migration_archive").fetchone()[0] == 4
        assert conn.execute("SELECT observation_kind FROM listing_price_history").fetchone()[0] == "legacy"
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute("INSERT INTO listing_status(listing_id) VALUES (1)")
    backups = list((tmp_path / "backups").glob("*.db"))
    assert len(backups) == 1
    with sqlite3.connect(backups[0]) as conn:
        assert conn.execute("SELECT count(*) FROM listing_status").fetchone()[0] == 2


def test_refresh_snapshots_and_properties(listing):
    lid, raw = listing
    for price in ("11万円", "10万円", "10万円"):
        raw.rent_raw = price
        raw.features_raw = ["ペット不可"]
        raw.layout = "2DK"
        with transaction() as conn:
            result, same_id = upsert_listing(conn, normalize(raw))
        assert same_id == lid and result == "updated"
    assert [r["total_monthly_cost"] for r in query_all("SELECT * FROM listing_price_history ORDER BY id")] == [120000, 110000, 100000]
    row = query_one("SELECT * FROM rental_listings WHERE id=?", (lid,))
    assert row["pet_allowed"] == 0 and row["layout"] == "2DK"


def test_repeated_favorite_is_idempotent(client, listing):
    lid, _ = listing
    one = client.post("/api/status", json={"listing_id": lid, "memo": "preserve me"})
    two = client.post("/api/status", json={"listing_id": lid})
    assert one.status_code == 201 and two.status_code == 200
    assert one.json["id"] == two.json["id"]
    assert query_one("SELECT memo FROM listing_status")["memo"] == "preserve me"
    assert len(client.get("/api/my-list").json["compare_rows"]) == 1


@pytest.mark.parametrize("method,path", [("post", "/api/status"), ("put", "/api/status/1"),
    ("delete", "/api/status/1"), ("post", "/api/import/detail"), ("post", "/api/listings/1/refresh"),
    ("put", "/api/preferences"), ("post", "/api/pool/clear"), ("post", "/api/scores/recalculate")])
def test_all_writes_require_configured_token(client, monkeypatch, method, path):
    import app
    monkeypatch.setattr(app, "ADMIN_TOKEN", "test-admin")
    response = getattr(client, method)(path, json={})
    assert response.status_code == 401


def test_valid_admin_token_can_save_and_html_status_is_rejected(client, monkeypatch, listing):
    import app
    monkeypatch.setattr(app, "ADMIN_TOKEN", "test-admin")
    headers = {"X-Admin-Token": "test-admin"}
    assert client.put("/api/preferences", json={"max_total_monthly_cost": 130000}, headers=headers).status_code == 200
    assert client.post("/api/status", json={"listing_id": listing[0], "status": "<b>test</b>"}, headers=headers).status_code == 400


@pytest.mark.parametrize("data", [{"max_total_monthly_cost": None}, {"max_total_monthly_cost": "bad"},
    {"max_total_monthly_cost": True}, {"broker_fee_rate": -1}, {"min_area_m2": 80, "ideal_area_m2": 40},
    {"target_station": []}, {"budget_weight": 1000}, {"unknown": 1}, [], None])
def test_invalid_preferences_do_not_persist(client, data):
    before = query_one("SELECT * FROM user_preferences WHERE id=1")
    response = client.put("/api/preferences", data=__import__('json').dumps(data), content_type="application/json")
    assert response.status_code == 400
    assert query_one("SELECT * FROM user_preferences WHERE id=1") == before


@pytest.mark.parametrize("ids", ["abc", "1,-1", "0", "1,2,3,4,5", "1,,2", "999999999999999999999999"])
def test_compare_rejects_invalid_ids(client, ids):
    assert client.get("/api/compare", query_string={"ids": ids}).status_code == 400


def test_commute_saved_consistently_and_cached(client, listing, monkeypatch):
    from core import commute
    calls = []
    monkeypatch.setattr(commute, "get_commute_minutes", lambda *args: calls.append(args) or 25)
    execute("UPDATE user_preferences SET target_station='品川' WHERE id=1")
    score_listing(listing[0])
    score_listing(listing[0])
    row = client.get("/api/my-list").json["compare_rows"][0]
    assert row["commute_resolved"] == 1 and row["commute_minutes"] == 25
    assert len(calls) == 1
    assert len(query_all("SELECT * FROM listing_scores")) == 1
    execute("UPDATE user_preferences SET target_station='' WHERE id=1")
    score_listing(listing[0])
    assert query_one("SELECT commute_minutes FROM rental_listings")["commute_minutes"] is None


def test_benchmark_matches_geography_layout_and_fee_basis(client, listing):
    rid = execute("INSERT INTO region_stats(prefecture,ward,avg_rent,avg_area,avg_building_age) "
                  "VALUES ('東京都','中央区',90000,40,25)")
    execute("INSERT INTO region_rent_benchmarks VALUES (?,?,?,?,?,?)",
            (rid, "1LDK", 100000, 0, "https://suumo.jp/chintai/soba/", datetime.now().isoformat()))
    execute("INSERT INTO region_stats(prefecture,city,ward,avg_rent) VALUES ('大阪府','大阪市','中央区',1)")
    row = client.get("/api/my-list").json["compare_rows"][0]
    assert row["region_avg_rent"] == 100000 and row["region_comparison_cost"] == 120000
    assert row["region_avg_area"] is None
    execute("UPDATE rental_listings SET layout='2DK'")
    assert client.get("/api/my-list").json["compare_rows"][0]["region_avg_rent"] is None
    execute("UPDATE rental_listings SET layout='1LDK'")
    execute("UPDATE region_rent_benchmarks SET includes_management_fee=NULL")
    assert client.get("/api/my-list").json["compare_rows"][0]["region_avg_rent"] is None
    execute("UPDATE region_rent_benchmarks SET includes_management_fee=0, fetched_at=?",
            ((datetime.now()-timedelta(days=181)).isoformat(),))
    assert client.get("/api/my-list").json["compare_rows"][0]["region_avg_rent"] is None


def test_layout_parser_keeps_1k_separate():
    from scripts.seed_regions import parse_rent_benchmarks
    rents, fees = parse_rent_benchmarks('<p>管理費・共益費を除く</p><table><tr><td>1K</td><td>8万円</td></tr>'
                                      '<tr><td>1LDK</td><td>12万円</td></tr></table>')
    assert rents == {"1K": 80000, "1LDK": 120000}
    assert fees == 0
