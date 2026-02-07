"""
OrderTimeout 유닛 테스트
- 취소 재시도 (_cancel_with_retry)
- 타임아웃 처리 (_handle_timeout)
- 부분 체결 타임아웃
- 강제 정리
- 4봉 경과 판단
"""
import pytest
from datetime import timedelta
from unittest.mock import Mock, AsyncMock, patch
from core.models import Order, OrderType, OrderStatus, TradingConfig
from core.order_manager import OrderManager
from utils.korean_time import now_kst


def _make_order_manager_with_pending(order_id="ORD-001", stock_code="005930",
                                      order_type=OrderType.BUY, filled_qty=0):
    """pending 주문이 있는 OrderManager 생성"""
    config = TradingConfig.from_json({
        'paper_trading': False,
        'order_management': {
            'buy_timeout_seconds': 300,
            'sell_timeout_seconds': 300,
        }
    })
    api = Mock()
    api.is_initialized = True
    telegram = AsyncMock()
    db = Mock()

    om = OrderManager(config, api, telegram, db)
    om.trading_manager = None

    ts = now_kst()
    order = Order(
        order_id=order_id,
        stock_code=stock_code,
        order_type=order_type,
        price=70000,
        quantity=10,
        timestamp=ts - timedelta(minutes=6),  # 6분 전 주문
        filled_quantity=filled_qty,
    )
    om.pending_orders[order_id] = order
    om.order_timeouts[order_id] = ts - timedelta(minutes=1)  # 이미 타임아웃

    return om


class TestCancelWithRetry:
    """취소 재시도 테스트"""

    @pytest.mark.asyncio
    async def test_cancel_retry_first_success(self):
        om = _make_order_manager_with_pending()

        with patch.object(om, 'cancel_order', new_callable=AsyncMock) as mock_cancel:
            mock_cancel.return_value = True
            result = await om._cancel_with_retry("ORD-001")

        assert result is True
        assert mock_cancel.call_count == 1

    @pytest.mark.asyncio
    async def test_cancel_retry_second_success(self):
        om = _make_order_manager_with_pending()

        with patch.object(om, 'cancel_order', new_callable=AsyncMock) as mock_cancel:
            mock_cancel.side_effect = [False, True]
            with patch('core.orders.order_timeout.asyncio.sleep', new_callable=AsyncMock):
                result = await om._cancel_with_retry("ORD-001")

        assert result is True
        assert mock_cancel.call_count == 2

    @pytest.mark.asyncio
    async def test_cancel_retry_all_fail(self):
        om = _make_order_manager_with_pending()

        with patch.object(om, 'cancel_order', new_callable=AsyncMock) as mock_cancel:
            mock_cancel.return_value = False
            with patch('core.orders.order_timeout.asyncio.sleep', new_callable=AsyncMock):
                result = await om._cancel_with_retry("ORD-001", max_retries=3)

        assert result is False
        assert mock_cancel.call_count == 3


class TestHandleTimeout:
    """타임아웃 처리 테스트"""

    @pytest.mark.asyncio
    async def test_timeout_unfilled(self):
        """미체결 주문 타임아웃 → 취소 시도"""
        om = _make_order_manager_with_pending(filled_qty=0)

        with patch.object(om, '_check_order_status', new_callable=AsyncMock):
            with patch.object(om, '_cancel_with_retry', new_callable=AsyncMock, return_value=True) as mock_cancel:
                with patch.object(om, '_notify_trading_manager_timeout', new_callable=AsyncMock):
                    await om._handle_timeout("ORD-001")

        mock_cancel.assert_called_once_with("ORD-001")

    @pytest.mark.asyncio
    async def test_timeout_partial_fill(self):
        """부분 체결 후 타임아웃 → _handle_partial_fill_timeout 호출"""
        om = _make_order_manager_with_pending(filled_qty=6)

        with patch.object(om, '_check_order_status', new_callable=AsyncMock):
            with patch.object(om, '_handle_partial_fill_timeout', new_callable=AsyncMock) as mock_partial:
                await om._handle_timeout("ORD-001")

        mock_partial.assert_called_once()
        call_args = mock_partial.call_args
        assert call_args[0][2] == 6  # filled_qty

    @pytest.mark.asyncio
    async def test_force_cleanup(self):
        """취소 3회 실패 후 강제 정리"""
        om = _make_order_manager_with_pending(filled_qty=0)

        with patch.object(om, '_check_order_status', new_callable=AsyncMock):
            with patch.object(om, '_cancel_with_retry', new_callable=AsyncMock, return_value=False):
                with patch.object(om, '_force_timeout_cleanup', new_callable=AsyncMock) as mock_force:
                    await om._handle_timeout("ORD-001")

        mock_force.assert_called_once_with("ORD-001")


class TestForceCleanup:
    """강제 정리 테스트"""

    @pytest.mark.asyncio
    async def test_force_timeout_cleanup(self):
        om = _make_order_manager_with_pending()
        om.trading_manager = None

        await om._force_timeout_cleanup("ORD-001")

        assert "ORD-001" not in om.pending_orders
        assert len(om.completed_orders) == 1
        assert om.completed_orders[0].status == OrderStatus.TIMEOUT


class TestFourCandlePassed:
    """4봉 경과 판단 테스트"""

    def test_4candle_passed(self):
        """12분 경과 → True"""
        om = _make_order_manager_with_pending()
        ts = now_kst()
        order_time = ts - timedelta(minutes=13)

        with patch('core.orders.order_base.now_kst', return_value=ts):
            result = om._has_4_candles_passed(order_time)

        assert result is True

    def test_4candle_not_passed(self):
        """8분 경과 → False"""
        om = _make_order_manager_with_pending()
        ts = now_kst()
        order_time = ts - timedelta(minutes=8)

        with patch('core.orders.order_base.now_kst', return_value=ts):
            result = om._has_4_candles_passed(order_time)

        assert result is False

    def test_4candle_none(self):
        """order_candle_time=None → False"""
        om = _make_order_manager_with_pending()
        result = om._has_4_candles_passed(None)
        assert result is False
