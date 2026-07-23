"""[모호조회] 다중소유 오귀속 결함 — 크로스모듈 wrong-object mutation 회귀 테스트.

배경(2026-07-23):
같은 stock_code 를 2개 전략이 동시 점유(설계상 정상 — "전략별 자본 독립")할 때,
StockStateManager.get_trading_stock(stock_code, strategy=None) 은 삽입순서상 첫
소유자를 임의 반환하고 [모호조회] WARNING 을 찍는다. TradingContext.buy()/sell()
가 strategy 를 넘기지 않으면 caller 자신의 전략이 아닌 '다른 전략의 TradingStock'
을 받아 변이(mutate)시킬 수 있다. 최악 시 caller 슬롯이 감시·매도에서 누락되는
고아 포지션.

이 파일은 기존 test_stock_state_manager_composite.py / test_phase_e8_duplicate_stock_guard.py
(StockStateManager 단독 또는 Mock trading_manager)와 달리, **실제 TradingContext 경로 +
실제 StockStateManager** 로 2소유자 시나리오를 태워, 반환/변이되는 객체의 정체성(identity,
`is`)이 호출 전략(B)의 슬롯인지, 그리고 사이클 중 [모호조회] WARNING 이 0건인지를 검증한다.
"""
import asyncio
import logging
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from core.trading.stock_state_manager import StockStateManager
from core.trading_context import TradingContext
from core.models import TradingStock, StockState
from utils.korean_time import now_kst


STATE_LOGGER_NAME = "core.trading.stock_state_manager"


# ============================================================================
# 헬퍼
# ============================================================================

def _make_ts(code: str, owner: str, state: StockState) -> TradingStock:
    ts = TradingStock(
        stock_code=code,
        stock_name=code,
        state=state,
        selected_time=now_kst(),
        selection_reason="test",
        prev_close=0.0,  # 상/하한가 가드 스킵 (prev_close<=0 → intraday None → 건너뜀)
    )
    ts.owner_strategy_name = owner
    return ts


class _StateLogCapture:
    """StockStateManager 네임드 로거([모호조회])를 직접 캡처.

    setup_logger 가 propagate=False 일 수 있어 caplog 대신 named logger 에
    핸들러를 직접 부착한다(기존 e8 테스트 관례).
    """

    def __init__(self):
        self.records = []

        class _H(logging.Handler):
            def emit(_self, record):
                self.records.append(record.getMessage())

        self._handler = _H()
        self._logger = logging.getLogger(STATE_LOGGER_NAME)

    def __enter__(self):
        self._logger.addHandler(self._handler)
        self._prev_level = self._logger.level
        self._logger.setLevel(logging.DEBUG)
        return self

    def __exit__(self, *exc):
        self._logger.removeHandler(self._handler)
        self._logger.setLevel(self._prev_level)
        return False

    def ambiguous_msgs(self):
        return [m for m in self.records if "[모호조회]" in m]


class _FakeTradingManager:
    """실제 StockStateManager 를 감싸는 최소 trading_manager.

    TradingContext.buy()/sell() 가 사용하는 표면(get_trading_stock,
    get_stocks_by_state, stock_state_manager)만 위임한다.
    """

    def __init__(self, ssm: StockStateManager):
        self._ssm = ssm
        self.stock_state_manager = ssm

    def get_trading_stock(self, stock_code, strategy=None):
        return self._ssm.get_trading_stock(stock_code, strategy=strategy)

    def get_stocks_by_state(self, state):
        return self._ssm.get_stocks_by_state(state)


def _make_ctx(trading_manager, trading_analyzer, current_strategy: str):
    """current_strategy 를 표기명(_current_strategy_name)으로 갖는 TradingContext.

    strategies_dict 에 .name==current_strategy 인스턴스를 넣어 __init__ 이
    _current_strategy_name 을 그 이름으로 세팅하게 한다.
    """
    strat = MagicMock()
    strat.name = current_strategy
    strat.holding_period = "swing"  # EOD intraday 차단 회피(안전)

    decision_engine = MagicMock()
    decision_engine.check_market_direction = MagicMock(return_value=(False, ""))
    decision_engine.check_regime_gate = MagicMock(return_value=(False, ""))

    fund_manager = MagicMock()
    fund_manager.is_daily_loss_limit_hit = MagicMock(return_value=False)

    intraday_manager = MagicMock()
    intraday_manager.get_cached_current_price.return_value = None

    broker = MagicMock()
    broker.get_current_price.return_value = None

    return TradingContext(
        trading_manager=trading_manager,
        decision_engine=decision_engine,
        fund_manager=fund_manager,
        data_collector=MagicMock(),
        intraday_manager=intraday_manager,
        trading_analyzer=trading_analyzer,
        db_manager=None,
        broker=broker,
        strategy_name="owner_b_key",
        strategies_dict={"owner_b_key": strat},
    )


def _register_two_owners(code: str, state: StockState):
    """전략 A(먼저)·전략 B(나중) 두 소유자로 동일 종목 등록. (ssm, ts_a, ts_b) 반환."""
    ssm = StockStateManager()
    ts_a = _make_ts(code, owner="StrategyA", state=state)
    ts_b = _make_ts(code, owner="StrategyB", state=state)
    assert ssm.register_stock(ts_a) is True
    assert ssm.register_stock(ts_b) is True
    return ssm, ts_a, ts_b


# ============================================================================
# 1. sell() — 2소유자에서 호출 전략(B)의 객체를 받아야 한다
# ============================================================================

class TestSellMultiOwnerIdentity:
    """전략 B 의 sell() 이 A 의 객체를 받아 owner-mismatch 로 잘못 거부되지 않아야."""

    @pytest.mark.asyncio
    async def test_sell_targets_callers_own_slot(self):
        code = "004100"
        ssm, ts_a, ts_b = _register_two_owners(code, StockState.POSITIONED)
        tm = _FakeTradingManager(ssm)
        analyzer = AsyncMock()
        ctx = _make_ctx(tm, analyzer, current_strategy="StrategyB")

        with _StateLogCapture() as cap:
            result = await ctx.sell(code)

        # B 의 매도는 정상 진행되어야 하고, analyze_sell_decision 이 B 의 객체로 호출돼야 한다.
        assert result == code, "B 소유 종목 매도가 owner-mismatch 로 잘못 거부됨"
        analyzer.analyze_sell_decision.assert_awaited_once()
        passed = analyzer.analyze_sell_decision.call_args.args[0]
        assert passed is ts_b, (
            "sell() 이 호출 전략(B)이 아닌 다른 전략(A)의 TradingStock 을 넘김 "
            f"(passed owner={getattr(passed, 'owner_strategy_name', None)})"
        )
        # 2소유자 매도 경로에서 [모호조회] WARNING 이 0건이어야 한다.
        assert cap.ambiguous_msgs() == [], (
            f"[모호조회] WARNING 발생: {cap.ambiguous_msgs()}"
        )


# ============================================================================
# 2. buy() — 2소유자에서 호출 전략(B)의 객체를 변이해야 한다 (wrong-object mutation)
# ============================================================================

class TestBuyMultiOwnerIdentity:
    """전략 B 의 buy() 가 A 의 객체를 받아 A 의 owner 를 덮어쓰지 않아야."""

    @pytest.mark.asyncio
    async def test_buy_mutates_callers_own_slot(self):
        code = "004100"
        # SELECTED 상태로 두 소유자 등록 (매수 게이트 통과 대상)
        ssm, ts_a, ts_b = _register_two_owners(code, StockState.SELECTED)
        tm = _FakeTradingManager(ssm)
        analyzer = AsyncMock()
        analyzer.analyze_buy_decision = AsyncMock(return_value=True)  # 체결 성공
        ctx = _make_ctx(tm, analyzer, current_strategy="StrategyB")

        with _StateLogCapture() as cap:
            with patch("config.market_hours.get_circuit_breaker_state") as mock_cb, \
                 patch("config.market_hours.MarketHours.is_eod_liquidation_time",
                       return_value=False):
                cb = MagicMock()
                cb.is_market_halted.return_value = False
                cb.is_vi_active.return_value = False
                mock_cb.return_value = cb
                result = await ctx.buy(code)

        assert result == code
        analyzer.analyze_buy_decision.assert_awaited_once()
        passed = analyzer.analyze_buy_decision.call_args.args[0]
        assert passed is ts_b, (
            "buy() 가 호출 전략(B)이 아닌 다른 전략(A)의 TradingStock 을 넘김 "
            f"(passed owner={getattr(passed, 'owner_strategy_name', None)})"
        )
        # 매수 성공 후 owner 기록이 A 의 객체를 덮어쓰지 않아야 한다(오귀속 방지).
        assert ts_a.owner_strategy_name == "StrategyA", (
            "buy() 가 다른 전략(A)의 owner_strategy_name 을 덮어씀 = 크로스모듈 오귀속"
        )
        assert ts_b.owner_strategy_name == "StrategyB"
        # 2소유자 매수 경로에서 [모호조회] WARNING 이 0건이어야 한다.
        assert cap.ambiguous_msgs() == [], (
            f"[모호조회] WARNING 발생: {cap.ambiguous_msgs()}"
        )
