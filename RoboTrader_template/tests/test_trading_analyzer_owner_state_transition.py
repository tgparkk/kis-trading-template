"""가상 매수 상태 전이의 owner 표기 정합 검증 (owner 오귀속 계열 6번째 — 상태머신 키잉)

증상 (2026-08-06 EOD 실측):
    15:00 EOD 청산 대상이 46 종목인데 실제 보유는 55 종목. 차 9 = 그날 매수한 9건이고
    전략별로 6/6 일치했다(우연이 아님).

체인 (코드에서 도출 · 이 파일이 고정하는 것):
    1. 선정: ``candidate_loader.py:186`` 이 ``owner_strategy=<폴더키>`` 로 넘기고
       ``order_execution.py:119`` 가 ``owner_strategy_name="book_pullback_ma20"``
       (폴더키)으로 ``TradingStock`` 을 만든다.
    2. 매수: ``trading_context.py:509`` 가 ``strategy_name=self._strategy_key``
       (= **폴더키**)로 ``analyze_buy_decision`` 을 부른다.
    3. 체결: ``trading_decision_engine.py:657~660`` 이 **슬롯 객체의 owner 를
       덮어쓴다** — ``display_name = owner.name`` = 전략 인스턴스의 ``.name``
       = **클래스명**(``"BookPullbackMa20Strategy"``).
    4. 그 직후 ``trading_analyzer.py:204·208`` 이 owner 를 **인자(폴더키)** 로
       넘긴다. ``stock_state_manager.py:86`` 은 ``==`` 정확일치라 매칭 0 이 되고,
       ``:158~159`` 의 **조용한 return** 으로 상태 전이가 실패한다(예외 없음 →
       호출부 ``try/except`` 무력).
    5. 종목은 SELECTED 로 남는다. EOD 청산 대상집합은
       ``get_stocks_by_state(POSITIONED)`` (``liquidation_handler``) 이므로
       그 종목이 통째로 빠진다.

같은 함수 안에서 owner 를 **인자와 객체 두 갈래**로 읽으면 비대칭이 생긴다 —
``trading_analyzer.py:191~196`` 주석이 이미 그 경고를 적어두고 있었다(add_position
은 객체에서 읽는다). 이 파일은 그 비대칭이 되살아나면 실패한다.

동일 결함 클래스 이력: ``f4c3683``(_position_owner) · ``01d336e``(모호조회) ·
``e79b440``(EOD 청산 (code,owner) 쌍) · ``6de60e2``(매도 평균단가 SQL WHERE).
"""

import datetime
from unittest.mock import AsyncMock, Mock

import pandas as pd
import pytest

from bot.trading_analyzer import TradingAnalyzer
from core.models import StockState, TradingStock
from core.trading.stock_state_manager import StockStateManager

# 실제 형상(strategies/book_pullback_ma20/): 폴더키 ≠ 전략 인스턴스 .name
FOLDER_KEY = "book_pullback_ma20"          # screener.py:13 strategy_name
CLASS_NAME = "BookPullbackMa20Strategy"    # strategy.py:48 name
OTHER_FOLDER_KEY = "book_pullback_ma5"
CODE = "037230"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_stock(code=CODE, owner=FOLDER_KEY, state=StockState.SELECTED):
    return TradingStock(
        stock_code=code,
        stock_name="테스트종목",
        state=state,
        selected_time=datetime.datetime.now(),
        owner_strategy_name=owner,
    )


def _make_daily_df(n=25):
    """CANDIDATE_MIN_DAILY_DATA(=22) 이상의 일봉."""
    return pd.DataFrame({
        "date": [f"202601{i + 1:02d}" for i in range(n)],
        "close": [50000] * n,
    })


def _make_bot(state_mgr: StockStateManager, on_virtual_buy=None):
    """**실제** StockStateManager 를 물린 bot mock.

    ``_change_stock_state`` 를 Mock 으로 두면 조용한 return 자체가 재현되지 않아
    이 결함은 영원히 보이지 않는다 — 반드시 실물에 위임한다.
    """
    bot = Mock()

    bot.trading_manager._change_stock_state = (
        lambda stock_code, new_state, reason="", strategy=None:
        state_mgr.change_stock_state(stock_code, new_state, reason, strategy=strategy)
    )
    bot.trading_manager.get_stocks_by_state = state_mgr.get_stocks_by_state
    bot.trading_manager.get_trading_stock = state_mgr.get_trading_stock

    bot.db_manager.price_repo.get_daily_prices.return_value = _make_daily_df()

    strategy_instance = Mock()
    strategy_instance.name = CLASS_NAME
    strategy_instance.regime_index = "both"
    bot.strategies = {FOLDER_KEY: strategy_instance}

    bot.decision_engine.set_fund_manager = Mock()
    bot.decision_engine.is_virtual_mode = True
    bot.decision_engine.analyze_buy_decision = AsyncMock(
        return_value=(
            True,
            "테스트 매수 신호",
            {"buy_price": 50000, "quantity": 10, "max_buy_amount": 500000, "signal": None},
        )
    )
    bot.decision_engine.execute_virtual_buy = AsyncMock(
        side_effect=on_virtual_buy if on_virtual_buy is not None else _rewrite_owner_to_class_name
    )

    bot.fund_manager.reserve_funds.return_value = True
    bot.fund_manager.confirm_order = Mock()
    bot.fund_manager.cancel_order = Mock()
    bot.fund_manager.add_position = Mock()
    bot.fund_manager.get_status.return_value = {
        "total_funds": 10_000_000, "available_funds": 1_000_000,
    }
    return bot


async def _rewrite_owner_to_class_name(trading_stock, *args, **kwargs):
    """프로덕션 ``execute_virtual_buy`` 의 owner 덮어쓰기를 그대로 흉내낸다.

    ``trading_decision_engine.py:660``:
        ``trading_stock.owner_strategy_name = display_name``  (= 인스턴스 .name)
    이 한 줄 때문에 상태 전이 호출 시점의 객체 owner 는 **클래스명**이고,
    인자로 흘러온 ``strategy_name`` 은 **폴더키**다.
    """
    trading_stock.owner_strategy_name = CLASS_NAME
    return True


# ---------------------------------------------------------------------------
# 1. 주 회귀 — 체결 후 POSITIONED 전이가 성공해야 EOD 청산 대상에 들어온다
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_virtual_buy_reaches_positioned_when_engine_rewrites_owner():
    """체결 엔진이 owner 를 클래스명으로 덮어써도 상태 전이가 성공해야 한다.

    수정 전(인자=폴더키 전달)에는 매칭 0 → 조용한 return → SELECTED 잔류 →
    EOD 청산 대상집합(POSITIONED)에서 누락된다.
    """
    state_mgr = StockStateManager()
    stock = _make_stock()
    assert state_mgr.register_stock(stock) is True

    bot = _make_bot(state_mgr)
    analyzer = TradingAnalyzer(bot)

    executed = await analyzer.analyze_buy_decision(stock, strategy_name=FOLDER_KEY)
    assert executed is True, "가상 매수 자체가 체결되지 않으면 이 테스트는 무효다"

    # 체결 엔진이 owner 를 덮어썼다는 전제 자체를 먼저 고정 (하네스 유효성)
    assert stock.owner_strategy_name == CLASS_NAME
    assert FOLDER_KEY != CLASS_NAME, "두 표기가 같으면 이 테스트는 판별력이 없다"

    eod_targets = state_mgr.get_stocks_by_state(StockState.POSITIONED)
    assert stock.state == StockState.POSITIONED, (
        f"상태 전이가 조용히 실패했다 (현재 {stock.state.name}) — "
        f"인자 owner({FOLDER_KEY!r}) 와 객체 owner({stock.owner_strategy_name!r}) 불일치"
    )
    assert [s.stock_code for s in eod_targets] == [CODE], (
        "POSITIONED 인덱스에 없다 = EOD 일괄청산 대상집합에서 누락된다 "
        f"(대상 {len(eod_targets)}건)"
    )


@pytest.mark.asyncio
async def test_virtual_buy_passes_slot_owner_not_the_argument():
    """호출부가 상태 전이에 넘기는 owner 는 **슬롯 객체의 값**이어야 한다.

    ``add_position``(:197) · ``get_trading_stock``(:159) · 매도 실패 복원(:300)
    과 같은 방식 — 같은 함수 안에서 owner 를 두 갈래로 읽으면 비대칭이 생긴다.
    """
    state_mgr = StockStateManager()
    stock = _make_stock()
    state_mgr.register_stock(stock)

    seen = []
    bot = _make_bot(state_mgr)
    _real = bot.trading_manager._change_stock_state

    def _spy(stock_code, new_state, reason="", strategy=None):
        seen.append((new_state, strategy))
        return _real(stock_code, new_state, reason, strategy=strategy)

    bot.trading_manager._change_stock_state = _spy

    await TradingAnalyzer(bot).analyze_buy_decision(stock, strategy_name=FOLDER_KEY)

    assert [s for _, s in seen] == [CLASS_NAME, CLASS_NAME], (
        f"상태 전이에 넘긴 owner={[s for _, s in seen]!r} — "
        f"인자(폴더키 {FOLDER_KEY!r})가 아니라 슬롯 owner({CLASS_NAME!r})여야 한다"
    )
    assert [st for st, _ in seen] == [StockState.BUY_PENDING, StockState.POSITIONED]


# ---------------------------------------------------------------------------
# 2. 대칭 단언 — 틀린 owner 로 부르면 **실패해야** 한다
# ---------------------------------------------------------------------------
# 「올바른 owner 로 부르면 성공한다」 단독 단언은 판별력이 없다: 매칭을 정규화·
# 대소문자 무시 등으로 느슨하게 만들어도 통과해버린다. 아래가 그 반쪽을 고정한다.

def test_wrong_owner_silently_fails_while_correct_owner_succeeds():
    """owner 표기가 어긋나면 예외 없이 조용히 실패한다(= 결함의 물리적 원인)."""
    state_mgr = StockStateManager()
    stock = _make_stock(owner=CLASS_NAME, state=StockState.BUY_PENDING)
    state_mgr.register_stock(stock)

    # (a) 틀린 owner(폴더키) — 예외도, 반환값도 없이 상태가 그대로다
    state_mgr.change_stock_state(CODE, StockState.POSITIONED, "오owner", strategy=FOLDER_KEY)
    assert stock.state == StockState.BUY_PENDING, (
        "틀린 owner 인데 전이가 됐다 — 매칭이 느슨해졌다면 다중소유 오귀속이 되살아난다"
    )

    # (b) 남의 owner 도 마찬가지 (내 슬롯을 남이 못 바꾼다)
    state_mgr.change_stock_state(CODE, StockState.POSITIONED, "타전략", strategy=OTHER_FOLDER_KEY)
    assert stock.state == StockState.BUY_PENDING

    # (c) 올바른 owner — 전이 성공
    state_mgr.change_stock_state(CODE, StockState.POSITIONED, "정상", strategy=CLASS_NAME)
    assert stock.state == StockState.POSITIONED
    assert state_mgr.get_stocks_by_state(StockState.POSITIONED) == [stock]


def test_empty_owner_is_an_exact_key_not_a_wildcard():
    """``""``(무기명)는 버릴 정보가 아니라 **가장 정밀한 키**다.

    ``_find_by_code`` 는 ``if strategy is not None`` 로 필터를 켠다. 호출부에서
    ``or None`` 을 붙이면 ``""`` 가 ``None`` 으로 뭉개져 필터가 **해제**되고,
    무기명 슬롯 대신 삽입순 첫 슬롯(대개 남의 named 슬롯)이 전이된다.
    """
    state_mgr = StockStateManager()
    named = _make_stock(owner=CLASS_NAME, state=StockState.BUY_PENDING)
    anon = _make_stock(owner="", state=StockState.BUY_PENDING)
    state_mgr.register_stock(named)
    state_mgr.register_stock(anon)

    state_mgr.change_stock_state(CODE, StockState.POSITIONED, "무기명 전이", strategy="")

    assert anon.state == StockState.POSITIONED, "무기명 슬롯이 전이되지 않았다"
    assert named.state == StockState.BUY_PENDING, (
        "남의 named 슬롯이 전이됐다 — ``\"\"`` 가 wildcard 로 뭉개졌다(`or None` 재발)"
    )
