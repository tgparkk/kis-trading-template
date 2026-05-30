"""systrader79 평균모멘텀스코어 + allocation_backtester 단위테스트.

검증 항목:
- 모멘텀스코어 계산 (알려진 입력 → 기대 score)
- 비중 = score, 워밍업 구간 제외
- no-lookahead (score[m] 이 미래 종가에 영향받지 않음)
- equity 합성 (b&h 동치, 현금 100%, 부분 비중)
"""

from __future__ import annotations

import math

import numpy as np
import pandas as pd
import pytest

from backtest.allocation_backtester import (
    AllocationBacktester,
    resample_month_end,
)
from strategies.allocation.systrader79_avgmom import AvgMomentumScoreStrategy


def _month_index(n: int, start: str = "2021-01-31") -> pd.DatetimeIndex:
    return pd.date_range(start=start, periods=n, freq="ME")


# ---------------------------------------------------------------------------
# 모멘텀스코어 계산
# ---------------------------------------------------------------------------

def test_momentum_score_monotonic_increasing_is_one():
    """단조 증가 시계열: 13번째 월부터 score=1.0 (12개 룩백 모두 과거가 < 현재가)."""
    close = pd.Series(np.arange(1.0, 25.0), index=_month_index(24))
    strat = AvgMomentumScoreStrategy(lookback_months=12)
    scores = strat.momentum_score(close)
    # 앞 12개월은 NaN (워밍업)
    assert scores.iloc[:12].isna().all()
    # 13번째(index 12)부터 전부 1.0
    assert (scores.iloc[12:] == 1.0).all()


def test_momentum_score_monotonic_decreasing_is_zero():
    """단조 감소 시계열: score=0.0 (현재가 < 모든 과거가)."""
    close = pd.Series(np.arange(24.0, 0.0, -1.0), index=_month_index(24))
    strat = AvgMomentumScoreStrategy(lookback_months=12)
    scores = strat.momentum_score(close)
    assert (scores.iloc[12:] == 0.0).all()


def test_momentum_score_known_partial():
    """알려진 입력 → 기대 score (3/12=0.25).

    구성: 12개월 워밍업 값들을 두고, 13번째 현재가가 정확히 3개 과거가보다 크거나 같게.
    값: index0..11 = [100,101,102,103,104,105,106,107,108,109,110,111]
        현재가(index12) = 103 → 과거가 중 100,101,102,103(=) → 4개 >= 103? 확인.
    현재가 103 >= [100,101,102,103,104,...,111] 중 1[103>=v]:
      v=111? no, 110 no, 109 no, 108 no, 107 no, 106 no, 105 no, 104 no,
      103 yes(=), 102 yes, 101 yes, 100 yes → 4 hits → 4/12.
    """
    vals = [100, 101, 102, 103, 104, 105, 106, 107, 108, 109, 110, 111, 103]
    close = pd.Series([float(v) for v in vals], index=_month_index(13))
    strat = AvgMomentumScoreStrategy(lookback_months=12)
    scores = strat.momentum_score(close)
    assert scores.iloc[12] == pytest.approx(4.0 / 12.0)


def test_momentum_score_equal_counts_as_hit():
    """현재가 == 과거가 도 1점(>= 조건)."""
    close = pd.Series([100.0] * 13, index=_month_index(13))
    strat = AvgMomentumScoreStrategy(lookback_months=12)
    scores = strat.momentum_score(close)
    assert scores.iloc[12] == pytest.approx(1.0)


def test_risk_weights_drops_warmup():
    """risk_weights 는 워밍업(NaN) 구간 제거하고 score 그대로 반환."""
    close = pd.Series(np.arange(1.0, 25.0), index=_month_index(24))
    strat = AvgMomentumScoreStrategy(lookback_months=12)
    w = strat.risk_weights(close)
    assert len(w) == 12  # 24 - 12 워밍업
    assert (w == 1.0).all()
    assert not w.isna().any()


# ---------------------------------------------------------------------------
# no-lookahead
# ---------------------------------------------------------------------------

def test_no_lookahead_score_unaffected_by_future():
    """score[m] 은 m 이후(미래) 종가를 변경해도 불변."""
    base = list(np.arange(1.0, 25.0))
    close_a = pd.Series(base, index=_month_index(24))
    strat = AvgMomentumScoreStrategy(lookback_months=12)
    scores_a = strat.momentum_score(close_a)

    # index 18 이후를 임의로 교란(미래 종가 변경).
    perturbed = list(base)
    for i in range(18, 24):
        perturbed[i] = perturbed[i] * 0.1  # 급락 주입
    close_b = pd.Series(perturbed, index=_month_index(24))
    scores_b = strat.momentum_score(close_b)

    # index 12..17 의 score 는 미래 교란과 무관하게 동일해야 함.
    for m in range(12, 18):
        assert scores_a.iloc[m] == pytest.approx(scores_b.iloc[m]), f"lookahead leak at {m}"


# ---------------------------------------------------------------------------
# equity 합성 (allocation_backtester)
# ---------------------------------------------------------------------------

def test_full_weight_matches_buy_and_hold():
    """비중 항상 1.0 → b&h 와 동일 최종수익(비용 0)."""
    idx = _month_index(13)
    close = pd.Series([100.0 * (1.05 ** i) for i in range(13)], index=idx)
    w = pd.Series(1.0, index=idx)
    bt = AllocationBacktester(round_trip_bps=0.0)
    res = bt.run(close, w)
    bh = bt.run_buy_and_hold(close)
    assert res.final_return_pct == pytest.approx(bh.final_return_pct, rel=1e-9)
    # 12개월 × 5% 복리.
    expected = (1.05 ** 12) - 1.0
    assert res.final_return_pct == pytest.approx(expected, rel=1e-9)


def test_zero_weight_is_cash_flat():
    """비중 항상 0 (현금 100%, 캐리 0) → equity 변동 없음."""
    idx = _month_index(13)
    close = pd.Series([100.0 * (1.05 ** i) for i in range(13)], index=idx)
    w = pd.Series(0.0, index=idx)
    bt = AllocationBacktester(round_trip_bps=0.0, safe_rate_annual=0.0)
    res = bt.run(close, w)
    assert res.final_return_pct == pytest.approx(0.0, abs=1e-12)
    assert res.max_dd_pct == pytest.approx(0.0, abs=1e-12)


def test_half_weight_returns_half_of_risk():
    """비중 0.5 고정, 단일 스텝 → 포트수익 = 0.5 * 위험자산수익 (비용 0, 현금 0%)."""
    idx = _month_index(2)
    close = pd.Series([100.0, 110.0], index=idx)  # +10%
    w = pd.Series(0.5, index=idx)
    bt = AllocationBacktester(round_trip_bps=0.0, safe_rate_annual=0.0)
    res = bt.run(close, w)
    assert res.final_return_pct == pytest.approx(0.5 * 0.10, rel=1e-9)


def test_rebalance_cost_reduces_return():
    """리밸런싱 비용 > 0 이면 동일 비중경로 대비 최종수익이 낮아진다."""
    idx = _month_index(13)
    close = pd.Series([100.0 * (1.02 ** i) for i in range(13)], index=idx)
    # 비중이 0.3↔0.9 로 매월 진동 → 회전율 발생.
    w = pd.Series([0.3 if i % 2 == 0 else 0.9 for i in range(13)], index=idx)
    free = AllocationBacktester(round_trip_bps=0.0).run(close, w)
    costed = AllocationBacktester(round_trip_bps=50.0).run(close, w)
    assert costed.final_return_pct < free.final_return_pct
    assert costed.turnover_total > 0.0


def test_backtester_no_lookahead_weight_applied_to_next_month():
    """w[m] 은 m→m+1 수익에 적용된다 (마지막 비중은 미래수익 없어 미사용).

    close: [100, 200] (+100% in step 0→1), w=[1.0(at m0), 0.0(at m1)].
    m0 비중 1.0 이 0→1 수익(+100%)에 적용 → +100%.
    m1 비중 0.0 은 적용할 다음 수익이 없음 → 결과는 +100% 단일스텝.
    """
    idx = _month_index(2)
    close = pd.Series([100.0, 200.0], index=idx)
    w = pd.Series([1.0, 0.0], index=idx)
    bt = AllocationBacktester(round_trip_bps=0.0, safe_rate_annual=0.0)
    res = bt.run(close, w)
    assert res.n_months == 1
    assert res.final_return_pct == pytest.approx(1.0, rel=1e-9)
    assert res.weights == [1.0]


# ---------------------------------------------------------------------------
# resample
# ---------------------------------------------------------------------------

def test_resample_month_end_takes_last():
    """일봉 → 월말 종가는 각 월의 마지막 값."""
    idx = pd.date_range("2021-01-01", "2021-03-31", freq="D")
    daily = pd.Series(np.arange(1.0, len(idx) + 1.0), index=idx)
    monthly = resample_month_end(daily)
    assert len(monthly) == 3
    # 1월 마지막(1/31) = 31번째 값 = 31.0
    assert monthly.iloc[0] == pytest.approx(31.0)
