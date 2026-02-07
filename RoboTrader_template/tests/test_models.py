"""
데이터 모델 유닛 테스트
- Enum 값 검증
- OHLCVData 검증 로직
- Order __post_init__ 및 get_filled_price
- TradingStock 상태 전이
- Position 평가손익
- TradingConfig.from_json
"""
import pytest
from datetime import datetime
from core.models import (
    OrderType, OrderStatus, StockState, PositionType,
    OHLCVData, Order, Position, TradingStock, TradingConfig
)


class TestEnumValues:
    """Enum 값 검증"""

    def test_order_type(self):
        assert OrderType.BUY.value == "buy"
        assert OrderType.SELL.value == "sell"

    def test_order_status(self):
        assert OrderStatus.PENDING.value == "pending"
        assert OrderStatus.PARTIAL.value == "partial"
        assert OrderStatus.FILLED.value == "filled"
        assert OrderStatus.CANCELLED.value == "cancelled"
        assert OrderStatus.TIMEOUT.value == "timeout"

    def test_stock_state(self):
        assert StockState.SELECTED.value == "selected"
        assert StockState.BUY_PENDING.value == "buy_pending"
        assert StockState.POSITIONED.value == "positioned"
        assert StockState.SELL_CANDIDATE.value == "sell_candidate"
        assert StockState.SELL_PENDING.value == "sell_pending"
        assert StockState.COMPLETED.value == "completed"
        assert StockState.FAILED.value == "failed"


class TestOHLCVData:
    """OHLCVData 검증 테스트"""

    def test_ohlcv_valid(self):
        ohlcv = OHLCVData(
            timestamp=datetime.now(),
            stock_code="005930",
            open_price=70000,
            high_price=71000,
            low_price=69000,
            close_price=70500,
            volume=1000000
        )
        assert ohlcv.close_price == 70500

    def test_ohlcv_invalid_high(self):
        with pytest.raises(ValueError, match="고가가 시가/종가보다 낮습니다"):
            OHLCVData(
                timestamp=datetime.now(),
                stock_code="005930",
                open_price=70000,
                high_price=69000,  # < max(open, close)
                low_price=68000,
                close_price=70500,
                volume=1000000
            )

    def test_ohlcv_invalid_low(self):
        with pytest.raises(ValueError, match="저가가 시가/종가보다 높습니다"):
            OHLCVData(
                timestamp=datetime.now(),
                stock_code="005930",
                open_price=70000,
                high_price=71000,
                low_price=70500,  # > min(open, close)
                close_price=70000,
                volume=1000000
            )

    def test_ohlcv_equal_prices(self):
        """시가=종가=고가=저가 (보합)"""
        ohlcv = OHLCVData(
            timestamp=datetime.now(),
            stock_code="005930",
            open_price=70000,
            high_price=70000,
            low_price=70000,
            close_price=70000,
            volume=0
        )
        assert ohlcv.high_price == ohlcv.low_price


class TestOrder:
    """Order 테스트"""

    def test_order_remaining_auto(self):
        """remaining_quantity=0이면 quantity 복사"""
        order = Order(
            order_id="ORD001",
            stock_code="005930",
            order_type=OrderType.BUY,
            price=70000,
            quantity=10,
            timestamp=datetime.now()
        )
        assert order.remaining_quantity == 10

    def test_order_remaining_explicit(self):
        """remaining_quantity 명시 시 유지"""
        order = Order(
            order_id="ORD001",
            stock_code="005930",
            order_type=OrderType.BUY,
            price=70000,
            quantity=10,
            timestamp=datetime.now(),
            remaining_quantity=5
        )
        assert order.remaining_quantity == 5

    def test_order_get_filled_price_with_filled(self):
        """filled_price가 있으면 우선"""
        order = Order(
            order_id="ORD001",
            stock_code="005930",
            order_type=OrderType.BUY,
            price=70000,
            quantity=10,
            timestamp=datetime.now(),
            filled_price=69500
        )
        assert order.get_filled_price() == 69500

    def test_order_get_filled_price_without_filled(self):
        """filled_price 없으면 price"""
        order = Order(
            order_id="ORD001",
            stock_code="005930",
            order_type=OrderType.BUY,
            price=70000,
            quantity=10,
            timestamp=datetime.now()
        )
        assert order.get_filled_price() == 70000


class TestTradingStock:
    """TradingStock 테스트"""

    def _make_stock(self):
        return TradingStock(
            stock_code="005930",
            stock_name="삼성전자",
            state=StockState.SELECTED,
            selected_time=datetime.now()
        )

    def test_change_state(self):
        stock = self._make_stock()
        stock.change_state(StockState.BUY_PENDING, "매수 주문")
        assert stock.state == StockState.BUY_PENDING
        assert len(stock.state_history) == 1
        assert stock.state_history[0]['from_state'] == 'selected'
        assert stock.state_history[0]['to_state'] == 'buy_pending'

    def test_state_chain(self):
        """SELECTED → BUY_PENDING → POSITIONED → COMPLETED"""
        stock = self._make_stock()
        stock.change_state(StockState.BUY_PENDING, "주문")
        stock.change_state(StockState.POSITIONED, "체결")
        stock.change_state(StockState.COMPLETED, "매도완료")
        assert stock.state == StockState.COMPLETED
        assert len(stock.state_history) == 3

    def test_virtual_buy_info(self):
        stock = self._make_stock()
        assert stock.has_virtual_position() is False
        stock.set_virtual_buy_info(record_id=42, price=70000, quantity=10)
        assert stock.has_virtual_position() is True
        assert stock._virtual_buy_record_id == 42
        stock.clear_virtual_buy_info()
        assert stock.has_virtual_position() is False

    def test_set_position(self):
        stock = self._make_stock()
        stock.set_position(quantity=10, avg_price=70000)
        assert stock.position is not None
        assert stock.position.quantity == 10
        assert stock.position.avg_price == 70000

    def test_clear_position(self):
        stock = self._make_stock()
        stock.set_position(10, 70000)
        stock.last_signal_candle_time = datetime.now()
        stock.clear_position()
        assert stock.position is None
        assert stock.last_signal_candle_time is None

    def test_add_order(self):
        stock = self._make_stock()
        stock.add_order("ORD001")
        assert stock.current_order_id == "ORD001"
        assert "ORD001" in stock.order_history
        stock.clear_current_order()
        assert stock.current_order_id is None


class TestPosition:
    """Position 테스트"""

    def test_update_price_profit(self):
        pos = Position(stock_code="005930", quantity=10, avg_price=70000)
        pos.update_current_price(72000)
        assert pos.current_price == 72000
        assert pos.unrealized_pnl == 20000  # (72000-70000)*10

    def test_update_price_loss(self):
        pos = Position(stock_code="005930", quantity=10, avg_price=70000)
        pos.update_current_price(68000)
        assert pos.unrealized_pnl == -20000  # (68000-70000)*10

    def test_update_price_break_even(self):
        pos = Position(stock_code="005930", quantity=10, avg_price=70000)
        pos.update_current_price(70000)
        assert pos.unrealized_pnl == 0


class TestTradingConfig:
    """TradingConfig 테스트"""

    def test_from_json_empty(self):
        config = TradingConfig.from_json({})
        assert config.paper_trading is True
        assert config.rebalancing_mode is False
        assert config.data_collection.interval_seconds == 30
        assert config.order_management.buy_timeout_seconds == 180
        assert config.risk_management.max_position_count == 20

    def test_from_json_partial(self):
        config = TradingConfig.from_json({
            'paper_trading': False,
            'order_management': {'buy_timeout_seconds': 300}
        })
        assert config.paper_trading is False
        assert config.order_management.buy_timeout_seconds == 300
        assert config.order_management.sell_timeout_seconds == 180  # 기본값

    def test_from_json_complete(self):
        config = TradingConfig.from_json({
            'paper_trading': False,
            'rebalancing_mode': True,
            'data_collection': {'interval_seconds': 60, 'candidate_stocks': ['005930']},
            'order_management': {
                'buy_timeout_seconds': 300,
                'sell_timeout_seconds': 240,
                'max_adjustments': 5,
                'buy_cooldown_minutes': 30
            },
            'risk_management': {'max_position_count': 10, 'max_position_ratio': 0.2},
            'strategy': {'name': 'quant', 'parameters': {'k': 0.5}},
            'logging': {'level': 'DEBUG', 'file_retention_days': 7}
        })
        assert config.paper_trading is False
        assert config.rebalancing_mode is True
        assert config.data_collection.interval_seconds == 60
        assert config.data_collection.candidate_stocks == ['005930']
        assert config.order_management.buy_timeout_seconds == 300
        assert config.order_management.buy_cooldown_minutes == 30
        assert config.risk_management.max_position_count == 10
        assert config.strategy.name == 'quant'
        assert config.logging.level == 'DEBUG'
