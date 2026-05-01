"""Phase 6 — 봇 재시작 시 상태 복원 통합 테스트."""
from __future__ import annotations

import pytest

from RoboTrader_template.multiverse.persistence import (
    save_paramset,
    save_position,
    restore_all,
    delete_paramset,
    delete_position,
    is_conservative_mode,
)

_TEST_SYMBOL = "TEST_005930"


@pytest.fixture
def setup_state(valid_paramset):
    """paramset 저장 + 포지션 1개 저장."""
    save_paramset(valid_paramset)
    save_position(
        symbol=_TEST_SYMBOL,
        paramset_id=valid_paramset.paramset_id(),
        entry_price=70000.0,
        held_days=2,
    )
    yield valid_paramset
    delete_position(_TEST_SYMBOL, valid_paramset.paramset_id())
    delete_paramset(valid_paramset.paramset_id())


def test_restore_all_loads_paramset_and_positions(setup_state):
    """restore_all이 paramset과 포지션을 모두 복원해야 한다."""
    states, strategies = restore_all()
    assert setup_state.paramset_id() in states
    state = states[setup_state.paramset_id()]
    assert state.paramset == setup_state
    assert len(state.positions) == 1
    assert state.positions[0].symbol == _TEST_SYMBOL
    assert state.config_hash_drift is False


def test_restore_with_strategy_factory(setup_state):
    """factory 제공 시 strategies dict에도 인스턴스가 반환된다."""
    from unittest.mock import MagicMock

    mock_strategy = MagicMock()
    factory = MagicMock(return_value=mock_strategy)

    states, strategies = restore_all(strategy_factory=factory)

    assert setup_state.paramset_id() in strategies
    factory.assert_called_once_with(setup_state)
    assert strategies[setup_state.paramset_id()] is mock_strategy


def test_is_conservative_mode_false_by_default(setup_state):
    """정상 paramset은 보수적 청산 모드가 False여야 한다."""
    states, _ = restore_all()
    state = states[setup_state.paramset_id()]
    assert is_conservative_mode(state) is False
