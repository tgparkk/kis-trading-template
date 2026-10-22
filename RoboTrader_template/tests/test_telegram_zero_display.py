"""텔레그램 «0원» 표시 결함 회귀 (2026-10-22, 10-21 실전 로그 근거).

1) 시장가 매도 «주문 실행» 이 가격 0원 → «시장가»
2) 매도 «주문 체결» 이 손익 항상 +0원 → 실현 손익 전달 (매수는 손익 줄 생략)
3) «일일 거래 요약» 손익 0원 → 체결 손익 누적이 요약에 반영
"""
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

from core.models import OrderType
from tests.test_live_fill_position_registry_owner import (
    CODE, KEY_A, _order, _setup, _status,
)


def _run(coro):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


def _notifier(captured):
    from utils.telegram.telegram_notifier import TelegramNotifier
    with patch("utils.telegram.telegram_notifier.Bot"), \
         patch("utils.telegram.telegram_notifier.HTTPXRequest"):
        n = TelegramNotifier("dummy", "1")

    async def _capture(message, parse_mode="Markdown"):
        captured.append(message)
        return True

    n.send_message = _capture
    return n


def _placed(n, order_type, price):
    _run(n.send_order_placed(stock_code="005930", stock_name="삼성전자",
                             order_type=order_type, quantity=10, price=price,
                             order_id="O1"))


def test_market_sell_placed_shows_market_price():
    cap = []
    n = _notifier(cap)
    _placed(n, "sell_market", 0)
    assert "가격: 시장가" in cap[0]
    assert "0원" not in cap[0]
    assert "구분: 매도" in cap[0]


def test_limit_orders_placed_keep_price():
    cap = []
    n = _notifier(cap)
    _placed(n, "buy", 70000)
    _placed(n, "sell", 71000)
    assert "가격: 70,000원" in cap[0]
    assert "가격: 71,000원" in cap[1]


def test_filled_pnl_line_only_for_sell_with_known_pnl():
    cap = []
    n = _notifier(cap)
    kw = dict(stock_code="005930", stock_name="삼성전자", quantity=10, price=70000)
    _run(n.send_order_filled(order_type="buy", **kw))
    _run(n.send_order_filled(order_type="sell", pnl=-1234.0, **kw))
    _run(n.send_order_filled(order_type="sell", **kw))  # 손익 미상
    assert "손익" not in cap[0]
    assert "손익: -1,234원" in cap[1]
    assert "손익" not in cap[2]


def test_real_sell_fill_passes_realized_pnl_to_telegram():
    """실전 매도 체결: fund_manager 가 반영한 pnl 이 그대로 텔레그램에 간다."""
    fm, om, _made, _a, _b = _setup(KEY_A)
    om.telegram = MagicMock()
    om.telegram.notify_order_filled = AsyncMock()
    fm.add_position(CODE, KEY_A)
    fm.invested_funds = 700_000
    total_before = fm.total_funds

    order = _order(OrderType.SELL, KEY_A, 'OID-S', price=0.0)  # 시장가 매도
    om.pending_orders[order.order_id] = order
    _run(om._handle_full_fill(order.order_id, order, _status(10, 77_000.0), 10))

    om.telegram.notify_order_filled.assert_awaited_once()
    args, kwargs = om.telegram.notify_order_filled.call_args
    pnl = kwargs['pnl']
    assert pnl is not None and pnl > 0
    # fund_manager 에 반영된 손익과 동일해야 한다 (재계산 아님)
    assert abs((fm.total_funds - total_before) - pnl) < 1e-6


def test_real_buy_fill_passes_no_pnl():
    fm, om, _made, _a, _b = _setup(KEY_A)
    om.telegram = MagicMock()
    om.telegram.notify_order_filled = AsyncMock()
    fm.reserve_funds('OID-B', 700_000)

    order = _order(OrderType.BUY, KEY_A, 'OID-B')
    om.pending_orders[order.order_id] = order
    _run(om._handle_full_fill(order.order_id, order, _status(10, 70_000.0), 10))

    assert om.telegram.notify_order_filled.call_args.kwargs['pnl'] is None


def test_daily_summary_reflects_realized_pnl():
    from core.telegram_integration import TelegramIntegration
    ti = TelegramIntegration.__new__(TelegramIntegration)
    ti.logger = MagicMock()
    ti.is_enabled = True
    ti.notification_settings = {'order_events': True, 'daily_summary': True}
    ti.daily_stats = {'orders_filled': 0, 'profit_loss': 0, 'trades_count': 0}
    ti.trading_bot = MagicMock()
    ti.trading_bot.fund_manager.total_funds = 5_000_000
    ti.notifier = MagicMock()
    ti.notifier.send_order_filled = AsyncMock()
    ti.notifier.send_daily_summary = AsyncMock()

    sell = {'stock_code': CODE, 'order_type': OrderType.SELL.value,
            'quantity': 10, 'price': 77000}
    _run(ti.notify_order_filled(sell, pnl=30_000))
    _run(ti.notify_order_filled(sell, pnl=-10_000))
    _run(ti.notify_order_filled({**sell, 'order_type': 'buy'}))  # pnl 미지정
    _run(ti.notify_daily_summary())

    kw = ti.notifier.send_daily_summary.call_args.kwargs
    assert kw['total_trades'] == 2
    assert kw['total_pnl'] == 20_000
    assert abs(kw['return_rate'] - 0.4) < 1e-9


def _sell_without_position(order_price):
    """보유 슬롯 없음 → 매수원가 폴백 경로. (fund_manager 반영 pnl, 알림 kwargs) 반환."""
    fm, om, _made, _a, _b = _setup()  # 슬롯 0개
    om.telegram = MagicMock()
    om.telegram.notify_order_filled = AsyncMock()
    fm.invested_funds = 700_000
    total_before = fm.total_funds

    order = _order(OrderType.SELL, KEY_A, 'OID-S', price=order_price)
    om.pending_orders[order.order_id] = order
    _run(om._handle_full_fill(order.order_id, order, _status(10, 77_000.0), 10))
    return fm.total_funds - total_before, om.telegram.notify_order_filled.call_args.kwargs


def test_market_sell_without_avg_price_hides_estimated_pnl():
    """3차 폴백(체결가=매수가 추정): 알림 pnl=None, fund_manager 는 종전대로 -(수수료+세금) 반영."""
    delta, kwargs = _sell_without_position(0.0)
    assert kwargs['pnl'] is None
    assert delta < 0  # 종전 동작 유지: 수수료·세금만큼 total_funds 감소


def test_limit_sell_without_position_hides_estimated_pnl():
    """2차 폴백(주문가=매수가 추정)도 알림 pnl=None."""
    delta, kwargs = _sell_without_position(70_000.0)
    assert kwargs['pnl'] is None
    assert delta != 0  # fund_manager 반영은 그대로
