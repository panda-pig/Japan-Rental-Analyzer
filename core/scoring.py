from dataclasses import dataclass


@dataclass
class Weights:
    budget: int = 20
    area: int = 15
    commute: int = 15
    floor: int = 10
    pet: int = 15
    station: int = 10
    age: int = 10
    initial_cost: int = 5


# 各次元の満点。「その物件がその軸でどれだけ良いか」の尺度であり、重みとは独立。
DIM_MAX = {
    "budget": 20, "area": 15, "commute": 15, "floor": 10,
    "pet": 15, "station": 10, "age": 10, "initial_cost": 5,
}


@dataclass
class ScoreInput:
    total_monthly_cost: int
    area_m2: float
    floor: int
    pet_allowed: int
    walk_minutes: int
    building_age: int
    deposit: int
    key_money: int
    rent: int


@dataclass
class ScoreResult:
    budget_score: int
    area_score: int
    commute_score: int
    floor_score: int
    pet_score: int
    station_score: int
    age_score: int
    initial_cost_score: int
    feature_score: int
    total_score: int
    score_reason: str
    commute_resolved: int


def _budget_score(total, max_cost):
    if total is None:
        return 3
    if total <= max_cost:
        return 20
    if total <= max_cost + 10000:
        return 10
    if total <= max_cost + 20000:
        return 5
    return 0


def _area_score(area, ideal, minimum=35):
    if area is None:
        return 3
    if area >= ideal:
        return 15
    if area >= minimum:
        return 10
    if area >= 30:
        return 5
    return 0


def _floor_score(floor, min_floor):
    if floor is None:
        return 3
    return 10 if floor >= (min_floor or 2) else 0


def _pet_score(pet):
    if pet == 1:
        return 15
    if pet is None:
        return 5
    return 0


def _station_score(walk, max_walk):
    """許容徒歩分を基準に段階評価。既定(15分)では 5/10/15/20分 の従来の区切りと一致する。"""
    if walk is None:
        return 3
    limit = max_walk or 15
    if walk <= limit / 3:
        return 10
    if walk <= limit * 2 / 3:
        return 8
    if walk <= limit:
        return 5
    if walk <= limit * 4 / 3:
        return 2
    return 0


def _age_score(age, max_age):
    """許容築年数を基準に段階評価。既定(20年)では 5/10/20/30年 の従来の区切りと一致する。"""
    if age is None:
        return 3
    limit = max_age or 20
    if age <= limit / 4:
        return 10
    if age <= limit / 2:
        return 8
    if age <= limit:
        return 5
    if age <= limit * 1.5:
        return 2
    return 0


def _initial_cost_score(deposit, key_money, rent):
    d = deposit or 0
    k = key_money or 0
    if d == 0 and k == 0:
        return 5
    if k == 0:
        return 4
    total_months = 0
    if rent:
        total_months = (d + k) / rent
    if total_months <= 1:
        return 3
    if total_months <= 2:
        return 1
    return 0


def _commute_score(minutes):
    if minutes is None:
        return None
    if minutes <= 30:
        return 15
    if minutes <= 45:
        return 12
    if minutes <= 60:
        return 8
    if minutes <= 90:
        return 4
    return 0


def calculate_scores(inp: ScoreInput, w: Weights, max_cost, ideal_area,
                     min_floor, max_walk, max_age, broker_rate, prepaid, misc,
                     commute_minutes=None, min_area=35) -> ScoreResult:
    bs = _budget_score(inp.total_monthly_cost, max_cost)
    as_ = _area_score(inp.area_m2, ideal_area, min_area or 35)
    fs = _floor_score(inp.floor, min_floor)
    ps = _pet_score(inp.pet_allowed)
    ss = _station_score(inp.walk_minutes, max_walk)
    ags = _age_score(inp.building_age, max_age)
    ics = _initial_cost_score(inp.deposit, inp.key_money, inp.rent)
    cs = _commute_score(commute_minutes)
    commute_resolved = 1 if cs is not None else 0
    cs_val = cs if cs is not None else 0

    parts = [
        ("budget", bs, w.budget), ("area", as_, w.area), ("floor", fs, w.floor),
        ("pet", ps, w.pet), ("station", ss, w.station), ("age", ags, w.age),
        ("initial_cost", ics, w.initial_cost),
    ]
    if commute_resolved:
        parts.append(("commute", cs_val, w.commute))

    weight_sum = sum(max(wt or 0, 0) for _n, _s, wt in parts)
    if weight_sum:
        achieved = sum((s / DIM_MAX[n]) * max(wt or 0, 0) for n, s, wt in parts)
        total = int(round(achieved / weight_sum * 100))
    else:
        total = 0
    total = max(0, min(100, total))

    reasons = []
    if inp.total_monthly_cost and inp.total_monthly_cost <= max_cost:
        reasons.append(f"月額{max_cost // 10000}万円以内")
    if inp.area_m2 and inp.area_m2 >= ideal_area:
        reasons.append(f"{ideal_area}㎡以上")
    if inp.floor and inp.floor >= 2:
        reasons.append("2階以上")
    if inp.walk_minutes and inp.walk_minutes <= 10:
        reasons.append("駅徒歩10分以内")
    if inp.pet_allowed == 1:
        reasons.append("ペット可/相談可")
    if commute_resolved and cs_val >= 12:
        reasons.append(f"通勤{commute_minutes}分以内")
    if not commute_resolved:
        reasons.append("※通勤分未計算")
    score_reason = " / ".join(reasons)

    return ScoreResult(
        budget_score=bs, area_score=as_, commute_score=cs_val,
        floor_score=fs, pet_score=ps, station_score=ss, age_score=ags,
        initial_cost_score=ics, feature_score=0,
        total_score=total, score_reason=score_reason,
        commute_resolved=commute_resolved,
    )