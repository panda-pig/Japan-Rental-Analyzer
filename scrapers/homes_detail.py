from bs4 import BeautifulSoup
from scrapers.models import RawListing
import re

HOMES_BASE = "https://www.homes.co.jp"


def parse_homes_detail(html, detail_url=""):
    """解析 HOMES (homes.co.jp) 物件详情页,提取为 RawListing。"""
    soup = BeautifulSoup(html, "html.parser")

    title = ""
    for h1 in soup.select("h1"):
        t = h1.get_text(strip=True)
        if t:
            title = re.sub(r"（.*$", "", t).strip()
            break

    kv = {}
    for dt in soup.select("dt"):
        dd = dt.find_next_sibling("dd")
        if dd:
            kv[dt.get_text(strip=True)] = dd.get_text(strip=True)

    rent_raw = kv.get("賃料", "")

    management_fee_raw = kv.get("管理費等", None)
    if management_fee_raw == "-":
        management_fee_raw = None

    deposit_raw = "0"
    key_money_raw = "0"
    dk = kv.get("敷金/礼金", "")
    if dk:
        parts = dk.split("/")
        if parts:
            deposit_raw = parts[0] if parts[0] != "無" else "0"
        if len(parts) > 1:
            key_money_raw = parts[1] if parts[1] != "無" else "0"

    walk_text = kv.get("交通", None)
    nearest_station = walk_text
    walk_raw = walk_text

    address_raw = kv.get("所在地", None)
    if address_raw:
        address_raw = re.sub(r"地図を見る$", "", address_raw).strip()

    age_raw = kv.get("築年月", None)

    layout = kv.get("間取り", None)

    area_raw = kv.get("専有面積", None)

    floor_raw = kv.get("所在階/階数", None)

    features = []
    full_text = soup.get_text()
    for kw in ["バストイレ別", "オートロック", "宅配ボックス", "南向き", "エアコン", "2人入居可"]:
        if kw in full_text:
            features.append(kw)

    return RawListing(
        platform="HOMES",
        detail_url=detail_url,
        title=title,
        rent_raw=rent_raw,
        management_fee_raw=management_fee_raw,
        deposit_raw=deposit_raw,
        key_money_raw=key_money_raw,
        layout=layout,
        area_raw=area_raw,
        floor_raw=floor_raw,
        age_raw=age_raw,
        walk_raw=walk_raw,
        nearest_station=nearest_station,
        address_raw=address_raw,
        features_raw=features,
    )