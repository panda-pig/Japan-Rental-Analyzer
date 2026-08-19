import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from scrapers.base import allowed_domain


def test_real_listing_hosts_are_allowed():
    for url, domain in [
        ("https://suumo.jp/chintai/jnc_000012345/", "suumo.jp"),
        ("https://www.homes.co.jp/chintai/room/abc/", "homes.co.jp"),
        ("https://www.athome.co.jp.athome.jp/x", "athome.jp"),
        ("https://realestate.yahoo.co.jp/rent/detail/1", "yahoo.co.jp"),
        ("http://SUUMO.JP/chintai/x", "suumo.jp"),
    ]:
        assert allowed_domain(url) == domain, url


def test_lookalike_and_internal_hosts_are_rejected():
    for url in [
        "http://127.0.0.1:8080/?x=suumo.jp",
        "http://169.254.169.254/latest/meta-data/#suumo.jp",
        "http://evil.example/?ref=homes.co.jp",
        "http://suumo.jp.evil.example/x",
        "https://notsuumo.jp/x",
        "http://localhost/suumo.jp",
    ]:
        assert allowed_domain(url) is None, url


def test_non_http_schemes_are_rejected():
    for url in [
        "file:///etc/passwd",
        "ftp://suumo.jp/x",
        "javascript:alert(1)//suumo.jp",
        "gopher://suumo.jp/",
    ]:
        assert allowed_domain(url) is None, url


def test_garbage_input_does_not_raise():
    for url in ["", "   ", "http://", "://suumo.jp", "suumo.jp"]:
        assert allowed_domain(url) is None, url
