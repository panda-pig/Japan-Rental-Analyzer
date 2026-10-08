"""Privacy and integrity regressions through the API and persisted snapshots."""
from dataclasses import replace
from datetime import datetime, timedelta
from types import SimpleNamespace

import pytest

from core.dedup import canonical_listing_url
from db_helper import execute, query_all, query_one, transaction
from scrapers.models import RawListing
from scripts.run_scrape import normalize, upsert_listing
from services.scoring import score_listing


@pytest.fixture
def listing():
    raw = RawListing(platform="SUUMO", detail_url="https://suumo.jp/chintai/private/", title="Private home",
                     rent_raw="10万円", management_fee_raw="5000円", deposit_raw="1ヶ月", key_money_raw="なし",
                     area_raw="40㎡", layout="1LDK", floor_raw="3階", age_raw="築5年", walk_raw="徒歩5分",
                     address_raw="東京都中央区1-1", nearest_station="東京", features_raw=["ペット可", "オートロック"])
    with transaction() as conn:
        _, lid = upsert_listing(conn, normalize(raw))
    execute("INSERT INTO listing_status(listing_id,memo,viewing_date) VALUES(?,?,?)",
            (lid, "Private memo", "2026-10-20"))
    score_listing(lid, resolve_commute=False)
    return lid, raw


@pytest.mark.parametrize("path", ["/api/status", "/api/preferences", "/api/my-list", "/api/compare?ids={id}",
    "/api/listings/{id}", "/api/listings/{id}/price-history", "/api/listings/{id}/enrichment"])
def test_private_reads_and_head_require_token(client, monkeypatch, listing, path):
    import app
    monkeypatch.setattr(app, "ADMIN_TOKEN", "test-admin")
    path = path.format(id=listing[0])
    for headers in ({}, {"X-Admin-Token": "wrong"}, {"X-Admin-Token": "日本語"}):
        for method in (client.get, client.head):
            response = method(path, headers=headers)
            assert response.status_code == 401
            assert response.headers["Cache-Control"] == "private, no-store"
            assert "X-Admin-Token" in response.vary
            assert "Private" not in response.get_data(as_text=True)
    assert client.get(path, headers={"X-Admin-Token": "test-admin"}).status_code == 200


def test_public_dashboard_contains_no_listing_or_preference_data(client, monkeypatch, listing):
    import app
    monkeypatch.setattr(app, "ADMIN_TOKEN", "test-admin")
    response = client.get("/api/dashboard")
    assert response.status_code == 200
    assert set(response.json) == {"region_count", "area_summary", "regions", "tokyo_region_rent", "yokohama_region_rent"}
    assert "Private" not in response.get_data(as_text=True)
    rid = execute("INSERT INTO region_stats(prefecture,ward) VALUES('東京都','テスト区')")
    for path in ("/api/regions", "/api/regions/テスト区", f"/api/regions/id/{rid}"):
        assert client.get(path).status_code == 200


def test_render_private_access_fails_closed_without_token(client, monkeypatch):
    import app
    monkeypatch.setattr(app, "ADMIN_TOKEN", "")
    monkeypatch.setenv("RENDER", "true")
    assert client.get("/api/status").status_code == 503
    assert client.put("/api/preferences", json={"target_station": "品川"}).status_code == 503
    assert client.get("/api/dashboard").status_code == 200


def snapshot():
    return {table: query_all(f"SELECT * FROM {table} ORDER BY id") for table in
            ("rental_listings", "listing_price_history", "listing_scores", "listing_status")}


@pytest.mark.parametrize("action", ["refresh", "import"])
@pytest.mark.parametrize("partial", ["price_only", "amenities_missing"])
def test_partial_fetch_preserves_entire_snapshot(client, monkeypatch, listing, action, partial):
    import app
    from scrapers import base
    lid, raw = listing
    before = snapshot()
    parsed = (RawListing(platform=raw.platform, detail_url=raw.detail_url, title=raw.title, rent_raw="9万円")
              if partial == "price_only" else replace(raw, rent_raw="9万円", features_raw=["ペット可"]))
    monkeypatch.setattr(base, "fetch_html", lambda url: "partial HTML")
    monkeypatch.setattr(app, "_detail_parser", lambda url: lambda *args: parsed)
    response = (client.post(f"/api/listings/{lid}/refresh") if action == "refresh" else
                client.post("/api/import/detail", json={"url": raw.detail_url + "?utm_source=share"}))
    assert response.status_code == 422
    assert response.json["preserved"] is True
    assert "auto_lock" in response.json["missing_fields"]
    if partial == "price_only":
        assert {"area_m2", "management_fee", "deposit", "pet_allowed"} <= set(response.json["missing_fields"])
    assert snapshot() == before


def test_explicit_zero_fees_and_prohibited_pet_can_replace_previous_values(client, monkeypatch, listing):
    import app
    from scrapers import base
    lid, raw = listing
    parsed = replace(raw, rent_raw="9万円", management_fee_raw="0円", deposit_raw="なし",
                     features_raw=["ペット不可", "オートロック"])
    monkeypatch.setattr(base, "fetch_html", lambda url: "complete HTML")
    monkeypatch.setattr(app, "_detail_parser", lambda url: lambda *args: parsed)
    response = client.post(f"/api/listings/{lid}/refresh")
    assert response.status_code == 200 and response.json["price_changed"] is True
    row = query_one("SELECT * FROM rental_listings WHERE id=?", (lid,))
    assert (row["management_fee"], row["deposit"], row["pet_allowed"], row["auto_lock"]) == (0, 0, 0, 1)
    assert [r["total_monthly_cost"] for r in query_all("SELECT * FROM listing_price_history ORDER BY id")] == [105000, 90000]


@pytest.mark.parametrize("legacy", [False, True])
def test_share_urls_reuse_listing_favorite_and_history(client, monkeypatch, listing, legacy):
    import app
    from scrapers import base
    lid, raw = listing
    if legacy:
        execute("UPDATE rental_listings SET detail_url=? WHERE id=?", (raw.detail_url + "?utm_source=old", lid))
    favorite = query_one("SELECT * FROM listing_status")
    history = query_all("SELECT * FROM listing_price_history")
    monkeypatch.setattr(base, "fetch_html", lambda url: "complete HTML")
    monkeypatch.setattr(app, "_detail_parser", lambda url: lambda html, url: replace(raw, detail_url=url))
    for suffix in ("?utm_source=share#room", "?gclid=click&utm_medium=social", "#photos"):
        response = client.post("/api/import/detail", json={"url": raw.detail_url + suffix})
        assert response.status_code == 200
        assert response.json["id"] == lid and response.json["status"] == "updated"
    assert len(query_all("SELECT * FROM rental_listings")) == 1
    assert query_one("SELECT * FROM listing_status") == favorite
    assert query_all("SELECT * FROM listing_price_history") == history


def test_canonical_url_preserves_identifiers_and_encoding():
    assert canonical_listing_url("https://suumo.jp/room?id=a%2fb+z&flag=&UTM_source=s#photos") == "https://suumo.jp/room?id=a%2fb+z&flag="
    assert canonical_listing_url("https://suumo.jp/room?id=1&utm_source=s") != canonical_listing_url("https://suumo.jp/room?id=2&utm_source=s")
    raw = RawListing(platform="SUUMO", title="Home", detail_url="https://suumo.jp/room?id=1&utm_source=s", rent_raw="10万円")
    with transaction() as conn:
        _, first = upsert_listing(conn, normalize(raw))
        _, second = upsert_listing(conn, normalize(replace(raw, detail_url="https://suumo.jp/room?id=2")))
    assert first != second
    assert query_one("SELECT detail_url FROM rental_listings WHERE id=?", (first,))["detail_url"] == "https://suumo.jp/room?id=1"


def test_refresh_targets_requested_id_when_legacy_aliases_exist(client, monkeypatch, listing):
    import app
    from scrapers import base
    lid, raw = listing
    # Existing duplicates keep their own favorites/history; a refresh must not
    # silently update another listing that now has the same canonical URL.
    alias = execute("INSERT INTO rental_listings(platform,title,detail_url) VALUES(?,?,?)",
                    (raw.platform, raw.title, raw.detail_url + "?utm_source=old"))
    before = query_one("SELECT * FROM rental_listings WHERE id=?", (lid,))
    monkeypatch.setattr(base, "fetch_html", lambda url: "complete HTML")
    monkeypatch.setattr(app, "_detail_parser", lambda url: lambda *args: replace(raw, rent_raw="9万円"))
    assert client.post(f"/api/listings/{alias}/refresh").status_code == 200
    assert query_one("SELECT * FROM rental_listings WHERE id=?", (lid,)) == before
    assert query_one("SELECT rent FROM rental_listings WHERE id=?", (alias,))["rent"] == 90000


@pytest.mark.parametrize("age,basis,ranked,comparable", [(1, 0, True, True), (179, 0, True, True),
    (181, 0, False, False), (-2, 0, False, False), ("invalid", 0, False, False),
    (1, None, False, False), (1, 1, False, True)])
def test_rankings_and_reports_share_benchmark_validity(client, listing, age, basis, ranked, comparable):
    rid = execute("INSERT INTO region_stats(prefecture,ward,avg_rent,rent_layout,rent_fetched_at) VALUES(?,?,?,?,?)",
                  ("東京都", "中央区", 999999, "1LDK", datetime.now().isoformat()))
    fetched_at = age if isinstance(age, str) else (datetime.now() - timedelta(days=age)).isoformat()
    execute("INSERT INTO region_rent_benchmarks VALUES(?,?,?,?,?,?)",
            (rid, "1LDK", 110000, basis, "https://suumo.jp/chintai/soba/", fetched_at))
    dashboard = client.get("/api/dashboard").json
    region = next(r for r in dashboard["regions"] if r["id"] == rid)
    assert region["avg_rent"] == 110000  # Authoritative layout benchmark, not legacy region_stats.
    assert region["rent_comparable"] is ranked
    assert (dashboard["area_summary"]["cheapest"] is not None) is ranked
    assert bool(dashboard["tokyo_region_rent"]) is ranked
    assert client.get(f"/api/regions/id/{rid}").json["rent_comparable"] is ranked
    row = client.get("/api/my-list").json["compare_rows"][0]
    assert (row["region_avg_rent"] is not None) is comparable
    if comparable:
        assert row["region_comparison_cost"] == (105000 if basis else 100000)
    else:
        assert region["rent_note"] == row["benchmark_note"]


def test_unverified_legacy_rent_remains_reference_only(client):
    rid = execute("INSERT INTO region_stats(prefecture,ward,avg_rent,rent_layout,rent_fetched_at) VALUES(?,?,?,?,?)",
                  ("東京都", "旧データ区", 90000, "1LDK", datetime.now().isoformat()))
    data = client.get("/api/dashboard").json
    assert data["area_summary"]["cheapest"] is None
    region = next(r for r in data["regions"] if r["id"] == rid)
    assert region["avg_rent"] == 90000 and region["rent_comparable"] is False


@pytest.mark.parametrize("target", ["/blocked", "https://homes.co.jp/blocked"])
@pytest.mark.parametrize("allowed", [False, True])
def test_redirect_checks_target_robots_before_fetch(monkeypatch, target, allowed):
    from urllib.parse import urljoin
    from scrapers import base
    start = "https://suumo.jp/allowed"
    destination = urljoin(start, target)
    checked, fetched = [], []
    monkeypatch.setattr(base, "is_safe_url", lambda url: True)
    monkeypatch.setattr(base.time, "sleep", lambda seconds: None)
    monkeypatch.setattr(base, "check_robots_allowed", lambda url: checked.append(url) or url == start or allowed)
    def get(url, **kwargs):
        fetched.append(url)
        assert kwargs["allow_redirects"] is False
        return SimpleNamespace(is_redirect=url == start, is_permanent_redirect=False,
                               headers={"Location": target}, text="body", raise_for_status=lambda: None)
    monkeypatch.setattr(base.requests, "get", get)
    assert base.fetch_html(start) == ("body" if allowed else None)
    assert checked == [start, destination]
    assert fetched == ([start, destination] if allowed else [start])
