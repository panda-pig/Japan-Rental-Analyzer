from bs4 import BeautifulSoup
from scrapers.models import RawListing
import re

SUUMO_BASE = "https://suumo.jp"


def parse_suumo_detail(html, detail_url=""):
    """解析 SUUMO 单个房源详情页,提取为 RawListing。"""
    soup = BeautifulSoup(html, "html.parser")

    title_tag = soup.select_one("h1")
    title = title_tag.get_text(strip=True) if title_tag else ""

    tables = soup.select("table")
    kv = {}
    for t in tables:
        for tr in t.select("tr"):
            th = tr.select_one("th")
            td = tr.select_one("td")
            if th and td:
                kv[th.get_text(strip=True)] = td.get_text(strip=True)

    rent_fee = kv.get("賃料(管理費)", "")
    rent_raw = ""
    management_fee_raw = None
    if rent_fee:
        rm = re.search(r"([\d,.]+万?円)", rent_fee)
        if rm:
            rent_raw = rm.group(1)
        mm = re.search(r"\(([\d,]+円)\)", rent_fee)
        if mm:
            management_fee_raw = mm.group(1)

    deposit_raw = "0"
    key_money_raw = "0"
    for nl in soup.select(".property_view_note-list"):
        note_text = nl.get_text(separator=" ", strip=True).replace("\xa0", " ")
        if "敷金" not in note_text:
            continue
        dm = re.search(r"敷金:\s*([\d,.]+万?円|-)", note_text)
        km = re.search(r"礼金:\s*([\d,.]+万?円|-)", note_text)
        if dm:
            deposit_raw = dm.group(1) if dm.group(1) != "-" else "0"
        if km:
            key_money_raw = km.group(1) if km.group(1) != "-" else "0"
        break

    floor_raw = kv.get("階建", None)

    age_raw = kv.get("築年数", None)

    address_raw = kv.get("所在地", None)

    walk_text = kv.get("駅徒歩", None)
    nearest_station = walk_text
    walk_raw = walk_text

    layout = None
    area_raw = None
    for tr in soup.select("tr"):
        ths = tr.select("th")
        tds = tr.select("td.property_view_table-body")
        if len(ths) >= 2 and len(tds) >= 2:
            th_texts = [th.get_text(strip=True) for th in ths]
            if th_texts[0] == "間取り" and th_texts[1] == "専有面積":
                layout = tds[0].get_text(strip=True)
                area_raw = tds[1].get_text(strip=True)
                break

    condition = kv.get("条件", "")
    pet_text = condition if "ペット" in condition else ""

    features = []
    if "二人入居可" in condition:
        features.append("2人入居可")
    full_text = soup.get_text()
    for kw in ["バストイレ別", "オートロック", "宅配ボックス", "南向き", "エアコン"]:
        if kw in full_text:
            features.append(kw)

    return RawListing(
        platform="SUUMO",
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