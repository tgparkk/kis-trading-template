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


def test_owner_set_after_register_then_change_state():
    """라이프사이클 패턴: owner 없이 등록(SELECTED) → 나중에 owner 설정 →
    change_stock_state(strategy=owner)가 정상 전이되어야 한다.

    복원(state_restorer)·매수후 매도 경로의 실제 시퀀스. 가변 owner를 키에
    쓰면 키가 stale해져 전이가 no-op이 되는 버그를 막는다.
    """
    mgr = StockStateManager()
    ts = _mk("010170", "", state=StockState.SELECTED)
    assert mgr.register_stock(ts) is True
    # owner를 등록 후에 설정 (add_selected_stock → 이후 owner 주입 패턴)
    ts.owner_strategy_name = "minervini"
    mgr.change_stock_state("010170", StockState.POSITIONED, "DB 복원", strategy="minervini")
    assert ts.state == StockState.POSITIONED
    positioned = mgr.get_stocks_by_state(StockState.POSITIONED)
    assert any(t is ts for t in positioned)
    # 인덱스 일관성: SELECTED 잔존물 없어야 함
    selected = mgr.get_stocks_by_state(StockState.SELECTED)
    assert all(t.stock_code != "010170" for t in selected)


def test_change_state_index_consistency_after_owner_change():
    """owner 변경 후 상태전이를 반복해도 stocks_by_state 인덱스가
    trading_stocks와 일관성을 유지해야 한다."""
    mgr = StockStateManager()
    ts = _mk("005930", "", state=StockState.SELECTED)
    mgr.register_stock(ts)
    ts.owner_strategy_name = "elder"
    mgr.change_stock_state("005930", StockState.BUY_PENDING, "", strategy="elder")
    mgr.change_stock_state("005930", StockState.POSITIONED, "", strategy="elder")
    # 단 하나의 POSITIONED, 다른 상태엔 잔존 없음
    assert len(mgr.get_stocks_by_state(StockState.POSITIONED)) == 1
    assert len(mgr.get_stocks_by_state(StockState.SELECTED)) == 0
    assert len(mgr.get_stocks_by_state(StockState.BUY_PENDING)) == 0
