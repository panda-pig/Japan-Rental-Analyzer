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
    if floor >= 2:
        return 10
    return 0


def _pet_score(pet):
    if pet == 1:
        return 15
    if pet is None:
        return 5
    return 0


def _station_score(walk, max_walk):
    if walk is None:
        return 3
    if walk <= 5:
        return 10
    if walk <= 10:
        return 8
    if walk <= 15:
        return 5
    if walk <= 20:
        return 2
    return 0


def _age_score(age, max_age):
    if age is None:
        return 3
    if age <= 5:
        return 10
    if age <= 10:
        return 8
    if age <= 20:
        return 5
    if age <= 30:
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
                     commute_minutes=None) -> ScoreResult:
    bs = _budget_score(inp.total_monthly_cost, max_cost)
    as_ = _area_score(inp.area_m2, ideal_area)
    fs = _floor_score(inp.floor, min_floor)
    ps = _pet_score(inp.pet_allowed)
    ss = _station_score(inp.walk_minutes, max_walk)
    ags = _age_score(inp.building_age, max_age)
    ics = _initial_cost_score(inp.deposit, inp.key_money, inp.rent)
    cs = _commute_score(commute_minutes)
    commute_resolved = 1 if cs is not None else 0
    cs_val = cs if cs is not None else 0

    # 各维度得分已是 0~weight 刻度,直接求和后按权重总和归一化到 0~100
    weight_sum = (w.budget + w.area + w.floor + w.pet + w.station +
                  w.age + w.initial_cost)
    score_sum = bs + as_ + fs + ps + ss + ags + ics
    if commute_resolved:
        weight_sum += w.commute
        score_sum += cs_val
    total = int(score_sum / weight_sum * 100) if weight_sum else 0

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