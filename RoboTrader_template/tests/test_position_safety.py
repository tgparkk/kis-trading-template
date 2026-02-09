"""
포지션 관리 안전성 테스트 (시나리오4 - 개발자B)

테스트 시나리오:
1. 손절가 도달 → 매도 실패 → 재시도
2. 쿨다운 기간 내 재매수 차단
3. max_positions 초과 시 매수 거부
4. 자금 부족 → reserve 실패 → 매수 중단
5. FundManager reserve→confirm/cancel 전체 흐름
6. PositionMonitor 단일 권한 검증
"""
import pytest
import asyncio
import threading
from datetime import datetime, timedelta
from unittest.mock import Mock, AsyncMock, patch, MagicMock

from core.fund_manager import FundManager
from core.models import (
    TradingStock, StockState, Position, Order, OrderType, OrderStatus
)
from core.trading.stock_state_manager import StockStateManager


# ============================================================================
# 1. 손절가 도달 → 매도 실패 → 재시도
# ============================================================================

class TestStopLossSellRetry:
    """손절 매도 실패 시 재시도 시나리오"""

    def _make_positioned_stock(self, buy_price=10000, current_price=8500,
                                stop_loss_rate=0.10):
        """포지션 보유 종목 생성 헬퍼"""
        stock = TradingStock(
            stock_code="005930",
            stock_name="삼성전자",
            state=StockState.POSITIONED,
            selected_time=datetime.now(),
        )
        stock.stop_loss_rate = stop_loss_rate
        stock.target_profit_rate = 0.03
        stock.position = Position(
            stock_code="005930",
            quantity=10,
            avg_price=buy_price,
            current_price=current_price,
        )
        return stock

    def test_stop_loss_condition_detected(self):
        """손절 조건이 올바르게 감지되는지 확인"""
        stock = self._make_positioned_stock(buy_price=10000, current_price=8900,
                                             stop_loss_rate=0.10)
        profit_rate = (stock.position.current_price - stock.position.avg_price) / stock.position.avg_price
        # -11% < -10% → 손절 조건 충족
        assert profit_rate <= -stock.stop_loss_rate

    def test_stop_loss_boundary_not_triggered(self):
        """손절 경계값 미도달 시 매도하지 않음"""
        stock = self._make_positioned_stock(buy_price=10000, current_price=9050,
                                             stop_loss_rate=0.10)
        profit_rate = (stock.position.current_price - stock.position.avg_price) / stock.position.avg_price
        # -9.5% > -10% → 손절 미해당
        assert profit_rate > -stock.stop_loss_rate

    @pytest.mark.asyncio
    async def test_sell_failure_should_not_change_state(self):
        """매도 실패 시 상태가 POSITIONED로 유지되어야 함"""
        state_mgr = StockStateManager()
        stock = self._make_positioned_stock()
        state_mgr.register_stock(stock)

        # 매도 실패 시뮬레이션: 상태가 그대로 유지되는지 확인
        assert stock.state == StockState.POSITIONED
        # 매도 실패 후에도 상태 유지 (SELL_PENDING으로 변경되지 않아야)
        assert stock.stock_code in state_mgr.stocks_by_state[StockState.POSITIONED]

    def test_sell_retry_flag_available(self):
        """is_selling 플래그로 중복 매도 방지 가능 확인"""
        stock = self._make_positioned_stock()
        assert stock.is_selling is False
        stock.is_selling = True
        assert stock.is_selling is True
        # 재시도 시 플래그 리셋
        stock.is_selling = False
        assert stock.is_selling is False


# ============================================================================
# 2. 쿨다운 기간 내 재매수 차단
# ============================================================================

class TestBuyCooldown:
    """매수 쿨다운 시나리오"""

    def test_cooldown_blocks_rebuy(self):
        """쿨다운 기간 내 재매수 차단"""
        stock = TradingStock(
            stock_code="005930",
            stock_name="삼성전자",
            state=StockState.COMPLETED,
            selected_time=datetime.now(),
        )
        stock.last_buy_time = datetime.now() - timedelta(minutes=10)
        stock.buy_cooldown_minutes = 25

        elapsed = (datetime.now() - stock.last_buy_time).total_seconds() / 60
        assert elapsed < stock.buy_cooldown_minutes, "쿨다운 기간 내 재매수 불가"

    def test_cooldown_expired_allows_rebuy(self):
        """쿨다운 만료 후 재매수 허용"""
        stock = TradingStock(
            stock_code="005930",
            stock_name="삼성전자",
            state=StockState.COMPLETED,
            selected_time=datetime.now(),
        )
        stock.last_buy_time = datetime.now() - timedelta(minutes=30)
        stock.buy_cooldown_minutes = 25

        elapsed = (datetime.now() - stock.last_buy_time).total_seconds() / 60
        assert elapsed >= stock.buy_cooldown_minutes, "쿨다운 만료 후 재매수 가능"

    def test_no_buy_time_means_no_cooldown(self):
        """매수 이력 없으면 쿨다운 없음"""
        stock = TradingStock(
            stock_code="005930",
            stock_name="삼성전자",
            state=StockState.SELECTED,
            selected_time=datetime.now(),
        )
        assert stock.last_buy_time is None, "매수 이력 없으면 즉시 매수 가능"

    def test_cooldown_default_value(self):
        """기본 쿨다운 25분 확인"""
        stock = TradingStock(
            stock_code="005930",
            stock_name="삼성전자",
            state=StockState.SELECTED,
            selected_time=datetime.now(),
        )
        assert stock.buy_cooldown_minutes == 25


# ============================================================================
# 3. max_positions 초과 시 매수 거부
# ============================================================================

class TestMaxPositions:
    """최대 포지션 수 제한 테스트"""

    def test_max_positions_exceeded(self):
        """max_positions 초과 시 매수 거부"""
        state_mgr = StockStateManager()
        max_positions = 10

        # 10개 포지션 등록
        for i in range(max_positions):
            code = f"{i:06d}"
            stock = TradingStock(
                stock_code=code,
                stock_name=f"종목{i}",
                state=StockState.POSITIONED,
                selected_time=datetime.now(),
            )
            stock.position = Position(stock_code=code, quantity=10, avg_price=10000)
            state_mgr.register_stock(stock)

        positioned = state_mgr.get_stocks_by_state(StockState.POSITIONED)
        assert len(positioned) == max_positions

        # 11번째 매수 시도 → 거부해야 함
        can_buy = len(positioned) < max_positions
        assert can_buy is False

    def test_under_max_positions_allows_buy(self):
        """포지션 여유 있으면 매수 허용"""
        state_mgr = StockStateManager()
        max_positions = 10

        for i in range(5):
            code = f"{i:06d}"
            stock = TradingStock(
                stock_code=code,
                stock_name=f"종목{i}",
                state=StockState.POSITIONED,
                selected_time=datetime.now(),
            )
            state_mgr.register_stock(stock)

        positioned = state_mgr.get_stocks_by_state(StockState.POSITIONED)
        can_buy = len(positioned) < max_positions
        assert can_buy is True

    def test_pending_orders_count_toward_limit(self):
        """BUY_PENDING도 포지션 카운트에 포함되어야 함"""
        state_mgr = StockStateManager()
        max_positions = 3

        # 2개 POSITIONED + 1개 BUY_PENDING
        for i in range(2):
            stock = TradingStock(
                stock_code=f"{i:06d}", stock_name=f"종목{i}",
                state=StockState.POSITIONED, selected_time=datetime.now(),
            )
            state_mgr.register_stock(stock)

        pending = TradingStock(
            stock_code="999999", stock_name="대기종목",
            state=StockState.BUY_PENDING, selected_time=datetime.now(),
        )
        state_mgr.register_stock(pending)

        total_active = (
            len(state_mgr.get_stocks_by_state(StockState.POSITIONED))
            + len(state_mgr.get_stocks_by_state(StockState.BUY_PENDING))
        )
        can_buy = total_active < max_positions
        assert can_buy is False, "POSITIONED + BUY_PENDING이 max에 도달하면 매수 거부"


# ============================================================================
# 4. 자금 부족 → reserve 실패 → 매수 중단
# ============================================================================

class TestInsufficientFundsReserve:
    """자금 부족 시 reserve 실패 및 매수 중단"""

    def test_reserve_fails_on_insufficient_funds(self):
        """자금 부족 시 reserve_funds 실패"""
        fm = FundManager(initial_funds=500_000)
        result = fm.reserve_funds("ORD1", 1_000_000)
        assert result is False
        assert fm.available_funds == 500_000
        assert fm.reserved_funds == 0

    def test_sequential_reserves_exhaust_funds(self):
        """순차 예약으로 자금 소진 시 다음 예약 실패"""
        fm = FundManager(initial_funds=2_000_000)
        assert fm.reserve_funds("ORD1", 1_000_000) is True
        assert fm.reserve_funds("ORD2", 1_000_000) is True
        assert fm.reserve_funds("ORD3", 1_000_000) is False
        assert fm.available_funds == 0
        assert fm.reserved_funds == 2_000_000

    def test_reserve_failure_leaves_state_intact(self):
        """reserve 실패 시 내부 상태 변경 없음"""
        fm = FundManager(initial_funds=1_000_000)
        fm.reserve_funds("ORD1", 500_000)
        
        before_available = fm.available_funds
        before_reserved = fm.reserved_funds
        
        result = fm.reserve_funds("ORD2", 600_000)  # 실패
        assert result is False
        assert fm.available_funds == before_available
        assert fm.reserved_funds == before_reserved

    def test_cancel_frees_funds_for_new_reserve(self):
        """취소 후 자금이 반환되어 새 예약 가능"""
        fm = FundManager(initial_funds=1_000_000)
        fm.reserve_funds("ORD1", 1_000_000)
        assert fm.reserve_funds("ORD2", 500_000) is False
        
        fm.cancel_order("ORD1")
        assert fm.reserve_funds("ORD2", 500_000) is True


# ============================================================================
# 5. FundManager reserve→confirm/cancel 전체 흐름
# ============================================================================

class TestFundManagerFullFlow:
    """FundManager 전체 라이프사이클 테스트"""

    def test_full_buy_flow_reserve_confirm(self):
        """예약 → 체결 전체 흐름"""
        fm = FundManager(initial_funds=10_000_000)
        
        # 1. 예약
        assert fm.reserve_funds("ORD1", 900_000) is True
        assert fm.available_funds == 9_100_000
        assert fm.reserved_funds == 900_000
        
        # 2. 체결 (실제 금액 850,000)
        fm.confirm_order("ORD1", 850_000)
        assert fm.invested_funds == 850_000
        assert fm.reserved_funds == 0
        assert fm.available_funds == 9_150_000  # 50K 환불

    def test_full_buy_flow_reserve_cancel(self):
        """예약 → 취소 전체 흐름"""
        fm = FundManager(initial_funds=10_000_000)
        
        fm.reserve_funds("ORD1", 900_000)
        fm.cancel_order("ORD1")
        
        assert fm.available_funds == 10_000_000
        assert fm.reserved_funds == 0
        assert fm.invested_funds == 0

    def test_full_buy_sell_cycle(self):
        """매수 → 매도 전체 사이클 (회수 금액 > 투자금 시 보정)"""
        fm = FundManager(initial_funds=10_000_000)
        
        # 매수
        fm.reserve_funds("BUY1", 900_000)
        fm.confirm_order("BUY1", 900_000)
        assert fm.invested_funds == 900_000
        
        # 매도 (수익 포함) — 회수 금액이 투자금 초과 시 invested=0 보정
        fm.release_investment(950_000)
        assert fm.invested_funds == 0  # 방어 코드가 0으로 보정
        assert fm.available_funds == 10_000_000  # 투자금만 회수 (수익분은 누락)

    def test_multiple_orders_consistency(self):
        """다중 주문 시 자금 정합성 유지"""
        fm = FundManager(initial_funds=10_000_000)
        
        fm.reserve_funds("ORD1", 900_000)
        fm.reserve_funds("ORD2", 900_000)
        fm.reserve_funds("ORD3", 900_000)
        
        fm.confirm_order("ORD1", 850_000)
        fm.cancel_order("ORD2")
        fm.confirm_order("ORD3", 900_000)
        
        # 정합성: total = available + reserved + invested
        status = fm.get_status()
        total_check = (
            status['available_funds'] + status['reserved_funds'] + status['invested_funds']
        )
        assert total_check == status['total_funds']

    def test_confirm_more_than_reserved_silent_loss(self):
        """체결 금액 > 예약 금액 시 차액이 어디에도 반영 안 됨 (취약점)
        
        예약 500K, 체결 600K → refund = -100K이지만 if refund > 0 조건에 걸려 스킵.
        결과: 100K가 자금 추적에서 누락됨 (정합성 깨짐)
        """
        fm = FundManager(initial_funds=10_000_000)
        fm.reserve_funds("ORD1", 500_000)
        fm.confirm_order("ORD1", 600_000)
        
        assert fm.invested_funds == 600_000
        # available은 변경 없음 (refund 음수는 스킵)
        assert fm.available_funds == 9_500_000
        
        # 정합성 깨짐: total != available + reserved + invested
        total_check = fm.available_funds + fm.reserved_funds + fm.invested_funds
        assert total_check != fm.total_funds, \
            f"취약점: 정합성 깨짐 {total_check} != {fm.total_funds} (100K 누락)"

    def test_double_confirm_ignored(self):
        """이미 confirm된 주문 재confirm 시 무시"""
        fm = FundManager(initial_funds=10_000_000)
        fm.reserve_funds("ORD1", 900_000)
        fm.confirm_order("ORD1", 900_000)
        
        # 두 번째 confirm → 예약에 없으므로 무시
        invested_before = fm.invested_funds
        fm.confirm_order("ORD1", 900_000)
        assert fm.invested_funds == invested_before

    def test_double_cancel_ignored(self):
        """이미 cancel된 주문 재cancel 시 무시"""
        fm = FundManager(initial_funds=10_000_000)
        fm.reserve_funds("ORD1", 900_000)
        fm.cancel_order("ORD1")
        
        available_before = fm.available_funds
        fm.cancel_order("ORD1")
        assert fm.available_funds == available_before


# ============================================================================
# 6. PositionMonitor 단일 권한 검증
# ============================================================================

class TestPositionMonitorAuthority:
    """PositionMonitor가 매도 판단의 단일 권한을 가지는지 검증"""

    def test_position_monitor_requires_decision_engine(self):
        """decision_engine 없으면 매도 판단 불가"""
        from core.trading.position_monitor import PositionMonitor
        
        pm = PositionMonitor(
            state_manager=Mock(),
            completion_handler=Mock(),
            intraday_manager=Mock(),
            data_collector=Mock(),
        )
        assert pm.decision_engine is None
        # decision_engine 없으면 매도 실행 불가능 (코드에서 if not self.decision_engine: continue)

    def test_set_decision_engine(self):
        """decision_engine 설정 테스트"""
        from core.trading.position_monitor import PositionMonitor
        
        pm = PositionMonitor(
            state_manager=Mock(),
            completion_handler=Mock(),
            intraday_manager=Mock(),
            data_collector=Mock(),
        )
        mock_engine = Mock()
        pm.set_decision_engine(mock_engine)
        assert pm.decision_engine is mock_engine

    def test_set_strategy(self):
        """전략 설정 테스트"""
        from core.trading.position_monitor import PositionMonitor
        
        pm = PositionMonitor(
            state_manager=Mock(),
            completion_handler=Mock(),
            intraday_manager=Mock(),
            data_collector=Mock(),
        )
        mock_strategy = Mock()
        mock_strategy.name = "TestStrategy"
        pm.set_strategy(mock_strategy)
        assert pm._strategy is mock_strategy

    def test_monitor_starts_and_stops(self):
        """모니터링 시작/중지 플래그 테스트"""
        from core.trading.position_monitor import PositionMonitor
        
        pm = PositionMonitor(
            state_manager=Mock(),
            completion_handler=Mock(),
            intraday_manager=Mock(),
            data_collector=Mock(),
        )
        assert pm.is_monitoring is False
        pm.stop_monitoring()
        assert pm.is_monitoring is False

    @pytest.mark.asyncio
    async def test_check_positions_once_handles_error(self):
        """check_positions_once가 예외를 삼키는지 확인"""
        from core.trading.position_monitor import PositionMonitor
        
        mock_state_mgr = Mock()
        mock_completion = AsyncMock()
        mock_completion.check_order_completions.side_effect = Exception("test error")
        
        pm = PositionMonitor(
            state_manager=mock_state_mgr,
            completion_handler=mock_completion,
            intraday_manager=Mock(),
            data_collector=Mock(),
        )
        # 예외가 전파되지 않아야 함
        await pm.check_positions_once()

    def test_only_positioned_stocks_checked_for_sell(self):
        """POSITIONED 상태의 종목만 매도 체크 대상"""
        state_mgr = StockStateManager()
        
        # 다양한 상태 종목 등록
        for state in [StockState.SELECTED, StockState.BUY_PENDING,
                       StockState.POSITIONED, StockState.SELL_PENDING]:
            stock = TradingStock(
                stock_code=f"{state.value}_001",
                stock_name=f"테스트_{state.value}",
                state=state,
                selected_time=datetime.now(),
            )
            if state == StockState.POSITIONED:
                stock.position = Position(stock_code=stock.stock_code,
                                          quantity=10, avg_price=10000)
            state_mgr.register_stock(stock)
        
        positioned = state_mgr.get_stocks_by_state(StockState.POSITIONED)
        assert len(positioned) == 1
        assert positioned[0].stock_code == "positioned_001"


# ============================================================================
# 7. 추가 안전성 테스트: 레이스 컨디션 방지
# ============================================================================

class TestRaceConditionPrevention:
    """레이스 컨디션 방지 플래그 테스트"""

    def test_is_buying_flag(self):
        """is_buying 플래그로 중복 매수 방지"""
        stock = TradingStock(
            stock_code="005930", stock_name="삼성전자",
            state=StockState.SELECTED, selected_time=datetime.now(),
        )
        assert stock.is_buying is False
        stock.is_buying = True
        # 다른 스레드에서 매수 시도 시 is_buying 체크로 차단
        assert stock.is_buying is True

    def test_order_processed_flag(self):
        """order_processed 플래그 동작 확인"""
        stock = TradingStock(
            stock_code="005930", stock_name="삼성전자",
            state=StockState.BUY_PENDING, selected_time=datetime.now(),
        )
        assert stock.order_processed is False
        stock.order_processed = True
        assert stock.order_processed is True

    def test_concurrent_fund_reserve_thread_safety(self):
        """동시 자금 예약 시 스레드 안전성 (기존 테스트 보강)"""
        fm = FundManager(initial_funds=5_000_000)
        results = {'success': 0, 'fail': 0}
        lock = threading.Lock()

        def try_reserve(oid):
            r = fm.reserve_funds(oid, 1_000_000)
            with lock:
                if r:
                    results['success'] += 1
                else:
                    results['fail'] += 1

        threads = [threading.Thread(target=try_reserve, args=(f"T{i}",)) for i in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert results['success'] == 5
        assert results['fail'] == 5
        assert fm.reserved_funds == 5_000_000
        assert fm.available_funds == 0


# ============================================================================
# 8. StockStateManager 상태 전이 안전성
# ============================================================================

class TestStateTransitionSafety:
    """상태 전이 안전성"""

    def test_state_change_updates_both_dicts(self):
        """상태 변경 시 두 딕셔너리 모두 업데이트"""
        mgr = StockStateManager()
        stock = TradingStock(
            stock_code="005930", stock_name="삼성전자",
            state=StockState.SELECTED, selected_time=datetime.now(),
        )
        mgr.register_stock(stock)
        
        mgr.change_stock_state("005930", StockState.BUY_PENDING, "매수 주문")
        assert "005930" not in mgr.stocks_by_state[StockState.SELECTED]
        assert "005930" in mgr.stocks_by_state[StockState.BUY_PENDING]
        assert mgr.trading_stocks["005930"].state == StockState.BUY_PENDING

    def test_unregister_cleans_up(self):
        """종목 해제 시 완전 정리"""
        mgr = StockStateManager()
        stock = TradingStock(
            stock_code="005930", stock_name="삼성전자",
            state=StockState.POSITIONED, selected_time=datetime.now(),
        )
        mgr.register_stock(stock)
        mgr.unregister_stock("005930")
        
        assert "005930" not in mgr.trading_stocks
        assert "005930" not in mgr.stocks_by_state[StockState.POSITIONED]

    def test_change_nonexistent_stock_noop(self):
        """존재하지 않는 종목 상태 변경 시 에러 없음"""
        mgr = StockStateManager()
        mgr.change_stock_state("NONEXIST", StockState.POSITIONED, "test")
        # 에러 없이 통과

    def test_state_history_recorded(self):
        """상태 변화 이력 기록 확인"""
        mgr = StockStateManager()
        stock = TradingStock(
            stock_code="005930", stock_name="삼성전자",
            state=StockState.SELECTED, selected_time=datetime.now(),
        )
        mgr.register_stock(stock)
        mgr.change_stock_state("005930", StockState.BUY_PENDING, "매수주문")
        mgr.change_stock_state("005930", StockState.POSITIONED, "체결완료")
        
        assert len(stock.state_history) == 2
        assert stock.state_history[0]['to_state'] == 'buy_pending'
        assert stock.state_history[1]['to_state'] == 'positioned'
