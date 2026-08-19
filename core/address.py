import re

PREFECTURES = [
    "北海道", "青森県", "岩手県", "宮城県", "秋田県", "山形県", "福島県",
    "茨城県", "栃木県", "群馬県", "埼玉県", "千葉県", "東京都", "神奈川県",
    "新潟県", "富山県", "石川県", "福井県", "山梨県", "長野県",
    "岐阜県", "静岡県", "愛知県", "三重県",
    "滋賀県", "京都府", "大阪府", "兵庫県", "奈良県", "和歌山県",
    "鳥取県", "島根県", "岡山県", "広島県", "山口県",
    "徳島県", "香川県", "愛媛県", "高知県",
    "福岡県", "佐賀県", "長崎県", "熊本県", "大分県", "宮崎県", "鹿児島県", "沖縄県",
]

DESIGNATED_CITIES = [
    "札幌市", "仙台市", "千葉市", "横浜市", "川崎市", "相模原市", "埼玉市",
    "名古屋市", "京都市", "大阪市", "堺市", "神戸市", "岡山市", "広島市",
    "北九州市", "福岡市", "熊本市",
]

CITY_TO_PREF = {
    "札幌市": "北海道", "仙台市": "宮城県", "千葉市": "千葉県",
    "横浜市": "神奈川県", "川崎市": "神奈川県", "相模原市": "神奈川県",
    "埼玉市": "埼玉県", "名古屋市": "愛知県", "京都市": "京都府",
    "大阪市": "大阪府", "堺市": "大阪府", "神戸市": "兵庫県",
    "岡山市": "岡山県", "広島市": "広島県", "北九州市": "福岡県",
    "福岡市": "福岡県", "熊本市": "熊本県",
}


def parse_address(text):
    """拆分日文地址 -> {prefecture, city, ward, address}
    东京都: prefecture=東京都, ward=〇〇区, city=None
    横浜市神奈川区: prefecture=神奈川県, city=横浜市, ward=神奈川区
    省略県名时从政令指定都市反推
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