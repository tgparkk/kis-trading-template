"""[모호조회] 다중소유 오귀속 결함 — 크로스모듈 wrong-object mutation 회귀 테스트.

배경(2026-07-23):
같은 stock_code 를 2개 전략이 동시 점유(설계상 정상 — "전략별 자본 독립")할 때,
StockStateManager.get_trading_stock(stock_code, strategy=None) 은 삽입순서상 첫
소유자를 임의 반환하고 [모호조회] WARNING 을 찍는다. TradingContext.buy()/sell()
가 strategy 를 넘기지 않으면 caller 자신의 전략이 아닌 '다른 전략의 TradingStock'
을 받아 변이(mutate)시킬 수 있다(최악: 감시·매도 누락 고아 포지션).

★ 프로덕션 owner 표기 분열(실증 2026-07-23):
- SELECTED(buy 조회): 폴더키(다중전략 로더 candidate_loader.py:186) 또는
  클래스명(단일전략 로더 :95).
- POSITIONED(sell 조회): 클래스명(라이브 매수 trading_decision_engine.py:644)
  또는 폴더키(DB 복원 state_restorer.py:482 = ledger_key).
TradingContext 는 _strategy_key=폴더키, _current_strategy_name=클래스명 을 갖는다.
따라서 어느 한쪽 표기만으로 조회하면 무거래(전 종목 매수 스킵) 또는 정당한
매도 오거부가 난다. 이 파일은 **프로덕션 형상**(owner=폴더키/클래스명 분열,
_current_strategy_name=클래스명)을 모델링해 표기-불변 조회를 검증한다.
"""
import logging
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from core.trading.stock_state_manager import StockStateManager
from core.trading_stock_manager import TradingStockManager
from core.trading_decision_engine import TradingDecisionEngine
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


def _make_ctx(trading_manager, trading_analyzer, folder_key: str, class_name: str):
    """_strategy_key=folder_key, _current_strategy_name=class_name 인 TradingContext.

    strategies_dict[folder_key].name==class_name 이면 __init__ 이
    _current_strategy_name 을 클래스명으로, _strategy_key 를 폴더키로 분리 저장한다
    (프로덕션 형상 재현).
    """
    strat = MagicMock()
    strat.name = class_name
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

    ctx = TradingContext(
        trading_manager=trading_manager,
        decision_engine=decision_engine,
        fund_manager=fund_manager,
        data_collector=MagicMock(),
        intraday_manager=intraday_manager,
        trading_analyzer=trading_analyzer,
        db_manager=None,
        broker=broker,
        strategy_name=folder_key,
        strategies_dict={folder_key: strat},
    )
    # 형상 사전검증: 폴더키≠클래스명 분리 저장 확인
    assert ctx._strategy_key == folder_key
    assert ctx._current_strategy_name == class_name
    return ctx


async def _run_buy(ctx, code):
    with patch("config.market_hours.get_circuit_breaker_state") as mock_cb, \
         patch("config.market_hours.MarketHours.is_eod_liquidation_time",
               return_value=False):
        cb = MagicMock()
        cb.is_market_halted.return_value = False
        cb.is_vi_active.return_value = False
        mock_cb.return_value = cb
        return await ctx.buy(code)


# ============================================================================
# 1. buy() — SELECTED owner=폴더키 인데 조회를 클래스명으로 하면 무거래(CRITICAL)
# ============================================================================

class TestBuyOwnerRepresentationCritical:
    """단일 소유라도 SELECTED owner 가 폴더키면, 클래스명 조회는 None→전 종목 매수 스킵."""

    @pytest.mark.asyncio
    async def test_buy_finds_slot_when_owner_is_folder_key(self):
        code = "004100"
        ssm = StockStateManager()
        # 프로덕션 다중전략 로더 형상: SELECTED owner = 폴더키
        ts = _make_ts(code, owner="elder_ema_pullback", state=StockState.SELECTED)
        assert ssm.register_stock(ts) is True
        tm = _FakeTradingManager(ssm)
        analyzer = AsyncMock()
        analyzer.analyze_buy_decision = AsyncMock(return_value=True)
        # ctx: 폴더키=elder_ema_pullback, 클래스명=ElderEmaPullbackStrategy
        ctx = _make_ctx(tm, analyzer,
                        folder_key="elder_ema_pullback",
                        class_name="ElderEmaPullbackStrategy")

        result = await _run_buy(ctx, code)

        # 정정 전(클래스명 단독 조회) 이면 None → 매수 스킵(RED). 정정 후 GREEN.
        assert result == code, (
            "SELECTED owner=폴더키인 종목을 클래스명으로만 조회 → 무거래(매수 스킵)"
        )
        analyzer.analyze_buy_decision.assert_awaited_once()
        passed = analyzer.analyze_buy_decision.call_args.args[0]
        assert passed is ts


# ============================================================================
# 2. buy() — 2소유자에서 호출 전략(B)의 슬롯만 조회/변이 (wrong-object mutation)
# ============================================================================

class TestBuyMultiOwnerIdentity:
    """전략 A(폴더키 aaa)·B(폴더키 bbb)가 같은 종목 SELECTED. B.buy()가 B 슬롯만."""

    @pytest.mark.asyncio
    async def test_buy_mutates_callers_own_slot(self):
        code = "004100"
        ssm = StockStateManager()
        ts_a = _make_ts(code, owner="aaa", state=StockState.SELECTED)   # 먼저
        ts_b = _make_ts(code, owner="bbb", state=StockState.SELECTED)   # 나중
        assert ssm.register_stock(ts_a) is True
        assert ssm.register_stock(ts_b) is True
        tm = _FakeTradingManager(ssm)
        analyzer = AsyncMock()
        analyzer.analyze_buy_decision = AsyncMock(return_value=True)
        ctx = _make_ctx(tm, analyzer, folder_key="bbb", class_name="BbbStrategy")

        with _StateLogCapture() as cap:
            result = await _run_buy(ctx, code)

        assert result == code
        analyzer.analyze_buy_decision.assert_awaited_once()
        passed = analyzer.analyze_buy_decision.call_args.args[0]
        assert passed is ts_b, (
            "buy() 가 호출 전략(B)이 아닌 다른 전략(A)의 TradingStock 을 넘김 "
            f"(passed owner={getattr(passed, 'owner_strategy_name', None)})"
        )
        # 매수 성공 후 owner 재기록이 A 의 객체를 덮어쓰지 않아야 한다(오귀속 방지).
        assert ts_a.owner_strategy_name == "aaa", (
            "buy() 가 다른 전략(A)의 owner_strategy_name 을 덮어씀 = 크로스모듈 오귀속"
        )
        assert cap.ambiguous_msgs() == [], f"[모호조회] 발생: {cap.ambiguous_msgs()}"


# ============================================================================
# 3. sell() — POSITIONED owner 표기 분열(클래스명/폴더키) 모두에서 B 슬롯 조회
# ============================================================================

class TestSellOwnerRepresentationInvariant:
    """POSITIONED owner 가 라이브(클래스명)/복원(폴더키) 어느 표기여도 정확히 조회."""

    @pytest.mark.asyncio
    @pytest.mark.parametrize("owner_repr", ["BbbStrategy", "bbb"])
    async def test_sell_targets_callers_own_slot(self, owner_repr):
        code = "004100"
        ssm = StockStateManager()
        # A 는 라이브 표기(클래스명), B 는 파라미터 표기로 POSITIONED
        ts_a = _make_ts(code, owner="AaaStrategy", state=StockState.POSITIONED)
        ts_b = _make_ts(code, owner=owner_repr, state=StockState.POSITIONED)
        assert ssm.register_stock(ts_a) is True
        assert ssm.register_stock(ts_b) is True
        tm = _FakeTradingManager(ssm)
        analyzer = AsyncMock()
        ctx = _make_ctx(tm, analyzer, folder_key="bbb", class_name="BbbStrategy")

        with _StateLogCapture() as cap:
            result = await ctx.sell(code)

        # 복원 표기(폴더키)일 때 정정 전(클래스명 단독 조회)은 None→매도 스킵(RED).
        assert result == code, "B 소유 종목 매도가 owner 표기 분열로 잘못 거부됨"
        analyzer.analyze_sell_decision.assert_awaited_once()
        passed = analyzer.analyze_sell_decision.call_args.args[0]
        assert passed is ts_b, (
            "sell() 이 호출 전략(B)이 아닌 다른 전략(A)의 TradingStock 을 넘김 "
            f"(passed owner={getattr(passed, 'owner_strategy_name', None)})"
        )
        assert cap.ambiguous_msgs() == [], f"[모호조회] 발생: {cap.ambiguous_msgs()}"


# ============================================================================
# 4. execute_real_buy (MEDIUM) — 2소유자에서 올바른 슬롯만 BUY_PENDING
# ============================================================================

class TestExecuteRealBuyMultiOwner:
    """execute_real_buy 가 owner 를 execute_buy_order 로 전달해 B 슬롯만 전이."""

    def _make_real_tm(self):
        order_manager = MagicMock()
        order_manager.place_buy_order = AsyncMock(return_value="ORD-1")
        # set_trading_manager 역참조 훅(있으면 호출됨) — no-op mock
        order_manager.set_trading_manager = MagicMock()
        tm = TradingStockManager(
            intraday_manager=MagicMock(),
            data_collector=MagicMock(),
            order_manager=order_manager,
        )
        return tm

    def _make_engine(self, tm):
        # 무거운 __init__ 우회 — execute_real_buy 는 trading_manager·logger 만 사용
        engine = TradingDecisionEngine.__new__(TradingDecisionEngine)
        engine.trading_manager = tm
        engine.logger = logging.getLogger("test.decision_engine")
        return engine

    @pytest.mark.asyncio
    async def test_real_buy_transitions_only_callers_slot(self):
        code = "004100"
        tm = self._make_real_tm()
        # 2소유자 SELECTED (프로덕션 다중전략 형상: owner=폴더키)
        ts_a = _make_ts(code, owner="aaa", state=StockState.SELECTED)
        ts_b = _make_ts(code, owner="bbb", state=StockState.SELECTED)
        tm._register_stock(ts_a)
        tm._register_stock(ts_b)
        # 등록 확인
        assert tm.get_trading_stock(code, strategy="aaa") is ts_a
        assert tm.get_trading_stock(code, strategy="bbb") is ts_b

        engine = self._make_engine(tm)

        with _StateLogCapture() as cap:
            ok = await engine.execute_real_buy(
                ts_b, buy_reason="test", buy_price=1000.0, quantity=10
            )

        assert ok is True
        # B 슬롯만 BUY_PENDING, A 슬롯은 그대로 SELECTED
        assert ts_b.state == StockState.BUY_PENDING, "B 슬롯이 BUY_PENDING 이 아님"
        assert ts_a.state == StockState.SELECTED, (
            "다른 전략(A)의 슬롯이 잘못 BUY_PENDING 으로 전이됨 = 오귀속"
        )
        tm.order_manager.place_buy_order.assert_awaited_once()
        assert cap.ambiguous_msgs() == [], f"[모호조회] 발생: {cap.ambiguous_msgs()}"
