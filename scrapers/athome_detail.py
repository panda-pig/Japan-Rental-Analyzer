from bs4 import BeautifulSoup
from scrapers.models import RawListing
import re

ATHOME_BASE = "https://www.athome.jp"


def parse_athome_detail(html, detail_url=""):
    """解析 athome (athome.jp) 物件详情页,提取为 RawListing。

    athome 详情页通常用 table 结构展示基本情報。
    实际部署后可能需要根据真实 HTML 调整选择器。
    """
    soup = BeautifulSoup(html, "html.parser")

    title = ""
    for tag in soup.select("h1, .bukkenTitle, .bukkenName, .detail-title"):
        t = tag.get_text(strip=True)
        if t:
            title = t
            break

    kv = {}
    for tr in soup.select("tr"):
        th = tr.select_one("th")
        td = tr.select_one("td")
        if th and td:
            kv[th.get_text(strip=True)] = td.get_text(strip=True)

    rent_raw = kv.get("賃料", "")
    management_fee_raw = kv.get("管理費等", kv.get("管理費", None))
    if management_fee_raw == "-":
        management_fee_raw = None

    deposit_raw = kv.get("敷金", "0")
    key_money_raw = kv.get("礼金", "0")
    if deposit_raw == "-":
        deposit_raw = "0"
    if key_money_raw == "-":
        key_money_raw = "0"

    walk_text = kv.get("交通", None)
    nearest_station = walk_text
    walk_raw = walk_text

    address_raw = kv.get("所在地", None)

    age_raw = kv.get("築年月", None)

    layout = kv.get("間取り", None)

    area_raw = kv.get("専有面積", None)

    floor_raw = kv.get("所在階", kv.get("所在階/階数", None))

    features = []
    full_text = soup.get_text()
    for kw in ["バストイレ別", "オートロック", "宅配ボックス", "南向き", "エアコン", "2人入居可"]:
        if kw in full_text:
            features.append(kw)

    return RawListing(
        platform="athome",
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