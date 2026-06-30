import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from unittest.mock import patch, MagicMock
from scrapers.base import check_robots_allowed, fetch_html


def test_robots_allowed(monkeypatch):
    monkeypatch.setattr("scrapers.base.requests.get", lambda url, **k: MagicMock(
        text="User-agent: *\nAllow: /", status_code=200))
    assert check_robots_allowed("https://suumo.jp/") is True


def test_robots_disallowed(monkeypatch):
    monkeypatch.setattr("scrapers.base.requests.get", lambda url, **k: MagicMock(
        text="User-agent: *\nDisallow: /", status_code=200))
    assert check_robots_allowed("https://suumo.jp/listing") is False


def test_fetch_html_returns_text(monkeypatch):
    monkeypatch.setattr("scrapers.base.check_robots_allowed", lambda url: True)
    monkeypatch.setattr("scrapers.base.requests.get", lambda url, **k: MagicMock(
        text="<html>ok</html>", status_code=200))
    html = fetch_html("https://example.com")
    assert "ok" in html


def test_fetch_html_robots_blocked(monkeypatch):
    monkeypatch.setattr("scrapers.base.check_robots_allowed", lambda url: False)
    assert fetch_html("https://example.com") is None