import pytest
from core.trading.stock_state_manager import StockStateManager
from core.models import TradingStock, StockState
from utils.korean_time import now_kst


def _mk(stock_code: str, owner: str, state: StockState = StockState.POSITIONED) -> TradingStock:
    ts = TradingStock(
        stock_code=stock_code,
        stock_name=stock_code,
        state=state,
        selected_time=now_kst(),
    )
    ts.owner_strategy_name = owner
    return ts


def test_two_strategies_hold_same_stock_independently():
    mgr = StockStateManager()
    assert mgr.register_stock(_mk("010170", "minervini")) is True
    assert mgr.register_stock(_mk("010170", "rs_leader")) is True
    positioned = mgr.get_stocks_by_state(StockState.POSITIONED)
    owners = sorted(ts.owner_strategy_name for ts in positioned if ts.stock_code == "010170")
    assert owners == ["minervini", "rs_leader"]


def test_same_strategy_same_stock_still_blocked():
    mgr = StockStateManager()
    assert mgr.register_stock(_mk("010170", "minervini")) is True
    assert mgr.register_stock(_mk("010170", "minervini")) is False


def test_get_trading_stock_legacy_fallback_unique():
    mgr = StockStateManager()
    mgr.register_stock(_mk("010170", "minervini"))
    ts = mgr.get_trading_stock("010170")
    assert ts is not None and ts.owner_strategy_name == "minervini"


def test_get_trading_stock_explicit_strategy():
    mgr = StockStateManager()
    mgr.register_stock(_mk("010170", "minervini"))
    mgr.register_stock(_mk("010170", "rs_leader"))
    ts = mgr.get_trading_stock("010170", strategy="rs_leader")
    assert ts is not None and ts.owner_strategy_name == "rs_leader"
