"""
Phase C2: BacktestEngine force_eod_liquidation 옵션 테스트
==========================================================

테스트 목록:
- test_force_eod_true_forces_swing_strategy_to_close_daily: force_eod=True → swing도 EOD 청산
- test_force_eod_false_allows_intraday_to_hold_days: force_eod=False → intraday도 다일 보유
- test_force_eod_none_uses_holding_period_intraday: force_eod=None + intraday → 기존 EOD 동작
- test_force_eod_none_uses_holding_period_swing: force_eod=None + swing → EOD 청산 없음
"""
import pytest
import pandas as pd

from backtest.engine import BacktestEngine
from strategies.base import BaseStrategy, Signal, SignalType


# ============================================================================
# 전략 스텁
# ============================================================================

class _SwingBuyOnce(BaseStrategy):
    """스윙 전략: 첫 날 매수, 이후 신호 없음."""
    name = "SwingBuyOnce"
    holding_period = "swing"

    def get_min_data_length(self) -> int:
        return 1

    def generate_signal(self, stock_code, data, timeframe="daily"):
        if stock_code not in self.positions:
            return Signal(signal_type=SignalType.BUY, stock_code=stock_code,
                          confidence=90, reasons=["test"])
        return None


class _IntradayBuyOnce(BaseStrategy):
    """인트라데이 전략: 첫 날 매수, 이후 신호 없음."""
    name = "IntradayBuyOnce"
    holding_period = "intraday"

    def get_min_data_length(self) -> int:
        return 1

    def generate_signal(self, stock_code, data, timeframe="daily"):
        if stock_code not in self.positions:
            return Signal(signal_type=SignalType.BUY, stock_code=stock_code,
                          confidence=90, reasons=["test"])
        return None


# ============================================================================
# 헬퍼
# ============================================================================

def _make_ohlcv(dates, closes=None):
    n = len(dates)
    closes = closes or [10_000] * n
    return pd.DataFrame({
        "date": dates,
        "open": closes,
        "high": closes,
        "low": closes,
        "close": closes,
        "volume": [100_000] * n,
    })


def _make_engine(strategy, **kwargs):
    defaults = dict(
        initial_capital=1_000_000,
        max_positions=1,
        position_size_pct=1.0,
        commission_rate=0.0,
        tax_rate=0.0,
    )
    defaults.update(kwargs)
    return BacktestEngine(strategy=strategy, **defaults)


# ============================================================================
# C2 테스트
# ============================================================================

class TestForceEodTrue:
    """force_eod_liquidation=True → swing 전략도 매일 EOD 청산."""

    def test_force_eod_true_forces_swing_strategy_to_close_daily(self):
        """swing 전략에 force_eod=True → 매수 다음날 EOD 청산."""
        strategy = _SwingBuyOnce()
        strategy._stop_loss_pct = 0.50
        strategy._take_profit_pct = 2.00
        engine = _make_engine(strategy)

        # 3일 데이터: Day1 매수, Day2 EOD 청산 (force_eod=True)
        data = _make_ohlcv(
            dates=["2024-01-02", "2024-01-03", "2024-01-04"],
            closes=[10_000] * 3,
        )

        result = engine.run(["A"], {"A": data}, force_eod_liquidation=True)

        assert result.sells_by_reason.get("eod", 0) >= 1, (
            f"force_eod=True면 swing도 EOD 청산 기대. sells={result.sells_by_reason}"
        )
        # _SwingBuyOnce는 EOD 매도 후 재매수하므로 forced_exit는 검증하지 않음


class TestForceEodFalse:
    """force_eod_liquidation=False → intraday 전략도 다일 보유."""

    def test_force_eod_false_allows_intraday_to_hold_days(self):
        """intraday 전략에 force_eod=False → EOD 청산 없이 강제청산까지 보유."""
        strategy = _IntradayBuyOnce()
        strategy._stop_loss_pct = 0.50
        strategy._take_profit_pct = 2.00
        engine = _make_engine(strategy)

        # 3일: Day1 매수, Day2+3 EOD 청산 없이 보유, 마지막날 강제청산
        data = _make_ohlcv(
            dates=["2024-01-02", "2024-01-03", "2024-01-04"],
            closes=[10_000] * 3,
        )

        result = engine.run(["A"], {"A": data}, force_eod_liquidation=False)

        assert result.sells_by_reason.get("eod", 0) == 0, (
            f"force_eod=False면 EOD 청산 없어야 함. sells={result.sells_by_reason}"
        )
        assert result.sells_by_reason.get("forced_exit", 0) == 1, (
            "마지막날 강제청산 1건 기대"
        )


class TestForceEodNone:
    """force_eod_liquidation=None (기본) → holding_period 기반 자동 결정."""

    def test_force_eod_none_uses_holding_period_intraday(self):
        """None + intraday → 기존 EOD 동작 (매수 다음날 청산)."""
        strategy = _IntradayBuyOnce()
        strategy._stop_loss_pct = 0.50
        strategy._take_profit_pct = 2.00
        engine = _make_engine(strategy)

        data = _make_ohlcv(
            dates=["2024-01-02", "2024-01-03"],
            closes=[10_000, 10_200],
        )

        result = engine.run(["A"], {"A": data}, force_eod_liquidation=None)

        assert result.sells_by_reason.get("eod", 0) >= 1, (
            f"None+intraday → EOD 청산 기대. sells={result.sells_by_reason}"
        )

    def test_force_eod_none_uses_holding_period_swing(self):
        """None + swing → EOD 청산 없음, 강제청산으로 종료."""
        strategy = _SwingBuyOnce()
        strategy._stop_loss_pct = 0.50
        strategy._take_profit_pct = 2.00
        engine = _make_engine(strategy)

        data = _make_ohlcv(
            dates=["2024-01-02", "2024-01-03", "2024-01-04"],
            closes=[10_000] * 3,
        )

        result = engine.run(["A"], {"A": data}, force_eod_liquidation=None)

        assert result.sells_by_reason.get("eod", 0) == 0, (
            f"None+swing → EOD 없어야 함. sells={result.sells_by_reason}"
        )
        assert result.sells_by_reason.get("forced_exit", 0) == 1

    def test_force_eod_default_same_as_none(self):
        """force_eod_liquidation 미전달 = None과 동일."""
        strategy = _IntradayBuyOnce()
        strategy._stop_loss_pct = 0.50
        strategy._take_profit_pct = 2.00
        engine = _make_engine(strategy)

        data = _make_ohlcv(
            dates=["2024-01-02", "2024-01-03"],
            closes=[10_000, 10_200],
        )

        result_default = engine.run(["A"], {"A": data})
        result_none = engine.run(["A"], {"A": data}, force_eod_liquidation=None)

        assert result_default.sells_by_reason == result_none.sells_by_reason
