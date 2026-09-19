"""sellprobe8 — 라이브 엔진 경로 tp/sl · 매도 탐침(generate_signal → _check_sell) — 합성 프레임 · DB 없음."""
from __future__ import annotations

from datetime import date, datetime

import numpy as np
import pandas as pd
import pytest

from backtest.concept_axes.ledger8 import exitsim8 as X
from backtest.concept_axes.ledger8 import livesignal8 as LS8
from backtest.concept_axes.ledger8 import registry as R
from backtest.concept_axes.ledger8 import sellprobe8 as SP
from backtest.concept_axes.ledger8 import sources8 as SRC8


@pytest.fixture(scope="module")
def strategies():
    return {f: LS8.load8(f) for f in R.ALL_FOLDERS}


def _rising(n: int = 90, last: float = 118.0) -> pd.DataFrame:
    days = pd.bdate_range(end="2026-09-16", periods=n)
    close = np.linspace(100.0, 130.0, n)
    close[-1] = last
    return pd.DataFrame({"date": days, "open": close, "high": close * 1.01, "low": close * 0.99,
                         "close": close, "volume": np.full(n, 1e5)})


def _crash(n: int = 90) -> pd.DataFrame:
    days = pd.bdate_range(end="2026-09-09", periods=n)
    close = np.full(n, 100.0)
    close[-1] = 60.0
    return pd.DataFrame({"date": days, "open": close, "high": close, "low": close, "close": close,
                         "volume": np.full(n, 1e5)})


def _pos(entry: float, day: date = date(2026, 9, 10)) -> X.Pos:
    return X.Pos("000001", day, SRC8.aware(datetime.combine(day, SRC8.FIRST_TICK)), entry, 10, X.BASIS_D_OPEN)


@pytest.mark.parametrize("folder", R.ALL_FOLDERS)
def test_tp_sl_from_engine_path_matches_config(strategies, folder):
    s = strategies[folder]
    rules = SP.resolve_live_tp_sl(folder, s)
    rm = s.config["risk_management"]
    assert rules.tp == pytest.approx(float(rm["take_profit_pct"]))
    assert rules.sl == pytest.approx(max(float(rm["stop_loss_pct"]), 0.03))    # 손절 하한 3% (engine :655-658)
    assert rules.max_hold_days == int(s.max_holding_days)
    assert s.positions == {} and s.daily_trades == 0                            # on_order_filled 는 사본에만


def test_probe_trail_exit_and_no_exit_when_losing(strategies):
    probe = SP.SellProbe("book_pullback_ma20", strategies["book_pullback_ma20"], lambda code, d: (_rising(), {}))
    assert probe(_pos(110.0), date(2026, 9, 17)) == "trail_ma"      # 수익 중 · 종가 < MA20
    assert probe(_pos(125.0), date(2026, 9, 17)) is None             # 손실 중 → trail 없음
    assert probe.inst.positions == {} and strategies["book_pullback_ma20"].positions == {}


def test_probe_respects_min_len_guard_like_live_sell_loop(strategies):
    probe = SP.SellProbe("elder_ema_pullback", strategies["elder_ema_pullback"], lambda code, d: (_rising(n=50), {}))
    assert probe(_pos(110.0), date(2026, 9, 17)) is None              # generate_signal 의 min_len(70) 가드


def test_probe_max_hold_counts_trading_days_by_patched_clock(strategies):
    s = strategies["deep_mr_dev20"]
    probe = SP.SellProbe("deep_mr_dev20", s, lambda code, d: (_crash(), {}))
    pos = _pos(100.0, date(2026, 9, 1))
    assert probe(pos, date(2026, 9, 9)) is None                        # hold 6 < 7
    assert probe(pos, date(2026, 9, 10)) == "max_hold"                 # hold 7 ≥ 7


def test_probe_no_data_returns_none(strategies):
    probe = SP.SellProbe("rs_leader", strategies["rs_leader"], lambda code, d: (None, {}))
    assert probe(_pos(100.0), date(2026, 9, 17)) is None and probe.calls == 0
