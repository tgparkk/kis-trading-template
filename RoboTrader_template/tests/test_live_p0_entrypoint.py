"""실전 복원 진입점을 실제로 돌려 호출 «순서»를 단언한다.

소스 문자열 단언은 죽은 경로에서도 통과한 전례가 있다(재사용 규칙, 08-12).
스펙 테스트 14(진입점 순서)·15(라이브 불변 — 페이퍼 복원은 실전 브로커 API 를
건드리지 않는다)를 실호출로 고정한다.

2026-08-14 최종 리뷰(Critical C1 / Important I1) — 아래 두 테스트군을 추가한다.
바깥 `except Exception` 두 곳(`state_restorer.restore_todays_candidates`,
`initializer.initialize_system`)이 안쪽에서 올라오는 `LiveStartupAbort` 를
삼켜 로그 한 줄로 뭉갰다: 실전에서 abort 가 프로세스를 못 멈췄다는 뜻이다.
여기서는 **진입점을 실호출**해 abort 가 그 두 겹을 뚫고 밖으로 전파되는지
고정한다 — 안쪽 단위 테스트(`test_live_p0_restore.py`·`test_live_p0_fund_init.py`)
는 `_restore_holdings_from_real_account()`/`_initialize_fund_manager()` 를 직접
불러 이 겹을 우회하므로 재발을 못 잡는다.
"""
import asyncio
from datetime import timedelta
from unittest.mock import AsyncMock, Mock

import pandas as pd
import pytest

from bot.initializer import BotInitializer
from tests.broker_contract import make_account_balance
from tests.test_live_p0_restore import _real_broker_mock, _restorer_with
from tests.test_state_restorer_live_real_table import _holdings_df
from utils.exceptions import LiveStartupAbort
from utils.korean_time import now_kst


def test_real_restore_call_order_cancel_then_balance_then_holdings():
    """스펙 테스트 14: 실전 복원은 «미체결 취소 → 잔고 요약 → 보유 목록» 순서로 돈다."""
    calls = []
    broker = Mock()
    broker.get_pending_orders.side_effect = lambda: calls.append('pending') or []
    broker.get_account_balance.side_effect = (
        lambda: calls.append('balance') or make_account_balance())
    broker.get_holdings.side_effect = lambda: calls.append('holdings') or []
    db = Mock()
    db.get_real_open_positions.return_value = pd.DataFrame()  # 불일치 0 상태로 순서만 관찰
    r = _restorer_with(db, broker, Mock())
    asyncio.run(r._restore_holdings_from_real_account())
    assert calls[0] == 'pending', f"미체결 취소가 첫 단계가 아니다: {calls}"
    assert calls.index('balance') < calls.index('holdings')


def test_paper_restore_never_touches_real_broker_apis():
    """스펙 테스트 15(라이브 불변): 페이퍼 복원은 실전용 브로커 API 를 호출하지 않는다."""
    from tests.test_state_restorer_live_real_table import _make_restorer, _wire_trading_manager
    broker = Mock()
    db = Mock()
    db.get_virtual_open_positions.return_value = pd.DataFrame()
    r = _make_restorer(db, strategies={}, paper_trading=True, broker=broker)
    _wire_trading_manager(r)
    asyncio.run(r._restore_holdings_from_db())
    broker.get_pending_orders.assert_not_called()
    broker.get_holdings.assert_not_called()
    broker.get_account_balance.assert_not_called()
    broker.cancel_order.assert_not_called()


# ============================================================================
# C1/I1 재발 방지 — abort 가 진입점 밖으로 실제로 전파되는지
# ============================================================================

def _entrypoint_restorer(db, broker, strat=None):
    """restore_todays_candidates() 진입점 테스트용 restorer.

    `_restore_candidates`(후보 종목 DB 조회)는 이 테스트군의 관심사가 아니므로
    mock 으로 무해화한다 — 보유 종목 복원(`_restore_holdings_from_real_account`)
    경로에서 올라오는 LiveStartupAbort 가 `restore_todays_candidates()` 의 바깥
    except 를 뚫고 나오는지만 본다.
    """
    r = _restorer_with(db, broker, strat or Mock())
    r._restore_candidates = AsyncMock()
    return r


def test_restore_todays_candidates_propagates_abort_on_mismatch():
    """(a) 계좌-DB 불일치 시나리오: LiveStartupAbort 가 restore_todays_candidates()
    밖으로 전파된다.

    수정 전에는 `restore_todays_candidates` 의 바깥 `except Exception` 이
    LiveStartupAbort 까지 삼켜 "❌ 종목 복원 실패" 로그 한 줄로 뭉개고 정상
    반환했다 — 실전에서 대사 불일치가 나도 프로세스가 멈추지 않았다는 뜻이다.
    """
    buy_time = now_kst() - timedelta(days=5)
    db = Mock()
    db.get_real_open_positions.return_value = _holdings_df(buy_time)  # DB 1종목
    broker = _real_broker_mock([])                                    # 실계좌 0종목 → 불일치
    r = _entrypoint_restorer(db, broker)

    with pytest.raises(LiveStartupAbort):
        asyncio.run(r.restore_todays_candidates())


def test_restore_todays_candidates_propagates_abort_on_pending_orders_query_failure():
    """(b) 미체결 조회 실패 시나리오: LiveStartupAbort 가 restore_todays_candidates()
    밖으로 전파된다.

    `get_pending_orders()` 가 None 을 반환하면 `_cancel_all_pending_orders_on_startup`
    이 복원 절차의 «첫 단계»에서 LiveStartupAbort 를 던진다(2026-08-14 P0 결정 6).
    이 테스트는 그 abort 가 두 겹(`_restore_holdings_from_real_account` 의
    `except LiveStartupAbort: raise` → `restore_todays_candidates` 의 바깥 except)을
    뚫고 나오는지를 진입점 실호출로 고정한다.
    """
    db = Mock()
    db.get_real_open_positions.return_value = pd.DataFrame()
    broker = Mock()
    broker.get_pending_orders.return_value = None  # 조회 실패
    r = _entrypoint_restorer(db, broker)

    with pytest.raises(LiveStartupAbort):
        asyncio.run(r.restore_todays_candidates())


def test_initialize_system_propagates_abort_not_return_false(monkeypatch):
    """initialize_system() 은 실전 자금 상한 미설정 시 False 를 반환하지 않고
    LiveStartupAbort 를 전파해야 한다.

    수정 전에는 `initialize_system` 의 바깥 `except Exception` 이 이 abort 를
    삼켜 "시스템 초기화 실패" 로그 후 `return False` 로 뭉갰다 — main.py 의
    전용 핸들러(텔레그램 경보 + `sys.exit(2)`) 대신 `sys.exit(1)` 무경보 경로를
    타게 된다는 뜻이다. 브로커 연결·텔레그램 초기화 등 앞 단계는 Mock 으로
    통과시키고(`test_live_p0_fund_init.py`·`test_live_p0_shutdown.py` 방식),
    `MarketHours`/`get_market_status` 는 실제 홀리데이 캐시/네트워크를 건드리지
    않도록 스텁한다(`tests/bot/test_regime_config_crosscheck.py` 방식).
    """
    import types
    import bot.initializer as initializer_mod

    monkeypatch.setattr(
        initializer_mod, "MarketHours",
        types.SimpleNamespace(get_today_info=lambda market='KRX': f"[{market}] stub"),
    )
    monkeypatch.setattr(initializer_mod, "get_market_status", lambda: "pre_market")

    bot = Mock()
    bot.broker.connect = AsyncMock(return_value=True)
    bot.telegram.initialize = AsyncMock(return_value=True)
    bot.decision_engine.is_virtual_mode = False  # 실전 분기
    bot.config.real_total_funds_cap = None       # cap 미설정 → LiveStartupAbort(결정 1)
    init = BotInitializer(bot)

    with pytest.raises(LiveStartupAbort):
        asyncio.run(init.initialize_system())

    bot.state_restoration_helper.restore_todays_candidates.assert_not_called()
