"""
TradingDecisionEngine 유닛 테스트
- _safe_float 유틸리티
- analyze_sell_decision 전략 기반 매도 판단
- 경계값 및 예외 안전성

Note: 손절/익절 판단은 PositionMonitor로 이동 (test_trading_flow.py에서 테스트)
"""
import pytest
import asyncio
import math
from unittest.mock import Mock, AsyncMock, MagicMock, patch
from core.trading_decision_engine import TradingDecisionEngine
from core.models import TradingStock, StockState, Position


def _make_engine(strategy=None):
    """최소 의존성 엔진 생성"""
    engine = TradingDecisionEngine.__new__(TradingDecisionEngine)
    engine.logger = Mock()
    engine.strategy = strategy
    engine.trading_manager = Mock()
    engine.virtual_trading = Mock()
    return engine


def _make_stock_with_position(buy_price: float):
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


class TestAnalyzeSellDecision:
    """analyze_sell_decision 매도 판단 테스트

    손절/익절은 PositionMonitor._analyze_sell_for_stock()으로 이동.
    여기서는 Strategy 기반 매도 신호만 테스트.
    """

    def test_no_position_returns_false(self):
        """포지션 없으면 매도 불가"""
        engine = _make_engine()
        stock = TradingStock(
            stock_code="005930", stock_name="삼성전자",
            state=StockState.SELECTED,
            selected_time=__import__('datetime').datetime.now()
        )
        stock.position = None
        result = asyncio.get_event_loop().run_until_complete(
            engine.analyze_sell_decision(stock))
        assert result[0] is False
        assert "포지션없음" in result[1]

    def test_zero_avg_price_returns_false(self):
        """avg_price가 0이면 매도 불가"""
        engine = _make_engine()
        stock = _make_stock_with_position(0)
        result = asyncio.get_event_loop().run_until_complete(
            engine.analyze_sell_decision(stock))
        assert result[0] is False

    def test_no_strategy_returns_false(self):
        """전략 미설정 시 매도 신호 없음"""
        engine = _make_engine(strategy=None)
        stock = _make_stock_with_position(10000)
        result = asyncio.get_event_loop().run_until_complete(
            engine.analyze_sell_decision(stock))
        assert result[0] is False
        assert result[1] == ""

    def test_strategy_sell_signal(self):
        """전략이 매도 신호를 반환하면 매도"""
        from unittest.mock import patch
        mock_strategy = Mock()
        mock_strategy.name = "TestStrategy"

        # SignalResult mock
        signal_result = Mock()
        signal_result.reasons = ["RSI 과매수"]

        engine = _make_engine(strategy=mock_strategy)
        stock = _make_stock_with_position(10000)

        import pandas as pd
        combined_data = pd.DataFrame({'close': [10500]})

        # SignalType.SELL mock
        with patch('core.trading_decision_engine.SignalType', create=True) as mock_signal_type:
            # 실제 import를 모킹
            mock_sell = Mock()
            mock_strong_sell = Mock()

            signal_result.signal_type = mock_sell

            mock_strategy.generate_signal.return_value = signal_result

            # strategies.base.SignalType을 모킹해야 함
            with patch.dict('sys.modules', {'strategies': Mock(), 'strategies.base': Mock()}):
                import sys
                sys.modules['strategies.base'].SignalType.SELL = mock_sell
                sys.modules['strategies.base'].SignalType.STRONG_SELL = mock_strong_sell

                result = asyncio.get_event_loop().run_until_complete(
                    engine.analyze_sell_decision(stock, combined_data))
                assert result[0] is True
                assert "RSI 과매수" in result[1]

    def test_strategy_no_signal(self):
        """전략이 신호 없음을 반환"""
        mock_strategy = Mock()
        mock_strategy.generate_signal.return_value = None
        engine = _make_engine(strategy=mock_strategy)
        stock = _make_stock_with_position(10000)

        import pandas as pd
        combined_data = pd.DataFrame({'close': [10500]})

        with patch.dict('sys.modules', {'strategies': Mock(), 'strategies.base': Mock()}):
            import sys
            sys.modules['strategies.base'].SignalType.SELL = Mock()
            sys.modules['strategies.base'].SignalType.STRONG_SELL = Mock()

            result = asyncio.get_event_loop().run_until_complete(
                engine.analyze_sell_decision(stock, combined_data))
            assert result[0] is False

    def test_strategy_exception_safety(self):
        """전략에서 예외 발생해도 안전"""
        mock_strategy = Mock()
        mock_strategy.generate_signal.side_effect = Exception("전략 오류")
        engine = _make_engine(strategy=mock_strategy)
        stock = _make_stock_with_position(10000)

        import pandas as pd
        combined_data = pd.DataFrame({'close': [10500]})

        with patch.dict('sys.modules', {'strategies': Mock(), 'strategies.base': Mock()}):
            result = asyncio.get_event_loop().run_until_complete(
                engine.analyze_sell_decision(stock, combined_data))
            assert result[0] is False

    def test_no_combined_data_skips_strategy(self):
        """combined_data가 None이면 전략 체크 건너뜀"""
        mock_strategy = Mock()
        engine = _make_engine(strategy=mock_strategy)
        stock = _make_stock_with_position(10000)

        result = asyncio.get_event_loop().run_until_complete(
            engine.analyze_sell_decision(stock, combined_data=None))
        assert result[0] is False
        mock_strategy.generate_signal.assert_not_called()
