"""
가상매매 잔고 이월 회귀 테스트
결함 A (initializer): _initialize_fund_manager가 VirtualTradingManager 잔고를 FundManager에 동기화
결함 B (liquidation_handler): _save_paper_eod_balance_if_virtual — 단순화된 탐색 경로
결함 C (virtual_trading_manager): get_cumulative_profit_info — initial_balance 기준 사용

(가) initializer 단위 테스트
(라) 통합 — D-1 잔고 이월 시나리오
"""
import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock, Mock, patch


# ---------------------------------------------------------------------------
# 헬퍼
# ---------------------------------------------------------------------------

def _make_vtm(balance: float = 9_500_000):
    """VirtualTradingManager mock: get_virtual_balance() → balance"""
    vtm = MagicMock()
    vtm.get_virtual_balance.return_value = balance
    vtm.virtual_balance = balance
    vtm.initial_balance = balance
    return vtm


def _make_bot_for_initializer(vtm_balance: float = 9_500_000):
    """BotInitializer 테스트용 최소 bot mock"""
    bot = MagicMock()
    bot.decision_engine.is_virtual_mode = True
    bot.decision_engine.virtual_trading = _make_vtm(vtm_balance)
    bot.fund_manager.update_total_funds = Mock()
    return bot


# ---------------------------------------------------------------------------
# (가) 단위 — BotInitializer._initialize_fund_manager
# ---------------------------------------------------------------------------

class TestInitializeFundManagerVirtualMode:
    """결함 A 수정 회귀 방지: 가상매매 모드에서 VTM 잔고를 FundManager에 동기화"""

    @pytest.mark.asyncio
    async def test_uses_vtm_balance_not_hardcoded(self):
        """VTM.get_virtual_balance() == 9,500,000 이면 FundManager.update_total_funds(9,500,000) 호출."""
        from bot.initializer import BotInitializer

        bot = _make_bot_for_initializer(vtm_balance=9_500_000)
        init = BotInitializer(bot)

        await init._initialize_fund_manager()

        bot.fund_manager.update_total_funds.assert_called_once_with(9_500_000)

    @pytest.mark.asyncio
    async def test_fallback_to_10m_when_vtm_returns_zero(self):
        """VTM.get_virtual_balance() == 0 이면 10,000,000 fallback."""
        from bot.initializer import BotInitializer

        bot = _make_bot_for_initializer(vtm_balance=0)
        init = BotInitializer(bot)

        await init._initialize_fund_manager()

        bot.fund_manager.update_total_funds.assert_called_once_with(10_000_000)

    @pytest.mark.asyncio
    async def test_fallback_when_virtual_trading_is_none(self):
        """decision_engine.virtual_trading == None 이면 10,000,000 fallback."""
        from bot.initializer import BotInitializer

        bot = _make_bot_for_initializer()
        bot.decision_engine.virtual_trading = None
        init = BotInitializer(bot)

        await init._initialize_fund_manager()

        bot.fund_manager.update_total_funds.assert_called_once_with(10_000_000)

    @pytest.mark.asyncio
    async def test_real_mode_uses_broker_balance(self):
        """실전 모드는 broker.get_account_balance()를 사용해야 함 (기존 로직 유지)."""
        from bot.initializer import BotInitializer

        bot = MagicMock()
        bot.decision_engine.is_virtual_mode = False
        bot.broker.get_account_balance.return_value = {'account_balance': 15_000_000}
        bot.fund_manager.update_total_funds = Mock()
        init = BotInitializer(bot)

        await init._initialize_fund_manager()

        bot.fund_manager.update_total_funds.assert_called_once_with(15_000_000.0)


# ---------------------------------------------------------------------------
# (라) 통합 — D-1 잔고 이월 시나리오
# ---------------------------------------------------------------------------

class TestPaperBalanceCarryover:
    """D-1 잔고 이월: VTM 초기화 → initializer 동기화 통합 시나리오

    DB 직접 접근 없이 Mock으로 paper_trading_state 9,979,251원을 시뮬레이션.
    VirtualTradingManager.virtual_balance와 FundManager.total_funds가 동일해야 함.
    """

    @pytest.mark.asyncio
    async def test_carryover_balance_synced_to_fund_manager(self):
        """D-1 잔고 9,979,251원 → VTM.virtual_balance == FundManager.total_funds."""
        from bot.initializer import BotInitializer

        carryover = 9_979_251.0

        # VirtualTradingManager: D-1 이월 잔고 반영
        vtm = MagicMock()
        vtm.get_virtual_balance.return_value = carryover
        vtm.virtual_balance = carryover
        vtm.initial_balance = carryover

        # FundManager: 실제 update_total_funds 호출값 캡처
        captured = {}
        def capture_update(v):
            captured['total_funds'] = v
        fund_manager = MagicMock()
        fund_manager.update_total_funds = Mock(side_effect=capture_update)

        bot = MagicMock()
        bot.decision_engine.is_virtual_mode = True
        bot.decision_engine.virtual_trading = vtm
        bot.fund_manager = fund_manager

        init = BotInitializer(bot)
        await init._initialize_fund_manager()

        # VTM 잔고와 FundManager에 전달된 값이 동일해야 함
        assert vtm.virtual_balance == carryover
        assert captured['total_funds'] == carryover

    @pytest.mark.asyncio
    async def test_vtm_initial_balance_set_from_db_eod(self):
        """VirtualTradingManager가 DB EOD 잔고로 initial_balance를 설정하는지 확인.

        _load_paper_eod_balance() → db_manager.get_latest_paper_eod_balance() mock으로 검증.
        """
        carryover = 9_979_251.0

        db_manager = MagicMock()
        db_manager.get_latest_paper_eod_balance.return_value = carryover

        with patch('core.virtual_trading_manager.setup_logger'):
            from core.virtual_trading_manager import VirtualTradingManager
            vtm = VirtualTradingManager(
                db_manager=db_manager,
                broker=None,
                paper_trading=True,
            )

        assert vtm.virtual_balance == carryover
        assert vtm.initial_balance == carryover
