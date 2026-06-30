from bs4 import BeautifulSoup
from scrapers.models import RawListing

ATHOME_BASE = "https://www.athome.jp"


def parse_athome(html, source_url=""):
    soup = BeautifulSoup(html, "html.parser")
    results = []
    for item in soup.select(".bukkenItem"):
        title_tag = item.select_one(".bukkenName")
        if not title_tag:
            continue
        title = title_tag.get_text(strip=True)
        href = title_tag.get("href", "")
        detail_url = href if href.startswith("http") else ATHOME_BASE + href
        price = item.select_one(".price")
        other = item.select_one(".priceOther")
        layout = item.select_one(".layout")
        area = item.select_one(".area")
        floor = item.select_one(".floor")
        age = item.select_one(".age")
        station = item.select_one(".station")
        addr = item.select_one(".address")
        results.append(RawListing(
            platform="athome",
            detail_url=detail_url,
            title=title,
            rent_raw=price.get_text(strip=True) if price else "",
            management_fee_raw=other.get_text(strip=True) if other else None,
            layout=layout.get_text(strip=True) if layout else None,
            area_raw=area.get_text(strip=True) if area else None,
            floor_raw=floor.get_text(strip=True) if floor else None,
            age_raw=age.get_text(strip=True) if age else None,
            walk_raw=station.get_text(strip=True) if station else None,
            nearest_station=station.get_text(strip=True) if station else None,
            address_raw=addr.get_text(strip=True) if addr else None,
        ))
    return results