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


def test_source_create_requires_fields(client):
    r = client.post("/api/sources", json={})
    assert r.status_code == 400


def test_source_update_requires_fields(client):
    r = client.put("/api/sources/1", json={})
    assert r.status_code == 400


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
