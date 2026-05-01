"""multiverse.metrics.calculator 회귀 테스트 (7개)."""
import math
from datetime import date, timedelta

import pytest

from RoboTrader_template.multiverse.metrics import Metrics, compute_metrics
from RoboTrader_template.multiverse.engine.pit_engine import Trade


def _equity_series(start: date, days: int, daily_return: float) -> list:
    """단조 증가 equity 시계열 헬퍼."""
    equity = 100.0
    series = [(start, equity)]
    for i in range(1, days):
        equity *= (1 + daily_return)
        series.append((start + timedelta(days=i), equity))
    return series


def test_compute_metrics_empty_safe():
    """빈 입력에서 ZeroDivisionError 없이 0.0 반환."""
    m = compute_metrics([], [], 100.0)
    assert isinstance(m, Metrics)
    assert m.sharpe == 0.0


def test_cagr_calculation():
    """일간 +0.1%로 252일 → CAGR ~28.6% 근사."""
    series = _equity_series(date(2026, 1, 1), 252, 0.001)
    m = compute_metrics(series, [], 100.0)
    assert m.cagr > 0.25 and m.cagr < 0.32


def test_mdd_zero_for_monotonic():
    """단조 증가 → MDD = 0."""
    series = _equity_series(date(2026, 1, 1), 252, 0.001)
    m = compute_metrics(series, [], 100.0)
    assert m.mdd < 0.001


def test_mdd_drop_recovery():
    """100→90→100 시계열에서 MDD = 0.10 (10%)."""
    series = [
        (date(2026, 1, 1), 100.0),
        (date(2026, 1, 2), 90.0),
        (date(2026, 1, 3), 100.0),
    ]
    m = compute_metrics(series, [], 100.0)
    assert abs(m.mdd - 0.10) < 0.01


def test_calmar_ratio():
    """CAGR>0이고 MDD>0이면 Calmar = CAGR/MDD."""
    series = _equity_series(date(2026, 1, 1), 252, 0.001)
    series_with_dip = list(series)
    series_with_dip[100] = (series[100][0], series[100][1] * 0.85)  # 15% drop
    m = compute_metrics(series_with_dip, [], 100.0)
    assert m.calmar > 0  # 회복은 안 됐을 수 있지만 양수


def test_tuw_calculation():
    """100→90→100→110: TUW >= 1 (90으로 떨어진 후 100 복귀까지)."""
    series = [
        (date(2026, 1, 1), 100.0),
        (date(2026, 1, 2), 90.0),
        (date(2026, 1, 3), 100.0),
        (date(2026, 1, 4), 110.0),
    ]
    m = compute_metrics(series, [], 100.0)
    assert m.tuw_days >= 1  # 정확한 정의는 구현 따라 1 또는 2


def test_tail_ratio_symmetric():
    """대칭 분포면 tail_ratio >= 0.0 (NaN 아님)."""
    series = [
        (date(2026, 1, 1) + timedelta(days=i), 100 * (1 + 0.01 * (i % 3 - 1)))
        for i in range(100)
    ]
    m = compute_metrics(series, [], 100.0)
    assert m.tail_ratio >= 0.0
    assert math.isfinite(m.tail_ratio)
