from bs4 import BeautifulSoup
from scrapers.models import RawListing

HOMES_BASE = "https://www.homes.co.jp"


def parse_homes(html, source_url=""):
    """解析 HOMES 搜索结果页。

    真实结构:每个 .bukken 是一条房源,
    .bukkenName 是标题,<a> 有详情链接,
    .figcaption > span 里的文本按 <br> 分行包含价格/车站/面积/間取り。
    """
    soup = BeautifulSoup(html, "html.parser")
    results = []
    for item in soup.select(".bukken"):
        title_tag = item.select_one(".bukkenName")
        if not title_tag:
            continue
        title = title_tag.get_text(strip=True)

        link_tag = item.find("a", href=True)
        if not link_tag:
            continue
        href = link_tag.get("href", "")
        detail_url = href if href.startswith("http") else HOMES_BASE + href

        # figcaption 里的文本行
        caption = item.select_one(".figcaption")
        lines = []
        if caption:
            # 取 span 直接子节点的文本
            for child in caption.find_all("span", recursive=False):
                text = child.get_text(separator="\n", strip=True)
                lines.extend(text.split("\n"))
            # 如果直接子 span 没拿到,退回全文本
            if not lines:
                lines = [l.strip() for l in caption.get_text(separator="\n", strip=True).split("\n") if l.strip()]

        rent_raw = ""
        nearest_station = None
        area_raw = None
        layout = None

        for line in lines:
            line = line.strip()
            if "万円" in line and "徒歩" not in line:
                rent_raw = line
            elif "徒歩" in line:
                nearest_station = line
                # 车站名: "菊名駅 徒歩12分"
            elif "m²" in line or "m2" in line or "㎡" in line:
                area_raw = line
            elif line and line not in ("物件詳細を見る", "もっと見る"):
                # 间取り如 1K, 1LDK 等
                if not layout and any(k in line for k in ["K", "DK", "LDK", "R"]):
                    if len(line) <= 8:
                        layout = line

        results.append(RawListing(
            platform="HOMES",
            detail_url=detail_url,
            title=title,
            rent_raw=rent_raw,
            management_fee_raw=None,
            deposit_raw=None,
            key_money_raw=None,
            layout=layout,
            area_raw=area_raw,
            floor_raw=None,
            age_raw=None,
            walk_raw=nearest_station,
            nearest_station=nearest_station,
            address_raw=None,
        ))
    return results