import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest
from app import app


@pytest.fixture
def client():
    app.config["TESTING"] = True
    with app.test_client() as c:
        yield c


def test_status_requires_listing_id(client):
    r = client.post("/api/status", json={})
    assert r.status_code == 400
    assert "listing_id" in r.get_json()["error"]


def test_status_rejects_unknown_listing(client):
    r = client.post("/api/status", json={"listing_id": 10 ** 9})
    assert r.status_code == 404


def test_preferences_keeps_fields_not_sent(client):
    from db_helper import query_one, execute
    execute("UPDATE user_preferences SET require_pet_allowed=1, ideal_walk_minutes=7 WHERE id=1")
    client.put("/api/preferences", json={"max_walk_minutes": 12})
    p = query_one("SELECT * FROM user_preferences WHERE id=1")
    assert p["require_pet_allowed"] == 1
    assert p["ideal_walk_minutes"] == 7
    assert p["max_walk_minutes"] == 12
    execute("UPDATE user_preferences SET require_pet_allowed=NULL, "
            "ideal_walk_minutes=NULL, max_walk_minutes=15 WHERE id=1")


def test_removed_v1_routes_are_gone(client):
    """CSV取込・一括抓取・source管理はUIごと廃止(一括抓取は run_scrape.py に残る)。"""
    for method, path in [("post", "/api/import/csv"), ("post", "/api/scrape"),
                         ("get", "/api/sources"), ("post", "/api/sources"),
                         ("get", "/api/listings"), ("get", "/api/rankings"),
                         ("get", "/import")]:
        assert getattr(client, method)(path).status_code == 404, path


def test_live_routes_still_answer(client):
    for path in ["/", "/my-list", "/favorites", "/compare", "/settings",
                 "/api/dashboard", "/api/my-list", "/api/preferences"]:
        assert client.get(path).status_code == 200, path


def test_my_list_exposes_a_clean_station_name(client):
    """nearest_station は路線名と複数駅が繋がった塊のことがある。

    表示用に取り出した駅名を、住民評価の有無にかかわらず返すこと。
    実データ例: 'ＪＲ山手線/東京駅 歩10分…東京メトロ日比谷線/八丁堀駅 歩3分'
    """
    from db_helper import get_conn
    raw = "ＪＲ山手線/東京駅 歩10分東京メトロ銀座線/京橋駅 歩7分東京メトロ日比谷線/八丁堀駅 歩3分"
    conn = get_conn()
    cur = conn.execute(
        "INSERT INTO rental_listings(platform, detail_url, source_url, title, ward, "
        "nearest_station, rent, total_monthly_cost, is_active) "
        "VALUES ('SUUMO', 'TEST://station', 'TEST://station', '駅名テスト', '中央区', ?, 1, 1, 1)",
        (raw,))
    lid = cur.lastrowid
    conn.commit()
    conn.close()
    try:
        rows = client.get("/api/my-list").get_json()["compare_rows"]
        row = next(r for r in rows if r["id"] == lid)
        assert row["station_name"] == "八丁堀"
        assert row["nearest_station"] == raw, "生の値も残しておくこと"

        cmp_rows = client.get(f"/api/compare?ids={lid}").get_json()
        assert cmp_rows[0]["station_name"] == "八丁堀"
    finally:
        conn = get_conn()
        conn.execute("DELETE FROM rental_listings WHERE id=?", (lid,))
        conn.commit()
        conn.close()
