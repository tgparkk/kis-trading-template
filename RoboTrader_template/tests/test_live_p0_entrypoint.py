"""실전 복원 진입점을 실제로 돌려 호출 «순서»를 단언한다.

소스 문자열 단언은 죽은 경로에서도 통과한 전례가 있다(재사용 규칙, 08-12).
스펙 테스트 14(진입점 순서)·15(라이브 불변 — 페이퍼 복원은 실전 브로커 API 를
건드리지 않는다)를 실호출로 고정한다.
"""
import asyncio
from unittest.mock import Mock

import pandas as pd

from tests.broker_contract import make_account_balance
from tests.test_live_p0_restore import _restorer_with


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
