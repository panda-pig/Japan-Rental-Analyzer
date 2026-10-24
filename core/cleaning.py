import re
import unicodedata
from decimal import Decimal
from datetime import datetime


def parse_money(text):
    """解析日文金额字符串为整数円。
    '12.8万円' -> 128000
    '8,000円' -> 8000
    'なし' -> 0
    None/'' -> None
    """
    if text is None:
        return None
    s = unicodedata.normalize("NFKC", str(text)).strip()
    if s == "":
        return None
    if s in ("なし", "無"):
        return 0
    if re.fullmatch(r"\d+", s):
        return int(s)
    m = re.search(r"(\d[\d,]*(?:\.\d+)?)\s*(万)?\s*円", s)
    if m:
        num_str = m.group(1).replace(",", "")
        val = Decimal(num_str)
        if m.group(2):
            val *= 10000
        return int(val)
    return None


def parse_deposit_key_money(text, rent):
    """解析敷金/礼金。'1ヶ月' -> rent*1, 'なし' -> 0。"""
    if text is None:
        return None
    s = unicodedata.normalize("NFKC", str(text)).strip()
    if not s:
        return None
    if s in ("なし", "無"):
        return 0
    m = re.fullmatch(r"(\d+(?:\.\d+)?)\s*(?:ヶ|ケ|か|カ|箇)?月(?:分)?", s)
    if m:
        return int(Decimal(m.group(1)) * rent) if rent is not None else None
    if "月" in s:
        return None
    return parse_money(s)


def parse_area(text):
    """'42.3m²' / '42.3㎡' / '42.3平米' -> 42.3"""
    if text is None:
        return None
    s = str(text).strip()
    if s == "":
        return None
    m = re.search(r"([\d.]+)\s*(?:m²|㎡|平米)", s)
    if m:
        return float(m.group(1))
    m = re.search(r"([\d.]+)", s)
    if m:
        return float(m.group(1))
    return None


def parse_station_walk(text):
    """Return the nearest station and its own walking time as one pair."""
    if not text:
        return None
    s = unicodedata.normalize("NFKC", str(text))
    pairs = re.findall(r'([^/\s線「」『』"]{1,30}?)(?:[」』"]?駅[」』"]?|[」』"])\s*(?:徒歩|歩)?\s*(\d{1,3})\s*分', s)
    return min(((name, int(minutes)) for name, minutes in pairs),
               key=lambda pair: pair[1], default=None)


def parse_walk_minutes(text):
    """'徒歩8分' / '歩8分' / '駅徒歩 12分' -> 8"""
    if text is None:
        return None
    s = unicodedata.normalize("NFKC", str(text)).strip()
    if s == "":
        return None
    pair = parse_station_walk(s)
    if pair:
        return pair[1]
    # Bus travel and a walk from the bus stop are not walking time to a station.
    if "バス" in s or "停歩" in s:
        return None
    m = re.search(r"(\d+)\s*分", s)
    if m:
        return int(m.group(1))
    return None


def parse_floor(text):
    """Return unit floor and above-ground building height independently."""
    if text is None:
        return (None, None)
    s = unicodedata.normalize("NFKC", str(text)).strip()
    if s == "":
        return (None, None)
    total = None

    def building(match):
        nonlocal total
        if match.group(1) != "地下":
            total = int(match.group(2))
        return " "

    # Remove the whole building description, including its basement, before
    # reading the unit floor. Its order relative to the unit varies by source.
    basement = r"(?:\s*[,、・]?\s*\(?\s*地下\s*\d+\s*階\s*\)?)?"
    s = re.sub(r"(地上|地下)?\s*(\d+)\s*階" + basement + r"\s*建(?:て)?" + basement, building, s)
    s = re.sub(r"(地上)\s*(\d+)\s*階" + basement, building, s)
    m = re.search(r"(地下|B)?\s*(\d+)(?:\s*[-~〜]\s*(\d+))?\s*(?:階|F)", s, re.I)
    if not m:
        return (None, total)
    floors = [int(value) for value in (m.group(2), m.group(3)) if value is not None]
    if m.group(1):
        floors = [-value for value in floors]
    return (min(floors), total)


def parse_building_age(text):
    """'築12年' -> 12, '新築' -> 0, '2010年3月' -> 相对当前年份, '築浅' -> None"""
    if text is None:
        return None
    s = str(text).strip()
    if s == "":
        return None
    if "新築" in s:
        return 0
    if "築浅" in s:
        return None
    m = re.search(r"築(\d+)\s*年", s)
    if m:
        return int(m.group(1))
    m = re.search(r"(\d{4})\s*年", s)
    if m:
        built_year = int(m.group(1))
        return max(0, datetime.now().year - built_year)
    return None


PET_KEYWORDS = ["ペット可", "ペット相談", "小型犬可", "猫可", "犬可"]

FEATURE_MAP = {
    "バストイレ別": "bath_toilet_separate",
    "オートロック": "auto_lock",
    "宅配ボックス": "delivery_box",
    "南向き": "south_facing",
    "エアコン": "aircon",
    "2人入居可": "two_person_allowed",
}

FEATURE_FIELDS = [
    "bath_toilet_separate", "auto_lock", "delivery_box",
    "south_facing", "aircon", "two_person_allowed",
]


def parse_pet_allowed(text):
    if text is None:
        return None
    s = re.sub(r"\s+", "", unicodedata.normalize("NFKC", str(text)))
    if re.search(r"ペット(?:飼育|相談)?(?:不可|禁止|NG)", s):
        return 0
    for kw in PET_KEYWORDS:
        if re.search(re.escape(kw) + r"(?!不可|禁止|NG)", s):
            return 1
    if re.search(r"(?:小型犬|犬|猫)(?:飼育|相談)?(?:不可|禁止|NG)", s):
        return 0
    return None


def parse_features(items):
    """items: list[str] 设备关键词列表 -> dict 各字段 0/1"""
    result = {f: 0 for f in FEATURE_FIELDS}
    if not items:
        return result
    for item in items:
        s = str(item)
        for kw, field in FEATURE_MAP.items():
            if kw in s:
                result[field] = 1
    return result
