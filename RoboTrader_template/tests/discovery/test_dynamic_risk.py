import pytest
from scripts.discovery.dynamic_risk import resolve_risk, eff_sl, eff_tp, SL_FLOOR, SL_CAP, TP_CAP

def test_atr_rr_preserved():
    sl, tp, clamped = resolve_risk("atr", {"atr": 200}, 10000, sl_mult=2.0, rr=2.0)
    assert abs(sl - 0.04) < 1e-9   # 2*200/10000 = 4%
    assert abs(tp - 0.08) < 1e-9   # rr*sl
    assert clamped is False

def test_sl_floor_applied():
    sl, tp, clamped = resolve_risk("atr", {"atr": 100}, 10000, sl_mult=1.0, rr=2.0)
    assert sl == SL_FLOOR          # raw 1% < 3%

def test_sl_cap_applied():
    sl, tp, clamped = resolve_risk("atr", {"atr": 2000}, 10000, sl_mult=1.0, rr=1.0)
    assert sl == SL_CAP            # raw 20% > 15%

def test_tp_cap_clamps_and_flags():
    sl, tp, clamped = resolve_risk("atr", {"atr": 2000}, 10000, sl_mult=1.0, rr=3.0)
    assert tp == TP_CAP            # 15%*3 = 45% -> cap 30%
    assert clamped is True

def test_box_structural():
    sl, tp, clamped = resolve_risk("box", {"box_low": 9000, "box_height": 1000}, 10000, sl_mult=1.0, rr=2.0, buffer=0.0)
    assert abs(sl - 0.10) < 1e-9   # (10000-9000)/10000
    assert abs(tp - 0.20) < 1e-9   # 1000*2/10000

def test_none_ref_returns_none():
    assert resolve_risk("atr", None, 10000, 1.0, 2.0) is None

def test_eff_sl_tp_fallback_and_override():
    params = {"stop_loss_pct": 0.08, "take_profit_pct": 0.12}
    assert eff_sl({}, params) == 0.08
    assert eff_tp({}, params) == 0.12
    assert eff_sl({"sl_pct": 0.05}, params) == 0.05
    assert eff_tp({"tp_pct": 0.20}, params) == 0.20
