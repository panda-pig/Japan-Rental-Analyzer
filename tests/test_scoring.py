import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.scoring import calculate_scores, ScoreInput, Weights


def _inp(**kw):
    defaults = dict(
        total_monthly_cost=120000, area_m2=42.3, floor=3, pet_allowed=1,
        walk_minutes=8, building_age=12, deposit=118000, key_money=0, rent=118000,
    )
    defaults.update(kw)
    return ScoreInput(**defaults)


def _kwargs(**kw):
    defaults = dict(
        max_cost=140000, ideal_area=40, min_floor=2, max_walk=15, max_age=20,
        broker_rate=0.55, prepaid=1, misc=40000, commute_minutes=None,
    )
    defaults.update(kw)
    return defaults


def test_budget_within():
    r = calculate_scores(_inp(), Weights(), **_kwargs())
    assert r.budget_score == 20


def test_area_full():
    r = calculate_scores(_inp(area_m2=42.3), Weights(), **_kwargs())
    assert r.area_score == 15


def test_floor_full():
    r = calculate_scores(_inp(floor=3), Weights(), **_kwargs())
    assert r.floor_score == 10


def test_pet_full():
    r = calculate_scores(_inp(pet_allowed=1), Weights(), **_kwargs())
    assert r.pet_score == 15


def test_station_score():
    r = calculate_scores(_inp(walk_minutes=8), Weights(), **_kwargs())
    assert r.station_score == 8


def test_age_score():
    r = calculate_scores(_inp(building_age=12), Weights(), **_kwargs())
    assert r.age_score == 5


def test_normalization_no_commute():
    """commute 降级时不计入分母,满分仍100"""
    r = calculate_scores(_inp(), Weights(), **_kwargs(commute_minutes=None))
    assert 0 <= r.total_score <= 100
    assert r.commute_resolved == 0


def test_commute_resolved():
    r = calculate_scores(_inp(), Weights(), **_kwargs(commute_minutes=40))
    assert r.commute_score == 12
    assert r.commute_resolved == 1


def test_commute_30min():
    r = calculate_scores(_inp(), Weights(), **_kwargs(commute_minutes=25))
    assert r.commute_score == 15


def test_commute_over_90():
    r = calculate_scores(_inp(), Weights(), **_kwargs(commute_minutes=100))
    assert r.commute_score == 0
    assert r.commute_resolved == 1


def test_score_reason():
    r = calculate_scores(_inp(), Weights(), **_kwargs(commute_minutes=None))
    assert "月額" in r.score_reason
    assert "※通勤分未計算" in r.score_reason


def test_score_reason_with_commute():
    r = calculate_scores(_inp(), Weights(), **_kwargs(commute_minutes=40))
    assert "通勤" in r.score_reason
    assert "※通勤分未計算" not in r.score_reason


def test_custom_weights_normalized():
    """用户改权重后总和仍 0-100"""
    w = Weights(budget=50, area=50, commute=0, floor=0, pet=0, station=0, age=0, initial_cost=0)
    r = calculate_scores(_inp(), w, **_kwargs(commute_minutes=None))
    assert 0 <= r.total_score <= 100


def _mixed():
    """预算満点(8万 <= 14万) 但築45年 → 築年数 0 分。用于观察加权方向。"""
    return _inp(total_monthly_cost=80000, building_age=45)


def test_total_never_exceeds_100_for_any_weight_sum():
    """权重和不等于 100 时也必须落在 0-100(这是旧实现失效的场景)。"""
    for w in [
        Weights(1, 1, 1, 1, 1, 1, 1, 1),
        Weights(3, 3, 3, 3, 3, 3, 3, 3),
        Weights(100, 100, 100, 100, 100, 100, 100, 100),
        Weights(budget=50, area=1, commute=1, floor=1, pet=1, station=1, age=1, initial_cost=1),
    ]:
        for cm in (None, 25, 120):
            r = calculate_scores(_inp(), w, **_kwargs(commute_minutes=cm))
            assert 0 <= r.total_score <= 100, (w, cm, r.total_score)


def test_equal_weights_match_default_weights():
    """各次元を等しく扱うなら、重みが 1 でも 100 でも同じ点になる。"""
    a = calculate_scores(_mixed(), Weights(1, 1, 1, 1, 1, 1, 1, 1), **_kwargs()).total_score
    b = calculate_scores(_mixed(), Weights(9, 9, 9, 9, 9, 9, 9, 9), **_kwargs()).total_score
    assert a == b


def test_weighting_a_strong_dimension_raises_score():
    rest = dict(area=1, commute=1, floor=1, pet=1, station=1, age=1, initial_cost=1)
    scores = [calculate_scores(_mixed(), Weights(budget=bw, **rest), **_kwargs()).total_score
              for bw in (1, 5, 20, 80)]
    assert scores == sorted(scores), scores


def test_weighting_a_weak_dimension_lowers_score():
    rest = dict(budget=1, area=1, commute=1, floor=1, pet=1, station=1, initial_cost=1)
    scores = [calculate_scores(_mixed(), Weights(age=aw, **rest), **_kwargs()).total_score
              for aw in (1, 5, 20, 80)]
    assert scores == sorted(scores, reverse=True), scores


def test_zero_weights_do_not_crash():
    r = calculate_scores(_inp(), Weights(0, 0, 0, 0, 0, 0, 0, 0), **_kwargs())
    assert r.total_score == 0


def test_min_floor_is_applied():
    assert calculate_scores(_inp(floor=4), Weights(), **_kwargs(min_floor=2)).floor_score == 10
    assert calculate_scores(_inp(floor=4), Weights(), **_kwargs(min_floor=5)).floor_score == 0


def test_max_walk_is_applied():
    strict = calculate_scores(_inp(walk_minutes=12), Weights(), **_kwargs(max_walk=10)).station_score
    loose = calculate_scores(_inp(walk_minutes=12), Weights(), **_kwargs(max_walk=30)).station_score
    assert strict < loose


def test_max_age_is_applied():
    strict = calculate_scores(_inp(building_age=25), Weights(), **_kwargs(max_age=10)).age_score
    loose = calculate_scores(_inp(building_age=25), Weights(), **_kwargs(max_age=40)).age_score
    assert strict < loose


def test_min_area_is_applied():
    strict = calculate_scores(_inp(area_m2=33), Weights(), **_kwargs(min_area=40)).area_score
    loose = calculate_scores(_inp(area_m2=33), Weights(), **_kwargs(min_area=32)).area_score
    assert strict < loose


def test_default_thresholds_keep_historic_bands():
    """既定値では従来の区切り(徒歩5/10/15/20分, 築5/10/20/30年)と一致する。"""
    for walk, expected in ((5, 10), (10, 8), (15, 5), (20, 2), (21, 0)):
        assert calculate_scores(_inp(walk_minutes=walk), Weights(), **_kwargs()).station_score == expected
    for age, expected in ((5, 10), (10, 8), (20, 5), (30, 2), (31, 0)):
        assert calculate_scores(_inp(building_age=age), Weights(), **_kwargs()).age_score == expected


def test_over_budget():
    r = calculate_scores(_inp(total_monthly_cost=170000), Weights(), **_kwargs())
    assert r.budget_score == 0