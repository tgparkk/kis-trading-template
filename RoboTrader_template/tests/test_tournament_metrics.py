"""토너먼트 평가 지표 단위 테스트.

DB 의존성 없음. FakeResult(equity_curve, trades)로 합성 결과를 생성하여
compute_metrics / _rank_by_composite 를 검증합니다.
"""
from __future__ import annotations

import math
from typing import Dict, List, Optional

import numpy as np
import pandas as pd
import pytest

from backtest.tournament_metrics import _rank_by_composite, _zero_metrics, compute_metrics


# ---------------------------------------------------------------------------
# 공통 픽스처
# ---------------------------------------------------------------------------

class FakeResult:
    """BacktestResult의 최소 duck-type 대역.

    Attributes:
        equity_curve: 일별 포트폴리오 가치 리스트 (초기 자본 포함, n+1개)
        trades:       거래 기록 리스트 [{exit_date, pnl, pnl_pct, ...}]
    """

    def __init__(
        self,
        equity_curve: List[float],
        trades: Optional[List[Dict]] = None,
    ) -> None:
        self.equity_curve = equity_curve
        self.trades = trades or []


INITIAL = 10_000_000.0  # 기본 초기 자본


def _make_trades(dates: List[str], pnls: List[float]) -> List[Dict]:
    """(date, pnl) 쌍 → trades 리스트."""
    return [
        {"exit_date": d, "pnl": p, "pnl_pct": p / INITIAL}
        for d, p in zip(dates, pnls)
    ]


# ---------------------------------------------------------------------------
# 1. 기본 반환값 형식
# ---------------------------------------------------------------------------

class TestComputeMetricsStructure:
    """compute_metrics가 8종 키를 모두 반환하는지 확인."""

    REQUIRED_KEYS = {
        "avg_daily_return_pct",
        "win_rate_pct",
        "calmar",
        "sortino",
        "mdd_pct",
        "max_daily_loss_pct",
        "total_pnl_pct",
        "trade_count",
    }

    def test_all_keys_present_normal(self):
        curve = [INITIAL, INITIAL * 1.01, INITIAL * 1.02]
        result = FakeResult(curve)
        m = compute_metrics(result, INITIAL)
        assert self.REQUIRED_KEYS.issubset(set(m.keys()))

    def test_all_keys_present_none_result(self):
        m = compute_metrics(None, INITIAL)
        assert self.REQUIRED_KEYS.issubset(set(m.keys()))

    def test_all_keys_present_empty_curve(self):
        m = compute_metrics(FakeResult([]), INITIAL)
        assert self.REQUIRED_KEYS.issubset(set(m.keys()))

    def test_all_keys_present_single_element_curve(self):
        m = compute_metrics(FakeResult([INITIAL]), INITIAL)
        assert self.REQUIRED_KEYS.issubset(set(m.keys()))


# ---------------------------------------------------------------------------
# 2. None / 빈 결과 처리
# ---------------------------------------------------------------------------

class TestZeroMetrics:
    def test_none_result_returns_zeros(self):
        m = compute_metrics(None, INITIAL)
        assert m["avg_daily_return_pct"] == 0.0
        assert m["win_rate_pct"] == 0.0
        assert m["calmar"] == 0.0
        assert m["trade_count"] == 0

    def test_empty_equity_curve_returns_zeros(self):
        m = compute_metrics(FakeResult([]), INITIAL)
        assert m["total_pnl_pct"] == 0.0
        assert m["mdd_pct"] == 0.0

    def test_single_element_equity_curve_returns_zeros(self):
        m = compute_metrics(FakeResult([INITIAL]), INITIAL)
        assert m["trade_count"] == 0

    def test_zero_initial_capital_returns_zeros(self):
        m = compute_metrics(FakeResult([INITIAL, INITIAL * 1.1]), 0.0)
        assert m == _zero_metrics()

    def test_empty_trades_list_zero_trade_count(self):
        curve = [INITIAL, INITIAL * 1.01, INITIAL * 1.02]
        m = compute_metrics(FakeResult(curve, trades=[]), INITIAL)
        assert m["trade_count"] == 0


# ---------------------------------------------------------------------------
# 3. 수익률 방향 검증
# ---------------------------------------------------------------------------

class TestReturnDirection:
    def test_monotonic_rising_positive_total_pnl(self):
        """단조 상승 equity → 양수 total_pnl_pct."""
        curve = [INITIAL * (1 + 0.01 * i) for i in range(11)]
        m = compute_metrics(FakeResult(curve), INITIAL)
        assert m["total_pnl_pct"] > 0.0
        assert m["avg_daily_return_pct"] > 0.0

    def test_monotonic_falling_negative_total_pnl(self):
        """단조 하락 equity → 음수 total_pnl_pct."""
        curve = [INITIAL * (1 - 0.01 * i) for i in range(11)]
        m = compute_metrics(FakeResult(curve), INITIAL)
        assert m["total_pnl_pct"] < 0.0
        assert m["avg_daily_return_pct"] < 0.0

    def test_flat_equity_near_zero_return(self):
        """완전 평탄 → 수익률 ≈ 0."""
        curve = [INITIAL] * 20
        m = compute_metrics(FakeResult(curve), INITIAL)
        assert abs(m["avg_daily_return_pct"]) < 1e-9
        assert m["total_pnl_pct"] == pytest.approx(0.0, abs=1e-6)

    def test_monotonic_falling_large_negative_mdd(self):
        """단조 하락 → MDD가 큰 음수."""
        # 10% 하락
        curve = [INITIAL * (1 - 0.01 * i) for i in range(11)]
        m = compute_metrics(FakeResult(curve), INITIAL)
        assert m["mdd_pct"] < -5.0

    def test_monotonic_rising_mdd_near_zero(self):
        """단조 상승 → MDD ≈ 0 (낙폭 없음)."""
        curve = [INITIAL * (1 + 0.01 * i) for i in range(11)]
        m = compute_metrics(FakeResult(curve), INITIAL)
        assert m["mdd_pct"] >= -1e-6  # 극소 부동소수 오차 허용


# ---------------------------------------------------------------------------
# 4. 일승률 (win_rate_pct)
# ---------------------------------------------------------------------------

class TestWinRate:
    def test_all_up_days_100_percent(self):
        """매일 상승 → 일승률 100%."""
        n = 10
        curve = [INITIAL * (1 + 0.005 * i) for i in range(n + 1)]
        m = compute_metrics(FakeResult(curve), INITIAL)
        assert m["win_rate_pct"] == pytest.approx(100.0, abs=0.1)

    def test_all_down_days_zero_percent(self):
        """매일 하락 → 일승률 0%."""
        n = 10
        curve = [INITIAL * (1 - 0.005 * i) for i in range(n + 1)]
        m = compute_metrics(FakeResult(curve), INITIAL)
        assert m["win_rate_pct"] == pytest.approx(0.0, abs=0.1)

    def test_half_up_half_down_approx_50(self):
        """격일 상승/하락 → 일승률 ≈ 50%."""
        base = INITIAL
        curve = [base]
        for i in range(10):
            if i % 2 == 0:
                curve.append(curve[-1] * 1.01)
            else:
                curve.append(curve[-1] * 0.99)
        m = compute_metrics(FakeResult(curve), INITIAL)
        assert 40.0 <= m["win_rate_pct"] <= 60.0


# ---------------------------------------------------------------------------
# 5. MDD 정확성 (수기 계산 일치)
# ---------------------------------------------------------------------------

class TestMddAccuracy:
    def test_known_drawdown(self):
        """알려진 고점→저점 낙폭 수기 계산 비교.

        curve: 100 → 120 → 90 → 110
        고점 120, 저점 90: MDD = (90-120)/120 = -25%
        """
        curve = [100.0, 120.0, 90.0, 110.0]
        initial = 100.0
        m = compute_metrics(FakeResult(curve), initial)
        # MDD = -25%
        assert m["mdd_pct"] == pytest.approx(-25.0, abs=0.1)

    def test_no_drawdown_mdd_zero(self):
        """고점이 갱신되지 않는 구간 없음 → MDD = 0."""
        curve = [100.0, 110.0, 120.0, 130.0]
        m = compute_metrics(FakeResult(curve), 100.0)
        assert m["mdd_pct"] == pytest.approx(0.0, abs=1e-6)

    def test_total_pnl_exact(self):
        """total_pnl_pct = (final - initial) / initial * 100."""
        curve = [10_000_000.0, 10_500_000.0]
        m = compute_metrics(FakeResult(curve), 10_000_000.0)
        assert m["total_pnl_pct"] == pytest.approx(5.0, abs=1e-4)


# ---------------------------------------------------------------------------
# 6. Calmar / Sortino 분자·분모
# ---------------------------------------------------------------------------

class TestCalmarSortino:
    def test_calmar_zero_when_no_drawdown(self):
        """MDD = 0 → Calmar = 0 (분모 0)."""
        curve = [INITIAL, INITIAL * 1.01, INITIAL * 1.02]
        m = compute_metrics(FakeResult(curve), INITIAL)
        # MDD가 거의 0이면 calmar = 0
        assert m["calmar"] == pytest.approx(0.0, abs=0.05)

    def test_calmar_positive_when_profitable_with_drawdown(self):
        """수익 + MDD 있으면 Calmar > 0."""
        curve = [100.0, 120.0, 90.0, 130.0]
        m = compute_metrics(FakeResult(curve), 100.0)
        assert m["calmar"] > 0.0

    def test_sortino_zero_when_no_downside(self):
        """하락 일자 < 2개 → Sortino = 0 또는 계산 불능."""
        # 모두 상승
        curve = [INITIAL * (1 + 0.01 * i) for i in range(11)]
        m = compute_metrics(FakeResult(curve), INITIAL)
        # 하락 일자 없으면 Sortino = 0
        assert m["sortino"] == pytest.approx(0.0, abs=1e-6)

    def test_sortino_negative_when_mostly_down(self):
        """대부분 하락 → Sortino < 0 (평균 수익률 < 0)."""
        curve = [INITIAL * (1 - 0.01 * i) for i in range(11)]
        m = compute_metrics(FakeResult(curve), INITIAL)
        assert m["sortino"] < 0.0

    def test_calmar_negative_when_losing(self):
        """손실 + MDD → Calmar < 0."""
        curve = [100.0, 90.0, 80.0, 70.0]
        m = compute_metrics(FakeResult(curve), 100.0)
        # CAGR < 0, MDD > 0 → calmar < 0
        assert m["calmar"] < 0.0


# ---------------------------------------------------------------------------
# 7. trade_count
# ---------------------------------------------------------------------------

class TestTradeCount:
    def test_trade_count_matches_trades_length(self):
        trades = _make_trades(
            ["2025-01-02", "2025-01-03", "2025-01-06"],
            [10_000.0, -5_000.0, 20_000.0],
        )
        curve = [INITIAL, INITIAL + 10_000, INITIAL + 5_000, INITIAL + 25_000]
        m = compute_metrics(FakeResult(curve, trades), INITIAL)
        assert m["trade_count"] == 3

    def test_trade_count_zero_no_trades(self):
        curve = [INITIAL, INITIAL * 1.01]
        m = compute_metrics(FakeResult(curve, []), INITIAL)
        assert m["trade_count"] == 0

    def test_trade_count_single_trade(self):
        trades = _make_trades(["2025-01-02"], [50_000.0])
        curve = [INITIAL, INITIAL + 50_000]
        m = compute_metrics(FakeResult(curve, trades), INITIAL)
        assert m["trade_count"] == 1

    def test_integer_vs_float_pnl_robust(self):
        """pnl이 정수여도 float 변환 후 정상 동작."""
        trades = [{"exit_date": "2025-01-02", "pnl": 10000, "pnl_pct": 0.001}]
        curve = [INITIAL, INITIAL + 10000]
        m = compute_metrics(FakeResult(curve, trades), INITIAL)
        assert m["trade_count"] == 1
        assert m["total_pnl_pct"] == pytest.approx(0.1, abs=0.01)


# ---------------------------------------------------------------------------
# 8. _rank_by_composite — 합격선 필터
# ---------------------------------------------------------------------------

class TestRankCompositePassFilter:
    def _make_df(self, rows: List[Dict]) -> pd.DataFrame:
        return pd.DataFrame(rows)

    def test_pass_all_criteria_met(self):
        df = self._make_df([
            {"avg_daily_return_pct": 0.5, "win_rate_pct": 55.0, "mdd_pct": -10.0, "calmar": 2.0},
        ])
        out = _rank_by_composite(df)
        assert bool(out.loc[0, "pass"]) is True

    def test_fail_low_daily_return(self):
        df = self._make_df([
            {"avg_daily_return_pct": 0.1, "win_rate_pct": 55.0, "mdd_pct": -10.0, "calmar": 1.0},
        ])
        out = _rank_by_composite(df)
        assert bool(out.loc[0, "pass"]) is False

    def test_fail_low_win_rate(self):
        df = self._make_df([
            {"avg_daily_return_pct": 0.5, "win_rate_pct": 40.0, "mdd_pct": -10.0, "calmar": 1.0},
        ])
        out = _rank_by_composite(df)
        assert bool(out.loc[0, "pass"]) is False

    def test_fail_large_mdd(self):
        df = self._make_df([
            {"avg_daily_return_pct": 0.5, "win_rate_pct": 55.0, "mdd_pct": -20.0, "calmar": 1.0},
        ])
        out = _rank_by_composite(df)
        assert bool(out.loc[0, "pass"]) is False

    def test_boundary_exact_values_pass(self):
        """경계값 정확히 = 합격."""
        df = self._make_df([
            {"avg_daily_return_pct": 0.3, "win_rate_pct": 50.0, "mdd_pct": -15.0, "calmar": 1.0},
        ])
        out = _rank_by_composite(df)
        assert bool(out.loc[0, "pass"]) is True


# ---------------------------------------------------------------------------
# 9. _rank_by_composite — 종합 점수 / 정렬
# ---------------------------------------------------------------------------

class TestRankCompositeScore:
    def _make_scenarios(self) -> pd.DataFrame:
        rows = [
            # 전략 A: 높은 수익률 + 높은 승률 + 높은 Calmar → 1위 예상
            {"strategy": "A", "universe": "s", "max_positions": 3,
             "avg_daily_return_pct": 1.0, "win_rate_pct": 70.0, "mdd_pct": -5.0, "calmar": 5.0},
            # 전략 B: 평균적
            {"strategy": "B", "universe": "s", "max_positions": 3,
             "avg_daily_return_pct": 0.5, "win_rate_pct": 55.0, "mdd_pct": -8.0, "calmar": 2.0},
            # 전략 C: 낮은 지표 → 꼴찌 예상
            {"strategy": "C", "universe": "s", "max_positions": 3,
             "avg_daily_return_pct": 0.1, "win_rate_pct": 40.0, "mdd_pct": -20.0, "calmar": 0.5},
        ]
        return pd.DataFrame(rows)

    def test_top_scenario_has_rank_1(self):
        df = _rank_by_composite(self._make_scenarios())
        assert df.loc[0, "rank"] == 1
        assert df.loc[0, "strategy"] == "A"

    def test_worst_scenario_has_last_rank(self):
        df = _rank_by_composite(self._make_scenarios())
        assert df.loc[2, "strategy"] == "C"

    def test_composite_score_descending(self):
        df = _rank_by_composite(self._make_scenarios())
        scores = df["composite_score"].tolist()
        assert scores == sorted(scores, reverse=True)

    def test_rank_column_sequential(self):
        df = _rank_by_composite(self._make_scenarios())
        assert list(df["rank"]) == [1, 2, 3]

    def test_z_score_columns_exist(self):
        df = _rank_by_composite(self._make_scenarios())
        assert "z_daily_return" in df.columns
        assert "z_win_rate" in df.columns
        assert "z_calmar" in df.columns

    def test_z_score_mean_near_zero(self):
        """z-score의 평균은 0이어야 함."""
        df = _rank_by_composite(self._make_scenarios())
        assert df["z_daily_return"].mean() == pytest.approx(0.0, abs=1e-9)
        assert df["z_win_rate"].mean() == pytest.approx(0.0, abs=1e-9)
        assert df["z_calmar"].mean() == pytest.approx(0.0, abs=1e-9)

    def test_single_scenario(self):
        """단일 시나리오 → z-score 0, rank 1."""
        df = pd.DataFrame([{
            "strategy": "X", "universe": "s", "max_positions": 3,
            "avg_daily_return_pct": 0.5, "win_rate_pct": 55.0,
            "mdd_pct": -10.0, "calmar": 2.0,
        }])
        out = _rank_by_composite(df)
        assert out.loc[0, "rank"] == 1
        assert out.loc[0, "composite_score"] == pytest.approx(0.0, abs=1e-9)

    def test_tie_handling_stable(self):
        """동점 시나리오 → 양쪽 모두 rank 존재 (크래시 없음)."""
        df = pd.DataFrame([
            {"strategy": "A", "universe": "s", "max_positions": 3,
             "avg_daily_return_pct": 0.5, "win_rate_pct": 55.0,
             "mdd_pct": -10.0, "calmar": 2.0},
            {"strategy": "B", "universe": "s", "max_positions": 3,
             "avg_daily_return_pct": 0.5, "win_rate_pct": 55.0,
             "mdd_pct": -10.0, "calmar": 2.0},
        ])
        out = _rank_by_composite(df)
        assert len(out) == 2
        assert set(out["rank"]) == {1, 2}

    def test_top10_subset_within_bounds(self):
        """60개 시나리오에서 상위 10개가 정상 추출되는지."""
        rows = []
        for i in range(60):
            rows.append({
                "strategy": f"s{i % 10}", "universe": "s", "max_positions": 3,
                "avg_daily_return_pct": float(i) * 0.01,
                "win_rate_pct": 50.0 + float(i) * 0.1,
                "mdd_pct": -10.0,
                "calmar": 1.0 + float(i) * 0.05,
            })
        df = _rank_by_composite(pd.DataFrame(rows))
        top10 = df.head(10)
        assert len(top10) == 10
        assert top10["rank"].tolist() == list(range(1, 11))


# ---------------------------------------------------------------------------
# 10. max_daily_loss_pct 방향
# ---------------------------------------------------------------------------

class TestMaxDailyLoss:
    def test_max_daily_loss_negative_when_loss_exists(self):
        """손실 발생 시 max_daily_loss_pct < 0."""
        # 하락 → 상승 패턴
        curve = [INITIAL, INITIAL * 0.95, INITIAL * 1.02]
        m = compute_metrics(FakeResult(curve), INITIAL)
        assert m["max_daily_loss_pct"] < 0.0

    def test_max_daily_loss_min_of_daily_returns(self):
        """max_daily_loss_pct는 일별 수익률 중 최솟값."""
        curve = [100.0, 110.0, 95.0, 105.0]
        m = compute_metrics(FakeResult(curve), 100.0)
        # 일별 수익률: +10%, -13.6%, +10.5%
        # min ≈ -13.6%
        assert m["max_daily_loss_pct"] < -10.0
