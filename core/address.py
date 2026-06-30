import re

PREFECTURES = [
    "東京都", "神奈川県", "埼玉県", "千葉県",
    "茨城県", "栃木県", "群馬県",
]

DESIGNATED_CITIES = [
    "横浜市", "川崎市", "相模原市", "埼玉市", "千葉市",
]

# 政令指定都市 -> 所属都道府県(地址中常省略県名)
CITY_TO_PREF = {
    "横浜市": "神奈川県", "川崎市": "神奈川県", "相模原市": "神奈川県",
    "埼玉市": "埼玉県", "千葉市": "千葉県",
}


def parse_address(text):
    """拆分日文地址 -> {prefecture, city, ward, address}
    东京都: prefecture=東京都, ward=〇〇区, city=None
    横浜市神奈川区: prefecture=神奈川県, city=横浜市, ward=神奈川区
    """
    result = {"prefecture": None, "city": None, "ward": None, "address": None}
    if text is None:
        return result
    s = str(text).strip()
    if s == "":
        return result

    rest = s
    for pref in PREFECTURES:
        if s.startswith(pref):
            result["prefecture"] = pref
            rest = s[len(pref):]
            break

    matched_city = False
    for city in DESIGNATED_CITIES:
        if rest.startswith(city):
            result["city"] = city
            # 省略県名时从市反推
            if result["prefecture"] is None:
                result["prefecture"] = CITY_TO_PREF.get(city)
            rest = rest[len(city):]
            m = re.match(r"(\S+?区)", rest)
            if m:
                result["ward"] = m.group(1)
                rest = rest[len(m.group(1)):]
            matched_city = True
            break

    if not matched_city:
        m = re.match(r"(\S+?区)", rest)
        if m:
            result["ward"] = m.group(1)
            rest = rest[len(m.group(1)):]

    result["address"] = rest.strip() if rest.strip() else None
    return result