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


def test_characterization_single_key_blocks_second_owner():
    """[특성화] 현재 구현: 동일 종목 2번째 POSITIONED 등록은 거부된다.

    이 테스트는 Phase 2에서 의도적으로 반대로 바뀐다(독립 허용).
    지금은 현재 동작을 못박아 회귀 기준점을 만든다.
    """
    mgr = StockStateManager()
    assert mgr.register_stock(_mk("010170", "minervini")) is True
    assert mgr.register_stock(_mk("010170", "rs_leader")) is False
