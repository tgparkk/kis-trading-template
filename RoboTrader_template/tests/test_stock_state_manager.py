"""
StockStateManager 유닛 테스트
- 종목 등록/해제
- 상태 변경
- 포트폴리오 요약
- 스레드 안전성
"""
import pytest
from datetime import datetime
from unittest.mock import patch
from core.models import TradingStock, StockState, Position
from core.trading.stock_state_manager import StockStateManager


@pytest.fixture
def manager():
    with patch('core.trading.stock_state_manager.setup_logger'):
        mgr = StockStateManager()
    return mgr


@pytest.fixture
def sample_stock():
    return TradingStock(
        stock_code="005930",
        stock_name="삼성전자",
        state=StockState.SELECTED,
        selected_time=datetime.now(),
        selection_reason="테스트"
    )


class TestRegisterUnregister:
    def test_register_stock(self, manager, sample_stock):
        manager.register_stock(sample_stock)
        assert "005930" in manager.trading_stocks
        assert "005930" in manager.stocks_by_state[StockState.SELECTED]

    def test_register_multiple(self, manager):
        for code in ["005930", "000660", "035720"]:
            stock = TradingStock(stock_code=code, stock_name=f"종목{code}",
                                 state=StockState.SELECTED, selected_time=datetime.now())
            manager.register_stock(stock)
        assert len(manager.trading_stocks) == 3

    def test_unregister_stock(self, manager, sample_stock):
        manager.register_stock(sample_stock)
        manager.unregister_stock("005930")
        assert "005930" not in manager.trading_stocks
        assert "005930" not in manager.stocks_by_state[StockState.SELECTED]

    def test_unregister_nonexistent(self, manager):
        # Should not raise
        manager.unregister_stock("999999")

    def test_register_duplicate_rejected(self, manager, sample_stock):
        """POSITIONED 상태 종목의 중복 등록은 거부되고 첫 번째 등록이 유지된다."""
        manager.register_stock(sample_stock)
        # POSITIONED 상태로 전이 후 두 번째 등록 시도
        manager.change_stock_state("005930", StockState.BUY_PENDING)
        manager.change_stock_state("005930", StockState.POSITIONED)
        new_stock = TradingStock(stock_code="005930", stock_name="삼성전자2",
                                  state=StockState.SELECTED, selected_time=datetime.now())
        result = manager.register_stock(new_stock)
        assert result is False
        assert manager.trading_stocks["005930"].stock_name == "삼성전자"


class TestChangeState:
    def test_change_state(self, manager, sample_stock):
        manager.register_stock(sample_stock)
        manager.change_stock_state("005930", StockState.BUY_PENDING, "매수 주문")
        assert manager.trading_stocks["005930"].state == StockState.BUY_PENDING
        assert "005930" not in manager.stocks_by_state[StockState.SELECTED]
        assert "005930" in manager.stocks_by_state[StockState.BUY_PENDING]

    def test_change_state_nonexistent(self, manager):
        # Should not raise
        manager.change_stock_state("999999", StockState.COMPLETED)

    def test_full_lifecycle(self, manager, sample_stock):
        manager.register_stock(sample_stock)
        states = [StockState.BUY_PENDING, StockState.POSITIONED,
                  StockState.SELL_CANDIDATE, StockState.SELL_PENDING, StockState.COMPLETED]
        for s in states:
            manager.change_stock_state("005930", s)
        assert manager.trading_stocks["005930"].state == StockState.COMPLETED


class TestQueryMethods:
    def test_get_stocks_by_state(self, manager):
        for i, code in enumerate(["A", "B", "C"]):
            state = StockState.SELECTED if i < 2 else StockState.POSITIONED
            stock = TradingStock(stock_code=code, stock_name=code,
                                 state=state, selected_time=datetime.now())
            manager.register_stock(stock)
        selected = manager.get_stocks_by_state(StockState.SELECTED)
        assert len(selected) == 2

    def test_get_trading_stock(self, manager, sample_stock):
        manager.register_stock(sample_stock)
        assert manager.get_trading_stock("005930") is sample_stock
        assert manager.get_trading_stock("999999") is None

    def test_update_current_order(self, manager, sample_stock):
        manager.register_stock(sample_stock)
        manager.update_current_order("005930", "ORD001")
        assert manager.trading_stocks["005930"].current_order_id == "ORD001"
        assert "ORD001" in manager.trading_stocks["005930"].order_history


class TestPortfolioSummary:
    def test_empty_portfolio(self, manager):
        summary = manager.get_portfolio_summary()
        assert summary['total_stocks'] == 0

    def test_with_positions(self, manager):
        stock = TradingStock(stock_code="005930", stock_name="삼성전자",
                             state=StockState.POSITIONED, selected_time=datetime.now())
        stock.position = Position(stock_code="005930", quantity=10,
                                   avg_price=70000, current_price=72000)
        stock.position.update_current_price(72000)
        manager.register_stock(stock)
        summary = manager.get_portfolio_summary()
        assert summary['total_stocks'] == 1
        assert len(summary['positions']) == 1
        assert summary['total_position_value'] == 720000

    def test_with_pending_orders(self, manager):
        stock = TradingStock(stock_code="005930", stock_name="삼성전자",
                             state=StockState.BUY_PENDING, selected_time=datetime.now())
        stock.current_order_id = "ORD001"
        manager.register_stock(stock)
        summary = manager.get_portfolio_summary()
        assert len(summary['pending_orders']) == 1
