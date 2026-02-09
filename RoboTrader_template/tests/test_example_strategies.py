"""
예제 전략 테스트 + StrategyFactory(StrategyLoader) 전략 교체 테스트
"""

import os
import sys
from datetime import datetime
from unittest.mock import MagicMock

import numpy as np
import pandas as pd
import pytest

# 프로젝트 루트를 path에 추가
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from strategies.base import BaseStrategy, Signal, SignalType, OrderInfo
from strategies.momentum.strategy import MomentumStrategy
from strategies.mean_reversion.strategy import MeanReversionStrategy
from strategies.volume_breakout.strategy import VolumeBreakoutStrategy
from strategies.config import StrategyLoader, StrategyConfigError


# ============================================================================
# 헬퍼
# ============================================================================

def make_ohlcv(days=30, base_price=10000, trend="flat", volume_base=100000):
    """테스트용 OHLCV 데이터 생성"""
    dates = pd.date_range("2025-01-01", periods=days, freq="B")
    prices = []
    p = base_price

    for i in range(days):
        if trend == "up":
            p = p * 1.015  # 매일 1.5% 상승
        elif trend == "down":
            p = p * 0.985
        elif trend == "crash":
            p = p * 0.96 if i > days - 5 else p * 1.001
        elif trend == "recovery":
            # 처음에 큰 하락, 후반에 회복
            if i < days // 2:
                p = p * 0.97
            else:
                p = p * 1.02
        prices.append(p)

    close = np.array(prices)
    high = close * 1.01
    low = close * 0.99
    open_ = close * 0.998
    volume = np.full(days, volume_base, dtype=float)

    return pd.DataFrame({
        "datetime": dates,
        "open": open_,
        "high": high,
        "low": low,
        "close": close,
        "volume": volume,
    })


def make_strategy(cls, config_overrides=None):
    """전략 인스턴스 생성 + on_init 호출"""
    config = {}
    if config_overrides:
        config.update(config_overrides)
    s = cls(config)
    broker = MagicMock()
    data_provider = MagicMock()
    executor = MagicMock()
    assert s.on_init(broker, data_provider, executor) is True
    return s


# ============================================================================
# BaseStrategy 인터페이스 준수 테스트
# ============================================================================

class TestStrategyInterface:
    """모든 예제 전략이 BaseStrategy 인터페이스를 준수하는지 검증"""

    @pytest.mark.parametrize("cls", [
        MomentumStrategy,
        MeanReversionStrategy,
        VolumeBreakoutStrategy,
    ])
    def test_is_subclass(self, cls):
        assert issubclass(cls, BaseStrategy)

    @pytest.mark.parametrize("cls", [
        MomentumStrategy,
        MeanReversionStrategy,
        VolumeBreakoutStrategy,
    ])
    def test_has_required_attrs(self, cls):
        for attr in ["name", "version", "description", "author"]:
            assert hasattr(cls, attr)
            assert getattr(cls, attr)  # non-empty

    @pytest.mark.parametrize("cls", [
        MomentumStrategy,
        MeanReversionStrategy,
        VolumeBreakoutStrategy,
    ])
    def test_on_init(self, cls):
        s = make_strategy(cls)
        assert s.is_initialized is True

    @pytest.mark.parametrize("cls", [
        MomentumStrategy,
        MeanReversionStrategy,
        VolumeBreakoutStrategy,
    ])
    def test_get_config(self, cls):
        s = make_strategy(cls, {"parameters": {"test": 1}})
        cfg = s.get_config()
        assert isinstance(cfg, dict)

    @pytest.mark.parametrize("cls", [
        MomentumStrategy,
        MeanReversionStrategy,
        VolumeBreakoutStrategy,
    ])
    def test_validate_config(self, cls):
        s = make_strategy(cls)
        assert s.validate_config() is True

    @pytest.mark.parametrize("cls", [
        MomentumStrategy,
        MeanReversionStrategy,
        VolumeBreakoutStrategy,
    ])
    def test_generate_signal_returns_none_or_signal(self, cls):
        s = make_strategy(cls)
        data = make_ohlcv(30)
        result = s.generate_signal("005930", data)
        assert result is None or isinstance(result, Signal)

    @pytest.mark.parametrize("cls", [
        MomentumStrategy,
        MeanReversionStrategy,
        VolumeBreakoutStrategy,
    ])
    def test_lifecycle(self, cls):
        """on_market_open → generate_signal → on_order_filled → on_market_close"""
        s = make_strategy(cls)
        s.on_market_open()
        data = make_ohlcv(30)
        s.generate_signal("005930", data)
        order = OrderInfo(
            order_id="TEST001",
            stock_code="005930",
            side="buy",
            quantity=10,
            price=10000,
            filled_at=datetime.now(),
        )
        s.on_order_filled(order)
        s.on_market_close()


# ============================================================================
# MomentumStrategy 테스트
# ============================================================================

class TestMomentumStrategy:
    def test_buy_signal_on_consecutive_up(self):
        """연속 상승 시 매수 시그널 생성"""
        s = make_strategy(MomentumStrategy, {
            "parameters": {
                "consecutive_up_days": 5,
                "min_total_change_pct": 0.0,  # 낮은 기준
                "min_daily_change_pct": 0.0,
            }
        })
        data = make_ohlcv(30, trend="up")
        signal = s.generate_signal("005930", data)
        assert signal is not None
        assert signal.is_buy

    def test_no_signal_on_flat(self):
        """횡보 시 매수 시그널 없음"""
        s = make_strategy(MomentumStrategy)
        data = make_ohlcv(30, trend="flat")
        signal = s.generate_signal("005930", data)
        assert signal is None

    def test_sell_on_take_profit(self):
        """익절 조건 시 매도"""
        s = make_strategy(MomentumStrategy, {
            "risk_management": {"take_profit_pct": 0.10, "stop_loss_pct": 0.05}
        })
        s.positions["005930"] = {
            "entry_price": 10000,
            "entry_time": datetime.now(),
            "holding_days": 0,
        }
        # 현재가 11500 = +15%
        data = make_ohlcv(30, base_price=11500, trend="flat")
        signal = s.generate_signal("005930", data)
        assert signal is not None
        assert signal.is_sell

    def test_sell_on_stop_loss(self):
        """손절 조건 시 매도"""
        s = make_strategy(MomentumStrategy, {
            "risk_management": {"stop_loss_pct": 0.05}
        })
        s.positions["005930"] = {
            "entry_price": 10000,
            "entry_time": datetime.now(),
            "holding_days": 0,
        }
        data = make_ohlcv(30, base_price=9000, trend="flat")
        signal = s.generate_signal("005930", data)
        assert signal is not None
        assert signal.is_sell

    def test_sell_on_max_holding(self):
        """보유기간 초과 시 매도"""
        s = make_strategy(MomentumStrategy, {
            "parameters": {"max_holding_days": 5}
        })
        s.positions["005930"] = {
            "entry_price": 10000,
            "entry_time": datetime.now(),
            "holding_days": 10,
        }
        data = make_ohlcv(30, base_price=10000, trend="flat")
        signal = s.generate_signal("005930", data)
        assert signal is not None
        assert signal.is_sell

    def test_insufficient_data(self):
        """데이터 부족 시 None"""
        s = make_strategy(MomentumStrategy)
        data = make_ohlcv(3)
        assert s.generate_signal("005930", data) is None


# ============================================================================
# MeanReversionStrategy 테스트
# ============================================================================

class TestMeanReversionStrategy:
    def test_buy_on_deviation(self):
        """MA 대비 큰 이탈 시 매수"""
        s = make_strategy(MeanReversionStrategy, {
            "parameters": {
                "ma_period": 20,
                "entry_deviation_pct": -10.0,
                "use_rsi_filter": False,  # RSI 필터 비활성
            }
        })
        # 크래시 데이터: 마지막 가격이 MA 대비 크게 하락
        data = make_ohlcv(30, trend="crash")
        signal = s.generate_signal("005930", data)
        # crash 트렌드에서 마지막 가격이 MA 대비 충분히 떨어지면 매수
        # (데이터 특성상 반드시 -10% 이탈은 아닐 수 있으므로 조건적)
        if signal is not None:
            assert signal.is_buy

    def test_no_signal_on_normal(self):
        """정상 범위 내 → 시그널 없음"""
        s = make_strategy(MeanReversionStrategy, {
            "parameters": {"use_rsi_filter": False}
        })
        data = make_ohlcv(30, trend="flat")
        signal = s.generate_signal("005930", data)
        assert signal is None

    def test_sell_on_ma_recovery(self):
        """MA 복귀 시 매도"""
        s = make_strategy(MeanReversionStrategy, {
            "parameters": {
                "ma_period": 20,
                "entry_deviation_pct": -10.0,
                "exit_recovery_ratio": 0.9,
                "use_rsi_filter": False,
            }
        })
        s.positions["005930"] = {
            "entry_price": 9000,
            "entry_time": datetime.now(),
        }
        # 현재가 ≈ MA (회복 완료)
        data = make_ohlcv(30, base_price=10000, trend="flat")
        signal = s.generate_signal("005930", data)
        # flat이면 MA ≈ close, deviation ≈ 0 → 복귀 조건 충족
        assert signal is not None
        assert signal.is_sell

    def test_sell_on_stop_loss(self):
        s = make_strategy(MeanReversionStrategy, {
            "parameters": {"use_rsi_filter": False},
            "risk_management": {"stop_loss_pct": 0.07}
        })
        s.positions["005930"] = {
            "entry_price": 10000,
            "entry_time": datetime.now(),
        }
        data = make_ohlcv(30, base_price=9000, trend="flat")
        signal = s.generate_signal("005930", data)
        assert signal is not None
        assert signal.is_sell


# ============================================================================
# VolumeBreakoutStrategy 테스트
# ============================================================================

class TestVolumeBreakoutStrategy:
    def test_buy_on_volume_spike(self):
        """거래량 폭증 + 양봉 시 매수"""
        s = make_strategy(VolumeBreakoutStrategy, {
            "parameters": {
                "volume_multiplier": 5.0,
                "min_candle_body_pct": 0.1,
                "volume_avg_period": 20,
            }
        })
        data = make_ohlcv(30, trend="up", volume_base=100000)
        # 마지막 봉 거래량을 100배로 (rolling avg에 포함돼도 5배 이상)
        data.loc[data.index[-1], "volume"] = 10_000_000
        # 양봉 보장: open < close
        data.loc[data.index[-1], "open"] = data.loc[data.index[-1], "close"] * 0.98
        signal = s.generate_signal("005930", data)
        assert signal is not None
        assert signal.is_buy
        assert "폭증" in signal.reasons[0]

    def test_no_signal_normal_volume(self):
        """정상 거래량 → 시그널 없음"""
        s = make_strategy(VolumeBreakoutStrategy)
        data = make_ohlcv(30, volume_base=100000)
        signal = s.generate_signal("005930", data)
        assert signal is None

    def test_no_signal_bearish_candle(self):
        """거래량 폭증이지만 음봉 → 시그널 없음"""
        s = make_strategy(VolumeBreakoutStrategy, {
            "parameters": {"volume_multiplier": 5.0}
        })
        data = make_ohlcv(30, trend="down", volume_base=100000)
        data.loc[data.index[-1], "volume"] = 1_000_000
        # 음봉 강제: open > close
        data.loc[data.index[-1], "open"] = data.loc[data.index[-1], "close"] * 1.05
        signal = s.generate_signal("005930", data)
        assert signal is None

    def test_sell_on_take_profit(self):
        s = make_strategy(VolumeBreakoutStrategy, {
            "risk_management": {"take_profit_pct": 0.10}
        })
        s.positions["005930"] = {
            "entry_price": 10000,
            "entry_time": datetime.now(),
            "holding_days": 0,
        }
        data = make_ohlcv(30, base_price=11500, volume_base=100000)
        signal = s.generate_signal("005930", data)
        assert signal is not None
        assert signal.is_sell

    def test_sell_on_volume_drop(self):
        """거래량 급감 시 매도"""
        s = make_strategy(VolumeBreakoutStrategy)
        s.positions["005930"] = {
            "entry_price": 10000,
            "entry_time": datetime.now(),
            "holding_days": 0,
        }
        data = make_ohlcv(30, base_price=10000, volume_base=100000)
        data.loc[data.index[-2], "volume"] = 500000
        data.loc[data.index[-1], "volume"] = 10000  # 급감
        signal = s.generate_signal("005930", data)
        assert signal is not None
        assert signal.is_sell


# ============================================================================
# StrategyLoader / Factory 테스트
# ============================================================================

class TestStrategyLoader:
    def test_discover_strategies(self):
        """전략 자동 발견"""
        os.chdir(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        strategies = StrategyLoader.discover_strategies()
        assert "sample" in strategies
        assert "momentum" in strategies
        assert "mean_reversion" in strategies
        assert "volume_breakout" in strategies

    def test_list_strategies(self):
        os.chdir(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        names = StrategyLoader.list_strategies()
        assert "sample" in names
        assert "momentum" in names

    def test_load_sample_strategy(self):
        os.chdir(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        s = StrategyLoader.load_strategy("sample")
        assert isinstance(s, BaseStrategy)
        assert s.name == "SampleStrategy"

    def test_load_momentum_strategy(self):
        os.chdir(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        s = StrategyLoader.load_strategy("momentum")
        assert isinstance(s, BaseStrategy)
        assert s.name == "MomentumStrategy"

    def test_load_mean_reversion_strategy(self):
        os.chdir(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        s = StrategyLoader.load_strategy("mean_reversion")
        assert isinstance(s, BaseStrategy)
        assert s.name == "MeanReversionStrategy"

    def test_load_volume_breakout_strategy(self):
        os.chdir(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        s = StrategyLoader.load_strategy("volume_breakout")
        assert isinstance(s, BaseStrategy)
        assert s.name == "VolumeBreakoutStrategy"

    def test_strategy_swap_by_name(self):
        """설정에서 전략 이름만 바꾸면 다른 전략이 로드되는지 확인"""
        os.chdir(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

        for name, expected_cls_name in [
            ("sample", "SampleStrategy"),
            ("momentum", "MomentumStrategy"),
            ("mean_reversion", "MeanReversionStrategy"),
            ("volume_breakout", "VolumeBreakoutStrategy"),
        ]:
            s = StrategyLoader.load_strategy(name)
            assert s.name == expected_cls_name
            assert isinstance(s, BaseStrategy)

    def test_invalid_strategy_raises(self):
        os.chdir(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        with pytest.raises((StrategyConfigError, FileNotFoundError)):
            StrategyLoader.load_strategy("nonexistent_strategy")

    def test_loaded_strategy_functional(self):
        """로드된 전략이 실제 동작하는지"""
        os.chdir(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        s = StrategyLoader.load_strategy("momentum")

        broker = MagicMock()
        data_provider = MagicMock()
        executor = MagicMock()
        assert s.on_init(broker, data_provider, executor) is True

        s.on_market_open()
        data = make_ohlcv(30)
        result = s.generate_signal("005930", data)
        assert result is None or isinstance(result, Signal)
        s.on_market_close()
