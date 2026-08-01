"""7차 핵심 — 자본가중·정답존재 게이트·정의 격자."""
import numpy as np
import pytest

from lab.bands import WEIGHTS, exogenous_quantiles, ladder
from lab.data import load_daily
from lab.run7 import CUM, DANAL, arm_fields, definitions
from lab.segments import find_segments_local
from lab.sim import Trade

PEAK = 380_000.0
LEVELS = ladder(PEAK, *exogenous_quantiles(6.14286), 0.8)


def _trade(fill_n, ret=0.10):
    return Trade(code="X", entry_date="2026-01-05", avg_cost=200_000.0,
                 exit_date="2026-02-05", exit_px=220_000.0, ret_net=ret,
                 filled_n=fill_n, truncated=False)


def test_definition_grid_is_the_eight_zero_error_cells():
    d = definitions()
    assert len(d) == 8
    assert {x["k"] for x in d} == {5.0, 10.0}
    assert {x["horizon"] for x in d} == {10, 20}
    assert {x["min_gain"] for x in d} == {0.15, 0.25}


def test_capital_weight_scales_by_deployed_capital():
    """부분체결은 투입자본만큼만 반영된다 — 6차 MAJOR 5 의 교정."""
    assert arm_fields(_trade(1), PEAK, LEVELS, None)["cw"] == pytest.approx(0.10 * 0.10)
    assert arm_fields(_trade(5), PEAK, LEVELS, None)["cw"] == pytest.approx(0.10 * 1.00)
    assert CUM[-1] == pytest.approx(1.0)


def test_roi_and_capital_weight_diverge_on_partial_fill():
    """둘이 같으면 교정이 안 들어간 것이다."""
    f = arm_fields(_trade(2), PEAK, LEVELS, None)
    assert f["ret"] == pytest.approx(0.10)
    assert f["cw"] == pytest.approx(0.10 * 0.23)
    assert f["cw"] != pytest.approx(f["ret"])


def test_unfilled_is_cash_in_both_measures():
    f = arm_fields(None, PEAK, LEVELS, None)
    assert f["ret"] == 0.0 and f["cw"] == 0.0 and f["filled"] == 0.0


def test_missing_band_is_nan_not_zero():
    f = arm_fields(None, PEAK, None, None)
    assert np.isnan(f["ret"]) and np.isnan(f["cw"])


def test_gate_c_danal_ground_truth_exists_in_every_definition():
    """사전등록 §4 게이트 C. 정답이 후보에 없으면 채점은 엉뚱한 구간을 매칭한다."""
    bars = load_daily("2021-01-04", "2026-07-31")
    d = bars[bars["stock_code"] == DANAL["code"]]
    for spec in definitions():
        segs = find_segments_local(d, spec["k"], spec["horizon"], spec["min_gain"])
        hit = any(abs(s.start_px - DANAL["start"]) / DANAL["start"] < DANAL["tol"]
                  and abs(s.peak_px - DANAL["peak"]) / DANAL["peak"] < DANAL["tol"]
                  for s in segs)
        assert hit, f'{spec["name"]} 가 다날 정답(3,930→5,100)을 재현하지 못한다'
