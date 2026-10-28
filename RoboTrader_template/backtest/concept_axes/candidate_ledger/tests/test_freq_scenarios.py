"""매수 빈도 시나리오 산수 단위 테스트 — 합성 데이터 · DB 없음.

DESIGN.md(freq_scenarios) §테스트: 자리 반환 규약(exit_date 당일엔 아직 차 있음 · 다음 거래일 빔) ·
하루 상한 N 이 rank 순으로 자름 · 중복 거부 · 비용 산술 손계산 1건 · 필요 자금 = 최대 동시 보유 × 100만.
"""
from __future__ import annotations

import hashlib

import pandas as pd
import pytest

from backtest.concept_axes.candidate_ledger.freq_scenarios import run_freq as F

CAL = [f"2024-01-{d:02d}" for d in range(2, 12)]              # 10 거래일(합성 · 주말 무시)
CAL_IDX = {d: i for i, d in enumerate(CAL)}


def _row(strategy="s", stock_code="A", rank=1, entry_date=CAL[0], exit_date=CAL[0], exit_reason="tp",
        ret_pct=0.0, pnl_won=0.0, notional=1_000_000) -> dict:
    return dict(strategy=strategy, stock_code=stock_code, rank=rank, entry_date=entry_date,
               exit_date=exit_date, exit_reason=exit_reason, ret_pct=ret_pct, pnl_won=pnl_won,
               notional=notional)


def _l0(rows: list) -> pd.DataFrame:
    return pd.DataFrame(rows)


# ── 자리 반환 규약 ───────────────────────────────────────────────────────────
def test_release_timing_still_held_on_exit_day_then_freed_next_day():
    l0 = _l0([_row(entry_date=CAL[0], exit_date=CAL[2], exit_reason="sl")])
    l0p = F.prep_l0(l0, CAL_IDX, len(CAL))
    assert l0p.loc[0, "_entry_idx"] == 0
    assert l0p.loc[0, "_release_idx"] == 3            # exit_idx(2) + 1

    selected, levels = F.simulate_capped(l0p, len(CAL), n_cap=None, k_cap=None)
    assert len(selected) == 1
    assert levels[0] == 1 and levels[1] == 1 and levels[2] == 1      # 청산일 당일엔 아직 자리 차지
    assert levels[3] == 0                                            # 다음 거래일부터 빔
    assert levels[9] == 0


def test_open_lot_occupies_till_window_end():
    l0 = _l0([_row(entry_date=CAL[7], exit_date=CAL[7], exit_reason="open")])
    l0p = F.prep_l0(l0, CAL_IDX, len(CAL))
    assert l0p.loc[0, "_release_idx"] == len(CAL)      # 창 안에서는 절대 안 빔
    _, levels = F.simulate_capped(l0p, len(CAL), n_cap=None, k_cap=None)
    assert levels[7] == 1 and levels[8] == 1 and levels[9] == 1


# ── 하루 상한 N 이 rank 순으로 자름 ───────────────────────────────────────────
def test_daily_cap_cuts_by_rank():
    rows = [_row(stock_code=c, rank=r, entry_date=CAL[0], exit_date=CAL[1], exit_reason="tp")
            for c, r in zip(["A", "B", "C"], [1, 2, 3])]
    l0p = F.prep_l0(_l0(rows), CAL_IDX, len(CAL))
    selected, _ = F.simulate_capped(l0p, len(CAL), n_cap=2, k_cap=None)
    assert set(selected["stock_code"]) == {"A", "B"}
    assert len(selected) == 2


def test_daily_cap_independent_of_k_when_k_not_binding():
    rows = [_row(stock_code=c, rank=r, entry_date=CAL[0], exit_date=CAL[1], exit_reason="tp")
            for c, r in zip(["A", "B", "C", "D"], [1, 2, 3, 4])]
    l0p = F.prep_l0(_l0(rows), CAL_IDX, len(CAL))
    selected, _ = F.simulate_capped(l0p, len(CAL), n_cap=3, k_cap=10)
    assert set(selected["stock_code"]) == {"A", "B", "C"}


# ── 중복 거부 ────────────────────────────────────────────────────────────────
def test_duplicate_same_stock_rejected_while_held_then_allowed_after_release():
    rows = [
        _row(stock_code="A", rank=1, entry_date=CAL[0], exit_date=CAL[2], exit_reason="sl"),  # rel=3
        _row(stock_code="A", rank=1, entry_date=CAL[1], exit_date=CAL[4], exit_reason="tp"),  # 보유중 → 거부
        _row(stock_code="A", rank=1, entry_date=CAL[3], exit_date=CAL[5], exit_reason="tp"),  # 3일에 재매수 가능
    ]
    l0p = F.prep_l0(_l0(rows), CAL_IDX, len(CAL))
    selected, levels = F.simulate_capped(l0p, len(CAL), n_cap=None, k_cap=None)
    assert len(selected) == 2
    assert set(selected["entry_date"]) == {CAL[0], CAL[3]}
    assert levels[1] == 1                              # 둘째 후보는 거부됐으니 보유 수 그대로


def test_k_cap_blocks_new_buy_when_full():
    rows = [
        _row(stock_code="A", rank=1, entry_date=CAL[0], exit_date=CAL[5], exit_reason="tp"),
        _row(stock_code="B", rank=1, entry_date=CAL[1], exit_date=CAL[5], exit_reason="tp"),
    ]
    l0p = F.prep_l0(_l0(rows), CAL_IDX, len(CAL))
    selected, levels = F.simulate_capped(l0p, len(CAL), n_cap=None, k_cap=1)
    assert len(selected) == 1 and selected.iloc[0]["stock_code"] == "A"
    assert levels[1] == 1


# ── 비용 산술 손계산 ─────────────────────────────────────────────────────────
def test_cost_arithmetic_hand_calc_and_open_excluded_from_financials():
    rows = [
        _row(stock_code="A", entry_date=CAL[0], exit_date=CAL[1], exit_reason="tp",
            ret_pct=5.0, pnl_won=50_000, notional=1_000_000),
        _row(stock_code="B", entry_date=CAL[0], exit_date=CAL[0], exit_reason="open",
            ret_pct=999.0, pnl_won=999_999, notional=1_000_000),   # open → 재무 지표에서 빠져야 함
    ]
    l0p = F.prep_l0(_l0(rows), CAL_IDX, len(CAL))
    selected, levels = F.simulate_capped(l0p, len(CAL), n_cap=None, k_cap=None)
    m = F.compute_metrics(selected, CAL_IDX, list(range(len(CAL))), levels)
    assert m["n_buys_completed"] == 1 and m["n_open"] == 1
    assert m["gross_won"] == 50_000                      # open 의 999,999 은 안 들어감
    assert m["cost_won"] == 2_500                         # 1,000,000 × 0.25%
    assert m["net_won"] == 47_500
    assert m["net_per_lot_won"] == 47_500
    assert m["win_rate"] == 1.0


# ── 필요 자금 = 최대 동시 보유 × 100만 ───────────────────────────────────────
def test_capital_needed_equals_max_concurrent_times_1m():
    rows = [_row(stock_code=c, rank=1, entry_date=CAL[0], exit_date=CAL[5], exit_reason="tp")
            for c in ["A", "B", "C"]]
    l0p = F.prep_l0(_l0(rows), CAL_IDX, len(CAL))
    selected, levels = F.simulate_capped(l0p, len(CAL), n_cap=None, k_cap=None)
    m = F.compute_metrics(selected, CAL_IDX, list(range(len(CAL))), levels)
    assert m["max_concurrent"] == 3
    assert m["capital_needed_won"] == 3_000_000


def test_uncapped_reference_r_counts_overlap_without_dedup():
    rows = [
        _row(stock_code="A", entry_date=CAL[0], exit_date=CAL[2], exit_reason="tp"),
        _row(stock_code="A", entry_date=CAL[0], exit_date=CAL[2], exit_reason="tp"),  # 같은 종목·같은 날 중복
    ]
    l0p = F.prep_l0(_l0(rows), CAL_IDX, len(CAL))
    selected, levels = F.simulate_uncapped(l0p, len(CAL))
    assert len(selected) == 2                             # R = 중복 거부 없음(로트 독립)
    assert levels[0] == 2 and levels[3] == 0


# ── 버킷·달력 ────────────────────────────────────────────────────────────────
def test_bucket_years_splits_by_calendar_year():
    cal = ["2024-12-30", "2024-12-31", "2025-01-02", "2025-01-03"]
    b = F.bucket_years(cal)
    assert b["전체"] == [0, 1, 2, 3]
    assert b["2024"] == [0, 1] and b["2025"] == [2, 3]


# ── md5 가드 ─────────────────────────────────────────────────────────────────
def test_load_ledger_raises_on_md5_mismatch(tmp_path):
    p = tmp_path / "ledger.csv"
    p.write_text("strategy,scan_date\nabc,2024-01-01\n", encoding="utf-8")
    got = hashlib.md5(p.read_bytes()).hexdigest()
    with pytest.raises(SystemExit):
        F.load_ledger(p, expect="0" * 32 if got != "0" * 32 else "1" * 32)
