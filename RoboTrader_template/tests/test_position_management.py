"""
시나리오4: 포지션 관리 이상 상황 테스트

테스트 범위:
1. 손절가 도달 매도 실패 → 재시도
2. 익절 후 재매수 방지 (쿨다운)
3. 동시 보유 종목 수 초과
4. 자금 부족 상태에서 매수 시도
5. FundManager 잔고 불일치 동기화
6. release_investment 음수 방지
7. FundManager 확장 기능
"""
import pytest
import threading
from datetime import datetime, timedelta
from unittest.mock import patch, AsyncMock, MagicMock

from core.fund_manager import FundManager
from core.models import TradingStock, StockState, Position


# ============================================================================
# 1. 매도 재시도 (PositionMonitor._execute_sell)
# ============================================================================
class TestSellRetry:
    """손절가 도달 매도 실패 시 재시도 테스트"""

    @pytest.mark.asyncio
    async def test_sell_retry_on_failure(self):
        """매도 실패 시 최대 3회 재시도"""
        from core.trading.position_monitor import PositionMonitor

        mock_state_mgr = MagicMock()
        mock_completion = MagicMock()
        mock_intraday = MagicMock()
        mock_data_collector = MagicMock()

        pm = PositionMonitor(mock_state_mgr, mock_completion, mock_intraday, mock_data_collector)

        # decision_engine 모의 - 3번 실패
        mock_engine = AsyncMock()
        mock_engine.execute_virtual_sell = AsyncMock(return_value=False)
        pm.decision_engine = mock_engine

        ts = TradingStock(
            stock_code="005930", stock_name="삼성전자",
            state=StockState.POSITIONED, selected_time=datetime.now()
        )
        ts.position = Position(stock_code="005930", quantity=10, avg_price=70000)

        with patch('config.settings.load_trading_config') as mock_cfg:
            mock_cfg.return_value = MagicMock(paper_trading=True)
            with patch('asyncio.sleep', new_callable=AsyncMock):
                await pm._execute_sell(ts, 65000, "손절")

        # 3회 호출되어야 함
        assert mock_engine.execute_virtual_sell.call_count == 3

    @pytest.mark.asyncio
    async def test_sell_success_first_try(self):
        """매도 1회 성공 시 재시도 안 함"""
        from core.trading.position_monitor import PositionMonitor

        pm = PositionMonitor(MagicMock(), MagicMock(), MagicMock(), MagicMock())

        mock_engine = AsyncMock()
        mock_engine.execute_virtual_sell = AsyncMock(return_value=True)
        pm.decision_engine = mock_engine

        ts = TradingStock(
            stock_code="005930", stock_name="삼성전자",
            state=StockState.POSITIONED, selected_time=datetime.now()
        )
        ts.position = Position(stock_code="005930", quantity=10, avg_price=70000)

        with patch('config.settings.load_trading_config') as mock_cfg:
            mock_cfg.return_value = MagicMock(paper_trading=True)
            await pm._execute_sell(ts, 65000, "손절")

        assert mock_engine.execute_virtual_sell.call_count == 1

    @pytest.mark.asyncio
    async def test_sell_duplicate_prevention(self):
        """이미 매도 진행 중이면 중복 방지"""
        from core.trading.position_monitor import PositionMonitor

        pm = PositionMonitor(MagicMock(), MagicMock(), MagicMock(), MagicMock())
        mock_engine = AsyncMock()
        pm.decision_engine = mock_engine

        ts = TradingStock(
            stock_code="005930", stock_name="삼성전자",
            state=StockState.POSITIONED, selected_time=datetime.now()
        )
        ts.is_selling = True  # 이미 매도 중

        await pm._execute_sell(ts, 65000, "손절")

        # 호출 안 됨
        mock_engine.execute_virtual_sell.assert_not_called()


# ============================================================================
# 2. 익절/손절 후 재매수 쿨다운
# ============================================================================
class TestSellCooldown:
    """매도 후 재매수 쿨다운 테스트"""

    def test_set_sell_cooldown(self):
        fm = FundManager(initial_funds=10_000_000)
        with patch('utils.korean_time.now_kst', return_value=datetime(2026, 2, 9, 10, 0)):
            fm.set_sell_cooldown("005930", "익절")

        assert "005930" in fm._sell_cooldowns

    def test_sell_cooldown_active(self):
        fm = FundManager(initial_funds=10_000_000)
        now = datetime(2026, 2, 9, 10, 0)
        with patch('utils.korean_time.now_kst', return_value=now):
            fm.set_sell_cooldown("005930", "익절")

        # 10분 후 → 아직 쿨다운 중 (30분 기본)
        later = now + timedelta(minutes=10)
        with patch('utils.korean_time.now_kst', return_value=later):
            assert fm.is_sell_cooldown_active("005930") is True

    def test_sell_cooldown_expired(self):
        fm = FundManager(initial_funds=10_000_000)
        now = datetime(2026, 2, 9, 10, 0)
        with patch('utils.korean_time.now_kst', return_value=now):
            fm.set_sell_cooldown("005930", "손절")

        # 31분 후 → 쿨다운 만료
        later = now + timedelta(minutes=31)
        with patch('utils.korean_time.now_kst', return_value=later):
            assert fm.is_sell_cooldown_active("005930") is False

    def test_sell_cooldown_no_entry(self):
        fm = FundManager(initial_funds=10_000_000)
        assert fm.is_sell_cooldown_active("005930") is False


# ============================================================================
# 3. 동시 보유 종목 수 초과
# ============================================================================
class TestMaxPositionCount:
    """동시 보유 종목 수 제한 테스트"""

    def test_can_add_position_under_limit(self):
        fm = FundManager(initial_funds=10_000_000, max_position_count=3)
        fm.current_position_codes = {"A", "B"}
        assert fm.can_add_position("C") is True

    def test_cannot_add_position_at_limit(self):
        fm = FundManager(initial_funds=10_000_000, max_position_count=3)
        fm.current_position_codes = {"A", "B", "C"}
        assert fm.can_add_position("D") is False

    def test_can_add_existing_position(self):
        """이미 보유 중인 종목은 분할매수 허용"""
        fm = FundManager(initial_funds=10_000_000, max_position_count=3)
        fm.current_position_codes = {"A", "B", "C"}
        assert fm.can_add_position("A") is True

    def test_add_remove_position(self):
        fm = FundManager(initial_funds=10_000_000, max_position_count=2)
        fm.add_position("A")
        fm.add_position("B")
        assert fm.can_add_position("C") is False
        fm.remove_position("A")
        assert fm.can_add_position("C") is True


# ============================================================================
# 4. 자금 부족 상태에서 매수 시도
# ============================================================================
class TestInsufficientFundsBuy:
    """자금 부족 매수 시도 테스트"""

    def test_reserve_more_than_available(self):
        fm = FundManager(initial_funds=1_000_000)
        result = fm.reserve_funds("ORD1", 2_000_000)
        assert result is False
        assert fm.available_funds == 1_000_000

    def test_max_buy_amount_zero_when_depleted(self):
        fm = FundManager(initial_funds=1_000_000)
        fm.reserve_funds("ORD1", 1_000_000)
        assert fm.get_max_buy_amount("005930") == 0

    def test_multiple_reserves_exhaust_funds(self):
        fm = FundManager(initial_funds=5_000_000)
        assert fm.reserve_funds("ORD1", 2_000_000) is True
        assert fm.reserve_funds("ORD2", 2_000_000) is True
        assert fm.reserve_funds("ORD3", 2_000_000) is False  # 잔고 부족
        assert fm.available_funds == 1_000_000


# ============================================================================
# 5. FundManager 잔고 불일치 동기화
# ============================================================================
class TestBalanceSync:
    """FundManager와 실제 계좌 잔고 동기화 테스트"""

    def test_sync_no_discrepancy(self):
        fm = FundManager(initial_funds=10_000_000)
        fm.reserve_funds("ORD1", 1_000_000)
        fm.confirm_order("ORD1", 1_000_000)
        # 내부: available=9M, invested=1M
        fm.sync_with_account(actual_available=9_000_000, actual_invested=1_000_000)
        assert fm._sync_discrepancy_count == 0

    def test_sync_detects_discrepancy(self):
        fm = FundManager(initial_funds=10_000_000)
        fm.sync_with_account(actual_available=8_000_000, actual_invested=0)
        assert fm._sync_discrepancy_count == 1

    def test_sync_auto_correct_after_3(self):
        """3회 연속 불일치 시 자동 보정"""
        fm = FundManager(initial_funds=10_000_000)
        for _ in range(3):
            fm.sync_with_account(actual_available=8_000_000, actual_invested=1_500_000)
        # 보정 후 실제 값 기준
        assert fm.available_funds == 8_000_000
        assert fm.invested_funds == 1_500_000
        assert fm._sync_discrepancy_count == 0


# ============================================================================
# 6. release_investment 음수 방지
# ============================================================================
class TestReleaseInvestmentSafety:
    """투자 자금 회수 음수 방지"""

    def test_release_clamped_to_zero(self):
        fm = FundManager(initial_funds=10_000_000)
        fm.reserve_funds("ORD1", 1_000_000)
        fm.confirm_order("ORD1", 1_000_000)
        fm.release_investment(5_000_000)  # 1M만 투자했는데 5M 회수 시도
        assert fm.invested_funds == 0
        assert fm.available_funds == 10_000_000

    def test_release_with_stock_code_tracking(self):
        fm = FundManager(initial_funds=10_000_000)
        fm.add_position("005930")
        fm.reserve_funds("ORD1", 1_000_000)
        fm.confirm_order("ORD1", 1_000_000)
        fm.release_investment(1_000_000, stock_code="005930")
        assert "005930" not in fm.current_position_codes


# ============================================================================
# 7. FundManager get_status 확장
# ============================================================================
class TestExtendedStatus:
    """확장된 상태 조회"""

    def test_status_includes_position_count(self):
        fm = FundManager(initial_funds=10_000_000, max_position_count=5)
        fm.add_position("A")
        fm.add_position("B")
        status = fm.get_status()
        assert status['position_count'] == 2
        assert status['max_position_count'] == 5

    def test_status_consistency_extended(self):
        fm = FundManager(initial_funds=10_000_000)
        fm.reserve_funds("ORD1", 1_000_000)
        fm.confirm_order("ORD1", 800_000)
        status = fm.get_status()
        total_check = status['available_funds'] + status['reserved_funds'] + status['invested_funds']
        assert total_check == status['total_funds']


# ============================================================================
# 8. 동시성 - 포지션 추가/제거
# ============================================================================
class TestPositionConcurrency:
    """포지션 추가/제거 동시성"""

    def test_concurrent_add_remove(self):
        fm = FundManager(initial_funds=10_000_000, max_position_count=100)
        errors = []

        def add_positions(start):
            try:
                for i in range(start, start + 20):
                    fm.add_position(f"STOCK_{i}")
            except Exception as e:
                errors.append(e)

        def remove_positions(start):
            try:
                for i in range(start, start + 10):
                    fm.remove_position(f"STOCK_{i}")
            except Exception as e:
                errors.append(e)

        threads = [
            threading.Thread(target=add_positions, args=(0,)),
            threading.Thread(target=add_positions, args=(20,)),
            threading.Thread(target=remove_positions, args=(0,)),
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(errors) == 0
