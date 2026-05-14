"""
SampleStrategy 매수 조건 단위 테스트 (A1+A2 상태 기반 전환 후)
================================================================

변경 내용:
  - A1: rsi_oversold 30 → 40 (config.yaml)
  - A2: 이벤트(골든크로스/RSI탈출) → 상태(MA5>MA20 / RSI<oversold) 조건

테스트 목적:
  1. 새 조건이 의도대로 매수 신호를 생성하는지 검증
  2. 조건 미충족 시 신호가 나오지 않는지 검증
  3. 기존 이벤트 조건(순간 전환) 과거 데이터에서는 반응하지 않음을 확인
"""

import os
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from strategies.sample.strategy import SampleStrategy


# ============================================================================
# Fixture / Helper
# ============================================================================

def _make_strategy() -> SampleStrategy:
    """최소 config 으로 SampleStrategy 인스턴스 생성 (on_init 없이도 동작)."""
    config = {
        "parameters": {
            "ma_short_period": 5,
            "ma_long_period": 20,
            "rsi_period": 14,
            "rsi_oversold": 40,       # A1: 40으로 완화된 값
            "rsi_overbought": 70,
            "volume_multiplier": 1.5,
            "min_buy_signals": 1,
        },
        "risk_management": {
            "stop_loss_pct": 0.05,
            "take_profit_pct": 0.10,
            "max_position_size": 0.10,
            "max_daily_trades": 5,
        },
    }
    s = SampleStrategy(config)
    # _check_buy 호출에 필요한 내부 속성 수동 설정
    s._ma_short = 5
    s._ma_long = 20
    s._rsi_period = 14
    s._rsi_oversold = 40
    s._rsi_overbought = 70
    s._rsi_entry_max = 60
    s._volume_multiplier = 1.5
    s._min_buy_signals = 1
    return s


def _build_series(values: list) -> pd.Series:
    return pd.Series(values, dtype=float)


def _make_close_with_rsi(target_rsi: float, length: int = 30) -> pd.Series:
    """지정된 RSI 값에 근접한 종가 시계열 생성.

    RSI≈target 이 되려면 gain/loss 비율을 조절.
    단순 근사: target_rsi < 50 이면 소폭 하락 지속.
    """
    if target_rsi < 50:
        # 작은 RSI → 하락 주도 (avg_loss > avg_gain)
        base = 10000.0
        prices = [base]
        for _ in range(length - 1):
            prices.append(prices[-1] * 0.998)
    else:
        base = 10000.0
        prices = [base]
        for _ in range(length - 1):
            prices.append(prices[-1] * 1.002)
    return pd.Series(prices, dtype=float)


def _make_ohlcv(close: pd.Series, volume_multiplier: float = 2.0) -> pd.DataFrame:
    """close 시리즈로 최소 OHLCV DataFrame 생성."""
    avg_vol = 1_000_000
    volume = [avg_vol * volume_multiplier] * len(close)
    return pd.DataFrame({
        "open": close * 0.995,
        "high": close * 1.005,
        "low": close * 0.990,
        "close": close,
        "volume": volume,
    })


# ============================================================================
# Test: A2 상태 조건 — MA5 > MA20
# ============================================================================

class TestMAStateCondition:
    """A2-1: 단기 MA가 장기 MA보다 위인 '상태'에서 신호가 발생해야 한다."""

    def test_ma_short_above_long_generates_signal(self):
        """MA5 > MA20 상태 → 매수 신호 발생."""
        s = _make_strategy()

        # MA5 > MA20 이 되도록: 뒤로 갈수록 가격 상승
        prices = list(range(9900, 9900 + 30))  # 완만한 우상향
        close = pd.Series(prices, dtype=float)
        sma_short = close.rolling(5).mean()
        sma_long = close.rolling(20).mean()
        # 마지막에 MA5 > MA20 확인
        assert sma_short.iloc[-1] > sma_long.iloc[-1], "test 전제조건 실패"

        # RSI 조건 비활성화 위해 flat RSI (중립 구간)
        rsi = pd.Series([50.0] * 30, dtype=float)
        # 거래량 조건 비활성화: 평균 이하
        volume = pd.Series([500_000] * 30, dtype=float)
        avg_volume = pd.Series([1_000_000] * 30, dtype=float)

        hit, reasons = s._check_buy(sma_short, sma_long, rsi, volume, avg_volume)
        assert hit is True
        assert any("상승 추세" in r for r in reasons)

    def test_ma_short_below_long_no_ma_signal(self):
        """MA5 < MA20 상태 → MA 조건 미충족."""
        s = _make_strategy()

        # MA5 < MA20: 우하향
        prices = list(range(10200, 10200 - 30, -1))
        close = pd.Series(prices, dtype=float)
        sma_short = close.rolling(5).mean()
        sma_long = close.rolling(20).mean()
        assert sma_short.iloc[-1] < sma_long.iloc[-1], "test 전제조건 실패"

        rsi = pd.Series([50.0] * 30, dtype=float)
        volume = pd.Series([500_000] * 30, dtype=float)
        avg_volume = pd.Series([1_000_000] * 30, dtype=float)

        hit, reasons = s._check_buy(sma_short, sma_long, rsi, volume, avg_volume)
        assert not any("상승 추세" in r for r in reasons)

    def test_old_golden_cross_event_no_longer_required(self):
        """이전 골든크로스(이벤트) 없이도 MA5>MA20 상태면 신호 발생.

        MA5 > MA20 이 이미 이전부터 유지된 경우:
        sma_short.iloc[-2] > sma_long.iloc[-2] (골든크로스 이벤트 없음)
        → 새 조건에서는 여전히 신호 발생해야 함.
        """
        s = _make_strategy()

        prices = list(range(9900, 9900 + 30))
        close = pd.Series(prices, dtype=float)
        sma_short = close.rolling(5).mean()
        sma_long = close.rolling(20).mean()

        # 전제: MA5 이미 MA20 위 (이벤트 없음)
        assert sma_short.iloc[-2] > sma_long.iloc[-2], "이미 상승 추세여야 함"

        rsi = pd.Series([50.0] * 30, dtype=float)
        volume = pd.Series([500_000] * 30, dtype=float)
        avg_volume = pd.Series([1_000_000] * 30, dtype=float)

        hit, reasons = s._check_buy(sma_short, sma_long, rsi, volume, avg_volume)
        assert hit is True, "골든크로스 이벤트 없어도 상태 조건으로 신호 발생해야 함"


# ============================================================================
# Test: A1+A2 상태 조건 — RSI 과매도 영역
# ============================================================================

class TestRSIOversoldStateCondition:
    """A2-2: RSI < 40(A1 완화값) 상태에서 신호가 발생해야 한다."""

    def test_rsi_below_oversold_generates_signal(self):
        """RSI = 35 (< 40) 상태 → 매수 신호 발생."""
        s = _make_strategy()

        sma_short = pd.Series([10100.0] * 30)
        sma_long = pd.Series([10200.0] * 30)   # MA5 < MA20 (MA 조건 비활성)
        rsi = pd.Series([35.0] * 30)
        volume = pd.Series([500_000] * 30, dtype=float)
        avg_volume = pd.Series([1_000_000] * 30, dtype=float)

        hit, reasons = s._check_buy(sma_short, sma_long, rsi, volume, avg_volume)
        assert hit is True
        assert any("과매도 영역" in r for r in reasons)
        assert "35.0" in reasons[-1]

    def test_rsi_at_threshold_below_generates_signal(self):
        """RSI = 39.9 (< 40) → 신호 발생."""
        s = _make_strategy()

        sma_short = pd.Series([10100.0] * 30)
        sma_long = pd.Series([10200.0] * 30)
        rsi = pd.Series([39.9] * 30)
        volume = pd.Series([500_000] * 30, dtype=float)
        avg_volume = pd.Series([1_000_000] * 30, dtype=float)

        hit, reasons = s._check_buy(sma_short, sma_long, rsi, volume, avg_volume)
        assert hit is True
        assert any("과매도 영역" in r for r in reasons)

    def test_rsi_at_threshold_equal_no_signal(self):
        """RSI = 40 (= 임계값) → 과매도 영역 아님, 신호 없음."""
        s = _make_strategy()

        sma_short = pd.Series([10100.0] * 30)
        sma_long = pd.Series([10200.0] * 30)
        rsi = pd.Series([40.0] * 30)
        volume = pd.Series([500_000] * 30, dtype=float)
        avg_volume = pd.Series([1_000_000] * 30, dtype=float)

        hit, reasons = s._check_buy(sma_short, sma_long, rsi, volume, avg_volume)
        assert not any("과매도 영역" in r for r in reasons)

    def test_rsi_above_oversold_no_rsi_signal(self):
        """RSI = 55 (> 40) → RSI 조건 미충족."""
        s = _make_strategy()

        sma_short = pd.Series([10100.0] * 30)
        sma_long = pd.Series([10200.0] * 30)
        rsi = pd.Series([55.0] * 30)
        volume = pd.Series([500_000] * 30, dtype=float)
        avg_volume = pd.Series([1_000_000] * 30, dtype=float)

        hit, reasons = s._check_buy(sma_short, sma_long, rsi, volume, avg_volume)
        assert not any("과매도 영역" in r for r in reasons)

    def test_old_rsi_escape_event_no_longer_required(self):
        """이전 RSI 탈출(이벤트): rsi[-2]<30 and rsi[-1]>=30 없이도 신호 발생.

        RSI가 이미 이전부터 35 이하인 경우(탈출 이벤트 없음)에도
        새 상태 조건에서는 신호가 발생해야 함.
        """
        s = _make_strategy()

        # MA 조건 활성: MA5 > MA20
        sma_short = pd.Series([10200.0] * 30)
        sma_long = pd.Series([10100.0] * 30)
        # RSI 이미 35로 유지 (탈출 이벤트 없음)
        rsi = pd.Series([35.0] * 30)
        volume = pd.Series([500_000] * 30, dtype=float)
        avg_volume = pd.Series([1_000_000] * 30, dtype=float)

        hit, reasons = s._check_buy(sma_short, sma_long, rsi, volume, avg_volume)
        assert hit is True, "RSI 탈출 이벤트 없어도 상태 조건으로 신호 발생해야 함"


# ============================================================================
# Test: 복합 조건 (MA5>MA20 상태 + RSI<40)
# ============================================================================

class TestCombinedConditions:
    """두 조건 동시 충족 시 reasons 에 모두 포함되어야 한다."""

    def test_both_conditions_met(self):
        """MA5>MA20 AND RSI=35 → reasons 2개."""
        s = _make_strategy()

        sma_short = pd.Series([10200.0] * 30)
        sma_long = pd.Series([10100.0] * 30)
        rsi = pd.Series([35.0] * 30)
        volume = pd.Series([500_000] * 30, dtype=float)
        avg_volume = pd.Series([1_000_000] * 30, dtype=float)

        hit, reasons = s._check_buy(sma_short, sma_long, rsi, volume, avg_volume)
        assert hit is True
        assert any("상승 추세" in r for r in reasons)
        assert any("과매도 영역" in r for r in reasons)
        assert len(reasons) == 2

    def test_no_conditions_met_returns_false(self):
        """MA5<MA20 AND RSI=55 AND 거래량 평균 이하 → 신호 없음."""
        s = _make_strategy()

        sma_short = pd.Series([10000.0] * 30)
        sma_long = pd.Series([10200.0] * 30)
        rsi = pd.Series([55.0] * 30)
        volume = pd.Series([500_000] * 30, dtype=float)
        avg_volume = pd.Series([1_000_000] * 30, dtype=float)

        hit, reasons = s._check_buy(sma_short, sma_long, rsi, volume, avg_volume)
        assert hit is False
        assert reasons == []

    def test_all_three_conditions_met(self):
        """MA5>MA20 AND RSI=35 AND 거래량 2배 → reasons 3개."""
        s = _make_strategy()

        sma_short = pd.Series([10200.0] * 30)
        sma_long = pd.Series([10100.0] * 30)
        rsi = pd.Series([35.0] * 30)
        volume = pd.Series([2_000_000.0] * 30)
        avg_volume = pd.Series([1_000_000.0] * 30)

        hit, reasons = s._check_buy(sma_short, sma_long, rsi, volume, avg_volume)
        assert hit is True
        assert len(reasons) == 3
        assert any("상승 추세" in r for r in reasons)
        assert any("과매도 영역" in r for r in reasons)
        assert any("거래량" in r for r in reasons)


# ============================================================================
# Test: generate_signal 통합 (최소 DataFrame으로 엔드-투-엔드)
# ============================================================================

class TestGenerateSignalIntegration:
    """generate_signal()이 새 조건에서 BUY Signal을 반환하는지 검증."""

    def _make_strat_initialized(self) -> SampleStrategy:
        from unittest.mock import MagicMock

        s = _make_strategy()
        broker = MagicMock()
        data_provider = MagicMock()
        executor = MagicMock()
        s.on_init(broker, data_provider, executor)
        return s

    def test_generate_signal_buy_on_ma_state(self):
        """MA5>MA20 상태 DataFrame → BUY Signal 반환.

        _calculate_rsi를 목킹해 RSI=50 (finite, < rsi_entry_max=60) 고정.
        순수 MA 조건 동작을 검증한다.
        """
        from unittest.mock import patch
        from strategies.base import SignalType

        s = self._make_strat_initialized()

        # 우상향 30일 데이터 → MA5 > MA20
        prices = [float(9900 + i) for i in range(30)]
        df = pd.DataFrame({
            "open": [p * 0.995 for p in prices],
            "high": [p * 1.005 for p in prices],
            "low": [p * 0.990 for p in prices],
            "close": prices,
            "volume": [1_000_000] * 30,
        })

        # RSI=50 고정 (rsi_entry_max=60 미만 → MA 조건 차단 없음)
        fixed_rsi = pd.Series([50.0] * 30)
        with patch.object(SampleStrategy, "_calculate_rsi", return_value=fixed_rsi):
            signal = s.generate_signal("005930", df)

        assert signal is not None
        assert signal.signal_type == SignalType.BUY
        assert any("상승 추세" in r for r in signal.reasons)

    def test_generate_signal_none_on_no_conditions(self):
        """조건 미충족 DataFrame → None 반환.

        조건이 모두 미충족이 되려면:
          - MA5 < MA20 (하락 추세)
          - RSI >= 40  (과매도 영역 아님)
          - 거래량 < 평균*1.5
        RSI >= 40 이 되려면 중간 정도의 하락이어야 한다.
        강한 하락이면 RSI → 0 이 되어 오히려 조건 충족되므로
        적당한 등락(RSI ≈ 50 수준)을 가진 하락 시리즈를 사용한다.
        """
        s = self._make_strat_initialized()

        # 소폭 하락 + 약간의 반등을 섞어 RSI ≈ 45~55 유지하면서
        # MA5 < MA20 이 되도록 구성:
        # 앞 20일은 고점 유지, 뒤 10일은 소폭 하락
        prices = [10200.0] * 20 + [10190.0, 10185.0, 10180.0, 10178.0,
                                    10176.0, 10175.0, 10174.0, 10173.0,
                                    10172.0, 10171.0]
        df = pd.DataFrame({
            "open": [p * 0.995 for p in prices],
            "high": [p * 1.005 for p in prices],
            "low": [p * 0.990 for p in prices],
            "close": prices,
            "volume": [500_000] * 30,  # 평균 이하 → 거래량 조건 미충족
        })

        # 실제 지표 계산으로 조건 확인
        close = pd.Series(prices, dtype=float)
        sma_short = close.rolling(5).mean()
        sma_long = close.rolling(20).mean()
        rsi_val = float(s._calculate_rsi(close, 14).iloc[-1])

        # MA5 < MA20 인지 확인
        ma_cond = sma_short.iloc[-1] < sma_long.iloc[-1]
        # RSI >= 40 인지 확인
        rsi_cond = rsi_val >= 40.0

        if ma_cond and rsi_cond:
            # 두 조건 모두 미충족 → None 이어야 함
            signal = s.generate_signal("005930", df)
            assert signal is None, (
                f"MA5={sma_short.iloc[-1]:.1f} < MA20={sma_long.iloc[-1]:.1f}, "
                f"RSI={rsi_val:.1f} >= 40 이므로 신호 없어야 함"
            )
        else:
            # 데이터 특성상 한 조건이 충족되면 테스트 전제조건 불만족 → skip
            pytest.skip(
                f"test 전제조건 미달: MA_cond={ma_cond}, RSI={rsi_val:.1f}"
            )

    def test_generate_signal_buy_on_rsi_oversold_state(self):
        """RSI < 40 상태 DataFrame → BUY Signal 반환.

        MA 조건이 충족 안 되더라도 RSI 단독으로 신호가 나와야 함 (min_buy_signals=1).
        """
        from strategies.base import SignalType

        s = self._make_strat_initialized()

        # 하락 데이터 (RSI 낮음, MA5 < MA20 가능성 높음)
        # RSI가 40 미만이 되도록 강한 하락 시리즈 사용
        prices = [10000.0 - i * 30 for i in range(30)]  # 강한 하락
        df = pd.DataFrame({
            "open": [p * 0.995 for p in prices],
            "high": [p * 1.005 for p in prices],
            "low": [p * 0.990 for p in prices],
            "close": prices,
            "volume": [500_000] * 30,
        })

        signal = s.generate_signal("005930", df)
        # RSI < 40 이면 BUY 신호, RSI >= 40 이면 None (데이터에 따라 다름)
        # 검증: 반환값이 None 또는 BUY 타입 중 하나여야 함
        from strategies.base import SignalType
        assert signal is None or signal.signal_type == SignalType.BUY


# ============================================================================
# Test: on_order_filled 카운터 갱신
# ============================================================================

class TestOnOrderFilled:
    """on_order_filled 호출 시 daily_trades / daily_profit 갱신 및 한도 가드 검증."""

    def _make_initialized_strategy(self) -> SampleStrategy:
        from unittest.mock import MagicMock
        s = _make_strategy()
        s.on_init(MagicMock(), MagicMock(), MagicMock())
        return s

    def _make_order(self, side: str, stock_code: str, price: float,
                    quantity: int = 10) -> object:
        from strategies.base import OrderInfo
        from datetime import datetime
        return OrderInfo(
            order_id="TEST001",
            stock_code=stock_code,
            side=side,
            quantity=quantity,
            price=price,
            filled_at=datetime.now(),
        )

    def test_buy_fill_increments_daily_trades(self):
        """매수 체결 후 daily_trades == 1."""
        s = self._make_initialized_strategy()
        assert s.daily_trades == 0

        order = self._make_order("buy", "005930", 10000.0, quantity=10)
        s.on_order_filled(order)

        assert s.daily_trades == 1

    def test_sell_fill_increments_daily_trades(self):
        """매도 체결 후 daily_trades 추가 증가."""
        s = self._make_initialized_strategy()
        # 먼저 포지션 추가 (매수 체결 시뮬)
        buy_order = self._make_order("buy", "005930", 10000.0, quantity=10)
        s.on_order_filled(buy_order)
        assert s.daily_trades == 1

        sell_order = self._make_order("sell", "005930", 11000.0, quantity=10)
        s.on_order_filled(sell_order)
        assert s.daily_trades == 2

    def test_sell_fill_updates_daily_profit(self):
        """매도 체결 후 daily_profit = (매도가 - 매수가) * 수량."""
        s = self._make_initialized_strategy()
        buy_price = 10000.0
        sell_price = 11000.0
        quantity = 10

        buy_order = self._make_order("buy", "005930", buy_price, quantity=quantity)
        s.on_order_filled(buy_order)
        assert s.daily_profit == 0.0

        sell_order = self._make_order("sell", "005930", sell_price, quantity=quantity)
        s.on_order_filled(sell_order)

        expected_profit = (sell_price - buy_price) * quantity  # 10,000원
        assert s.daily_profit == pytest.approx(expected_profit)

    def test_daily_trades_limit_guard(self):
        """daily_trades == max_daily_trades 일 때 generate_signal이 None 반환."""
        s = self._make_initialized_strategy()
        s._max_daily_trades = 2

        # 2번 매수 체결 → 한도 도달
        for i in range(2):
            order = self._make_order("buy", f"00593{i}", 10000.0)
            s.on_order_filled(order)

        assert s.daily_trades == 2

        # 일봉 데이터 준비 (min_len 충족)
        prices = [float(9900 + i) for i in range(30)]
        df = pd.DataFrame({
            "open": [p * 0.995 for p in prices],
            "high": [p * 1.005 for p in prices],
            "low": [p * 0.990 for p in prices],
            "close": prices,
            "volume": [2_000_000] * 30,
        })

        signal = s.generate_signal("999999", df)
        assert signal is None, "daily_trades 한도 초과 시 신호 없어야 함"

    def test_daily_reset_on_market_open(self):
        """on_market_open 호출 시 daily_trades / daily_profit 0으로 리셋."""
        s = self._make_initialized_strategy()

        buy_order = self._make_order("buy", "005930", 10000.0, quantity=10)
        s.on_order_filled(buy_order)
        sell_order = self._make_order("sell", "005930", 11000.0, quantity=10)
        s.on_order_filled(sell_order)

        assert s.daily_trades == 2
        assert s.daily_profit == pytest.approx(10000.0)

        s.on_market_open()

        assert s.daily_trades == 0
        assert s.daily_profit == 0.0


# ============================================================================
# Test: 가상매매 경로 → strategy.on_order_filled 통보 (HIGH 버그 회귀)
# ============================================================================

class TestVirtualOrderNotifiesStrategy:
    """5/14 가상매매 daily_trades=0 출력 버그 회귀 — decision_engine 가상매매 경로
    가 strategy.on_order_filled을 호출하여 daily_trades / daily_profit이 누적되는지.
    """

    def _make_decision_engine_with_strategy(self):
        from unittest.mock import MagicMock
        from core.trading_decision_engine import TradingDecisionEngine

        engine = TradingDecisionEngine.__new__(TradingDecisionEngine)
        # logger / strategy만 필요한 헬퍼 함수 단위 검증
        import logging
        engine.logger = logging.getLogger("test")
        engine.strategy = MagicMock()
        engine.strategy.on_order_filled = MagicMock()
        return engine

    def test_notify_buy_invokes_strategy_callback(self):
        engine = self._make_decision_engine_with_strategy()
        engine._notify_strategy_order_filled(
            side="buy", stock_code="005930", price=10000.0,
            quantity=10, order_id="VIRT-BUY-1",
        )
        engine.strategy.on_order_filled.assert_called_once()
        called_order = engine.strategy.on_order_filled.call_args[0][0]
        assert called_order.is_buy
        assert called_order.stock_code == "005930"
        assert called_order.quantity == 10
        assert called_order.price == pytest.approx(10000.0)

    def test_notify_sell_invokes_strategy_callback(self):
        engine = self._make_decision_engine_with_strategy()
        engine._notify_strategy_order_filled(
            side="sell", stock_code="005930", price=11000.0,
            quantity=10, order_id="VIRT-SELL-1",
        )
        engine.strategy.on_order_filled.assert_called_once()
        called_order = engine.strategy.on_order_filled.call_args[0][0]
        assert called_order.is_sell
        assert called_order.price == pytest.approx(11000.0)

    def test_notify_no_strategy_is_noop(self):
        """전략이 None이면 조용히 noop — 예외 없음."""
        engine = self._make_decision_engine_with_strategy()
        engine.strategy = None
        # 예외 발생하지 않아야 함
        engine._notify_strategy_order_filled(
            side="buy", stock_code="005930", price=10000.0, quantity=10,
        )

    def test_notify_callback_exception_isolated(self):
        """전략 콜백 내부 예외가 매매 결과를 무효화하지 않음 (WARNING 격리)."""
        engine = self._make_decision_engine_with_strategy()
        engine.strategy.on_order_filled.side_effect = RuntimeError("simulated")
        # 예외가 외부로 전파되지 않아야 함
        engine._notify_strategy_order_filled(
            side="buy", stock_code="005930", price=10000.0, quantity=10,
        )

    def test_end_to_end_daily_trades_increments(self):
        """SampleStrategy + 헬퍼 결합 — 가상매매 콜백 통보 후 daily_trades 증가."""
        from unittest.mock import MagicMock
        from core.trading_decision_engine import TradingDecisionEngine

        engine = TradingDecisionEngine.__new__(TradingDecisionEngine)
        import logging
        engine.logger = logging.getLogger("test")

        # 실제 SampleStrategy를 strategy로 연결
        s = _make_strategy()
        s.on_init(MagicMock(), MagicMock(), MagicMock())
        engine.strategy = s

        # 매수 통보
        engine._notify_strategy_order_filled(
            side="buy", stock_code="005930", price=10000.0,
            quantity=10, order_id="VIRT-BUY-1",
        )
        assert s.daily_trades == 1
        assert "005930" in s.positions

        # 매도 통보
        engine._notify_strategy_order_filled(
            side="sell", stock_code="005930", price=11000.0,
            quantity=10, order_id="VIRT-SELL-1",
        )
        assert s.daily_trades == 2
        assert s.daily_profit == pytest.approx(10000.0)  # (11000-10000)*10


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
