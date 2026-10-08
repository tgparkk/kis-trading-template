from __future__ import annotations

import pandas as pd
import pytest

from backtest.concept_axes.theme_rank import slots as SL


def L(day, code, rel, ret, rank, sig, theme=None):
    return SL.Lot(day, code, rel, ret, rank, sig, theme)


def test_baseline_path_rank_order_daily_cap_and_slots():
    lots = {0: [L(0, "A", 5, 1.0, 1, 0.0), L(0, "B", 5, 2.0, 2, 0.0), L(0, "C", 5, 3.0, 3, 0.0)],
            1: [L(1, "D", 5, 4.0, 1, 0.0)]}
    buys, held = SL.baseline_path(lots, 3, n_cap=2, k_cap=3)
    assert [l.code for l in buys[0]] == ["A", "B"]           # 하루 2
    assert [l.code for l in buys[1]] == ["D"]                # 자리 3 중 2 사용 → 1 남음
    assert held[1] == frozenset({"A", "B"})


def test_held_stock_skipped_in_both_arms():
    lots = {0: [L(0, "A", 3, 1.0, 1, 0.0)],
            1: [L(1, "A", 4, 9.0, 1, 5.0), L(1, "B", 4, 2.0, 2, 1.0), L(1, "C", 4, 3.0, 3, 2.0)]}
    buys, held = SL.baseline_path(lots, 2, n_cap=1, k_cap=10)
    assert [l.code for l in buys[1]] == ["B"]                 # A 는 보유 중
    cmp_ = SL.paired(lots, buys, held)
    d1 = [c for c in cmp_ if c.day == 1][0]
    assert d1.f == 1 and d1.theme == 3.0 and d1.base == 2.0  # 테마 쪽도 A 를 건너뛰고 C(sig 2) 선택
    assert d1.arena == pytest.approx(2.5) and d1.n_eligible == 2


def test_pick_descending_ties_by_rank_and_theme_cap():
    el = [L(0, "A", 9, 0, 3, 1.0, 7), L(0, "B", 9, 0, 1, 1.0, 7), L(0, "C", 9, 0, 2, 0.5, 7), L(0, "D", 9, 0, 4, 0.1, 8)]
    assert [l.code for l in SL.pick(el, 3)] == ["B", "A", "C"]
    assert [l.code for l in SL.pick(el, 3, cap_per_theme=2)] == ["B", "A", "D"]
    assert [l.code for l in SL.pick(el, 2, descending=False)] == ["D", "C"]


def test_summarize_weights_by_f():
    cmps = [SL.DayCmp(0, 1, 1.0, 3.0, 2.0, 4, 1), SL.DayCmp(1, 3, 0.0, 1.0, 1.0, 5, 2)]
    s = SL.summarize(cmps)
    assert s["R_base"] == pytest.approx(0.25) and s["R_theme"] == pytest.approx(1.5) and s["R_arena"] == pytest.approx(1.25)
    assert s["d_cur"] == pytest.approx(1.0) and s["d_theme"] == pytest.approx(0.25)
    assert s["n_days"] == 2 and s["n_lots"] == 4


def test_lots_from_release_rules():
    cal = ["2026-01-02", "2026-01-05", "2026-01-06", "2026-01-07"]
    df = pd.DataFrame({"scan_date": ["2026-01-02", "2026-01-02"], "stock_code": ["000001", "000002"],
                       "rank": [1, 2], "entry_date": ["2026-01-05", "2026-01-05"],
                       "exit_date": ["2026-01-06", "2026-01-07"], "exit_reason": ["tp", "open"],
                       "ret_net": [9.75, 1.0], "s": [1.0, 0.0], "main_theme": [7.0, None]})
    by = SL.lots_from(df, cal)
    a, b = by[1]
    assert (a.release, b.release) == (3, 4)                   # 청산 다음 날 / open = 창 끝
    assert a.main_theme == 7 and b.main_theme is None
