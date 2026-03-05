"""
TradingDecisionEngine 유닛 테스트 (v2)
- 초기화
- _get_max_buy_amount
- analyze_buy_decision
- _safe_float
"""
import pytest
import asyncio
import pandas as pd
import numpy as np
from datetime import datetime, timedelta, timezone
from unittest.mock import Mock, patch, AsyncMock
from core.models import TradingStock, StockState


@pytest.fixture
def engine():
    with patch('core.trading_decision_engine.setup_logger'), \
         patch('core.virtual_trading_manager.setup_logger'):
        from core.trading_decision_engine import TradingDecisionEngine
        e = TradingDecisionEngine(
            db_manager=Mock(),
            telegram_integration=None,
            trading_manager=None,
            broker=None,
            config=Mock(paper_trading=True)
        )
    return e


@pytest.fixture
def sample_daily_data():
    periods = 30
    base_time = datetime(2024, 1, 15, 9, 0, tzinfo=timezone(timedelta(hours=9)))
    np.random.seed(42)
    closes = [50000 * (1 + 0.001 * i) for i in range(periods)]
    return pd.DataFrame({
        'datetime': [base_time + timedelta(days=i) for i in range(periods)],
        'open': closes,
        'high': [c * 1.01 for c in closes],
        'low': [c * 0.99 for c in closes],
        'close': closes,
        'volume': [100000] * periods
    })


class TestSafeFloat:
    def test_normal(self, engine):
        assert engine._safe_float(123.45) == 123.45

    def test_string_with_comma(self, engine):
        assert engine._safe_float("1,234.5") == 1234.5

    def test_none(self, engine):
        assert engine._safe_float(None) == 0.0

    def test_nan(self, engine):
        assert engine._safe_float(float('nan')) == 0.0

    def test_invalid(self, engine):
        assert engine._safe_float("abc") == 0.0


class TestGetMaxBuyAmount:
    def test_with_fund_manager(self, engine):
        fm = Mock()
        fm.get_max_buy_amount.return_value = 300000
        engine.fund_manager = fm
        assert engine._get_max_buy_amount("005930") == 300000

    def test_fund_manager_zero_fallback_to_broker(self, engine):
        fm = Mock()
        fm.get_max_buy_amount.return_value = 0
        engine.fund_manager = fm
        broker = Mock()
        broker.get_account_balance.return_value = {'available_cash': 10000000}
        engine.broker = broker
        result = engine._get_max_buy_amount("005930")
        assert result == 1000000  # min(5000000, 10000000*0.1)

    def test_no_fund_manager_no_broker(self, engine):
        assert engine._get_max_buy_amount() == engine.DEFAULT_MAX_AMOUNT


class TestAnalyzeBuyDecision:
    def test_insufficient_data(self, engine):
        stock = TradingStock(stock_code="005930", stock_name="삼성전자",
                             state=StockState.SELECTED, selected_time=datetime.now())
        short_data = pd.DataFrame({'close': [1, 2, 3]})
        result = asyncio.get_event_loop().run_until_complete(
            engine.analyze_buy_decision(stock, short_data)
        )
        assert result[0] is False

    def test_none_data(self, engine):
        stock = TradingStock(stock_code="005930", stock_name="삼성전자",
                             state=StockState.SELECTED, selected_time=datetime.now())
        result = asyncio.get_event_loop().run_until_complete(
            engine.analyze_buy_decision(stock, None)
        )
        assert result[0] is False

    def test_no_strategy_no_buy(self, engine, sample_daily_data):
        stock = TradingStock(stock_code="005930", stock_name="삼성전자",
                             state=StockState.SELECTED, selected_time=datetime.now())
        result = asyncio.get_event_loop().run_until_complete(
            engine.analyze_buy_decision(stock, sample_daily_data)
        )
        assert result[0] is False

    def test_strategy_buy_signal(self, engine, sample_daily_data):
        from unittest.mock import MagicMock
        # 시장 방향성 필터 비활성화 (테스트 환경)
        engine.check_market_direction = Mock(return_value=(False, ""))
        strategy = MagicMock()
        strategy.name = "test"
        signal = MagicMock()
        signal.signal_type = MagicMock()
        # Use string comparison to simulate SignalType.BUY
        from strategies.base import SignalType
        signal.signal_type = SignalType.BUY
        signal.confidence = 80
        signal.reasons = ["테스트 매수"]
        strategy.generate_signal.return_value = signal
        engine.strategy = strategy
        engine.fund_manager = Mock()
        engine.fund_manager.get_max_buy_amount.return_value = 500000

        stock = TradingStock(stock_code="005930", stock_name="삼성전자",
                             state=StockState.SELECTED, selected_time=datetime.now())
        result = asyncio.get_event_loop().run_until_complete(
            engine.analyze_buy_decision(stock, sample_daily_data)
        )
        assert result[0] is True
        assert "테스트 매수" in result[1]
        assert result[2]['quantity'] > 0
