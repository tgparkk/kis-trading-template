"""SystemMonitor 전략 후보 종목 등록의 소유자 바인딩 — 오귀속 회귀 테스트.

배경(2026-07-24):
bot/system_monitor.py:_register_strategy_target_stocks 는 전략의
get_target_stocks() 결과를 add_selected_stock 으로 등록하면서
① owner_strategy 를 넘기지 않아 owner_strategy_name="" 로 등록하고
   (order_execution.py:119),
② 이어서 무한정 조회 get_trading_stock(stock_code) 로 얻은 슬롯에
   ts.strategy_name = strategy.name 을 대입했다.

TradingStock.strategy_name 은 owner_strategy_name 의 **별칭 프로퍼티**이므로
(core/models.py:206-213) 이 대입은 '표시용 이름'이 아니라 **소유권 자체**를
덮어쓴다. 다중소유(같은 종목을 여러 전략이 각자 보유 — 설계상 정상) 상황에서
무한정 조회는 삽입순 첫 소유자를 반환하므로, 다른 전략의 슬롯 소유권이
호출 전략 이름으로 바뀐다 = 실제 오귀속(f4c3683·01d336e 와 같은 계열).

★ 표기(notation) 요구:
SELECTED 소유자 표기는 **폴더키**여야 한다. SELECTED 소비자인
TradingContext.get_selected_stocks 가 owner 미지정 시 _strategy_key(폴더키)와
비교하기 때문이다(core/trading_context.py:285-297). 클래스명(strategy.name)으로
등록하면 어느 전략에게도 보이지 않는 유령 슬롯이 된다(65bf870 재현 유형).
"""
import logging
from unittest.mock import AsyncMock, MagicMock

import pytest

from core.trading.stock_state_manager import StockStateManager
from core.trading_stock_manager import TradingStockManager
from core.trading_context import TradingContext
from core.models import TradingStock, StockState
from utils.korean_time import now_kst


STATE_LOGGER_NAME = "core.trading.stock_state_manager"

TARGET_CODE = "005930"
FOLDER_KEY_B = "bbb"
CLASS_NAME_B = "BbbStrategy"


class _StateLogCapture:
    """StockStateManager 네임드 로거([모호조회]) 직접 캡처 (기존 e8 테스트 관례)."""

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


def _make_trading_manager() -> TradingStockManager:
    """실제 StockStateManager·OrderExecution 을 쓰는 TradingStockManager.

    외부 IO(장중 관리자·실시간 수집기·주문 관리자)만 목으로 대체하고
    등록 경로는 프로덕션 코드를 그대로 탄다.
    """
    intraday_manager = MagicMock()
    intraday_manager.add_selected_stock = AsyncMock(return_value=True)
    data_collector = MagicMock()
    order_manager = MagicMock()
    return TradingStockManager(
        intraday_manager=intraday_manager,
        data_collector=data_collector,
        order_manager=order_manager,
    )


def _make_bot(trading_manager) -> MagicMock:
    """프로덕션 형상 봇: strategies={폴더키: 인스턴스}, strategy=그 인스턴스."""
    strategy = MagicMock()
    strategy.name = CLASS_NAME_B          # 클래스명 표기
    strategy.get_target_stocks = MagicMock(return_value=[TARGET_CODE])

    bot = MagicMock()
    bot.strategy = strategy
    bot.strategies = {FOLDER_KEY_B: strategy}   # 폴더키 → 인스턴스 (main.py:170)
    bot.trading_manager = trading_manager
    bot.broker.get_stock_name.return_value = "테스트종목"
    return bot


def _make_ctx_for_b(trading_manager) -> TradingContext:
    """_strategy_key=폴더키, _current_strategy_name=클래스명 인 B 전략 컨텍스트."""
    strat = MagicMock()
    strat.name = CLASS_NAME_B
    return TradingContext(
        trading_manager=trading_manager,
        decision_engine=MagicMock(),
        fund_manager=MagicMock(),
        data_collector=MagicMock(),
        intraday_manager=MagicMock(),
        trading_analyzer=MagicMock(),
        db_manager=MagicMock(),
        broker=MagicMock(),
        is_running_check=lambda: True,
        strategy_name=FOLDER_KEY_B,
        strategies_dict={FOLDER_KEY_B: strat},
    )


class TestSystemMonitorTargetStockOwnerBinding:
    """_register_strategy_target_stocks 가 남의 슬롯을 건드리지 않는지."""

    @pytest.mark.asyncio
    @pytest.mark.parametrize("owner_a", [
        "aaa",           # 다중전략 로더 형상: owner=폴더키
        "AaaStrategy",   # 단일전략 로더 형상: owner=클래스명
    ])
    async def test_does_not_hijack_other_strategy_slot(self, owner_a):
        from bot.system_monitor import SystemMonitor

        tm = _make_trading_manager()
        ssm: StockStateManager = tm._state_manager

        # 전략 A 가 같은 종목을 이미 SELECTED 로 점유 (설계상 정상)
        ts_a = TradingStock(
            stock_code=TARGET_CODE,
            stock_name=TARGET_CODE,
            state=StockState.SELECTED,
            selected_time=now_kst(),
            selection_reason="A 전략 선정",
        )
        ts_a.owner_strategy_name = owner_a
        assert ssm.register_stock(ts_a) is True

        monitor = SystemMonitor(_make_bot(tm))

        with _StateLogCapture() as cap:
            await monitor._register_strategy_target_stocks()

        # (a) 남(A)의 슬롯 소유권이 변조되지 않아야 한다
        assert ts_a.owner_strategy_name == owner_a, (
            f"다른 전략(A)의 슬롯 소유자가 {owner_a!r} → "
            f"{ts_a.owner_strategy_name!r} 로 덮어써짐 = 오귀속"
        )
        # (b) B 자신의 슬롯이 별도로 생성되어야 한다
        slots = ssm._find_by_code(TARGET_CODE)
        b_slots = [s for s in slots if s is not ts_a]
        assert len(b_slots) == 1, (
            f"호출 전략(B) 소유 슬롯이 생성되지 않음 (slots={[s.owner_strategy_name for s in slots]})"
        )
        assert b_slots[0].owner_strategy_name in (FOLDER_KEY_B, CLASS_NAME_B), (
            f"B 슬롯 소유자 표기가 전략 식별자가 아님: {b_slots[0].owner_strategy_name!r}"
        )
        # (c) [모호조회] 무발생
        assert cap.ambiguous_msgs() == [], f"[모호조회] 발생: {cap.ambiguous_msgs()}"

    @pytest.mark.asyncio
    async def test_registered_stock_is_visible_to_owner_context(self):
        """등록된 슬롯이 소유 전략의 TradingContext 에 보여야 한다.

        get_selected_stocks 는 owner 미지정 시 _strategy_key(폴더키)와 비교하므로
        클래스명으로 등록하면 아무에게도 안 보이는 유령 슬롯이 된다.
        """
        from bot.system_monitor import SystemMonitor

        tm = _make_trading_manager()
        monitor = SystemMonitor(_make_bot(tm))
        await monitor._register_strategy_target_stocks()

        ctx = _make_ctx_for_b(tm)
        visible = [s.stock_code for s in ctx.get_selected_stocks()]
        assert TARGET_CODE in visible, (
            "등록된 후보가 소유 전략 컨텍스트에 보이지 않음 — "
            "SELECTED owner 표기가 폴더키가 아님(유령 슬롯)"
        )

    @pytest.mark.asyncio
    async def test_other_strategy_cannot_see_the_slot(self):
        """등록된 슬롯이 타 전략 컨텍스트에는 보이지 않아야 한다(소유 격리)."""
        from bot.system_monitor import SystemMonitor

        tm = _make_trading_manager()
        monitor = SystemMonitor(_make_bot(tm))
        await monitor._register_strategy_target_stocks()

        other = MagicMock()
        other.name = "AaaStrategy"
        ctx_other = TradingContext(
            trading_manager=tm,
            decision_engine=MagicMock(),
            fund_manager=MagicMock(),
            data_collector=MagicMock(),
            intraday_manager=MagicMock(),
            trading_analyzer=MagicMock(),
            db_manager=MagicMock(),
            broker=MagicMock(),
            is_running_check=lambda: True,
            strategy_name="aaa",
            strategies_dict={"aaa": other},
        )
        visible = [s.stock_code for s in ctx_other.get_selected_stocks()]
        assert TARGET_CODE not in visible, (
            "타 전략 컨텍스트에 남의 후보가 보임 — 소유자 미바인딩(공용 슬롯)"
        )
