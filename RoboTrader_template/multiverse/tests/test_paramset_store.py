"""Phase 6 — composable_paramset 테이블 영속성 통합 테스트."""
from __future__ import annotations

import pytest

from RoboTrader_template.multiverse.persistence import (
    save_paramset,
    load_paramset,
    exists_paramset,
    delete_paramset,
)


@pytest.fixture
def cleanup_test_paramset(valid_paramset):
    """save 후 테스트 끝나면 delete."""
    yield valid_paramset
    try:
        delete_paramset(valid_paramset.paramset_id())
    except Exception:
        pass


def test_save_and_load_roundtrip(cleanup_test_paramset):
    """저장 후 불러오면 동일한 ParamSet이어야 한다."""
    save_paramset(cleanup_test_paramset)
    loaded = load_paramset(cleanup_test_paramset.paramset_id())
    assert loaded == cleanup_test_paramset


def test_save_idempotent(cleanup_test_paramset):
    """같은 ParamSet 두 번 저장해도 충돌 없음 (ON CONFLICT DO NOTHING)."""
    save_paramset(cleanup_test_paramset)
    save_paramset(cleanup_test_paramset)  # 두 번째: 무시
    assert exists_paramset(cleanup_test_paramset.paramset_id())


def test_exists_paramset_false_for_unknown():
    """존재하지 않는 ID는 False 반환."""
    assert exists_paramset("NONEXISTENT_FAKE_ID_xyz") is False


def test_load_returns_none_for_unknown():
    """존재하지 않는 ID는 None 반환."""
    assert load_paramset("NONEXISTENT_FAKE_ID_xyz") is None
