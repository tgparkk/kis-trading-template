"""stages — arm A «멈춘 단계» 분류 · 접힌 단계 행(순수)."""
from __future__ import annotations

from datetime import date, datetime

from backtest.concept_axes.ledger8 import logscan8 as L8
from backtest.concept_axes.ledger8 import stages as ST
from backtest.concept_axes.minervini.cap_skip_ledger.classify import Trade

D = date(2026, 9, 18)


def _fold(*times: str) -> L8.Fold:
    f = L8.Fold()
    for t in times:
        f.hit(t)
    return f


def _facts(**kw) -> ST.AFacts:
    base = dict(d=D, folder="daytrading_3methods_breakout", code="072990", held_live=False, no_slot_live=False,
                slot_note="K=10 09:00보유=5 빈자리=09:00:00-15:30:00", cap_log={}, buysig=None, gates={},
                filled=None, signal_log="NA", signal_replay="N", a_qty_upper=None)
    base.update(kw)
    return ST.AFacts(**base)


def test_fill_wins():
    t = Trade(buy_id=1, code="209640", buy_ts=datetime(2026, 9, 18, 9, 2, 13), buy_price=3695.0)
    a = ST.classify_a(_facts(code="209640", filled=t, buysig=_fold("09:02:13")))
    assert (a.stage, a.result, a.basis) == (ST.STAGE_FILL, "Y", "vtr")


def test_deepest_gate_decides_cash_over_band_and_throttle():
    gates = {L8.G_THROTTLE: _fold("09:02:13"), L8.G_BAND_ABOVE: _fold("09:05:00"),
             L8.G_QTY: _fold("09:08:37", "09:30:00")}
    a = ST.classify_a(_facts(buysig=_fold("09:02:13", "09:08:37"), gates=gates, signal_log="Y"))
    assert (a.stage, a.result, a.basis) == (ST.STAGE_CASH, L8.G_QTY, "log")
    assert "qty_short×2" in a.detail and "throttle×1" in a.detail


def test_other_holder_gate():
    a = ST.classify_a(_facts(buysig=_fold("09:09:22"), gates={L8.G_HELD_ANY: _fold("09:09:22")}, signal_log="Y"))
    assert (a.stage, a.result) == (ST.STAGE_GATE, "other_holder")


def test_signal_without_trace_is_unexplained_or_recon_cash():
    assert ST.classify_a(_facts(buysig=_fold("09:11:00"), signal_log="Y")).stage == ST.STAGE_UNEXPLAINED
    a = ST.classify_a(_facts(buysig=_fold("09:11:00"), signal_log="Y", a_qty_upper=0))
    assert (a.stage, a.result, a.basis) == (ST.STAGE_CASH, "qty_zero_recon", "recon")


def test_held_then_cap_then_signal():
    assert ST.classify_a(_facts(held_live=True, no_slot_live=True)).stage == ST.STAGE_HELD
    a = ST.classify_a(_facts(cap_log={"max_positions": _fold("09:02:52")}, no_slot_live=True))
    assert (a.stage, a.result, a.basis) == (ST.STAGE_CAP, "max_positions", "log")
    a = ST.classify_a(_facts(no_slot_live=True))
    assert (a.stage, a.result, a.basis) == (ST.STAGE_CAP, "no_slot", "timeline")
    assert ST.classify_a(_facts(signal_log="N")).basis == "log"
    a = ST.classify_a(_facts(signal_log="NA", signal_replay="Y"))
    assert (a.stage, a.result, a.basis) == (ST.STAGE_SIGNAL, "Y", "replay")


def test_funnel_rows_fold_n_first_last():
    gates = {L8.G_QTY: _fold("09:08:37", "09:30:00")}
    rows = ST.funnel_rows(_facts(buysig=_fold("09:02:13", "09:08:37", "09:30:00"), gates=gates, signal_log="Y"))
    assert [(r["stage"], r["result"]) for r in rows] == [
        (ST.STAGE_CANDIDATE, "Y"), (ST.STAGE_SIGNAL, "Y"), (ST.STAGE_CASH, L8.G_QTY)]
    sig = rows[1]
    assert (sig["n"], sig["first_ts"], sig["last_ts"], sig["basis"]) == ("3", "09:02:13", "09:30:00", "log")
    assert all(set(r) == set(ST.FUNNEL_COLS) for r in rows)
