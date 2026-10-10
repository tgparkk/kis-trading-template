from datetime import date, timedelta
from types import SimpleNamespace

import numpy as np

from backtest.concept_axes.dt_dart_filter import lots as L
from backtest.concept_axes.ledger8 import exitsim8 as X

CAL = [date(2022, 1, 3) + timedelta(days=i) for i in range(30)]   # 합성 달력(연속일)


def _env(bars):
    idx = {d: i for i, d in enumerate(CAL)}
    return SimpleNamespace(cal=CAL, cal_idx=idx, bad_open=set(), bars=lambda code: bars,
                           next_day=lambda d: CAL[idx[d] + 1] if idx.get(d, -9) + 1 < len(CAL) else None)


def _flat(d, p):
    return X.Bar(d, p, p, p, p)


def test_open_fill_then_take_profit():
    bars = {CAL[0]: _flat(CAL[0], 100.0), CAL[1]: X.Bar(CAL[1], 101.0, 102.0, 100.0, 101.0),
            CAL[2]: X.Bar(CAL[2], 101.0, 112.0, 100.0, 110.0)}
    r = L.simulate_candidate(_env(bars), "1", CAL[0], set())
    assert r["status"] == "filled" and r["fill"] == "open" and r["entry_price"] == 101.0
    assert r["exit_reason"] == "tp" and round(r["ret_sl"], 6) == 10.0 and r["ret_tp"] == r["ret_sl"]


def test_band_touch_fill_at_upper():
    bars = {CAL[0]: _flat(CAL[0], 100.0), CAL[1]: X.Bar(CAL[1], 104.0, 105.0, 102.5, 103.0)}
    for d in CAL[2:]:
        bars[d] = _flat(d, 103.0)
    r = L.simulate_candidate(_env(bars), "1", CAL[0], set())
    assert r["fill"] == "band_touch" and abs(r["entry_price"] - 103.0) < 1e-9


def test_no_fill_when_gap_above_band_all_day():
    bars = {CAL[0]: _flat(CAL[0], 100.0), CAL[1]: X.Bar(CAL[1], 106.0, 108.0, 104.0, 107.0)}
    assert L.simulate_candidate(_env(bars), "1", CAL[0], set())["status"] == "no_fill"


def test_halt_on_entry_day_is_halt_entry():
    bars = {CAL[0]: _flat(CAL[0], 100.0), CAL[1]: _flat(CAL[1], 100.0)}
    assert L.simulate_candidate(_env(bars), "1", CAL[0], {CAL[1]})["status"] == "halt_entry"


def test_same_bar_both_touch_gives_two_rules():
    bars = {CAL[0]: _flat(CAL[0], 100.0), CAL[1]: _flat(CAL[1], 100.0),
            CAL[2]: X.Bar(CAL[2], 100.0, 111.0, 89.0, 100.0)}
    r = L.simulate_candidate(_env(bars), "1", CAL[0], set())
    assert r["both"] and round(r["ret_sl"], 6) == -10.0 and round(r["ret_tp"], 6) == 10.0


def test_halt_days_removed_from_path_exit_at_resume_open():
    bars = {CAL[0]: _flat(CAL[0], 100.0), CAL[1]: _flat(CAL[1], 100.0)}
    for d in CAL[2:5]:
        bars[d] = _flat(d, 100.0)                       # 정지 평평봉(거래량 0) — 경로에서 빠져야 한다
    bars[CAL[5]] = X.Bar(CAL[5], 70.0, 72.0, 68.0, 71.0)  # 재개 첫 봉 갭 하락
    r = L.simulate_candidate(_env(bars), "1", CAL[0], {CAL[2], CAL[3], CAL[4]})
    assert r["exit_reason"] == "sl" and r["exit_date"] == CAL[5] and abs(r["ret_sl"] - (-30.0)) < 1e-9
    assert r["halted_in_path"] and not r["unresolved"]


def test_halt_to_window_end_is_unresolved():
    bars = {CAL[0]: _flat(CAL[0], 100.0), CAL[1]: _flat(CAL[1], 100.0)}
    halts = set(CAL[2:])
    r = L.simulate_candidate(_env(bars), "1", CAL[0], halts)
    assert r["unresolved"]


def test_max_hold_exit_at_k10_open():
    bars = {d: _flat(d, 100.0) for d in CAL}
    r = L.simulate_candidate(_env(bars), "1", CAL[0], set())
    assert r["exit_reason"] == "max_hold" and r["exit_date"] == CAL[11]


def test_episode_first_breaks_on_gap():
    stock = np.array(["a", "a", "a", "b", "a"])
    ci = np.array([1, 2, 4, 2, 5])
    assert L.episode_first(stock, ci).tolist() == [True, False, True, True, False]
