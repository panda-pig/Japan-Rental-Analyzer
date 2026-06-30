import hashlib


def generate_listing_hash(address, title, layout, area_m2, floor, rent):
    """生成房源近似去重 hash。"""
    raw_key = f"{address or ''}|{title or ''}|{layout or ''}|{area_m2 or ''}|{floor or ''}|{rent or ''}"
    return hashlib.md5(raw_key.encode("utf-8")).hexdigest()