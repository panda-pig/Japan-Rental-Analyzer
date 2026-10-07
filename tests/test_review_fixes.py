"""Regression coverage from raw platform fields through persisted reports."""
from concurrent.futures import ThreadPoolExecutor
from threading import Event

import pytest

from core.cleaning import parse_pet_allowed, parse_station_walk, parse_walk_minutes
from db_helper import execute, query_one, transaction
from scrapers.models import RawListing
from scrapers.suumo_detail import parse_suumo_detail
from scrapers.homes_detail import parse_homes_detail
from scrapers.athome_detail import parse_athome_detail
from scrapers.yahoo_detail import parse_yahoo_detail
from scripts.run_scrape import normalize, upsert_listing
from services.scoring import score_listing


def suumo_html(notes="", condition="", access=""):
    return f'''<h1>テスト物件</h1><table>
      <tr><th>賃料(管理費)</th><td>10万円(5,000円)</td></tr>
      <tr><th>その他</th><td>情報</td><th>条件</th><td>{condition}</td></tr>
      <tr><th>駅徒歩</th><td>{access}</td></tr>
    </table><ul class="property_view_note-list">{notes}</ul>'''


@pytest.fixture
def listing():
    raw = RawListing(platform="SUUMO", title="Test", detail_url="https://suumo.jp/chintai/test/",
                     rent_raw="10万円", management_fee_raw="5000円", deposit_raw="なし", key_money_raw="なし",
                     nearest_station="東京", floor_raw="3階", walk_raw="徒歩5分", age_raw="築5年")
    with transaction() as conn:
        _, lid = upsert_listing(conn, normalize(raw))
    return lid


@pytest.mark.parametrize("notes,deposit,key_money", [
    ("", None, None), ("敷金: - 礼金: ―", None, None),
    ("敷金: 0.5ヶ月 礼金: 1ヶ月", 50000, 100000),
    ("敷金：０．５カ月 礼金：１．５ヶ月", 50000, 150000),
    ("敷金: なし 礼金: 0円", 0, 0),
    ("<li>敷金: 10万円</li><li>礼金: 5万円</li>", 100000, 50000),
    ("礼金: 1ヶ月", None, 100000),
])
def test_suumo_fees_survive_parse_normalize_and_score(notes, deposit, key_money):
    data = normalize(parse_suumo_detail(suumo_html(notes), "https://suumo.jp/chintai/fees/"))
    assert (data["deposit"], data["key_money"]) == (deposit, key_money)
    with transaction() as conn:
        _, lid = upsert_listing(conn, data)
    assert score_listing(lid, resolve_commute=False)
    result = query_one("SELECT initial_cost_score FROM listing_scores WHERE listing_id=?", (lid,))
    if deposit is None or key_money is None:
        assert data["initial_cost_estimate"] is None
        assert result["initial_cost_score"] is None
    else:
        assert data["initial_cost_estimate"] == 195000 + deposit + key_money
        assert result["initial_cost_score"] == (5 if deposit + key_money == 0 else 1)


@pytest.mark.parametrize("parser", [parse_suumo_detail, parse_homes_detail, parse_athome_detail, parse_yahoo_detail])
def test_all_detail_parsers_keep_missing_fees_unknown(parser):
    data = normalize(parser("<h1>テスト物件</h1>"))
    assert data["deposit"] is None and data["key_money"] is None
    assert data["initial_cost_estimate"] is None


@pytest.mark.parametrize("condition,expected,points", [
    ("ペット相談 / 二人入居可", 1, 15), ("楽器不可 ペット相談", 1, 15),
    ("ペット不可", 0, 0), ("ペット相談不可", 0, 0),
    ("猫不可 小型犬可", 1, 15), ("猫不可", 0, 0), ("", None, 5),
])
def test_pet_condition_reaches_scoring(condition, expected, points):
    data = normalize(parse_suumo_detail(suumo_html(condition=condition), "https://suumo.jp/chintai/pet/"))
    assert data["pet_allowed"] == expected
    with transaction() as conn:
        _, lid = upsert_listing(conn, data)
    score_listing(lid, resolve_commute=False)
    assert query_one("SELECT pet_score FROM listing_scores WHERE listing_id=?", (lid,))["pet_score"] == points


@pytest.mark.parametrize("access,station,minutes", [
    ("ＪＲ山手線/東京駅 歩10分東京メトロ日比谷線/八丁堀駅 歩3分", "八丁堀", 3),
    ('JR線 「東京」駅 徒歩１０分', "東京", 10),
    ('JR線「東京駅」徒歩10分 メトロ線「八丁堀駅」徒歩3分', "八丁堀", 3),
    ('東急東横線「中目黒」徒歩6分', "中目黒", 6),
    ("東京駅 バス10分 停歩2分 / 八丁堀駅 歩8分", "八丁堀", 8),
])
def test_station_and_walking_time_stay_paired(access, station, minutes):
    from scrapers.machimusubi import extract_station
    data = normalize(parse_suumo_detail(suumo_html(access=access)))
    assert (data["nearest_station"], data["walk_minutes"]) == (station, minutes)
    assert extract_station(access) == station
    assert parse_walk_minutes(access) == minutes


def test_bus_time_is_not_station_walking_time():
    assert parse_station_walk("東京駅 バス10分 停歩2分") is None
    assert parse_walk_minutes("東京駅 バス10分 停歩2分") is None
    assert parse_pet_allowed("楽器不可") is None


@pytest.mark.parametrize("changed", ["destination", "origin"])
def test_stale_commute_cannot_erase_new_score(listing, monkeypatch, changed):
    from services import scoring
    started, release = Event(), Event()
    execute("UPDATE user_preferences SET target_station='品川' WHERE id=1")

    def lookup(origin, destination, resolve):
        if resolve:
            started.set()
            assert release.wait(5)
            return 25
        return 20

    monkeypatch.setattr(scoring, "commute_minutes", lookup)
    with ThreadPoolExecutor(max_workers=1) as pool:
        old = pool.submit(score_listing, listing)
        try:
            assert started.wait(3)
            if changed == "destination":
                execute("UPDATE user_preferences SET target_station='新宿' WHERE id=1")
            else:
                execute("UPDATE rental_listings SET nearest_station='横浜' WHERE id=?", (listing,))
            assert score_listing(listing, resolve_commute=False)
            before = query_one("SELECT * FROM listing_scores WHERE listing_id=?", (listing,))
        finally:
            release.set()
        assert old.result(timeout=5) is False
    assert query_one("SELECT * FROM listing_scores WHERE listing_id=?", (listing,)) == before
    assert query_one("SELECT commute_minutes FROM rental_listings WHERE id=?", (listing,))["commute_minutes"] == 20


def test_preferences_schedule_latest_target_while_old_job_runs(client, listing, monkeypatch):
    import app
    from core import commute
    from services import enrichment
    started, release = Event(), Event()
    destinations, futures = [], []
    execute("UPDATE user_preferences SET target_station='品川' WHERE id=1")
    monkeypatch.setattr(enrichment, "_jobs", {})
    monkeypatch.setattr(enrichment, "_rerun", set())
    monkeypatch.setattr(enrichment, "get_station_review", lambda *a, **k: None)
    monkeypatch.setattr(app, "_enqueue_enrichment", enrichment.enqueue)

    def lookup(origin, destination):
        destinations.append(destination)
        if destination == "品川":
            started.set()
            assert release.wait(5)
            return 25
        return 20

    monkeypatch.setattr(commute, "get_commute_minutes", lookup)
    with ThreadPoolExecutor(max_workers=1) as pool:
        class Executor:
            def submit(self, *args):
                future = pool.submit(*args)
                futures.append(future)
                return future
        monkeypatch.setattr(enrichment, "_executor", Executor())
        assert enrichment.enqueue(listing) == "pending"
        try:
            assert started.wait(3)
            response = client.put("/api/preferences", json={"target_station": "新宿"})
            assert response.status_code == 200 and response.json["pending"] == 1
            assert client.get("/api/my-list").json["pending_enrichment_ids"] == [listing]
            enrichment.enqueue(listing)
            enrichment.enqueue(listing)
        finally:
            release.set()
        futures[0].result(timeout=5)
    assert len(futures) == 1
    assert destinations == ["品川", "新宿"]
    assert enrichment.status(listing) == "complete"
    row = query_one("SELECT commute_minutes,commute_target_station FROM rental_listings WHERE id=?", (listing,))
    assert row == {"commute_minutes": 20, "commute_target_station": "新宿"}


def test_report_and_feature_cloud_use_saved_preferences(client, listing):
    response = client.put("/api/preferences", json={"min_floor": 2, "max_walk_minutes": 7, "max_building_age": 6})
    assert response.status_code == 200
    data = client.get("/api/my-list").json
    for key, value in [("min_floor", 2), ("max_walk_minutes", 7), ("max_building_age", 6)]:
        assert data["prefs"][key] == value
    labels = {r["name"] for r in data["feature_cloud"]}
    assert {"2階以上", "駅徒歩7分以内", "築6年以内"} <= labels
    assert not {"3階以上", "駅徒歩10分以内", "築浅"} & labels


def test_price_history_is_loaded_only_for_selected_listing(client, listing):
    other = execute("INSERT INTO rental_listings(title,detail_url) VALUES('Other','https://suumo.jp/other')")
    with transaction() as conn:
        conn.execute("DELETE FROM listing_price_history WHERE listing_id=?", (listing,))
        conn.executemany("INSERT INTO listing_price_history(listing_id,total_monthly_cost,checked_at,observation_kind) VALUES(?,?,?,?)", [
            (listing, 105000, '2026-10-02', 'observed'), (listing, 110000, '2026-10-01', 'observed'),
            (listing, 1, '2026-09-01', 'legacy'), (listing, None, '2026-10-03', 'observed'),
            (other, 999, '2026-10-03', 'observed'),
        ])
    assert "price_history" not in client.get("/api/my-list").json
    result = client.get(f"/api/listings/{listing}/price-history")
    assert result.status_code == 200
    assert result.json == {"listing_id": listing, "history": [
        {"checked_at": "2026-10-01", "total_monthly_cost": 110000},
        {"checked_at": "2026-10-02", "total_monthly_cost": 105000},
    ]}
    assert client.get("/api/listings/99999/price-history").status_code == 404
    execute("UPDATE rental_listings SET is_active=0 WHERE id=?", (listing,))
    assert client.get(f"/api/listings/{listing}/price-history").status_code == 404
