import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from unittest.mock import MagicMock
import pytest
import requests
from scrapers.base import check_robots_allowed, fetch_html

ALLOWED = "https://suumo.jp/chintai/jnc_1/"


def _response(text="<html>ok</html>", status=200, location=None):
    """redirect 判定用の属性まで明示した擬似レスポンス。"""
    r = MagicMock(status_code=status, text=text)
    r.is_redirect = location is not None
    r.is_permanent_redirect = False
    r.headers = {"Location": location} if location else {}
    r.raise_for_status = MagicMock()
    return r


def _allow_dns(monkeypatch):
    """テストで名前解決させない(許可ドメインは公開IPとみなす)。"""
    monkeypatch.setattr("scrapers.base._resolves_to_public_ip", lambda host: True)


def test_robots_allowed(monkeypatch):
    _allow_dns(monkeypatch)
    monkeypatch.setattr("scrapers.base.requests.get", lambda url, **k: MagicMock(
        text="User-agent: *\nAllow: /", status_code=200))
    assert check_robots_allowed("https://suumo.jp/") is True


def test_robots_disallowed(monkeypatch):
    _allow_dns(monkeypatch)
    monkeypatch.setattr("scrapers.base.requests.get", lambda url, **k: MagicMock(
        text="User-agent: *\nDisallow: /", status_code=200))
    assert check_robots_allowed("https://suumo.jp/listing") is False


def test_fetch_html_returns_text(monkeypatch):
    _allow_dns(monkeypatch)
    monkeypatch.setattr("scrapers.base.check_robots_allowed", lambda url: True)
    monkeypatch.setattr("scrapers.base.requests.get", lambda url, **k: _response())
    monkeypatch.setattr("scrapers.base.time.sleep", lambda s: None)
    assert "ok" in fetch_html(ALLOWED)


def test_fetch_html_robots_blocked(monkeypatch):
    _allow_dns(monkeypatch)
    monkeypatch.setattr("scrapers.base.check_robots_allowed", lambda url: False)
    assert fetch_html(ALLOWED) is None


def test_fetch_html_rejects_host_outside_allowlist(monkeypatch):
    """URL に許可ドメイン名が含まれるだけでは取得しない。"""
    called = []
    monkeypatch.setattr("scrapers.base.check_robots_allowed", lambda url: True)
    monkeypatch.setattr("scrapers.base.requests.get",
                        lambda url, **k: called.append(url) or _response())
    for url in ["http://127.0.0.1:8080/?x=suumo.jp",
                "http://169.254.169.254/latest/meta-data/",
                "https://example.com/"]:
        assert fetch_html(url) is None, url
    assert called == [], f"取得を試みてはいけない: {called}"


def test_fetch_html_stops_redirect_to_internal_host(monkeypatch):
    """許可ドメインから内部アドレスへ逃がされないこと。"""
    _allow_dns(monkeypatch)
    monkeypatch.setattr("scrapers.base.check_robots_allowed", lambda url: True)
    monkeypatch.setattr("scrapers.base.requests.get",
                        lambda url, **k: _response(location="http://127.0.0.1/secret"))
    assert fetch_html(ALLOWED) is None


def test_fetch_html_follows_redirect_within_allowlist(monkeypatch):
    _allow_dns(monkeypatch)
    monkeypatch.setattr("scrapers.base.check_robots_allowed", lambda url: True)
    monkeypatch.setattr("scrapers.base.time.sleep", lambda s: None)
    seen = []

    def fake_get(url, **k):
        seen.append(url)
        if len(seen) == 1:
            return _response(location="https://suumo.jp/chintai/jnc_2/")
        return _response(text="<html>moved</html>")

    monkeypatch.setattr("scrapers.base.requests.get", fake_get)
    assert "moved" in fetch_html(ALLOWED)
    assert seen[-1] == "https://suumo.jp/chintai/jnc_2/"


@pytest.mark.parametrize("target", ["http://127.0.0.1/secret", "http://169.254.169.254/latest/meta-data/", "https://example.com/robots.txt"])
def test_robots_redirect_cannot_escape_allowed_targets(monkeypatch, target):
    _allow_dns(monkeypatch)
    seen = []
    def get(url, **kwargs):
        seen.append(url)
        assert kwargs.get("allow_redirects") is False
        return _response(status=302, location=target)
    monkeypatch.setattr("scrapers.base.requests.get", get)
    assert fetch_html(ALLOWED) is None
    assert seen == ["https://suumo.jp/robots.txt"]


def test_redirected_robots_rules_apply_to_original_listing(monkeypatch):
    _allow_dns(monkeypatch)
    seen = []
    def get(url, **kwargs):
        seen.append(url)
        assert kwargs.get("allow_redirects") is False
        if len(seen) == 1:
            return _response(status=301, location="/rules/robots.txt")
        return _response(text="User-agent: *\nDisallow: /chintai/")
    monkeypatch.setattr("scrapers.base.requests.get", get)
    assert fetch_html(ALLOWED) is None
    assert seen == ["https://suumo.jp/robots.txt", "https://suumo.jp/rules/robots.txt"]


def test_allowed_robots_redirect_still_fetches_listing(monkeypatch):
    _allow_dns(monkeypatch)
    monkeypatch.setattr("scrapers.base.time.sleep", lambda seconds: None)
    seen = []
    def get(url, **kwargs):
        seen.append(url)
        assert kwargs["allow_redirects"] is False
        if url == "https://suumo.jp/robots.txt":
            return _response(status=307, location="/rules/robots.txt")
        if url == "https://suumo.jp/rules/robots.txt":
            return _response(text="User-agent: *\nAllow: /")
        assert url == ALLOWED
        return _response(text="<h1>Listing</h1>")
    monkeypatch.setattr("scrapers.base.requests.get", get)
    assert fetch_html(ALLOWED) == "<h1>Listing</h1>"
    assert seen == ["https://suumo.jp/robots.txt", "https://suumo.jp/rules/robots.txt", ALLOWED]


@pytest.mark.parametrize("status,allowed", [(404, True), (410, True), (401, False), (403, False),
    (429, False), (500, False), (503, False)])
def test_robots_unavailable_does_not_silently_allow_fetch(monkeypatch, status, allowed):
    _allow_dns(monkeypatch)
    monkeypatch.setattr("scrapers.base.requests.get", lambda *a, **k: _response(status=status))
    assert check_robots_allowed(ALLOWED) is allowed


def test_robots_timeout_stops_listing_request(monkeypatch):
    _allow_dns(monkeypatch)
    seen = []
    def get(url, **kwargs):
        seen.append(url)
        raise requests.Timeout()
    monkeypatch.setattr("scrapers.base.requests.get", get)
    assert fetch_html(ALLOWED) is None
    assert seen == ["https://suumo.jp/robots.txt"]


def test_robots_redirect_to_private_dns_is_blocked(monkeypatch):
    monkeypatch.setattr("scrapers.base._resolves_to_public_ip", lambda host: host == "suumo.jp")
    seen = []
    monkeypatch.setattr("scrapers.base.requests.get", lambda url, **k:
                        seen.append(url) or _response(status=302, location="https://private.suumo.jp/robots.txt"))
    assert fetch_html(ALLOWED) is None
    assert seen == ["https://suumo.jp/robots.txt"]


def test_robots_redirect_limit_stops_cycles(monkeypatch):
    _allow_dns(monkeypatch)
    seen = []
    monkeypatch.setattr("scrapers.base.requests.get", lambda url, **k:
                        seen.append(url) or _response(status=302, location="/robots.txt"))
    assert check_robots_allowed(ALLOWED) is False
    assert len(seen) <= 6
