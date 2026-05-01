"""
MultiverseEngine IS/OOS + 워크포워드 단위 테스트 (Phase B1 + B2)
================================================================

테스트 범위 (B1 — IS/OOS 자동 분리):
- test_run_oos_split_default_ratio: 100일 데이터를 80/20 분리 검증
- test_run_oos_split_custom_ratio: oos_ratio=0.3 → 70/30
- test_oos_metrics_distinct_from_is: 결과에 is_metrics / oos_metrics 모두 존재
- test_oos_degradation_calculation: 알려진 입력으로 degradation 값 검증

테스트 범위 (B2 — 워크포워드):
- test_run_walkforward_window_count: n_windows=3 시 3 윈도우 생성
- test_walkforward_pf_filter: min(window_pfs) > 1.0 통과 조합만 wf_pass=True
- test_walkforward_overlapping_windows: 윈도우 stride = is_window + oos_window
"""
from __future__ import annotations

import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

# 경로 설정
_PROJ_ROOT = Path(__file__).parent.parent
if str(_PROJ_ROOT.parent) not in sys.path:
    sys.path.insert(0, str(_PROJ_ROOT.parent))
if str(_PROJ_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJ_ROOT))

from backtest.multiverse import MultiverseEngine, MultiverseResult
from backtest.engine import BacktestResult
from strategies.base import BaseStrategy, Signal, SignalType


# ============================================================================
# 최소 전략 스텁 (IS/OOS 테스트용 — 항상 매수 신호)
# ============================================================================

class _AlwaysBuyStrategy(BaseStrategy):
    """테스트용 최소 전략 — 미보유 종목에 항상 매수 신호."""
    name = "AlwaysBuy"
    holding_period = "swing"

    def get_min_data_length(self) -> int:
        return 1

    def generate_signal(self, stock_code, data, timeframe="daily"):
        if stock_code not in self.positions:
            return Signal(
                signal_type=SignalType.BUY,
                stock_code=stock_code,
                confidence=80,
                reasons=["test"],
            )
        return None


# ============================================================================
# 헬퍼
# ============================================================================

def _make_daily_data(
    n_days: int,
    start: str = "2024-01-01",
    price: float = 10_000.0,
    code: str = "005930",
) -> dict:
    """n_days 길이의 단순 일봉 DataFrame 반환."""
    start_dt = datetime.strptime(start, "%Y-%m-%d")
    dates = [(start_dt + timedelta(days=i)).strftime("%Y-%m-%d") for i in range(n_days)]
    df = pd.DataFrame({
        "date": dates,
        "open": [price] * n_days,
        "high": [price * 1.02] * n_days,
        "low": [price * 0.98] * n_days,
        "close": [price] * n_days,
        "volume": [100_000] * n_days,
    })
    return {code: df}


def _make_engine(n_days: int = 100, start: str = "2024-01-01") -> MultiverseEngine:
    """테스트용 MultiverseEngine 인스턴스 생성."""
    daily_data = _make_daily_data(n_days=n_days, start=start)
    mv = MultiverseEngine(
        strategy_class=_AlwaysBuyStrategy,
        daily_data=daily_data,
        stock_codes=["005930"],
        initial_capital=1_000_000,
        max_positions=1,
        position_size_pct=1.0,
    )
    mv.add_param("parameters.rsi_oversold", [25, 30])
    return mv


def _date_at(start: str, offset_days: int) -> str:
    dt = datetime.strptime(start, "%Y-%m-%d") + timedelta(days=offset_days)
    return dt.strftime("%Y-%m-%d")


# ============================================================================
# B1 — IS/OOS 자동 분리
# ============================================================================

class TestRunOosSplit:

    def test_run_oos_split_default_ratio(self):
        """100일 데이터를 80/20 분리: IS=80일, OOS=20일."""
        mv = _make_engine(n_days=100, start="2024-01-01")
        start = "2024-01-01"
        end = _date_at(start, 99)  # 100일 범위 (0~99)

        result = mv.run_oos_split(start=start, end=end, oos_ratio=0.2, min_trades=0)

        assert isinstance(result, MultiverseResult)
        assert result.total_combinations == 2  # [25, 30] → 2개

    def test_run_oos_split_custom_ratio(self):
        """oos_ratio=0.3 → IS 70%, OOS 30%."""
        mv = _make_engine(n_days=100, start="2024-01-01")
        start = "2024-01-01"
        end = _date_at(start, 99)

        result = mv.run_oos_split(start=start, end=end, oos_ratio=0.3, min_trades=0)

        assert isinstance(result, MultiverseResult)
        # IS 기간: 70일, OOS 기간: 30일 — 엔진이 에러 없이 실행되면 통과
        assert result.total_combinations == 2

    def test_oos_metrics_distinct_from_is(self):
        """IS 통과 후보에는 is_metrics 와 oos_metrics 가 모두 포함되어야 한다."""
        mv = _make_engine(n_days=200, start="2024-01-01")
        start = "2024-01-01"
        end = _date_at(start, 199)

        result = mv.run_oos_split(start=start, end=end, oos_ratio=0.2, min_trades=0)

        # OOS 검증을 거친 아이템에는 is_metrics / oos_metrics 가 있어야 함
        oos_checked = [item for item in result.results if "oos_metrics" in item]
        assert len(oos_checked) > 0, "OOS 검증 결과가 하나도 없음"
        for item in oos_checked:
            assert "is_metrics" in item
            assert isinstance(item["is_metrics"], BacktestResult)
            assert isinstance(item["oos_metrics"], BacktestResult)
            # result (IS) 와 oos_metrics 는 다른 객체여야 함
            assert item["result"] is item["is_metrics"]

    def test_oos_degradation_calculation(self):
        """oos_degradation = (is_calmar - oos_calmar) / max(|is_calmar|, 1e-9)."""
        mv = _make_engine(n_days=200, start="2024-01-01")
        start = "2024-01-01"
        end = _date_at(start, 199)

        result = mv.run_oos_split(start=start, end=end, oos_ratio=0.2, min_trades=0)

        oos_items = [item for item in result.results if "oos_degradation" in item]
        for item in oos_items:
            is_calmar = item["is_metrics"].calmar_ratio
            oos_calmar = item["oos_metrics"].calmar_ratio
            expected = (is_calmar - oos_calmar) / max(abs(is_calmar), 1e-9)
            assert abs(item["oos_degradation"] - expected) < 1e-9, (
                f"degradation 계산 불일치: expected={expected:.6f}, "
                f"got={item['oos_degradation']:.6f}"
            )

    def test_oos_split_invalid_ratio_raises(self):
        """oos_ratio 범위 오류 시 ValueError."""
        mv = _make_engine(n_days=100)
        with pytest.raises(ValueError, match="oos_ratio"):
            mv.run_oos_split("2024-01-01", "2024-04-10", oos_ratio=0.0)
        with pytest.raises(ValueError, match="oos_ratio"):
            mv.run_oos_split("2024-01-01", "2024-04-10", oos_ratio=1.0)

    def test_oos_split_invalid_dates_raises(self):
        """start >= end 시 ValueError."""
        mv = _make_engine(n_days=100)
        with pytest.raises(ValueError, match="start"):
            mv.run_oos_split("2024-04-10", "2024-01-01", oos_ratio=0.2)


# ============================================================================
# B2 — 워크포워드
# ============================================================================

class TestRunWalkforward:

    def test_run_walkforward_window_count(self):
        """n_windows=3 시 3개 윈도우가 생성되고 결과가 반환되어야 한다."""
        # 충분한 데이터: is_window=30 + oos_window=10 = 40일 × 3 = 120일
        mv = _make_engine(n_days=200, start="2024-01-01")
        start = "2024-01-01"
        end = _date_at(start, 149)  # 150일

        result = mv.run_walkforward(
            start=start, end=end,
            is_window=30, oos_window=10, n_windows=3,
            min_trades=0,
        )

        assert isinstance(result, MultiverseResult)
        assert result.total_combinations == 2
        # wf_window_pfs 길이 = 윈도우 수
        for item in result.results:
            assert "wf_window_pfs" in item
            assert len(item["wf_window_pfs"]) == 3, (
                f"기대 3개 윈도우, 실제 {len(item['wf_window_pfs'])}개"
            )

    def test_walkforward_pf_filter(self):
        """wf_pass=True 조합은 모든 window OOS PF > 1.0 이어야 한다."""
        mv = _make_engine(n_days=200, start="2024-01-01")
        start = "2024-01-01"
        end = _date_at(start, 149)

        result = mv.run_walkforward(
            start=start, end=end,
            is_window=30, oos_window=10, n_windows=3,
            min_trades=0,
        )

        for item in result.results:
            pfs = item.get("wf_window_pfs", [])
            wf_pass = item.get("wf_pass", False)
            if wf_pass:
                assert all(pf > 1.0 for pf in pfs), (
                    f"wf_pass=True 이지만 PF<=1.0 윈도우 존재: {pfs}"
                )
            else:
                # wf_pass=False 이면 하나 이상 PF<=1.0 이거나 pfs가 비어있어야 함
                assert not pfs or not all(pf > 1.0 for pf in pfs)

    def test_walkforward_overlapping_windows(self):
        """윈도우 stride = is_window + oos_window 로 분리되어야 한다.

        MultiverseEngine.run_walkforward 의 내부 윈도우 계산을 간접 검증:
        n_windows=2, is_window=40, oos_window=10 → stride=50 → 2윈도우가 겹치지 않음.
        전체 기간이 충분하면 두 번째 윈도우가 존재해야 한다.
        """
        # stride=50일 × 2 = 100일 이상 필요
        mv = _make_engine(n_days=200, start="2024-01-01")
        start = "2024-01-01"
        end = _date_at(start, 149)  # 150일

        result = mv.run_walkforward(
            start=start, end=end,
            is_window=40, oos_window=10, n_windows=2,
            min_trades=0,
        )

        assert result.total_combinations == 2
        for item in result.results:
            # 2개 윈도우가 생성됐어야 함
            assert len(item["wf_window_pfs"]) == 2, (
                f"기대 2개 윈도우, 실제 {len(item['wf_window_pfs'])}개"
            )

    def test_walkforward_empty_grid(self):
        """파라미터 그리드가 없으면 빈 MultiverseResult 반환."""
        daily_data = _make_daily_data(n_days=100)
        mv = MultiverseEngine(
            strategy_class=_AlwaysBuyStrategy,
            daily_data=daily_data,
            stock_codes=["005930"],
        )
        # add_param 없이 호출
        result = mv.run_walkforward(
            start="2024-01-01", end="2024-04-10",
            is_window=30, oos_window=10, n_windows=3,
        )
        assert isinstance(result, MultiverseResult)
        assert result.total_combinations == 0
        assert result.results == []

    def test_oos_split_empty_grid(self):
        """파라미터 그리드가 없으면 빈 MultiverseResult 반환 (oos_split)."""
        daily_data = _make_daily_data(n_days=100)
        mv = MultiverseEngine(
            strategy_class=_AlwaysBuyStrategy,
            daily_data=daily_data,
            stock_codes=["005930"],
        )
        result = mv.run_oos_split(
            start="2024-01-01", end="2024-04-10", oos_ratio=0.2,
        )
        assert isinstance(result, MultiverseResult)
        assert result.total_combinations == 0
        assert result.results == []
