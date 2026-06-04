import pytest
from runners._adapter_factory import build_adapter

ACTIVE = [
    "elder_ema_pullback", "minervini_volume_dryup",
    "book_pullback_ma20", "book_pullback_ma5", "daytrading_3methods_breakout",
]

@pytest.mark.parametrize("name", ACTIVE)
def test_build_adapter_for_active_strategies(name):
    a = build_adapter(name)
    assert a is not None
    assert a.strategy_name == name
