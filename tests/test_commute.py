import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from unittest.mock import patch, MagicMock
import core.commute as commute_mod


def test_no_key_returns_none(monkeypatch):
    monkeypatch.setattr(commute_mod, "NAVITIME_CLIENT_KEY", "")
    assert commute_mod.get_commute_minutes("東神奈川", "品川") is None


def test_api_success(monkeypatch):
    def fake_get(url, **k):
        r = MagicMock()
        r.status_code = 200
        r.json.return_value = {"items": [{"summary": {"moveTime": 35}}]}
        return r
    monkeypatch.setattr(commute_mod.requests, "get", fake_get)
    monkeypatch.setattr(commute_mod, "NAVITIME_CLIENT_KEY", "test_key")
    assert commute_mod.get_commute_minutes("東神奈川", "品川") == 35


def test_api_error_returns_none(monkeypatch):
    def fake_get(url, **k):
        r = MagicMock()
        r.status_code = 401
        return r
    monkeypatch.setattr(commute_mod.requests, "get", fake_get)
    monkeypatch.setattr(commute_mod, "NAVITIME_CLIENT_KEY", "bad")
    assert commute_mod.get_commute_minutes("東神奈川", "品川") is None


def test_empty_items(monkeypatch):
    def fake_get(url, **k):
        r = MagicMock()
        r.status_code = 200
        r.json.return_value = {"items": []}
        return r
    monkeypatch.setattr(commute_mod.requests, "get", fake_get)
    monkeypatch.setattr(commute_mod, "NAVITIME_CLIENT_KEY", "test_key")
    assert commute_mod.get_commute_minutes("東神奈川", "品川") is None