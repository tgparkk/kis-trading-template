"""
TradingDecisionEngine 유닛 테스트
- _safe_float 유틸리티
- _check_stop_profit 손절/익절 판단
- 경계값 및 예외 안전성
"""
import pytest
import math
from unittest.mock import Mock
from core.trading_decision_engine import TradingDecisionEngine
from core.models import TradingStock, StockState, Position


def _make_engine():
    """최소 의존성 엔진 생성"""
    engine = TradingDecisionEngine.__new__(TradingDecisionEngine)
    engine.logger = Mock()
    engine.DEFAULT_STOP_LOSS = 0.10
    engine.DEFAULT_TAKE_PROFIT = 0.15
    return engine


def _make_stock_with_position(buy_price: float, target=None, stop=None):
    """포지션이 있는 TradingStock 생성"""
    stock = TradingStock(
        stock_code="005930",
        stock_name="삼성전자",
        state=StockState.POSITIONED,
        selected_time=__import__('datetime').datetime.now()
    )
    stock.position = Position(
        stock_code="005930",
        quantity=10,
        avg_price=buy_price
    )
    if target is not None:
        stock.target_profit_rate = target
    if stop is not None:
        stock.stop_loss_rate = stop
    return stock


class TestSafeFloat:
    """_safe_float 유틸리티 테스트"""

    def test_normal_values(self):
        engine = _make_engine()
        assert engine._safe_float(100) == 100.0
        assert engine._safe_float(100.5) == 100.5
        assert engine._safe_float("100") == 100.0

    def test_none_nan(self):
        engine = _make_engine()
        assert engine._safe_float(None) == 0.0
        assert engine._safe_float(float('nan')) == 0.0

    def test_comma_separated(self):
        engine = _make_engine()
        assert engine._safe_float("1,000") == 1000.0
        assert engine._safe_float("100,000,000") == 100000000.0

    def test_invalid_string(self):
        engine = _make_engine()
        assert engine._safe_float("abc") == 0.0


class TestCheckStopProfit:
    """_check_stop_profit 손절/익절 테스트"""

    def test_take_profit(self):
        engine = _make_engine()
        stock = _make_stock_with_position(10000, target=0.15, stop=0.10)
        # 16% 수익 → target=15% 초과
        signal, reason = engine._check_stop_profit(stock, 11600)
        assert signal is True
        assert "익절" in reason
        assert "16.0%" in reason

    def test_stop_loss(self):
        engine = _make_engine()
        stock = _make_stock_with_position(10000, target=0.15, stop=0.10)
        # -10% 손실 → stop=10% 도달
        signal, reason = engine._check_stop_profit(stock, 9000)
        assert signal is True
        assert "손절" in reason

    def test_hold_no_signal(self):
        engine = _make_engine()
        stock = _make_stock_with_position(10000, target=0.15, stop=0.10)
        # 5% 수익 → target=15% 미달, stop=10% 미달
        signal, reason = engine._check_stop_profit(stock, 10500)
        assert signal is False
        assert reason == ""

    def test_custom_rates(self):
        engine = _make_engine()
        stock = _make_stock_with_position(10000, target=0.20, stop=0.08)
        # 16% 수익 → target=20% 미달
        signal, reason = engine._check_stop_profit(stock, 11600)
        assert signal is False

        # 20% 수익 → target=20% 도달
        signal, reason = engine._check_stop_profit(stock, 12000)
        assert signal is True
        assert "익절" in reason

    def test_default_rates(self):
        engine = _make_engine()
        # target/stop 속성 삭제 → getattr 기본값(DEFAULT_TAKE_PROFIT) 사용
        stock = TradingStock(
            stock_code="005930",
            stock_name="삼성전자",
            state=StockState.POSITIONED,
            selected_time=__import__('datetime').datetime.now()
        )
        stock.position = Position(stock_code="005930", quantity=10, avg_price=10000)
        del stock.target_profit_rate
        del stock.stop_loss_rate
        # 15% 수익 → DEFAULT_TAKE_PROFIT(0.15)
        signal, reason = engine._check_stop_profit(stock, 11500)
        assert signal is True

    def test_zero_buy_price(self):
        engine = _make_engine()
        stock = _make_stock_with_position(0)
        signal, reason = engine._check_stop_profit(stock, 10000)
        assert signal is False
        assert reason == ""

    def test_boundary_exact_profit(self):
        engine = _make_engine()
        stock = _make_stock_with_position(10000, target=0.15, stop=0.10)
        # 정확히 15% → pnl >= target → True
        signal, reason = engine._check_stop_profit(stock, 11500)
        assert signal is True

    def test_boundary_exact_loss(self):
        engine = _make_engine()
        stock = _make_stock_with_position(10000, target=0.15, stop=0.10)
        # 정확히 -10% → pnl <= -stop → True
        signal, reason = engine._check_stop_profit(stock, 9000)
        assert signal is True

    def test_boundary_just_below_profit(self):
        engine = _make_engine()
        stock = _make_stock_with_position(10000, target=0.15, stop=0.10)
        # 14.99% → 익절 미달
        signal, reason = engine._check_stop_profit(stock, 11499)
        assert signal is False

    def test_with_stock_defaults(self):
        """TradingStock 기본값(target=3%, stop=10%) 사용"""
        engine = _make_engine()
        stock = _make_stock_with_position(10000)  # 기본값 target=0.03
        # 5% 수익 → stock.target=3% 초과 → 익절
        signal, reason = engine._check_stop_profit(stock, 10500)
        assert signal is True
        assert "익절" in reason

    def test_exception_safety(self):
        engine = _make_engine()
        stock = _make_stock_with_position(10000)
        stock.position = None  # position 없음
        signal, reason = engine._check_stop_profit(stock, 10000)
        assert signal is False
        assert reason == ""
