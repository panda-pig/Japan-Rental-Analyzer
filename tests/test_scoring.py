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


def test_over_budget():
    r = calculate_scores(_inp(total_monthly_cost=170000), Weights(), **_kwargs())
    assert r.budget_score == 0