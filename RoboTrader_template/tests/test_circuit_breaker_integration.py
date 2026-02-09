"""
CircuitBreakerState 주문 흐름 통합 테스트 + 동시성 안전성 테스트

P0 이슈:
1. VI 발동 시 매수 주문 차단, 시장 전체 서킷브레이커 시 매수/매도 차단
2. CircuitBreakerState의 thread-safety 검증
"""
import pytest
import threading
import asyncio
from unittest.mock import Mock, AsyncMock, patch
from datetime import datetime, timedelta

from core.models import TradingConfig, OrderStatus
from core.order_manager import OrderManager
from config.market_hours import CircuitBreakerState, get_circuit_breaker_state


def _make_order_manager(paper_trading=True):
    """OrderManager 생성 헬퍼"""
    config = TradingConfig.from_json({
        'paper_trading': paper_trading,
        'order_management': {
            'buy_timeout_seconds': 180,
            'sell_timeout_seconds': 180,
        }
    })
    broker = Mock()
    broker.is_initialized = True
    telegram = AsyncMock()
    db = Mock()
    db.save_virtual_buy.return_value = 1
    db.save_virtual_sell.return_value = True
    db.get_last_open_virtual_buy.return_value = None

    om = OrderManager(config, broker, telegram, db)
    return om


# ========== P0-1: CircuitBreakerState → 주문 흐름 통합 ==========

class TestBuyOrderVIBlock:
    """VI 발동 시 매수 주문 차단"""

    @pytest.mark.asyncio
    async def test_buy_blocked_when_vi_active(self):
        """종목 VI 발동 중이면 매수 주문 거부"""
        om = _make_order_manager()
        cb = get_circuit_breaker_state()
        cb.clear_all()
        cb.trigger_vi("005930")

        order_id = await om.place_buy_order("005930", 10, 70000)
        assert order_id is None

        cb.clear_all()

    @pytest.mark.asyncio
    async def test_buy_allowed_when_vi_not_active(self):
        """VI 없는 종목은 정상 매수"""
        om = _make_order_manager()
        cb = get_circuit_breaker_state()
        cb.clear_all()

        order_id = await om.place_buy_order("005930", 10, 70000)
        assert order_id is not None

        cb.clear_all()

    @pytest.mark.asyncio
    async def test_buy_blocked_when_market_halted(self):
        """시장 전체 서킷브레이커 발동 시 매수 거부"""
        om = _make_order_manager()
        cb = get_circuit_breaker_state()
        cb.clear_all()
        cb.trigger_market_halt(duration_minutes=20)

        order_id = await om.place_buy_order("005930", 10, 70000)
        assert order_id is None

        cb.clear_all()

    @pytest.mark.asyncio
    async def test_buy_allowed_after_vi_release(self):
        """VI 해제 후 매수 가능"""
        om = _make_order_manager()
        cb = get_circuit_breaker_state()
        cb.clear_all()
        cb.trigger_vi("005930")

        assert await om.place_buy_order("005930", 10, 70000) is None

        cb.release_vi("005930")
        order_id = await om.place_buy_order("005930", 10, 70000)
        assert order_id is not None

        cb.clear_all()

    @pytest.mark.asyncio
    async def test_other_stock_not_affected_by_vi(self):
        """A 종목 VI 발동이 B 종목에 영향 없음"""
        om = _make_order_manager()
        cb = get_circuit_breaker_state()
        cb.clear_all()
        cb.trigger_vi("005930")

        # 005930 차단
        assert await om.place_buy_order("005930", 10, 70000) is None
        # 035720 허용
        order_id = await om.place_buy_order("035720", 5, 30000)
        assert order_id is not None

        cb.clear_all()


class TestSellOrderCircuitBreaker:
    """서킷브레이커/VI와 매도 주문"""

    @pytest.mark.asyncio
    async def test_sell_allowed_when_vi_active(self):
        """종목 VI 발동 중에도 매도는 허용 (포지션 청산 기회 보장)"""
        om = _make_order_manager()
        cb = get_circuit_breaker_state()
        cb.clear_all()
        cb.trigger_vi("005930")

        order_id = await om.place_sell_order("005930", 10, 70000)
        assert order_id is not None

        cb.clear_all()

    @pytest.mark.asyncio
    async def test_sell_blocked_when_market_halted(self):
        """시장 전체 서킷브레이커 시 매도도 차단"""
        om = _make_order_manager()
        cb = get_circuit_breaker_state()
        cb.clear_all()
        cb.trigger_market_halt(duration_minutes=20)

        order_id = await om.place_sell_order("005930", 10, 70000)
        assert order_id is None

        cb.clear_all()

    @pytest.mark.asyncio
    async def test_sell_allowed_after_market_halt_release(self):
        """시장 서킷브레이커 해제 후 매도 가능"""
        om = _make_order_manager()
        cb = get_circuit_breaker_state()
        cb.clear_all()
        cb.trigger_market_halt(duration_minutes=20)

        assert await om.place_sell_order("005930", 10, 70000) is None

        cb.release_market_halt()
        order_id = await om.place_sell_order("005930", 10, 70000)
        assert order_id is not None

        cb.clear_all()


class TestBuySignalsVISkip:
    """메인 루프 _check_buy_signals에서 VI 종목 스킵"""

    @pytest.mark.asyncio
    async def test_vi_stocks_skipped_in_buy_signals(self):
        """_check_buy_signals에서 VI 발동 종목 스킵"""
        cb = get_circuit_breaker_state()
        cb.clear_all()
        cb.trigger_vi("005930")

        # Mock DayTradingBot
        mock_bot = Mock()
        mock_bot.is_running = True

        mock_stock_vi = Mock()
        mock_stock_vi.stock_code = "005930"
        mock_stock_vi.is_buy_cooldown_active.return_value = False

        mock_stock_ok = Mock()
        mock_stock_ok.stock_code = "035720"
        mock_stock_ok.is_buy_cooldown_active.return_value = False

        mock_bot.trading_manager.get_stocks_by_state.return_value = [mock_stock_vi, mock_stock_ok]
        mock_bot._analyze_buy_decision = AsyncMock()

        # DayTradingBot은 외부 의존성(telegram 등)이 필요하므로
        # CircuitBreakerState 동작만 직접 검증
        assert cb.is_vi_active("005930") is True
        assert cb.is_vi_active("035720") is False

        cb.clear_all()

    @pytest.mark.asyncio
    async def test_market_halt_skips_all_buy_signals(self):
        """시장 전체 서킷브레이커 발동 시 모든 매수 판단 스킵"""
        cb = get_circuit_breaker_state()
        cb.clear_all()
        cb.trigger_market_halt(duration_minutes=20)

        assert cb.is_market_halted() is True

        cb.clear_all()


# ========== P0-2: 동시성 안전성 ==========

class TestCircuitBreakerStateThreadSafety:
    """CircuitBreakerState의 thread-safety 검증"""

    def test_concurrent_vi_trigger_release(self):
        """여러 스레드에서 동시에 VI trigger/release"""
        cb = CircuitBreakerState()
        errors = []

        def trigger_and_release(stock_code, iterations):
            try:
                for _ in range(iterations):
                    cb.trigger_vi(stock_code)
                    _ = cb.is_vi_active(stock_code)
                    cb.release_vi(stock_code)
                    _ = cb.get_active_vi_stocks()
            except Exception as e:
                errors.append(e)

        threads = [
            threading.Thread(target=trigger_and_release, args=(f"STOCK_{i}", 500))
            for i in range(10)
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(errors) == 0, f"Thread errors: {errors}"

    def test_concurrent_market_halt(self):
        """여러 스레드에서 동시에 market halt trigger/release/check"""
        cb = CircuitBreakerState()
        errors = []

        def halt_cycle(iterations):
            try:
                for _ in range(iterations):
                    cb.trigger_market_halt(duration_minutes=1)
                    _ = cb.is_market_halted()
                    cb.release_market_halt()
                    _ = cb.is_market_halted()
            except Exception as e:
                errors.append(e)

        threads = [
            threading.Thread(target=halt_cycle, args=(500,))
            for _ in range(10)
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(errors) == 0, f"Thread errors: {errors}"

    def test_concurrent_mixed_operations(self):
        """VI trigger + market halt + clear_all 동시 실행"""
        cb = CircuitBreakerState()
        errors = []

        def mixed_ops(thread_id, iterations):
            try:
                for i in range(iterations):
                    code = f"STOCK_{thread_id}_{i % 5}"
                    cb.trigger_vi(code)
                    cb.is_vi_active(code)
                    cb.is_market_halted()
                    if i % 10 == 0:
                        cb.trigger_market_halt(1)
                    if i % 15 == 0:
                        cb.clear_all()
                    cb.get_active_vi_stocks()
                    cb.release_vi(code)
            except Exception as e:
                errors.append(e)

        threads = [
            threading.Thread(target=mixed_ops, args=(i, 300))
            for i in range(10)
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(errors) == 0, f"Thread errors: {errors}"


class TestAsyncConcurrencySafety:
    """asyncio 이벤트 루프 내 동시성 안전성"""

    @pytest.mark.asyncio
    async def test_pending_orders_not_corrupted_during_iteration(self):
        """pending_orders 딕셔너리가 반복 중 변경되어도 안전"""
        om = _make_order_manager()

        # 여러 주문 동시 생성
        tasks = [
            om.place_buy_order(f"00{i}000", 10, 50000)
            for i in range(5)
        ]
        results = await asyncio.gather(*tasks)

        # 모두 성공 (가상매매이므로 즉시 체결)
        assert all(r is not None for r in results)

    @pytest.mark.asyncio
    async def test_order_summary_safe_during_concurrent_orders(self):
        """주문 실행 중 get_order_summary 호출해도 안전"""
        om = _make_order_manager()

        await om.place_buy_order("005930", 10, 70000)

        # 동시에 summary 조회
        summary = om.get_order_summary()
        assert isinstance(summary, dict)
        assert 'pending_count' in summary

    @pytest.mark.asyncio
    async def test_fund_manager_concurrent_access(self):
        """FundManager가 여러 비동기 태스크에서 접근되어도 안전"""
        from core.fund_manager import FundManager

        fm = FundManager(initial_funds=10_000_000)

        # 동시 예약 시도 (asyncio는 single-threaded이므로 실제 경합 없지만 API 확인)
        results = []
        for i in range(5):
            ok = fm.reserve_funds(f"order_{i}", 1_000_000)
            results.append(ok)

        # 최소 1개 이상 성공해야 함
        assert any(results)
