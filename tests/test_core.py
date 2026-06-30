import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.cleaning import (
    parse_money, parse_deposit_key_money, parse_area, parse_walk_minutes,
    parse_floor, parse_building_age, parse_pet_allowed, parse_features,
)
from core.address import parse_address
from core.initial_cost import estimate_initial_cost
from core.dedup import generate_listing_hash


# --- money ---
def test_parse_money_wan():
    assert parse_money("12.8万円") == 128000

def test_parse_money_yen():
    assert parse_money("8,000円") == 8000

def test_parse_money_yen_no_comma():
    assert parse_money("8000円") == 8000

def test_parse_money_none():
    assert parse_money(None) is None

def test_parse_money_na():
    assert parse_money("なし") == 0

def test_parse_money_empty():
    assert parse_money("") is None

def test_parse_money_already_int():
    assert parse_money("128000") == 128000

def test_deposit_key_money_months():
    assert parse_deposit_key_money("1ヶ月", 128000) == 128000
    assert parse_deposit_key_money("2ヶ月", 100000) == 200000

def test_deposit_key_money_none():
    assert parse_deposit_key_money(None, 100000) is None

def test_deposit_key_money_na():
    assert parse_deposit_key_money("なし", 100000) == 0


# --- area / walk / floor / age ---
def test_parse_area():
    assert parse_area("42.3m²") == 42.3
    assert parse_area("42.3㎡") == 42.3
    assert parse_area("専有面積 42.3平米") == 42.3
    assert parse_area(None) is None

def test_parse_walk_minutes():
    assert parse_walk_minutes("徒歩8分") == 8
    assert parse_walk_minutes("歩8分") == 8
    assert parse_walk_minutes("駅徒歩 12分") == 12
    assert parse_walk_minutes(None) is None

def test_parse_floor():
    assert parse_floor("3階/5階建") == (3, 5)
    assert parse_floor("1階") == (1, None)
    assert parse_floor("地下1階") == (-1, None)
    assert parse_floor(None) == (None, None)

def test_parse_building_age():
    assert parse_building_age("築12年") == 12
    assert parse_building_age("新築") == 0
    assert parse_building_age("築浅") is None
    assert parse_building_age("2010年3月") == 16  # 相对 2026
    assert parse_building_age(None) is None


# --- pet / features ---
def test_parse_pet_allowed():
    assert parse_pet_allowed("ペット可") == 1
    assert parse_pet_allowed("ペット相談") == 1
    assert parse_pet_allowed("小型犬可") == 1
    assert parse_pet_allowed("猫可") == 1
    assert parse_pet_allowed("ペット不可") == 0
    assert parse_pet_allowed(None) == 0

def test_parse_features():
    feats = parse_features(["バストイレ別", "オートロック", "宅配ボックス"])
    assert feats["bath_toilet_separate"] == 1
    assert feats["auto_lock"] == 1
    assert feats["delivery_box"] == 1
    assert feats["south_facing"] == 0

def test_parse_features_2person():
    feats = parse_features(["2人入居可", "南向き", "エアコン"])
    assert feats["two_person_allowed"] == 1
    assert feats["south_facing"] == 1
    assert feats["aircon"] == 1

def test_parse_features_empty():
    feats = parse_features([])
    assert all(v == 0 for v in feats.values())


# --- address ---
def test_tokyo_ward():
    r = parse_address("東京都大田区蒲田5-20-3")
    assert r["prefecture"] == "東京都"
    assert r["ward"] == "大田区"
    assert r["address"] == "蒲田5-20-3"

def test_yokohama_ward():
    r = parse_address("神奈川県横浜市神奈川区栄町10-1")
    assert r["prefecture"] == "神奈川県"
    assert r["city"] == "横浜市"
    assert r["ward"] == "神奈川区"
    assert r["address"] == "栄町10-1"

def test_kawasaki():
    r = parse_address("神奈川県川崎市川崎区東田町2-1")
    assert r["prefecture"] == "神奈川県"
    assert r["city"] == "川崎市"
    assert r["ward"] == "川崎区"

def test_yokohama_no_pref():
    """地址省略県名(SUUMO 常见格式)"""
    r = parse_address("横浜市神奈川区栄町10-1")
    assert r["prefecture"] == "神奈川県"
    assert r["city"] == "横浜市"
    assert r["ward"] == "神奈川区"

def test_kawasaki_no_pref():
    r = parse_address("川崎市川崎区東田町2-1")
    assert r["prefecture"] == "神奈川県"
    assert r["city"] == "川崎市"

def test_none():
    r = parse_address(None)
    assert r["prefecture"] is None
    assert r["ward"] is None

def test_unparseable():
    r = parse_address("不明な住所")
    assert r["prefecture"] is None


# --- initial cost ---
def test_initial_basic():
    r = estimate_initial_cost(rent=118000, deposit=118000, key_money=0)
    # 118000 + 0 + 64900 + 118000 + 40000 = 340900
    assert r == 340900

def test_initial_zero_deposit_key():
    r = estimate_initial_cost(rent=100000, deposit=0, key_money=0)
    # 0 + 0 + 55000 + 100000 + 40000 = 195000
    assert r == 195000

def test_initial_custom():
    r = estimate_initial_cost(
        rent=100000, deposit=0, key_money=0,
        broker_fee_rate=0.5, prepaid_rent_months=0, misc_cost=20000,
    )
    assert r == 70000


# --- dedup ---
def test_hash_stable():
    h1 = generate_listing_hash("蒲田5-20-3", "〇〇マンション", "1LDK", 42.3, 3, 118000)
    h2 = generate_listing_hash("蒲田5-20-3", "〇〇マンション", "1LDK", 42.3, 3, 118000)
    assert h1 == h2
    assert len(h1) == 32

def test_hash_differs():
    h1 = generate_listing_hash("A", "T", "1LDK", 42.3, 3, 118000)
    h2 = generate_listing_hash("B", "T", "1LDK", 42.3, 3, 118000)
    assert h1 != h2

def test_hash_none_fields():
    h = generate_listing_hash(None, None, None, None, None, None)
    assert len(h) == 32