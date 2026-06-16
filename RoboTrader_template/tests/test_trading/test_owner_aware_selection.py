"""두 번째 벽: add_selected_stock owner-aware 등록 검증.

전략별 자본이 독립이므로, 두 전략이 같은 종목을 선정하면 각자 자기 소유의
TradingStock 인스턴스를 등록해야 한다(과거엔 종목코드 dedup으로 2번째 전략이
등록되지 못했다).
"""
import pytest
from unittest.mock import AsyncMock, MagicMock

from core.trading.order_execution import OrderExecution
from core.trading.stock_state_manager import StockStateManager
from core.models import StockState


def _make_exec():
    state_mgr = StockStateManager()
    intraday = MagicMock()
    intraday.add_selected_stock = AsyncMock(return_value=True)
    data_collector = MagicMock()
    data_collector.add_candidate_stock = MagicMock()
    order_mgr = MagicMock()
    ex = OrderExecution(state_mgr, intraday, data_collector, order_mgr)
    return ex, state_mgr


@pytest.mark.asyncio
async def test_two_strategies_register_same_stock_independently():
    ex, state_mgr = _make_exec()

    ok1 = await ex.add_selected_stock("010170", "X", "minv 후보", owner_strategy="minervini")
    ok2 = await ex.add_selected_stock("010170", "X", "rs 후보", owner_strategy="rs_leader")

    assert ok1 is True and ok2 is True
    minv = state_mgr.get_trading_stock("010170", strategy="minervini")
    rs = state_mgr.get_trading_stock("010170", strategy="rs_leader")
    assert minv is not None and minv.owner_strategy_name == "minervini"
    assert rs is not None and rs.owner_strategy_name == "rs_leader"
    assert minv is not rs  # 서로 다른 인스턴스


@pytest.mark.asyncio
async def test_same_strategy_same_stock_not_duplicated():
    ex, state_mgr = _make_exec()

    await ex.add_selected_stock("010170", "X", "1차", owner_strategy="minervini")
    await ex.add_selected_stock("010170", "X", "2차", owner_strategy="minervini")

    # 동일 전략은 단일 인스턴스만 유지 (이미 관리 중)
    minv_all = [
        ts for ts in state_mgr.get_stocks_by_state(StockState.SELECTED)
        if ts.stock_code == "010170" and ts.owner_strategy_name == "minervini"
    ]
    assert len(minv_all) == 1
