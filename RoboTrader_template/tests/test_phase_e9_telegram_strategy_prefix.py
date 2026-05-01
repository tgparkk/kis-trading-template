"""
Phase E9 — 텔레그램 알림 [전략명] prefix 테스트
"""
import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock, patch


def _run_async(coro):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


# ---------------------------------------------------------------------------
# 헬퍼: TelegramNotifier 인스턴스 (Bot 초기화 없이)
# ---------------------------------------------------------------------------

def _make_notifier(captured: list):
    """send_message를 가로채는 TelegramNotifier 인스턴스 반환."""
    with patch("utils.telegram.telegram_notifier.Bot"), \
         patch("utils.telegram.telegram_notifier.HTTPXRequest"):
        from utils.telegram.telegram_notifier import TelegramNotifier
        notifier = TelegramNotifier.__new__(TelegramNotifier)
        notifier.bot_token = "dummy"
        notifier.chat_id = "12345"
        notifier.logger = MagicMock()
        notifier.templates = {
            'order_placed': "📝 *주문 실행*\n종목: {stock_name}({stock_code})\n구분: {order_type}\n수량: {quantity:,}주\n가격: {price:,}원\n주문ID: {order_id}",
            'order_filled': "✅ *주문 체결*\n종목: {stock_name}({stock_code})\n구분: {order_type}\n수량: {quantity:,}주\n가격: {price:,}원\n손익: {pnl:+,.0f}원",
        }

        async def _capture(message, parse_mode="Markdown"):
            captured.append(message)
            return True

        notifier.send_message = _capture
        return notifier


# ---------------------------------------------------------------------------
# 1. 매수 알림 — 전략명 prefix 포함
# ---------------------------------------------------------------------------

def test_buy_alert_with_strategy_prefix():
    """send_order_placed에 strategy_name 전달 시 [SampleStrategy] prefix가 붙는다."""
    captured = []
    notifier = _make_notifier(captured)

    _run_async(notifier.send_order_placed(
        stock_code="005930",
        stock_name="삼성전자",
        order_type="buy",
        quantity=10,
        price=70000,
        order_id="ORD-001",
        strategy_name="SampleStrategy"
    ))

    assert len(captured) == 1
    assert captured[0].startswith("[SampleStrategy] ")
    assert "삼성전자" in captured[0]
    assert "매수" in captured[0]


# ---------------------------------------------------------------------------
# 2. 매도 알림 — 전략명 prefix 포함
# ---------------------------------------------------------------------------

def test_sell_alert_with_strategy_prefix():
    """send_order_filled에 strategy_name 전달 시 [Lynch] prefix가 붙는다."""
    captured = []
    notifier = _make_notifier(captured)

    _run_async(notifier.send_order_filled(
        stock_code="000660",
        stock_name="SK하이닉스",
        order_type="sell",
        quantity=5,
        price=120000,
        pnl=15000.0,
        strategy_name="Lynch"
    ))

    assert len(captured) == 1
    assert captured[0].startswith("[Lynch] ")
    assert "SK하이닉스" in captured[0]
    assert "매도" in captured[0]


# ---------------------------------------------------------------------------
# 3. strategy_name 없으면 prefix 생략
# ---------------------------------------------------------------------------

def test_alert_without_strategy_no_prefix():
    """strategy_name이 빈 문자열이면 prefix가 없다."""
    captured = []
    notifier = _make_notifier(captured)

    _run_async(notifier.send_order_placed(
        stock_code="005930",
        stock_name="삼성전자",
        order_type="buy",
        quantity=10,
        price=70000,
        order_id="ORD-002",
        strategy_name=""
    ))

    assert len(captured) == 1
    # "[" 로 시작하면 안 됨
    assert not captured[0].startswith("[")
    assert "삼성전자" in captured[0]


# ---------------------------------------------------------------------------
# 4. TelegramIntegration — order_data에 strategy_name 전달 시 notifier에 통과
# ---------------------------------------------------------------------------

def test_telegram_integration_passes_strategy_name():
    """TelegramIntegration.notify_order_placed가 order_data['strategy_name']을 notifier에 전달한다."""
    with patch("utils.telegram.telegram_notifier.Bot"), \
         patch("utils.telegram.telegram_notifier.HTTPXRequest"):
        from core.telegram_integration import TelegramIntegration

        integration = TelegramIntegration.__new__(TelegramIntegration)
        integration.logger = MagicMock()
        integration.is_enabled = True
        integration.notification_settings = {'order_events': True}
        integration.daily_stats = {'orders_placed': 0}

        mock_notifier = MagicMock()
        mock_notifier.send_order_placed = AsyncMock()
        integration.notifier = mock_notifier

        _run_async(integration.notify_order_placed({
            'stock_code': '005930',
            'stock_name': '삼성전자',
            'order_type': 'buy',
            'quantity': 10,
            'price': 70000,
            'order_id': 'ORD-003',
            'strategy_name': 'MomentumStrategy'
        }))

        mock_notifier.send_order_placed.assert_called_once()
        call_kwargs = mock_notifier.send_order_placed.call_args.kwargs
        assert call_kwargs.get('strategy_name') == 'MomentumStrategy'
