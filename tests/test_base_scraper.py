import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from unittest.mock import MagicMock
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
    monkeypatch.setattr("scrapers.base.requests.get", lambda url, **k: MagicMock(
        text="User-agent: *\nAllow: /", status_code=200))
    assert check_robots_allowed("https://suumo.jp/") is True


def test_robots_disallowed(monkeypatch):
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
