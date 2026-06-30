import re
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
    s = str(text).strip()
    if s == "":
        return None
    if s in ("なし", "無"):
        return 0
    if re.fullmatch(r"\d+", s):
        return int(s)
    m = re.search(r"([\d,]+\.?\d*)\s*万?円", s)
    if m:
        num_str = m.group(1).replace(",", "")
        val = float(num_str)
        if "万" in s:
            val *= 10000
        return int(val)
    m = re.search(r"([\d,]+)\s*円", s)
    if m:
        return int(m.group(1).replace(",", ""))
    return None


def parse_deposit_key_money(text, rent):
    """解析敷金/礼金。'1ヶ月' -> rent*1, 'なし' -> 0。"""
    if text is None:
        return None
    s = str(text).strip()
    if s == "" or s in ("なし", "無"):
        return 0
    m = re.search(r"(\d+)\s*ヶ月", s)
    if m and rent is not None:
        return int(rent) * int(m.group(1))
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


def parse_walk_minutes(text):
    """'徒歩8分' / '歩8分' / '駅徒歩 12分' -> 8"""
    if text is None:
        return None
    s = str(text).strip()
    if s == "":
        return None
    m = re.search(r"(\d+)\s*分", s)
    if m:
        return int(m.group(1))
    return None


def parse_floor(text):
    """'3階/5階建' -> (3, 5), '地下1階' -> (-1, None)"""
    if text is None:
        return (None, None)
    s = str(text).strip()
    if s == "":
        return (None, None)
    floor = None
    total = None
    m = re.search(r"地下(\d+)\s*階", s)
    if m:
        floor = -int(m.group(1))
    else:
        m = re.search(r"(\d+)\s*階", s)
        if m:
            floor = int(m.group(1))
    m = re.search(r"(\d+)\s*階建", s)
    if m:
        total = int(m.group(1))
    return (floor, total)


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
        return 0
    s = str(text)
    if "不可" in s:
        return 0
    for kw in PET_KEYWORDS:
        if kw in s:
            return 1
    return 0


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