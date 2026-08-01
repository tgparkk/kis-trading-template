"""6차 핵심 — 미체결이 표본에서 사라지지 않고 현금 0% 로 남는다."""
import numpy as np
import pytest

from lab.bands import WEIGHTS, exogenous_quantiles, ladder
from lab.control5 import intended_depth
from lab.run6 import CASH_RETURN, arm_fields
from lab.sim import Trade

PEAK = 380_000.0
LEVELS = ladder(PEAK, *exogenous_quantiles(6.14286), 0.8)


def test_unfilled_becomes_cash_not_a_missing_observation():
    """5차 GATE_FAIL 의 원인을 없애는 한 줄. 여기가 NaN 이면 6차는 5차다."""
    f = arm_fields(None, PEAK, LEVELS, None)
    assert f["ret"] == CASH_RETURN == 0.0
    assert not np.isnan(f["ret"])
    assert f["filled"] == 0.0 and f["fill_n"] == 0.0


def test_unfilled_still_reports_the_intended_depth():
    """게이트 B 는 체결과 무관하게 전 행에서 재야 한다."""
    f = arm_fields(None, PEAK, LEVELS, None)
    assert f["want"] == pytest.approx(intended_depth(PEAK, LEVELS, WEIGHTS))
    assert np.isnan(f["depth"])          # 실현 깊이는 체결분에만 존재


def test_missing_band_is_the_only_nan_return():
    f = arm_fields(None, PEAK, None, None)
    assert np.isnan(f["ret"]) and np.isnan(f["want"])


def test_filled_arm_passes_the_trade_through():
    t = Trade(code="005930", entry_date="2026-01-05", avg_cost=200_000.0,
              exit_date="2026-02-05", exit_px=220_000.0, ret_net=0.0979,
              filled_n=4, truncated=False)
    f = arm_fields(t, PEAK, LEVELS, None)
    assert f["ret"] == pytest.approx(0.0979)
    assert f["filled"] == 1.0 and f["fill_n"] == 4.0
    assert f["depth"] == pytest.approx(1.0 - 200_000.0 / PEAK)


def test_cash_arm_costs_nothing():
    """지정가가 안 걸리면 수수료·세금도 없다. 0.0 이어야지 −0.0021 이 아니다."""
    assert arm_fields(None, PEAK, LEVELS, None)["ret"] == 0.0
