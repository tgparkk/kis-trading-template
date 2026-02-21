"""
Sawkami Strategy Unit Tests
"""

import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch

import numpy as np
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from strategies.sawkami.strategy import SawkamiStrategy
from strategies.base import Signal, SignalType, OrderInfo
from utils.korean_time import now_kst


# ============================================================================
# Fixtures
# ============================================================================

def _make_config(**overrides):
    config = {
        "paper_trading": True,
        "parameters": {
            "op_income_growth_min": 30.0,
            "high52w_drop_pct": -20.0,
            "high52w_period": 252,
            "pbr_max": 1.5,
            "volume_ratio_min": 1.5,
            "volume_ma_period": 20,
            "rsi_period": 14,
            "rsi_oversold": 30,
        },
        "risk_management": {
            "take_profit_pct": 0.15,
            "stop_loss_pct": 0.15,
            "max_hold_days": 40,
            "max_daily_trades": 5,
        },
        "target_stocks": ["005930"],
    }
    config.update(overrides)
    return config


def _make_ohlcv(n=300, base_price=10000, drop_from_high=True):
    """테스트용 OHLCV DataFrame 생성"""
    dates = pd.date_range(end=datetime.now(), periods=n, freq="B")
    np.random.seed(42)

    if drop_from_high:
        prices_up = np.linspace(base_price, base_price * 1.5, n // 2)
        prices_down = np.linspace(base_price * 1.5, base_price * 1.1, n // 2)
        prices = np.concatenate([prices_up, prices_down])
    else:
        prices = np.full(n, base_price, dtype=float)

    noise = np.random.normal(0, base_price * 0.005, n)
    close = prices + noise

    # 마지막 14일 연속 하락 → RSI < 30
    for i in range(n - 14, n):
        close[i] = close[i - 1] * 0.98

    volume = np.random.randint(100000, 200000, n).astype(float)
    volume[-1] = volume[-21:-1].mean() * 2.0

    df = pd.DataFrame({
        "datetime": dates,
        "open": close * 1.001,
        "high": close * 1.01,
        "low": close * 0.99,
        "close": close,
        "volume": volume,
    })
    return df


_patch_market_open = patch(
    "strategies.sawkami.strategy.MarketHours.is_market_open", return_value=True
)


@pytest.fixture
def strategy():
    s = SawkamiStrategy(_make_config())
    with patch("strategies.sawkami.db_manager.SawkamiDBManager.get_holding_positions", return_value=[]):
        s.on_init(MagicMock(), MagicMock(), MagicMock())
    return s


# ============================================================================
# Tests — Init
# ============================================================================

class TestSawkamiInit:
    def test_init_success(self, strategy):
        assert strategy.is_initialized
        assert strategy._paper_trading is True

    def test_default_params(self, strategy):
        assert strategy._op_growth_min == 30.0
        assert strategy._high52w_drop_pct == -20.0
        assert strategy._pbr_max == 1.5
        assert strategy._take_profit_pct == 0.15
        assert strategy._max_hold_days == 40


# ============================================================================
# Tests — Buy Signal
# ============================================================================

class TestBuySignal:
    @_patch_market_open
    def test_no_signal_without_fundamental(self, _mock, strategy):
        """재무 데이터 없으면 매수 불가"""
        data = _make_ohlcv()
        signal = strategy.generate_signal("005930", data, "daily")
        assert signal is None

    @_patch_market_open
    def test_buy_all_conditions_met(self, _mock, strategy):
        """5개 조건 모두 충족 시 BUY 시그널"""
        data = _make_ohlcv(drop_from_high=True)
        current_price = float(data["close"].iloc[-1])
        strategy._fundamental_cache["005930"] = {
            "op_income_growth": 50.0,
            "bps": current_price * 2,
        }
        signal = strategy.generate_signal("005930", data, "daily")
        assert signal is not None
        assert signal.signal_type == SignalType.BUY
        assert signal.stock_code == "005930"
        assert len(signal.reasons) == 5

    @_patch_market_open
    def test_no_buy_low_op_growth(self, _mock, strategy):
        """영업이익 성장률 30% 미만 → 매수 안 함"""
        data = _make_ohlcv(drop_from_high=True)
        current_price = float(data["close"].iloc[-1])
        strategy._fundamental_cache["005930"] = {
            "op_income_growth": 10.0,
            "bps": current_price * 2,
        }
        signal = strategy.generate_signal("005930", data, "daily")
        assert signal is None

    @_patch_market_open
    def test_no_buy_high_pbr(self, _mock, strategy):
        """PBR >= 1.5 → 매수 안 함"""
        data = _make_ohlcv(drop_from_high=True)
        current_price = float(data["close"].iloc[-1])
        strategy._fundamental_cache["005930"] = {
            "op_income_growth": 50.0,
            "bps": current_price * 0.5,  # PBR = 2.0
        }
        signal = strategy.generate_signal("005930", data, "daily")
        assert signal is None

    @_patch_market_open
    def test_no_buy_52w_high_not_enough_drop(self, _mock, strategy):
        """52주 고점 대비 -20% 미달 → 매수 안 함
        
        고점과 현재가가 가까운 데이터를 생성하여 하락폭 부족 테스트.
        """
        n = 300
        dates = pd.date_range(end=datetime.now(), periods=n, freq="B")
        np.random.seed(42)
        # 지속 상승 → 현재가 ≈ 52주 고점 (drop < 20%)
        close = np.linspace(10000, 12000, n).astype(float)
        # 마지막 14일 소폭 하락 (RSI<30 유도하지만 고점 대비 하락은 작게)
        for i in range(n - 14, n):
            close[i] = close[i - 1] * 0.995
        volume = np.random.randint(100000, 200000, n).astype(float)
        volume[-1] = volume[-21:-1].mean() * 2.0
        data = pd.DataFrame({
            "datetime": dates,
            "open": close * 1.001,
            "high": close * 1.01,
            "low": close * 0.99,
            "close": close,
            "volume": volume,
        })
        current_price = float(data["close"].iloc[-1])
        strategy._fundamental_cache["005930"] = {
            "op_income_growth": 50.0,
            "bps": current_price * 2,
        }
        signal = strategy.generate_signal("005930", data, "daily")
        assert signal is None

    @_patch_market_open
    def test_no_buy_low_volume_ratio(self, _mock, strategy):
        """거래량 1.5배 미만 → 매수 안 함"""
        data = _make_ohlcv(drop_from_high=True)
        current_price = float(data["close"].iloc[-1])
        data.iloc[-1, data.columns.get_loc("volume")] = 10.0
        strategy._fundamental_cache["005930"] = {
            "op_income_growth": 50.0,
            "bps": current_price * 2,
        }
        signal = strategy.generate_signal("005930", data, "daily")
        assert signal is None

    @_patch_market_open
    def test_no_buy_rsi_above_30(self, _mock, strategy):
        """RSI >= 30 → 매수 안 함"""
        n = 300
        dates = pd.date_range(end=datetime.now(), periods=n, freq="B")
        np.random.seed(42)
        prices_up = np.linspace(10000, 15000, n // 2)
        prices_down = np.linspace(15000, 11000, n // 2)
        prices = np.concatenate([prices_up, prices_down])
        # 마지막 14일 상승 → RSI > 30
        for i in range(n - 14, n):
            prices[i] = prices[i - 1] * 1.02
        volume = np.random.randint(100000, 200000, n).astype(float)
        volume[-1] = volume[-21:-1].mean() * 2.0
        data = pd.DataFrame({
            "datetime": dates,
            "open": prices * 1.001,
            "high": prices * 1.01,
            "low": prices * 0.99,
            "close": prices,
            "volume": volume,
        })
        current_price = float(data["close"].iloc[-1])
        strategy._fundamental_cache["005930"] = {
            "op_income_growth": 50.0,
            "bps": current_price * 2,
        }
        signal = strategy.generate_signal("005930", data, "daily")
        assert signal is None


# ============================================================================
# Tests — Sell Signal
# ============================================================================

class TestSellSignal:
    @_patch_market_open
    def test_take_profit(self, _mock, strategy):
        """익절: +15% 도달 → 매도"""
        strategy.positions["005930"] = {
            "entry_price": 10000,
            "entry_time": now_kst() - timedelta(days=5),
        }
        data = _make_ohlcv(n=300, base_price=10000)
        data.iloc[-1, data.columns.get_loc("close")] = 11600
        signal = strategy.generate_signal("005930", data)
        assert signal is not None
        assert signal.signal_type == SignalType.SELL
        assert any("익절" in r for r in signal.reasons)

    @_patch_market_open
    def test_stop_loss(self, _mock, strategy):
        """손절: -15% 도달 → 매도"""
        strategy.positions["005930"] = {
            "entry_price": 10000,
            "entry_time": now_kst() - timedelta(days=5),
        }
        data = _make_ohlcv(n=300, base_price=10000)
        data.iloc[-1, data.columns.get_loc("close")] = 8400
        signal = strategy.generate_signal("005930", data)
        assert signal is not None
        assert signal.signal_type == SignalType.SELL
        assert any("손절" in r for r in signal.reasons)

    @_patch_market_open
    def test_max_hold_days(self, _mock, strategy):
        """최대 보유일 40일 초과 → 매도"""
        strategy.positions["005930"] = {
            "entry_price": 10000,
            "entry_time": now_kst() - timedelta(days=45),
        }
        data = _make_ohlcv(n=300, base_price=10000)
        data.iloc[-1, data.columns.get_loc("close")] = 10100
        signal = strategy.generate_signal("005930", data)
        assert signal is not None
        assert signal.signal_type == SignalType.SELL
        assert any("보유일" in r for r in signal.reasons)

    @_patch_market_open
    def test_no_sell_within_range(self, _mock, strategy):
        """TP/SL/보유일 모두 미충족 → 매도 없음"""
        strategy.positions["005930"] = {
            "entry_price": 10000,
            "entry_time": now_kst() - timedelta(days=5),
        }
        data = _make_ohlcv(n=300, base_price=10000)
        data.iloc[-1, data.columns.get_loc("close")] = 10500
        signal = strategy.generate_signal("005930", data)
        assert signal is None


# ============================================================================
# Tests — Edge Cases
# ============================================================================

class TestEdgeCases:
    @_patch_market_open
    def test_data_none(self, _mock, strategy):
        """data=None → None 반환"""
        signal = strategy.generate_signal("005930", None, "daily")
        assert signal is None

    @_patch_market_open
    def test_data_empty(self, _mock, strategy):
        """빈 DataFrame → None 반환"""
        empty_df = pd.DataFrame(columns=["datetime", "open", "high", "low", "close", "volume"])
        signal = strategy.generate_signal("005930", empty_df, "daily")
        assert signal is None

    @_patch_market_open
    def test_data_too_short(self, _mock, strategy):
        """데이터 252행 미만 → None 반환"""
        short_data = _make_ohlcv(n=100)
        strategy._fundamental_cache["005930"] = {
            "op_income_growth": 50.0,
            "bps": 20000,
        }
        signal = strategy.generate_signal("005930", short_data, "daily")
        assert signal is None

    @_patch_market_open
    def test_bps_zero(self, _mock, strategy):
        """BPS=0 → PBR 계산 불가 → 매수 안 함"""
        data = _make_ohlcv(drop_from_high=True)
        strategy._fundamental_cache["005930"] = {
            "op_income_growth": 50.0,
            "bps": 0,
        }
        signal = strategy.generate_signal("005930", data, "daily")
        assert signal is None

    @_patch_market_open
    def test_volume_zero(self, _mock, strategy):
        """거래량 전부 0 → vol_ma=0 → 매수 안 함"""
        data = _make_ohlcv(drop_from_high=True)
        data["volume"] = 0.0
        current_price = float(data["close"].iloc[-1])
        strategy._fundamental_cache["005930"] = {
            "op_income_growth": 50.0,
            "bps": current_price * 2,
        }
        signal = strategy.generate_signal("005930", data, "daily")
        assert signal is None

    @_patch_market_open
    def test_52w_high_zero(self, _mock, strategy):
        """52주 고점 0 → 매수 안 함"""
        data = _make_ohlcv(drop_from_high=True)
        data["high"] = 0.0
        current_price = float(data["close"].iloc[-1])
        strategy._fundamental_cache["005930"] = {
            "op_income_growth": 50.0,
            "bps": current_price * 2,
        }
        signal = strategy.generate_signal("005930", data, "daily")
        assert signal is None


# ============================================================================
# Tests — Order Filled
# ============================================================================

class TestOrderFilled:
    def test_buy_order_records_position(self, strategy):
        with patch.object(strategy._db, 'open_trade', return_value=1):
            order = OrderInfo(
                order_id="ORD001",
                stock_code="005930",
                side="buy",
                quantity=10,
                price=10000,
                filled_at=now_kst(),
            )
            strategy.on_order_filled(order)
            assert "005930" in strategy.positions
            assert strategy.positions["005930"]["entry_price"] == 10000

    def test_sell_order_removes_position(self, strategy):
        strategy.positions["005930"] = {
            "entry_price": 10000,
            "entry_time": now_kst(),
        }
        with patch.object(strategy._db, 'close_trade', return_value=True):
            order = OrderInfo(
                order_id="ORD002",
                stock_code="005930",
                side="sell",
                quantity=10,
                price=11500,
                filled_at=now_kst(),
            )
            strategy.on_order_filled(order)
            assert "005930" not in strategy.positions


# ============================================================================
# Tests — RSI (utils.indicators)
# ============================================================================

class TestRSI:
    def test_rsi_range(self):
        from utils.indicators import calculate_rsi
        np.random.seed(0)
        series = pd.Series(np.random.normal(100, 5, 100).cumsum())
        rsi = calculate_rsi(series, 14)
        valid = rsi.dropna()
        assert (valid >= 0).all() and (valid <= 100).all()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
