"""Phase 6 — composable_position 테이블 영속성 통합 테스트."""
from __future__ import annotations

import pytest

from RoboTrader_template.multiverse.persistence import (
    save_paramset,
    delete_paramset,
    save_position,
    load_all,
    load_by_symbol,
    delete_position,
    update_held_days,
    update_lock_step,
    update_pending_scale_qty,
)

_TEST_SYMBOL = "TEST_005930"


@pytest.fixture
def saved_paramset(valid_paramset):
    """ParamSet을 DB에 저장해 두고, 테스트 후 cleanup."""
    save_paramset(valid_paramset)
    yield valid_paramset
    # 포지션 먼저 삭제 (FK 제약)
    for p in load_by_symbol(_TEST_SYMBOL):
        delete_position(p.symbol, p.paramset_id)
    delete_paramset(valid_paramset.paramset_id())


def test_save_and_load_position(saved_paramset):
    """포지션 저장 후 불러오면 필드가 일치해야 한다."""
    save_position(
        symbol=_TEST_SYMBOL,
        paramset_id=saved_paramset.paramset_id(),
        entry_price=70000.0,
        atr_at_entry=1500.0,
        lock_step=1,
        held_days=3,
        entry_signal={"reason": "trend_align + breakout"},
        pending_scale_qty=5.0,
    )
    positions = load_by_symbol(_TEST_SYMBOL)
    assert len(positions) == 1
    p = positions[0]
    assert p.entry_price == 70000.0
    assert p.lock_step == 1
    assert p.held_days == 3
    assert p.pending_scale_qty == 5.0
    assert p.entry_signal_json == {"reason": "trend_align + breakout"}


def test_upsert_updates_existing(saved_paramset):
    """같은 (symbol, paramset_id) 다시 save → 기존 행 갱신."""
    save_position(
        symbol=_TEST_SYMBOL,
        paramset_id=saved_paramset.paramset_id(),
        entry_price=70000.0,
    )
    save_position(
        symbol=_TEST_SYMBOL,
        paramset_id=saved_paramset.paramset_id(),
        entry_price=72000.0,
        lock_step=2,
    )
    positions = load_by_symbol(_TEST_SYMBOL)
    assert len(positions) == 1
    assert positions[0].entry_price == 72000.0
    assert positions[0].lock_step == 2


def test_update_held_days(saved_paramset):
    """update_held_days 후 held_days 값이 갱신된다."""
    save_position(
        symbol=_TEST_SYMBOL,
        paramset_id=saved_paramset.paramset_id(),
        entry_price=70000.0,
    )
    update_held_days(_TEST_SYMBOL, saved_paramset.paramset_id(), 7)
    positions = load_by_symbol(_TEST_SYMBOL)
    assert positions[0].held_days == 7


def test_update_lock_step(saved_paramset):
    """update_lock_step 후 lock_step 값이 갱신된다."""
    save_position(
        symbol=_TEST_SYMBOL,
        paramset_id=saved_paramset.paramset_id(),
        entry_price=70000.0,
    )
    update_lock_step(_TEST_SYMBOL, saved_paramset.paramset_id(), 2)
    positions = load_by_symbol(_TEST_SYMBOL)
    assert positions[0].lock_step == 2


def test_delete_position(saved_paramset):
    """delete_position 후 조회 결과가 빈 리스트여야 한다."""
    save_position(
        symbol=_TEST_SYMBOL,
        paramset_id=saved_paramset.paramset_id(),
        entry_price=70000.0,
    )
    assert delete_position(_TEST_SYMBOL, saved_paramset.paramset_id()) is True
    assert load_by_symbol(_TEST_SYMBOL) == []
