"""
Phase E8 단위 테스트 — 종목 중복 가드 (POSITIONED + BUY_PENDING 둘 다 거부)

테스트 범위:
- test_register_rejected_when_positioned: POSITIONED 상태 종목의 두 번째 등록 거부
- test_register_rejected_when_buy_pending: BUY_PENDING 상태도 거부
- test_register_allowed_when_completed: COMPLETED 상태는 덮어쓰기 허용
- test_buy_rejected_for_other_strategy_owned_stock: 전략 A 보유 종목을 전략 B 매수 시도 거부
- test_log_message_includes_owner_name: 거부 로그에 기존 owner 이름 포함
"""
import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from core.trading.stock_state_manager import StockStateManager
from core.models import TradingStock, StockState
from utils.korean_time import now_kst


# ============================================================================
# 헬퍼
# ============================================================================

def _make_ts(code: str, state: StockState = StockState.SELECTED,
             owner: str = "") -> TradingStock:
    ts = TradingStock(
        stock_code=code,
        stock_name=code,
        state=state,
        selected_time=now_kst(),
        selection_reason="test",
    )
    ts.owner_strategy_name = owner
    return ts


def _run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


# ============================================================================
# 1. StockStateManager — POSITIONED 거부
# ============================================================================

class TestRegisterRejectedWhenPositioned:
    """POSITIONED 상태 종목의 두 번째 등록을 거부."""

    def test_register_rejected_when_positioned(self):
        mgr = StockStateManager()
        ts1 = _make_ts("000001", StockState.SELECTED, owner="StrategyA")
        mgr.register_stock(ts1)

        # 상태를 POSITIONED으로 변경
        mgr.change_stock_state("000001", StockState.BUY_PENDING)
        mgr.change_stock_state("000001", StockState.POSITIONED)

        ts2 = _make_ts("000001", StockState.SELECTED, owner="StrategyB")
        result = mgr.register_stock(ts2)

        assert result is False
        # 원본 객체(StrategyA 소유) 유지
        assert mgr.trading_stocks["000001"].owner_strategy_name == "StrategyA"

    def test_register_rejected_when_positioned_direct_state(self):
        """TradingStock을 처음부터 POSITIONED로 만들어 등록 후 두 번째 거부."""
        mgr = StockStateManager()
        ts1 = _make_ts("000002", StockState.POSITIONED, owner="StrategyA")
        mgr.register_stock(ts1)

        ts2 = _make_ts("000002", StockState.SELECTED, owner="StrategyB")
        result = mgr.register_stock(ts2)

        assert result is False
        assert mgr.trading_stocks["000002"] is ts1


# ============================================================================
# 2. StockStateManager — BUY_PENDING 거부
# ============================================================================

class TestRegisterRejectedWhenBuyPending:
    """BUY_PENDING 상태 종목의 두 번째 등록도 거부."""

    def test_register_rejected_when_buy_pending(self):
        mgr = StockStateManager()
        ts1 = _make_ts("000003", StockState.SELECTED, owner="StrategyA")
        mgr.register_stock(ts1)
        mgr.change_stock_state("000003", StockState.BUY_PENDING)

        ts2 = _make_ts("000003", StockState.SELECTED, owner="StrategyB")
        result = mgr.register_stock(ts2)

        assert result is False
        assert mgr.trading_stocks["000003"].owner_strategy_name == "StrategyA"

    def test_register_rejected_when_buy_pending_direct(self):
        """BUY_PENDING 상태로 직접 등록 후 두 번째 거부."""
        mgr = StockStateManager()
        ts1 = _make_ts("000004", StockState.BUY_PENDING, owner="StrategyA")
        mgr.register_stock(ts1)

        ts2 = _make_ts("000004", StockState.SELECTED, owner="StrategyB")
        result = mgr.register_stock(ts2)

        assert result is False
        assert mgr.trading_stocks["000004"] is ts1


# ============================================================================
# 3. StockStateManager — COMPLETED 상태는 덮어쓰기 허용
# ============================================================================

class TestRegisterAllowedWhenCompleted:
    """COMPLETED 상태(거래 종료)는 새 등록을 허용한다."""

    def test_register_allowed_when_completed(self):
        mgr = StockStateManager()
        ts1 = _make_ts("000005", StockState.SELECTED, owner="StrategyA")
        mgr.register_stock(ts1)
        # COMPLETED로 전이
        mgr.change_stock_state("000005", StockState.COMPLETED)

        ts2 = _make_ts("000005", StockState.SELECTED, owner="StrategyB")
        result = mgr.register_stock(ts2)

        assert result is True
        # 새 객체로 교체됨
        assert mgr.trading_stocks["000005"].owner_strategy_name == "StrategyB"

    def test_register_allowed_when_failed(self):
        """FAILED 상태도 덮어쓰기 허용."""
        mgr = StockStateManager()
        ts1 = _make_ts("000006", StockState.FAILED, owner="StrategyA")
        mgr.register_stock(ts1)

        ts2 = _make_ts("000006", StockState.SELECTED, owner="StrategyB")
        result = mgr.register_stock(ts2)

        assert result is True
        assert mgr.trading_stocks["000006"].owner_strategy_name == "StrategyB"

    def test_register_allowed_when_selected(self):
        """SELECTED 상태도 덮어쓰기 허용 (아직 매수 전)."""
        mgr = StockStateManager()
        ts1 = _make_ts("000007", StockState.SELECTED, owner="StrategyA")
        mgr.register_stock(ts1)

        ts2 = _make_ts("000007", StockState.SELECTED, owner="StrategyB")
        result = mgr.register_stock(ts2)

        assert result is True
        assert mgr.trading_stocks["000007"].owner_strategy_name == "StrategyB"


# ============================================================================
# 4. TradingContext.buy() — 다른 전략 소유 종목 매수 거부
# ============================================================================

class TestBuyRejectedForOtherStrategyOwnedStock:
    """전략 A 보유 종목(POSITIONED/BUY_PENDING)을 전략 B가 매수 시도 시 거부."""

    def _make_context(self, strategy_name: str, existing_owner: str,
                      existing_state: StockState):
        """TradingContext mock 구성."""
        from core.trading_context import TradingContext

        # stock_state_manager mock
        stock_state_mgr = MagicMock()
        existing_ts = _make_ts("999999", existing_state, owner=existing_owner)
        stock_state_mgr.trading_stocks = {"999999": existing_ts}

        # trading_manager mock
        trading_manager = MagicMock()
        trading_manager.get_trading_stock = MagicMock(return_value=existing_ts)
        trading_manager.stock_state_manager = stock_state_mgr

        # decision_engine mock — 시장급락 아님
        decision_engine = MagicMock()
        decision_engine.check_market_direction = MagicMock(return_value=(False, ""))

        # fund_manager mock — 손실한도 미초과
        fund_manager = MagicMock()
        fund_manager.is_daily_loss_limit_hit = MagicMock(return_value=False)

        ctx = TradingContext(
            trading_manager=trading_manager,
            decision_engine=decision_engine,
            fund_manager=fund_manager,
            data_collector=None,
            intraday_manager=None,
            trading_analyzer=None,
            db_manager=None,
            broker=None,
            strategy_name=strategy_name,
        )
        return ctx

    def test_buy_rejected_when_positioned_by_other_strategy(self):
        """POSITIONED 상태 종목: 다른 전략의 매수 거부."""
        ctx = self._make_context(
            strategy_name="StrategyB",
            existing_owner="StrategyA",
            existing_state=StockState.POSITIONED,
        )

        async def run():
            with patch("config.market_hours.get_circuit_breaker_state") as mock_cb:
                cb = MagicMock()
                cb.is_market_halted.return_value = False
                cb.is_vi_active.return_value = False
                mock_cb.return_value = cb
                result = await ctx.buy("999999")
            return result

        result = _run(run())
        assert result is None

    def test_buy_rejected_when_buy_pending_by_other_strategy(self):
        """BUY_PENDING 상태 종목: 다른 전략의 매수 거부."""
        ctx = self._make_context(
            strategy_name="StrategyB",
            existing_owner="StrategyA",
            existing_state=StockState.BUY_PENDING,
        )

        async def run():
            with patch("config.market_hours.get_circuit_breaker_state") as mock_cb:
                cb = MagicMock()
                cb.is_market_halted.return_value = False
                cb.is_vi_active.return_value = False
                mock_cb.return_value = cb
                result = await ctx.buy("999999")
            return result

        result = _run(run())
        assert result is None

    def test_buy_allowed_when_no_stock_state_manager(self):
        """stock_state_manager가 없으면 가드 스킵 (기존 동작 유지)."""
        from core.trading_context import TradingContext

        trading_manager = MagicMock()
        ts = _make_ts("888888", StockState.SELECTED, owner="")
        trading_manager.get_trading_stock = MagicMock(return_value=ts)
        # stock_state_manager 없음
        del trading_manager.stock_state_manager

        decision_engine = MagicMock()
        decision_engine.check_market_direction = MagicMock(return_value=(False, ""))

        fund_manager = MagicMock()
        fund_manager.is_daily_loss_limit_hit = MagicMock(return_value=False)

        trading_analyzer = AsyncMock()
        trading_analyzer.analyze_buy_decision = AsyncMock()

        ctx = TradingContext(
            trading_manager=trading_manager,
            decision_engine=decision_engine,
            fund_manager=fund_manager,
            data_collector=None,
            intraday_manager=None,
            trading_analyzer=trading_analyzer,
            db_manager=None,
            broker=None,
            strategy_name="StrategyA",
        )

        async def run():
            with patch("config.market_hours.get_circuit_breaker_state") as mock_cb, \
                 patch("config.constants.PRICE_LIMIT_GUARD_RATE", 0.3):
                cb = MagicMock()
                cb.is_market_halted.return_value = False
                cb.is_vi_active.return_value = False
                mock_cb.return_value = cb
                result = await ctx.buy("888888")
            return result

        result = _run(run())
        # trading_analyzer.analyze_buy_decision이 호출됐으면 매수 진행한 것
        trading_analyzer.analyze_buy_decision.assert_called_once()


# ============================================================================
# 5. 거부 로그에 기존 owner 이름 포함
# ============================================================================

class TestLogMessageIncludesOwnerName:
    """중복 등록 거부 시 로그에 기존 owner_strategy_name이 포함됨."""

    def test_log_message_includes_owner_name(self):
        import logging
        mgr = StockStateManager()

        ts1 = _make_ts("111111", StockState.POSITIONED, owner="StrategyA")
        mgr.register_stock(ts1)

        log_messages = []

        class CapturingHandler(logging.Handler):
            def emit(self, record):
                log_messages.append(record.getMessage())

        handler = CapturingHandler()
        import logging as _logging
        logger = _logging.getLogger("core.trading.stock_state_manager")
        logger.addHandler(handler)
        logger.setLevel(logging.DEBUG)

        ts2 = _make_ts("111111", StockState.SELECTED, owner="StrategyB")
        result = mgr.register_stock(ts2)

        logger.removeHandler(handler)

        assert result is False
        matched = [m for m in log_messages if "111111" in m and "StrategyA" in m]
        assert matched, (
            f"거부 로그에 'StrategyA' 미포함. 캡처된 로그: {log_messages}"
        )

    def test_log_message_includes_state_name(self):
        """거부 로그에 기존 state 이름도 포함됨."""
        import logging as _logging

        mgr = StockStateManager()
        ts1 = _make_ts("222222", StockState.BUY_PENDING, owner="StrategyX")
        mgr.register_stock(ts1)

        log_messages = []

        class CapturingHandler(_logging.Handler):
            def emit(self, record):
                log_messages.append(record.getMessage())

        handler = CapturingHandler()
        logger = _logging.getLogger("core.trading.stock_state_manager")
        logger.addHandler(handler)
        logger.setLevel(_logging.DEBUG)

        ts2 = _make_ts("222222", StockState.SELECTED, owner="StrategyY")
        mgr.register_stock(ts2)

        logger.removeHandler(handler)

        matched = [m for m in log_messages if "BUY_PENDING" in m or "POSITIONED" in m]
        assert matched, (
            f"거부 로그에 state 이름 미포함. 캡처된 로그: {log_messages}"
        )
