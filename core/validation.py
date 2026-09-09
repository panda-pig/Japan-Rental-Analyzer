"""Validation shared by API writes; do not let invalid settings reach SQLite."""
from datetime import date

STATUSES = ("気になる", "問い合わせ予定", "問い合わせ済み", "内見予定", "内見済み",
            "申込候補", "申込済み", "見送り", "成約不可")
LABELS = {
    "max_total_monthly_cost": "月額上限", "min_area_m2": "面積下限", "ideal_area_m2": "理想面積",
    "min_floor": "最低階", "max_walk_minutes": "徒歩上限", "ideal_walk_minutes": "理想徒歩分",
    "max_building_age": "築年数上限", "broker_fee_rate": "仲介手数料率",
    "prepaid_rent_months": "前家賃", "misc_cost": "固定雑費", "priority": "優先度",
}


def number(value, name, low, high, integer=False):
    name = LABELS.get(name, name)
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{name}: 数値を入力してください")
    if not low <= value <= high or (integer and int(value) != value):
        raise ValueError(f"{name}: {low}〜{high}の{'整数' if integer else '数値'}を入力してください")
    return int(value) if integer else value


def preferences(data, current):
    rules = {
        "max_total_monthly_cost": (1, 10000000, True),
        "min_area_m2": (1, 10000, False), "ideal_area_m2": (1, 10000, False),
        "min_floor": (-10, 200, True), "require_pet_allowed": (0, 1, True),
        "max_walk_minutes": (1, 240, True), "ideal_walk_minutes": (1, 240, True),
        "max_building_age": (1, 300, True), "broker_fee_rate": (0, 5, False),
        "prepaid_rent_months": (0, 24, False), "misc_cost": (0, 10000000, True),
    }
    rules.update({name + "_weight": (0, 100, True) for name in
                  ("budget", "area", "commute", "floor", "pet", "station", "age", "initial_cost")})
    if set(data) - (rules.keys() | {"target_station"}):
        raise ValueError("未対応の設定項目があります")
    clean = {k: number(v, k, *rules[k]) for k, v in data.items() if k in rules}
    if "target_station" in data:
        station = data["target_station"]
        if not isinstance(station, str) or len(station) > 100:
            raise ValueError("target_station: 100文字以内の駅名を入力してください")
        clean["target_station"] = station.strip()
    merged = {**current, **clean}
    if merged["min_area_m2"] > merged["ideal_area_m2"]:
        raise ValueError("面積下限は理想面積以下にしてください")
    # ideal_walk_minutes is a legacy field, unused by scoring and not exposed in
    # Settings. It must not prevent users from lowering their walking limit.
    if sum(merged[k] or 0 for k in rules if k.endswith("_weight") and k != "commute_weight") <= 0:
        raise ValueError("通勤以外の評価ウェイトを1項目以上設定してください")
    return clean


def status_fields(data, creating=False):
    allowed = {"status", "priority", "memo", "contacted", "viewing_date", "decision"}
    if creating:
        allowed.add("listing_id")
    if set(data) - allowed:
        raise ValueError("未対応のステータス項目があります")
    clean = dict(data)
    if creating:
        clean["listing_id"] = number(data.get("listing_id"), "listing_id", 1, 2**63 - 1, True)
        clean.setdefault("status", "気になる")
    if "status" in clean and clean["status"] not in STATUSES:
        raise ValueError("status: 有効なステータスを選択してください")
    for key, limit in (("memo", 5000), ("decision", 500)):
        if key in clean and clean[key] is not None:
            if not isinstance(clean[key], str) or len(clean[key]) > limit:
                raise ValueError(f"{key}: {limit}文字以内で入力してください")
    for key, bounds in (("priority", (1, 5)), ("contacted", (0, 1))):
        if key in clean:
            clean[key] = number(clean[key], key, *bounds, integer=True)
    if "viewing_date" in clean:
        value = clean["viewing_date"]
        if value in (None, ""):
            clean["viewing_date"] = None
        elif not isinstance(value, str) or len(value) != 10 or date.fromisoformat(value).isoformat() != value:
            raise ValueError("viewing_date: YYYY-MM-DDで入力してください")
    return clean
