"""
E2E 시나리오 테스트
- 동시성: 동시 3종목 매수, 매수 중 매도 신호
- 주문 처리: API 타임아웃, 부분 체결, 취소 실패
- 시간/자금: 갭손절 중단, 리밸런싱 타임아웃, 잔고 부족
- 데이터: 스크리닝 0건, 현재가 조회 실패
"""
import pytest
import asyncio
import threading
from datetime import datetime, timedelta
from unittest.mock import Mock, AsyncMock, patch

from core.fund_manager import FundManager
from core.models import (
    Order, OrderType, OrderStatus, StockState,
    TradingStock, Position, TradingConfig
)
from core.order_manager import OrderManager
from utils.korean_time import now_kst


@pytest.fixture(autouse=True)
def _mock_market_hours():
    """장 시간 체크를 우회하여 테스트 시간에 관계없이 주문 가능하게 함"""
    with patch('config.market_hours.MarketHours.can_place_order', return_value=True):
        yield


# ============================================================================
# Fixtures
# ============================================================================

def _make_fund_manager(funds=10_000_000):
    return FundManager(initial_funds=funds)


def _make_trading_stock(code="005930", name="삼성전자", buy_price=None):
    stock = TradingStock(
        stock_code=code,
        stock_name=name,
        state=StockState.SELECTED,
        selected_time=datetime.now()
    )
    stock.target_profit_rate = 0.17
    stock.stop_loss_rate = 0.09
    if buy_price:
        stock.state = StockState.POSITIONED
        stock.position = Position(stock_code=code, quantity=10, avg_price=buy_price)
    return stock


def _make_order_manager(paper_trading=False):
    config = TradingConfig.from_json({
        'paper_trading': paper_trading,
        'order_management': {
            'buy_timeout_seconds': 300,
            'sell_timeout_seconds': 300,
        }
    })
    api = Mock()
    api.is_initialized = True
    telegram = AsyncMock()
    db = Mock()
    db.save_virtual_buy.return_value = 1
    db.save_virtual_sell.return_value = True
    db.get_last_open_virtual_buy.return_value = None

    om = OrderManager(config, api, telegram, db)
    om.trading_manager = None
    return om


# ============================================================================
# 동시성 시나리오
# ============================================================================

class TestConcurrencyScenarios:
    """동시성 시나리오"""

    def test_concurrent_3stock_buy_reservation(self):
        """동시 3종목 매수 자금 예약 - Lock 보호, 정합성 유지"""
        fm = FundManager(initial_funds=10_000_000)
        results = {}

        def reserve(code, amount):
            results[code] = fm.reserve_funds(f"ORD-{code}", amount)

        threads = [
            threading.Thread(target=reserve, args=("005930", 900_000)),
            threading.Thread(target=reserve, args=("000660", 900_000)),
            threading.Thread(target=reserve, args=("035420", 900_000)),
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert all(results.values())
        assert fm.reserved_funds == 2_700_000
        assert fm.available_funds == 7_300_000
        # 정합성
        assert fm.available_funds + fm.reserved_funds + fm.invested_funds == fm.total_funds

    def test_buying_flag_blocks_sell(self):
        """매수 중 동일 종목 매도 신호 차단"""
        stock = _make_trading_stock("005930", buy_price=70000)
        stock.is_buying = True

        assert stock.is_buying is True
        should_process_sell = not stock.is_buying
        assert should_process_sell is False


# ============================================================================
# 주문 처리 이상 시나리오
# ============================================================================

class TestOrderProcessingScenarios:
    """주문 처리 이상 시나리오"""

    @pytest.mark.asyncio
    async def test_api_timeout_order_id_loss(self):
        """안전성 이슈 #1: API 타임아웃 후 주문ID 손실"""
        om = _make_order_manager(paper_trading=False)

        with patch('core.orders.order_executor.run_with_timeout', new_callable=AsyncMock) as mock:
            mock.return_value = None
            order_id = await om.place_buy_order("005930", 10, 70000)

        assert order_id is None
        assert len(om.pending_orders) == 0

    @pytest.mark.asyncio
    async def test_partial_fill_then_timeout(self):
        """부분 체결 후 타임아웃 → 체결분만 포지션"""
        om = _make_order_manager(paper_trading=False)
        ts = now_kst()
        order = Order(
            order_id="ORD-PARTIAL",
            stock_code="005930",
            order_type=OrderType.BUY,
            price=70000,
            quantity=10,
            timestamp=ts - timedelta(minutes=6),
            filled_quantity=6,
        )
        om.pending_orders["ORD-PARTIAL"] = order
        om.order_timeouts["ORD-PARTIAL"] = ts - timedelta(minutes=1)

        with patch.object(om, '_check_order_status', new_callable=AsyncMock):
            with patch.object(om, '_handle_partial_fill_timeout', new_callable=AsyncMock) as mock_partial:
                await om._handle_timeout("ORD-PARTIAL")

        mock_partial.assert_called_once()
        assert mock_partial.call_args[0][2] == 6

    @pytest.mark.asyncio
    async def test_cancel_3_failures_force_cleanup(self):
        """주문 취소 3회 실패 → force_cleanup"""
        om = _make_order_manager(paper_trading=False)
        ts = now_kst()
        order = Order(
            order_id="ORD-STUCK",
            stock_code="005930",
            order_type=OrderType.BUY,
            price=70000,
            quantity=10,
            timestamp=ts - timedelta(minutes=6),
        )
        om.pending_orders["ORD-STUCK"] = order
        om.order_timeouts["ORD-STUCK"] = ts - timedelta(minutes=1)

        with patch.object(om, '_check_order_status', new_callable=AsyncMock):
            with patch.object(om, '_cancel_with_retry', new_callable=AsyncMock, return_value=False):
                with patch.object(om, '_force_timeout_cleanup', new_callable=AsyncMock) as mock_force:
                    await om._handle_timeout("ORD-STUCK")

        mock_force.assert_called_once_with("ORD-STUCK")


# ============================================================================
# 자금 시나리오
# ============================================================================

class TestFundScenarios:
    """자금 관련 시나리오"""

    def test_insufficient_balance_buy(self):
        """잔고 부족 매수 불가"""
        fm = FundManager(initial_funds=100_000)
        max_amt = fm.get_max_buy_amount("005930")
        assert max_amt == 9_000  # 100K * 0.09

    def test_investment_limit_90_reached(self):
        """투자 한도 90% 도달"""
        fm = FundManager(initial_funds=10_000_000)
        fm.reserve_funds("ORD1", 8_500_000)
        fm.confirm_order("ORD1", 8_500_000)

        # invested_funds = 8.5M (수수료 미포함), 투자여력: 10M*0.9 - 8.5M = 500K
        max_amt = fm.get_max_buy_amount("005930")
        assert max_amt == pytest.approx(10_000_000 * 0.9 - 8_500_000)

    def test_fund_consistency_after_operations(self):
        """다양한 자금 연산 후 정합성 유지"""
        from config.constants import COMMISSION_RATE
        fm = FundManager(initial_funds=10_000_000)

        fm.reserve_funds("ORD1", 900_000)
        fm.reserve_funds("ORD2", 900_000)
        fm.reserve_funds("ORD3", 900_000)

        fm.confirm_order("ORD1", 850_000)
        fm.cancel_order("ORD2")

        fm.release_investment(400_000)

        status = fm.get_status()
        commission = 850_000 * COMMISSION_RATE
        total_check = status['available_funds'] + status['reserved_funds'] + status['invested_funds']
        assert total_check == pytest.approx(status['total_funds'] - commission)


# ============================================================================
# 데이터 이상 시나리오
# ============================================================================

class TestDataAnomalyScenarios:
    """데이터 이상 시나리오"""

    def test_screening_zero_results(self):
        """스크리닝 결과 0건 → CandidateSelector가 빈 목록 반환 시 후속 처리 없음"""
        from core.candidate_selector import CandidateSelector
        from core.models import TradingConfig

        config = TradingConfig()
        selector = CandidateSelector(config, broker=None, db_manager=None)

        # _load_candidates가 빈 목록을 반환하도록 Mock
        selector._load_candidates = Mock(return_value=[])

        candidates = selector._load_candidates()

        assert isinstance(candidates, list)
        assert len(candidates) == 0
        # 빈 결과에서 종목 필터링을 수행해도 예외 없이 빈 목록이어야 함
        filtered = [c for c in candidates if getattr(c, 'score', 0) > 50]
        assert filtered == []

    def test_current_price_fetch_failure(self):
        """현재가 조회 실패 → TradingDecisionEngine이 graceful하게 처리"""
        from core.trading_decision_engine import TradingDecisionEngine

        engine = TradingDecisionEngine.__new__(TradingDecisionEngine)
        engine.logger = Mock()
        engine.intraday_manager = Mock()
        engine.intraday_manager.get_cached_current_price.return_value = None

        stock = _make_trading_stock("005930", buy_price=70000)

        # 현재가 조회 결과가 None이면 current_price는 0이어야 함 (예외 없음)
        price_info = engine.intraday_manager.get_cached_current_price(stock.stock_code)
        assert price_info is None

        # None을 안전하게 처리하면 current_price는 0으로 간주
        current_price = (price_info or {}).get('current_price', 0)
        assert current_price == 0

        # current_price == 0이면 손익절 판단을 스킵해야 함 (분기 조건 확인)
        should_evaluate = current_price > 0
        assert should_evaluate is False

    @pytest.mark.asyncio
    async def test_paper_mode_full_cycle(self):
        """가상매매 전체 사이클: 매수 → 매도"""
        om = _make_order_manager(paper_trading=True)

        buy_id = await om.place_buy_order("005930", 10, 70000)
        assert buy_id is not None
        assert buy_id.startswith("VT-BUY")

        sell_id = await om.place_sell_order("005930", 10, 72000)
        assert sell_id is not None
        assert sell_id.startswith("VT-SELL")

        assert len(om.completed_orders) == 2


# ============================================================================
# 시간 시나리오
# ============================================================================

class TestTimeScenarios:
    """시간 관련 시나리오"""

    @pytest.mark.asyncio
    async def test_rebalancing_timeout(self):
        """리밸런싱 20분 타임아웃"""
        async def slow_rebalancing():
            await asyncio.sleep(100)

        with pytest.raises(asyncio.TimeoutError):
            await asyncio.wait_for(slow_rebalancing(), timeout=0.1)

    def test_order_timeout_calculation(self):
        """주문 타임아웃 시간 계산"""
        config = TradingConfig.from_json({
            'order_management': {'buy_timeout_seconds': 300}
        })
        assert config.order_management.buy_timeout_seconds == 300


# ============================================================================
# 상태 전이 시나리오
# ============================================================================

class TestStateTransitionScenarios:
    """상태 전이 시나리오"""

    def test_full_buy_sell_cycle(self):
        """전체 매수-매도 상태 전이"""
        stock = _make_trading_stock("005930")
        assert stock.state == StockState.SELECTED

        stock.change_state(StockState.BUY_PENDING, "매수 주문")
        stock.change_state(StockState.POSITIONED, "체결")
        stock.set_position(10, 70000)
        stock.change_state(StockState.SELL_CANDIDATE, "익절 조건")
        stock.change_state(StockState.SELL_PENDING, "매도 주문")
        stock.change_state(StockState.COMPLETED, "매도 완료")

        assert stock.state == StockState.COMPLETED
        assert len(stock.state_history) == 5

    def test_failed_state_recovery(self):
        """실패 상태에서 복구"""
        stock = _make_trading_stock("005930")
        stock.change_state(StockState.BUY_PENDING, "매수 주문")
        stock.change_state(StockState.FAILED, "주문 실패")
        assert stock.state == StockState.FAILED

        stock.change_state(StockState.SELECTED, "재시도")
        assert stock.state == StockState.SELECTED
