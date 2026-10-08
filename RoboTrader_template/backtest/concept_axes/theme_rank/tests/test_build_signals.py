from __future__ import annotations

from datetime import date

import pytest

from backtest.concept_axes.theme_rank import build_signals as BS
from backtest.concept_axes.theme_rank import signal as SG

D0, D1 = date(2026, 1, 5), date(2026, 1, 6)
UNI = {f"{i:06d}" for i in range(10)}


def _inputs():
    ex0 = {c: 0.0 for c in UNI}
    ex1 = {c: (0.06 if c in {"000001", "000002"} else 0.0) for c in UNI}
    members = {1: frozenset({"000009", "000001", "000002", "000003"}), 2: frozenset({"000009", "000004"})}
    th = {"000009": frozenset({1, 2})}
    full_members = dict(members) | {3: frozenset({"000009", "000005", "000006"})}
    return BS.Inputs(states={D0: SG.day_state(ex0), D1: SG.day_state(ex1)}, excess={D0: ex0, D1: ex1},
                     raw_r={D0: dict(ex0), D1: {**ex1, "000009": 0.30}},
                     themes_of=th, members=members,
                     themes_of_full={"000009": frozenset({1, 2, 3})}, members_full=full_members,
                     day_codes={D1: frozenset({"000009", "000001", "000777"})},
                     streak_of={(1, D1): 1, (2, D1): 0})


def test_compute_rows_primary_and_print_items():
    row = BS.compute_rows([(D1, "000009")], _inputs())[0]
    expect = -SG.log10_binom_tail(3, 0.2, 2) - __import__("math").log10(2)
    assert row["s"] == pytest.approx(expect) and row["m"] == 2 and row["main_theme"] == 1
    assert row["single"] is False and row["s_input_ok"] is True
    assert row["c_same_theme"] == 1 and row["b_rank_in_theme"] == 3 and row["b_limit_up"] is True
    assert row["a2_streak"] == 1 and row["a_mean_excess"] == pytest.approx(0.04)
    assert row["s_full"] == pytest.approx(-SG.log10_binom_tail(3, 0.2, 2) - __import__("math").log10(3))


def test_compute_rows_missing_day_state_marks_input_not_ok():
    row = BS.compute_rows([(date(2026, 1, 7), "000009")], _inputs())[0]
    assert row["s_input_ok"] is False and row["s"] == "" and row["main_theme"] == ""


def test_primary_s_matches_compute_rows():
    inp = _inputs()
    assert BS.primary_s([(D1, "000009"), (D0, "000009")], inp.states, inp.themes_of, inp.members) == [
        pytest.approx(BS.compute_rows([(D1, "000009")], inp)[0]["s"]), 0.0]
