"""5차 대조군 가드. 4차 결함(깊이 교란)이 재발하면 여기서 죽는다."""
import numpy as np
import pandas as pd
import pytest

from lab.bands import WEIGHTS, exogenous_quantiles, ladder
from lab.control import control_levels                      # 4차판(재현용)
from lab.control5 import (MIN_LABEL_POOL, intended_depth,
                          random_shape_levels, shuffled_label_levels)
from lab.sim import simulate

PEAK = 380_000.0            # 삼성 A급 화면값
SAMSUNG_GAIN = 6.14286
C = 0.8
POOL = np.exp(np.linspace(np.log(0.30), np.log(6.00), 60))   # 상승폭 30~600%


def _strategy_levels(gain, c=C, peak=PEAK):
    q1, q3 = exogenous_quantiles(gain)
    return ladder(peak, q1, q3, c)


def test_old_control_is_structurally_shallower():
    """4차 결함의 회귀 증인. 이 격차가 Δ+8%p 의 정체다."""
    lv = _strategy_levels(SAMSUNG_GAIN)
    rng = np.random.default_rng(0)
    old = np.mean([intended_depth(PEAK, control_levels(PEAK, min(lv), rng))
                   for _ in range(4000)])
    assert intended_depth(PEAK, lv) - old > 0.10, "4차 대조군은 15%p 얕았다"


def test_c1_matches_strategy_depth_on_average():
    """C1 의 존재 이유. 4차 대조군을 넣으면 이 단언이 깨진다."""
    strat = float(np.mean([intended_depth(PEAK, _strategy_levels(g)) for g in POOL]))
    rng = np.random.default_rng(1)
    ctrl = float(np.mean([
        intended_depth(PEAK, shuffled_label_levels(PEAK, POOL, exogenous_quantiles, C, rng))
        for _ in range(4000)]))
    assert abs(strat - ctrl) < 0.01, f"깊이 비대칭 {100*(strat-ctrl):.2f}%p"


def test_c1_destroys_the_gain_to_depth_mapping():
    """전략은 상승폭↔깊이가 붙어 있고, C1 은 끊겨 있어야 한다."""
    rng = np.random.default_rng(2)
    gains = rng.choice(POOL, size=2000)
    strat = [intended_depth(PEAK, _strategy_levels(g)) for g in gains]
    ctrl = [intended_depth(PEAK, shuffled_label_levels(PEAK, POOL, exogenous_quantiles, C, rng))
            for _ in gains]
    assert np.corrcoef(gains, strat)[0, 1] > 0.90
    assert abs(np.corrcoef(gains, ctrl)[0, 1]) < 0.10


def test_c1_refuses_a_pool_smaller_than_the_registered_minimum():
    rng = np.random.default_rng(3)
    small = POOL[: MIN_LABEL_POOL - 1]
    assert shuffled_label_levels(PEAK, small, exogenous_quantiles, C, rng) is None
    assert shuffled_label_levels(PEAK, POOL[:MIN_LABEL_POOL], exogenous_quantiles, C, rng) is not None


def test_c1_never_reads_the_events_own_gain():
    """라벨 풀만 보고 밴드를 만든다 — 자기 상승폭은 인자에 없다."""
    rng = np.random.default_rng(4)
    flat = np.full(60, 0.30)                      # 풀이 전부 30%면 결과도 30% 밴드
    lv = shuffled_label_levels(PEAK, flat, exogenous_quantiles, C, rng)
    assert intended_depth(PEAK, lv) == pytest.approx(
        intended_depth(PEAK, _strategy_levels(0.30)), abs=1e-12)


def test_c2_center_is_identical_to_the_strategy_band():
    q1, q3 = exogenous_quantiles(SAMSUNG_GAIN)
    lv_s = ladder(PEAK, q1, q3, C)
    rng = np.random.default_rng(5)
    for _ in range(50):
        lv_c, _ = random_shape_levels(PEAK, q1, q3, rng)
        c_s = (min(lv_s) + max(lv_s)) / 2.0
        c_c = (min(lv_c) + max(lv_c)) / 2.0
        assert c_c == pytest.approx(c_s, rel=1e-12)


def test_c2_weight_permutation_alone_is_systematically_shallower():
    """왜 깊이 맞춤이 필요한가 — 등록비중은 깊은 쪽에 쏠려 있다(Σw(k−3)=+0.62)."""
    q1, q3 = exogenous_quantiles(SAMSUNG_GAIN)
    want = intended_depth(PEAK, ladder(PEAK, q1, q3, C))
    rng = np.random.default_rng(7)
    raw = np.mean([intended_depth(PEAK, *random_shape_levels(PEAK, q1, q3, rng))
                   for _ in range(2000)])
    assert want - raw > 0.005, "이 편향이 없으면 깊이 맞춤은 불필요하다"


def test_c2_depth_is_matched_exactly_when_requested():
    q1, q3 = exogenous_quantiles(SAMSUNG_GAIN)
    want = intended_depth(PEAK, ladder(PEAK, q1, q3, C))
    rng = np.random.default_rng(8)
    for _ in range(50):
        lv, w = random_shape_levels(PEAK, q1, q3, rng, match_depth=want)
        assert intended_depth(PEAK, lv, w) == pytest.approx(want, abs=1e-12)


def test_c2_weights_are_a_permutation_of_the_registered_weights():
    q1, q3 = exogenous_quantiles(SAMSUNG_GAIN)
    rng = np.random.default_rng(6)
    seen = set()
    for _ in range(50):
        _, w = random_shape_levels(PEAK, q1, q3, rng)
        assert sorted(w) == pytest.approx(sorted(WEIGHTS))
        seen.add(w)
    assert len(seen) > 1, "순열이 고정돼 있으면 모양 무작위가 아니다"


def _bars(lows, closes):
    n = len(lows)
    return pd.DataFrame({"date": [f"2026-01-{i+1:02d}" for i in range(n)],
                         "open": [1e9] * n, "high": [1e9] * n,
                         "low": lows, "close": closes})


def test_simulate_honours_custom_weights():
    """C2 의 비중 순열이 실제로 평단에 반영돼야 한다."""
    bars = _bars([100.0, 90.0] + [95.0] * 25, [95.0] * 27)
    lv = [100.0, 90.0]
    base = simulate(bars, lv, hold_days=20, cost=0.0, max_fill_bars=5)
    flip = simulate(bars, lv, hold_days=20, cost=0.0, max_fill_bars=5,
                    weights=(WEIGHTS[1], WEIGHTS[0]))
    assert base.avg_cost != pytest.approx(flip.avg_cost)
    assert base.avg_cost == pytest.approx(
        (100 * WEIGHTS[0] + 90 * WEIGHTS[1]) / (WEIGHTS[0] + WEIGHTS[1]))
