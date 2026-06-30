from dataclasses import dataclass, field
from typing import Optional


@dataclass
class RawListing:
    platform: str
    detail_url: str
    title: str
    rent_raw: str = ""
    management_fee_raw: Optional[str] = None
    deposit_raw: Optional[str] = None
    key_money_raw: Optional[str] = None
    layout: Optional[str] = None
    area_raw: Optional[str] = None
    floor_raw: Optional[str] = None
    age_raw: Optional[str] = None
    nearest_station: Optional[str] = None
    walk_raw: Optional[str] = None
    address_raw: Optional[str] = None
    features_raw: list = field(default_factory=list)
    image_url: Optional[str] = None