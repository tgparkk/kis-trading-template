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
    assert r["exit_reason"] == L.EXIT_HALT_RESUME and r["exit_date"] == CAL[5] and abs(r["ret_sl"] - (-30.0)) < 1e-9
    assert r["halted_in_path"] and not r["unresolved"]


def test_halt_then_in_band_resumption_forces_exit_at_resume_open():
    """스펙 :84 «보유 중 정지 → 재개 뒤 첫 체결가로 청산» — 재개 시가가 ±10% 안이어도 그날 시가로 무조건 청산."""
    bars = {CAL[0]: _flat(CAL[0], 100.0), CAL[1]: _flat(CAL[1], 100.0)}
    for d in CAL[2:4]:
        bars[d] = _flat(d, 100.0)                                 # 정지 평평봉
    bars[CAL[4]] = X.Bar(CAL[4], 103.0, 105.0, 101.0, 104.0)      # 재개 첫 봉 — 밴드 안(+3%)
    for d in CAL[5:]:
        bars[d] = _flat(d, 104.0)
    r = L.simulate_candidate(_env(bars), "1", CAL[0], {CAL[2], CAL[3]})
    assert r["exit_reason"] == L.EXIT_HALT_RESUME and r["exit_date"] == CAL[4]
    assert abs(r["ret_sl"] - 3.0) < 1e-9 and r["ret_tp"] == r["ret_sl"] and not r["both"]
    assert r["halted_in_path"] and not r["unresolved"] and r["hold_days"] == 3


def test_exit_before_halt_is_not_forced():
    bars = {CAL[0]: _flat(CAL[0], 100.0), CAL[1]: _flat(CAL[1], 100.0),
            CAL[2]: X.Bar(CAL[2], 100.0, 101.0, 89.0, 95.0)}     # k=1 손절
    for d in CAL[3:]:
        bars[d] = _flat(d, 95.0)
    r = L.simulate_candidate(_env(bars), "1", CAL[0], {CAL[4], CAL[5]})
    assert r["exit_reason"] == "sl" and r["exit_date"] == CAL[2] and not r["halted_in_path"]


def test_halt_to_window_end_is_unresolved():
    bars = {CAL[0]: _flat(CAL[0], 100.0), CAL[1]: _flat(CAL[1], 100.0)}
    halts = set(CAL[2:])
    r = L.simulate_candidate(_env(bars), "1", CAL[0], halts)
    assert r["unresolved"] and r["halted_in_path"]


def test_halt_after_exit_not_counted_in_path():
    bars = {CAL[0]: _flat(CAL[0], 100.0), CAL[1]: _flat(CAL[1], 100.0),
            CAL[2]: X.Bar(CAL[2], 100.0, 112.0, 100.0, 110.0)}   # k=1 익절
    for d in CAL[5:8]:
        bars[d] = _flat(d, 100.0)
    r = L.simulate_candidate(_env(bars), "1", CAL[0], set(CAL[5:8]))
    assert r["exit_reason"] == "tp" and r["exit_date"] == CAL[2] and not r["halted_in_path"]


def test_missing_bar_not_in_halts_is_not_halted():
    bars = {CAL[0]: _flat(CAL[0], 100.0), CAL[1]: _flat(CAL[1], 100.0),
            CAL[4]: X.Bar(CAL[4], 100.0, 112.0, 100.0, 110.0)}   # CAL[2..3] 봉 없음(정지 아님)
    r = L.simulate_candidate(_env(bars), "1", CAL[0], set())
    assert r["exit_date"] == CAL[4] and not r["halted_in_path"]


def test_max_hold_exit_at_k10_open():
    bars = {d: _flat(d, 100.0) for d in CAL}
    r = L.simulate_candidate(_env(bars), "1", CAL[0], set())
    assert r["exit_reason"] == "max_hold" and r["exit_date"] == CAL[11]


def test_episode_first_breaks_on_gap():
    stock = np.array(["a", "a", "a", "b", "a"])
    ci = np.array([1, 2, 4, 2, 5])
    assert L.episode_first(stock, ci).tolist() == [True, False, True, True, False]


# ── critic B2 · 보유 창 기업행위(ca_path) ─────────────────────────────────────────
import pandas as pd                                                 # noqa: E402

CA_CAL = [date(2022, 3, 1) + timedelta(days=i) for i in range(40)]
CA_IDX = {d: i for i, d in enumerate(CA_CAL)}


def _ca_px():
    rows = []

    def stock(code, closes, opens=None, adj=None, vol=None):
        for i, d in enumerate(CA_CAL):
            c = closes[i]
            o = opens[i] if opens is not None else c
            rows.append(dict(stock_code=code, date=pd.Timestamp(d), open=o, high=max(o, c) * 1.001,
                             low=min(o, c) * 0.999, close=c, volume=(vol[i] if vol is not None else 1000.0),
                             adj_factor=(adj[i] if adj is not None else np.nan)))
    base = [100.0 + (i % 3) for i in range(40)]
    stock("NONE00", base)
    stock("JUMP10", [c if i < 25 else c * 1.4 for i, c in enumerate(base)])          # k=10 에 +40% 종가 → 창 안
    stock("JUMP11", [c if i < 26 else c * 1.4 for i, c in enumerate(base)])          # k=11 → 창 밖
    stock("JUMP00", [c if i < 15 else c * 1.4 for i, c in enumerate(base)])          # k=0(진입일) → 창 밖
    gap = [c if i != 20 else c * 0.65 for i, c in enumerate(base)]                    # 시가만 −35%(종가 정상)
    stock("GAPOPN", base, opens=gap)
    stock("ADJSTP", base, adj=[1.0 if i < 20 else 0.5 for i in range(40)])          # adj 계단
    stock("ADJNUL", base, adj=[np.nan if i < 20 else 1.0 for i in range(40)])       # NULL→1.0 = 계단 아님
    cl = [100.0] * 40
    cl[22] = 80.0                                                                     # −20% · 시가 −21% · 거래량 평소
    op = list(cl)
    op[22] = 79.0
    stock("CLIFF0", cl, opens=op)
    return pd.DataFrame(rows).sort_values(["stock_code", "date"]).reset_index(drop=True)


def test_ca_path_fixed_window_k1_to_k10_after_entry():
    fd = L.ca_flag_days(_ca_px(), CA_IDX)
    entry = CA_CAL[15]
    got = {c: L.ca_path(fd, c, entry, CA_IDX) for c in
           ("NONE00", "JUMP10", "JUMP11", "JUMP00", "GAPOPN", "ADJSTP", "ADJNUL", "CLIFF0", "NOROWS")}
    assert got == {"NONE00": False, "JUMP10": True, "JUMP11": False, "JUMP00": False, "GAPOPN": True,
                   "ADJSTP": True, "ADJNUL": False, "CLIFF0": True, "NOROWS": False}


def test_ca_path_cliff_uses_frozen_fd1_flag_not_a_new_threshold():
    """CLIFF0 은 ±30% 문턱에 안 걸리고(−20%) FD1 동결식 flag_cliff 로만 잡힌다."""
    from backtest.concept_axes.replayer import flags as FL
    px = _ca_px()
    fl = FL.compute_bar_flags(px)
    m = (px["stock_code"] == "CLIFF0").to_numpy()
    assert fl.loc[m, "flag_cliff"].sum() == 1
    assert (fl.loc[m, "ret_1d"].dropna().abs() <= 0.30).all()
