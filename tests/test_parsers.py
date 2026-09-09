import sys
import os
import pytest
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from scrapers.suumo import parse_suumo
from scrapers.homes import parse_homes
from scrapers.athome import parse_athome

FIXTURES = os.path.join(os.path.dirname(__file__), "fixtures")


def _read(name):
    if name.endswith('_real.html') and not os.path.exists(os.path.join(FIXTURES, name)):
        pytest.skip('Optional local site snapshot; portable sample coverage runs in CI')
    with open(os.path.join(FIXTURES, name), encoding="utf-8") as f:
        return f.read()


def test_parse_suumo_sample_rooms():
    listings = parse_suumo(_read('suumo_sample.html'))
    assert len(listings) == 2
    assert [l.detail_url for l in listings] == [
        'https://suumo.jp/chintai/jnc_sample001/',
        'https://suumo.jp/chintai/jnc_sample002/',
    ]
    assert [l.title for l in listings] == ['サンプル物件 A', 'サンプル物件 A']
    assert [l.floor_raw for l in listings] == ['3階', '4階']
    assert all(l.platform == 'SUUMO' for l in listings)


def test_parse_suumo_sample_fields():
    first, second = parse_suumo(_read('suumo_sample.html'))
    assert (first.rent_raw, first.management_fee_raw) == ('12.8万円', '8000円')
    assert (first.deposit_raw, first.key_money_raw) == ('0.5ヶ月', '0')
    assert (first.layout, first.area_raw) == ('1LDK', '42.3m²')
    assert first.address_raw == '神奈川県横浜市神奈川区サンプル町1-1'
    assert first.nearest_station == '東神奈川駅 徒歩8分'
    assert second.rent_raw == '13.2万円'


def test_parse_homes_sample_listings():
    listings = parse_homes(_read('homes_sample.html'))
    assert len(listings) == 2
    assert [l.detail_url for l in listings] == [
        'https://www.homes.co.jp/chintai/room/sample001/',
        'https://www.homes.co.jp/chintai/room/sample002/',
    ]
    assert [l.title for l in listings] == ['サンプル物件 B', 'サンプル物件 C']
    assert all(l.platform == 'HOMES' for l in listings)


def test_parse_homes_sample_fields():
    first, second = parse_homes(_read('homes_sample.html'))
    assert (first.rent_raw, first.layout, first.area_raw) == ('8.5万円', '2DK', '36.8㎡')
    assert first.nearest_station == first.walk_raw == '横浜駅 徒歩12分'
    assert first.management_fee_raw is None
    assert (second.rent_raw, second.layout, second.area_raw) == ('9.2万円', '1LDK', '38.0m²')
    assert second.nearest_station == '川崎駅 徒歩7分'


def test_parse_suumo_real():
    """真实 SUUMO 搜索结果页。"""
    html = _read("suumo_real.html")
    listings = parse_suumo(html)
    assert len(listings) >= 10
    l = listings[0]
    assert l.platform == "SUUMO"
    assert l.title
    assert l.detail_url.startswith("http")
    assert "万円" in l.rent_raw or "円" in l.rent_raw
    assert l.layout


def test_parse_suumo_fields():
    """验证 SUUMO 解析的关键字段正确。"""
    listings = parse_suumo(_read("suumo_real.html"))
    l = listings[0]
    assert "万円" in l.rent_raw
    assert l.management_fee_raw is not None
    assert l.layout is not None
    assert l.area_raw is not None
    assert l.address_raw


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
