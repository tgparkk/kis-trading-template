"""사이징 두 arm — 사장님 규칙 예시 · 복리 per_stock · 종목당 상한 · 0주."""
from __future__ import annotations

from backtest.concept_axes.ledger8 import sizing as Z


def test_arm_b_examples_from_rule():
    q = Z.arm_b_qty(204_000)
    assert (q.qty, q.basis, q.notional) == (4, Z.BASIS_AMOUNT, 816_000.0)
    q = Z.arm_b_qty(1_078_000)
    assert (q.qty, q.basis, q.notional) == (1, Z.BASIS_ONE_SHARE, 1_078_000.0)


def test_arm_b_boundary_and_missing():
    assert (Z.arm_b_qty(1_000_000).qty, Z.arm_b_qty(1_000_000).basis) == (1, Z.BASIS_AMOUNT)
    assert Z.arm_b_qty(999_999).qty == 1
    assert Z.arm_b_qty(None).blocked and Z.arm_b_qty(0).blocked


def test_arm_a_compounded_per_stock():
    q = Z.arm_a_qty(10_000, 864_374, cap=3_000_000, per_stock_src="log")
    assert q.qty == 86 and q.per_stock == 864_374


def test_arm_a_cap_binds():
    q = Z.arm_a_qty(10_000, 3_337_630, cap=3_000_000)
    assert q.qty == 300 and "상한" in q.note


def test_arm_a_zero_when_price_above_limit():
    q = Z.arm_a_qty(1_097_000, 864_374, cap=3_000_000)
    assert q.blocked and q.qty == 0 and "수량부족" in q.note


def test_arm_a_missing_inputs():
    assert Z.arm_a_qty(None, 1_000_000).blocked
    assert Z.arm_a_qty(10_000, None).blocked
