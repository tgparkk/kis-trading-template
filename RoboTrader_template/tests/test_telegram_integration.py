"""텔레그램 통합 모듈 테스트 - 수익률 계산 등"""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
import asyncio


@pytest.fixture
def mock_telegram_config():
    """텔레그램 설정 mock"""
    return {
        'enabled': True,
        'bot_token': 'test-token',
        'chat_id': '12345',
    }


@pytest.fixture
def telegram_integration(mock_telegram_config):
    """TelegramIntegration 인스턴스 생성"""
    with patch('core.telegram_integration.TelegramIntegration._load_telegram_config', return_value=mock_telegram_config):
        from core.telegram_integration import TelegramIntegration
        ti = TelegramIntegration()
        ti.is_enabled = True
        ti.notifier = MagicMock()
        ti.notifier.send_daily_summary = AsyncMock()
        return ti


class TestDailySummaryReturnRate:
    """일일 요약의 수익률 계산 테스트"""

    @pytest.mark.asyncio
    async def test_return_rate_with_fund_manager(self, telegram_integration):
        """fund_manager가 있으면 수익률을 정확히 계산"""
        ti = telegram_integration
        ti.daily_stats['profit_loss'] = 50000.0
        ti.daily_stats['trades_count'] = 3

        # mock trading_bot with fund_manager
        mock_bot = MagicMock()
        mock_bot.fund_manager.total_funds = 10_000_000  # 1천만원
        ti.trading_bot = mock_bot

        await ti.notify_daily_summary()

        ti.notifier.send_daily_summary.assert_called_once()
        call_kwargs = ti.notifier.send_daily_summary.call_args
        # return_rate = 50000 / 10000000 * 100 = 0.5%
        assert abs(call_kwargs.kwargs.get('return_rate', call_kwargs[1].get('return_rate', 0)) - 0.5) < 0.01

    @pytest.mark.asyncio
    async def test_return_rate_without_trading_bot(self, telegram_integration):
        """trading_bot이 없으면 수익률 0"""
        ti = telegram_integration
        ti.trading_bot = None
        ti.daily_stats['profit_loss'] = 50000.0

        await ti.notify_daily_summary()

        ti.notifier.send_daily_summary.assert_called_once()
        call_kwargs = ti.notifier.send_daily_summary.call_args
        assert call_kwargs.kwargs.get('return_rate', call_kwargs[1].get('return_rate', 0)) == 0.0

    @pytest.mark.asyncio
    async def test_return_rate_zero_funds(self, telegram_integration):
        """total_funds가 0이면 수익률 0 (division by zero 방지)"""
        ti = telegram_integration
        mock_bot = MagicMock()
        mock_bot.fund_manager.total_funds = 0
        ti.trading_bot = mock_bot
        ti.daily_stats['profit_loss'] = 50000.0

        await ti.notify_daily_summary()

        ti.notifier.send_daily_summary.assert_called_once()
        call_kwargs = ti.notifier.send_daily_summary.call_args
        assert call_kwargs.kwargs.get('return_rate', call_kwargs[1].get('return_rate', 0)) == 0.0

    @pytest.mark.asyncio
    async def test_return_rate_negative_pnl(self, telegram_integration):
        """손실 시 음수 수익률"""
        ti = telegram_integration
        mock_bot = MagicMock()
        mock_bot.fund_manager.total_funds = 5_000_000
        ti.trading_bot = mock_bot
        ti.daily_stats['profit_loss'] = -100000.0  # -10만원 손실

        await ti.notify_daily_summary()

        call_kwargs = ti.notifier.send_daily_summary.call_args
        # -100000 / 5000000 * 100 = -2.0%
        assert abs(call_kwargs.kwargs.get('return_rate', call_kwargs[1].get('return_rate', 0)) - (-2.0)) < 0.01

    @pytest.mark.asyncio
    async def test_return_rate_no_fund_manager_attr(self, telegram_integration):
        """trading_bot에 fund_manager 속성이 없으면 수익률 0"""
        ti = telegram_integration
        mock_bot = MagicMock(spec=[])  # no attributes
        ti.trading_bot = mock_bot
        ti.daily_stats['profit_loss'] = 50000.0

        await ti.notify_daily_summary()

        ti.notifier.send_daily_summary.assert_called_once()
        call_kwargs = ti.notifier.send_daily_summary.call_args
        assert call_kwargs.kwargs.get('return_rate', call_kwargs[1].get('return_rate', 0)) == 0.0

    @pytest.mark.asyncio
    async def test_disabled_skips_summary(self, telegram_integration):
        """비활성화 시 알림 안 보냄"""
        ti = telegram_integration
        ti.is_enabled = False

        await ti.notify_daily_summary()

        ti.notifier.send_daily_summary.assert_not_called()
