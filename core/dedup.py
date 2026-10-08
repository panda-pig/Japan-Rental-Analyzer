import hashlib
from urllib.parse import unquote_plus, urlsplit, urlunsplit


def canonical_listing_url(url):
    """Strip sharing metadata, preserving parameters that identify a listing."""
    if not url:
        return url
    parts = urlsplit(url.strip())
    tracking = {"fbclid", "gclid", "yclid", "msclkid"}
    query = []
    for part in parts.query.split("&"):
        key = unquote_plus(part.split("=", 1)[0]).lower()
        if not key.startswith("utm_") and key not in tracking:
            query.append(part)
    return urlunsplit((parts.scheme.lower(), parts.netloc.lower(), parts.path,
                       "&".join(query), ""))


def generate_listing_hash(address, title, layout, area_m2, floor, rent):
    """生成房源近似去重 hash。"""
    raw_key = f"{address or ''}|{title or ''}|{layout or ''}|{area_m2 or ''}|{floor or ''}|{rent or ''}"
    return hashlib.md5(raw_key.encode("utf-8")).hexdigest()
