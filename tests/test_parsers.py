import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from scrapers.suumo import parse_suumo
from scrapers.homes import parse_homes
from scrapers.athome import parse_athome

FIXTURES = os.path.join(os.path.dirname(__file__), "fixtures")


def _read(name):
    with open(os.path.join(FIXTURES, name), encoding="utf-8") as f:
        return f.read()


def test_parse_suumo_real():
    """真实 SUUMO 搜索结果页。"""
    html = _read("suumo_real.html")
    listings = parse_suumo(html)
    assert len(listings) >= 10  # 真实页面有多条
    l = listings[0]
    assert l.platform == "SUUMO"
    assert l.title  # 标题非空
    assert l.detail_url.startswith("http")
    assert "万円" in l.rent_raw or "円" in l.rent_raw
    assert l.layout  # 间取り非空


def test_parse_suumo_fields():
    """验证 SUUMO 解析的关键字段正确。"""
    listings = parse_suumo(_read("suumo_real.html"))
    l = listings[0]
    # 第一条: キャトルセゾン白楽, 10.7万円, 4000円管理費, 1LDK, 40.4m2
    assert "万円" in l.rent_raw
    assert l.management_fee_raw is not None  # 管理費已提取
    assert l.layout is not None
    assert l.area_raw is not None
    assert l.address_raw  # 地址非空


def test_parse_homes_real():
    """真实 HOMES 搜索结果页。"""
    html = _read("homes_real.html")
    listings = parse_homes(html)
    assert len(listings) >= 10
    l = listings[0]
    assert l.platform == "HOMES"
    assert l.title
    assert l.detail_url.startswith("http")
    assert "万円" in l.rent_raw


def test_parse_homes_fields():
    """验证 HOMES 解析的关键字段正确。"""
    listings = parse_homes(_read("homes_real.html"))
    # 找一个有车站信息的
    with_station = [l for l in listings if l.nearest_station]
    assert with_station, "至少一条房源应有车站信息"
    l = with_station[0]
    assert "徒歩" in l.nearest_station or "歩" in l.nearest_station


def test_parse_athome_fixture():
    """athome 仍用简化 fixture(真实站点 DNS 在开发环境不可达)。"""
    listings = parse_athome(_read("athome_sample.html"))
    assert len(listings) == 1
    l = listings[0]
    assert l.platform == "athome"
    assert "13.5万円" in l.rent_raw
    assert l.layout == "2LDK"