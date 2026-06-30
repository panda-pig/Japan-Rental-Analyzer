from bs4 import BeautifulSoup
from scrapers.models import RawListing

SUUMO_BASE = "https://suumo.jp"


def parse_suumo(html, source_url=""):
    """解析 SUUMO 搜索结果页。

    真实结构:每个 .cassetteitem 是一栋楼(物件),
    楼下 <tbody><tr> 是每个房间(空室),每个房间产出一条 RawListing。
    """
    soup = BeautifulSoup(html, "html.parser")
    results = []
    for building in soup.select(".cassetteitem"):
        # 楼级信息
        title_tag = building.select_one(".cassetteitem_content-title")
        if not title_tag:
            continue
        title = title_tag.get_text(strip=True)

        # 地址
        addr_tag = building.select_one(".cassetteitem_detail-col1")
        address = addr_tag.get_text(strip=True) if addr_tag else None

        # 车站/徒歩(取第一个)
        station_texts = building.select(".cassetteitem_detail-text")
        nearest_station = station_texts[0].get_text(strip=True) if station_texts else None
        walk_raw = nearest_station  # "東急東横線/白楽駅 歩6分"

        # 築年/阶建
        detail3 = building.select_one(".cassetteitem_detail-col3")
        age_floor_text = detail3.get_text(strip=True) if detail3 else ""

        # 每个房间行
        room_rows = building.select("tbody tr")
        if not room_rows:
            # 有些页面用 .cassetteitem_item
            room_rows = building.select(".cassetteitem_item")
        if not room_rows:
            continue

        for tr in room_rows:
            tds = tr.select("td")
            if len(tds) < 6:
                continue
            # td[2] = 楼层 (1階)
            # td[3] = 賃料 + 管理費 (10.7万円4000円)
            # td[4] = 敷金/礼金
            # td[5] = 間取り/専有面積 (1LDK40.4m2)
            floor_raw = tds[2].get_text(strip=True) if len(tds) > 2 else None
            rent_fee_text = tds[3].get_text(strip=True) if len(tds) > 3 else ""
            deposit_key_text = tds[4].get_text(strip=True) if len(tds) > 4 else ""
            layout_area_text = tds[5].get_text(strip=True) if len(tds) > 5 else ""

            # 详情链接
            detail_link = tr.select_one("a[href*='/chintai/']")
            if detail_link:
                href = detail_link.get("href", "")
                detail_url = href if href.startswith("http") else SUUMO_BASE + href
            else:
                continue  # 没链接的行跳过

            # 用 class 精确提取各字段(真实 SUUMO 结构)
            rent_tag = tr.select_one(".cassetteitem_price--rent")
            fee_tag = tr.select_one(".cassetteitem_price--administration")
            dep_tag = tr.select_one(".cassetteitem_price--deposit")
            key_tag = tr.select_one(".cassetteitem_price--gratuity")
            madori_tag = tr.select_one(".cassetteitem_madori")
            menseki_tag = tr.select_one(".cassetteitem_menseki")

            rent_raw = rent_tag.get_text(strip=True) if rent_tag else ""
            management_fee_raw = fee_tag.get_text(strip=True) if fee_tag else None
            deposit_raw = dep_tag.get_text(strip=True) if dep_tag else None
            key_money_raw = key_tag.get_text(strip=True) if key_tag else None
            layout = madori_tag.get_text(strip=True) if madori_tag else None
            area_raw = menseki_tag.get_text(strip=True) if menseki_tag else None

            # "-" を 0 に
            if deposit_raw == "-":
                deposit_raw = "0"
            if key_money_raw == "-":
                key_money_raw = "0"

            # 築年数从楼级信息提取
            age_raw = age_floor_text

            results.append(RawListing(
                platform="SUUMO",
                detail_url=detail_url,
                title=title,
                rent_raw=rent_raw or rent_fee_text,
                management_fee_raw=management_fee_raw,
                deposit_raw=deposit_raw,
                key_money_raw=key_money_raw,
                layout=layout,
                area_raw=area_raw or layout_area_text,
                floor_raw=floor_raw,
                age_raw=age_raw,
                walk_raw=walk_raw,
                nearest_station=nearest_station,
                address_raw=address,
            ))
    return results