"""
데이터 모델 확장 테스트
- Stock.add_ohlcv 메모리 관리
- TradingStock 가상매매/쿨다운
- TradingConfig.from_json 전체 필드
"""
import pytest
from datetime import datetime, timedelta
from unittest.mock import patch
from core.models import (
    OHLCVData, Stock, Order, OrderType, OrderStatus,
    TradingStock, StockState, Position, TradingConfig
)


class TestStockMemoryManagement:
    def test_add_ohlcv_limits_to_1000(self):
        stock = Stock(code="005930", name="삼성전자")
        for i in range(1100):
            ohlcv = OHLCVData(
                timestamp=datetime.now(), stock_code="005930",
                open_price=100, high_price=110, low_price=90,
                close_price=105, volume=1000
            )
            stock.add_ohlcv(ohlcv)
        assert len(stock.ohlcv_data) == 1000

    def test_last_price_updated(self):
        stock = Stock(code="005930", name="삼성전자")
        ohlcv = OHLCVData(
            timestamp=datetime.now(), stock_code="005930",
            open_price=100, high_price=110, low_price=90,
            close_price=105, volume=1000
        )
        stock.add_ohlcv(ohlcv)
        assert stock.last_price == 105

    def test_get_recent_ohlcv(self):
        stock = Stock(code="005930", name="삼성전자")
        for i in range(50):
            cp = 100 + i
            stock.add_ohlcv(OHLCVData(
                timestamp=datetime.now(), stock_code="005930",
                open_price=cp, high_price=cp + 10, low_price=cp - 10,
                close_price=cp, volume=1000
            ))
        recent = stock.get_recent_ohlcv(10)
        assert len(recent) == 10
        assert recent[-1].close_price == 149

    def test_get_recent_ohlcv_more_than_available(self):
        stock = Stock(code="005930", name="삼성전자")
        stock.add_ohlcv(OHLCVData(
            timestamp=datetime.now(), stock_code="005930",
            open_price=100, high_price=110, low_price=90,
            close_price=105, volume=1000
        ))
        recent = stock.get_recent_ohlcv(20)
        assert len(recent) == 1


class TestTradingStockVirtualTrading:
    def test_set_and_clear_virtual_buy_info(self):
        stock = TradingStock(stock_code="005930", stock_name="삼성전자",
                              state=StockState.POSITIONED, selected_time=datetime.now())
        stock.set_virtual_buy_info(record_id=42, price=70000, quantity=10)
        assert stock.has_virtual_position() is True
        assert stock._virtual_buy_record_id == 42
        stock.clear_virtual_buy_info()
        assert stock.has_virtual_position() is False

    def test_has_virtual_position_partial(self):
        stock = TradingStock(stock_code="005930", stock_name="삼성전자",
                              state=StockState.POSITIONED, selected_time=datetime.now())
        stock._virtual_buy_record_id = 1
        stock._virtual_buy_price = 70000
        # quantity is None
        assert stock.has_virtual_position() is False


class TestTradingStockCooldown:
    def test_cooldown_active(self):
        stock = TradingStock(stock_code="005930", stock_name="삼성전자",
                              state=StockState.COMPLETED, selected_time=datetime.now())
        with patch('utils.korean_time.now_kst') as mock_now:
            mock_now.return_value = datetime(2024, 1, 15, 10, 0, 0)
            stock.set_buy_time(datetime(2024, 1, 15, 9, 50, 0))
            assert stock.is_buy_cooldown_active() is True

    def test_cooldown_expired(self):
        stock = TradingStock(stock_code="005930", stock_name="삼성전자",
                              state=StockState.COMPLETED, selected_time=datetime.now())
        with patch('utils.korean_time.now_kst') as mock_now:
            mock_now.return_value = datetime(2024, 1, 15, 11, 0, 0)
            stock.set_buy_time(datetime(2024, 1, 15, 9, 50, 0))
            assert stock.is_buy_cooldown_active() is False

    def test_no_buy_time(self):
        stock = TradingStock(stock_code="005930", stock_name="삼성전자",
                              state=StockState.COMPLETED, selected_time=datetime.now())
        assert stock.is_buy_cooldown_active() is False
        assert stock.get_remaining_cooldown_minutes() == 0


class TestTradingStockStateHistory:
    def test_change_state_records_history(self):
        stock = TradingStock(stock_code="005930", stock_name="삼성전자",
                              state=StockState.SELECTED, selected_time=datetime.now())
        stock.change_state(StockState.BUY_PENDING, "매수 주문")
        assert len(stock.state_history) == 1
        assert stock.state_history[0]['from_state'] == 'selected'
        assert stock.state_history[0]['to_state'] == 'buy_pending'

    def test_clear_position_resets_signal(self):
        stock = TradingStock(stock_code="005930", stock_name="삼성전자",
                              state=StockState.POSITIONED, selected_time=datetime.now())
        stock.last_signal_candle_time = datetime.now()
        stock.clear_position()
        assert stock.position is None
        assert stock.last_signal_candle_time is None


class TestTradingConfigFromJson:
    def test_full_config(self):
        config = TradingConfig.from_json({
            'paper_trading': False,
            'rebalancing_mode': True,
            'order_management': {
                'buy_timeout_seconds': 300,
                'sell_timeout_seconds': 300,
                'max_adjustments': 5,
                'buy_budget_ratio': 0.15,
                'buy_cooldown_minutes': 30
            },
            'risk_management': {
                'max_position_count': 10,
                'max_position_ratio': 0.2,
                'stop_loss_ratio': 0.05,
                'take_profit_ratio': 0.08
            }
        })
        assert config.paper_trading is False
        assert config.rebalancing_mode is True
        assert config.order_management.buy_timeout_seconds == 300
        assert config.order_management.buy_cooldown_minutes == 30
        assert config.risk_management.max_position_count == 10

    def test_empty_json_defaults(self):
        config = TradingConfig.from_json({})
        assert config.paper_trading is True
        assert config.order_management.buy_timeout_seconds == 180


class TestOrderModel:
    def test_get_filled_price_with_filled(self):
        order = Order(order_id="O1", stock_code="005930", order_type=OrderType.BUY,
                      price=70000, quantity=10, timestamp=datetime.now(), filled_price=70500)
        assert order.get_filled_price() == 70500

    def test_get_filled_price_without_filled(self):
        order = Order(order_id="O1", stock_code="005930", order_type=OrderType.BUY,
                      price=70000, quantity=10, timestamp=datetime.now())
        assert order.get_filled_price() == 70000

    def test_remaining_quantity_auto_set(self):
        order = Order(order_id="O1", stock_code="005930", order_type=OrderType.BUY,
                      price=70000, quantity=10, timestamp=datetime.now())
        assert order.remaining_quantity == 10


class TestPositionModel:
    def test_update_current_price(self):
        pos = Position(stock_code="005930", quantity=10, avg_price=70000)
        pos.update_current_price(72000)
        assert pos.current_price == 72000
        assert pos.unrealized_pnl == 20000

    def test_negative_pnl(self):
        pos = Position(stock_code="005930", quantity=10, avg_price=70000)
        pos.update_current_price(68000)
        assert pos.unrealized_pnl == -20000
