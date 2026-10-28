from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from types import SimpleNamespace

import pandas as pd
import pytest

from backtest.concept_axes.ledger8 import exitsim8 as X
from backtest.concept_axes.theme_rank import bandfill as BF
from backtest.concept_axes.theme_rank import build_arena as BA


def test_band_fill_rules():
    assert BF.band_fill(102.0, 101.0, 103.0) == BF.Fill(BF.FILL_OPEN, 102.0)
    assert BF.band_fill(103.0, 99.0, 103.0) == BF.Fill(BF.FILL_OPEN, 103.0)          # 경계 포함
    assert BF.band_fill(106.0, 102.0, 103.0) == BF.Fill(BF.FILL_BAND, 103.0)
    assert BF.band_fill(106.0, 104.0, 103.0) == BF.Fill(BF.FILL_NONE, None)
    assert BF.band_fill(None, None, 103.0) == BF.Fill(BF.FILL_NO_BAR, None)
    assert BF.band_fill(0.0, 0.0, 103.0).status == BF.FILL_NO_BAR


def _bar(d, o, h, lo, c):
    return X.Bar(d, o, h, lo, c)


def test_resim_band_touch_enters_at_upper_and_skips_entry_day_touch():
    d1, d2 = date(2026, 1, 5), date(2026, 1, 6)
    bars = {d1: _bar(d1, 106.0, 120.0, 90.0, 104.0),          # 진입일: 고저가 ±10% 를 넘지만 시각 불명 → 안 봄
            d2: _bar(d2, 105.0, 114.0, 104.0, 110.0)}         # 다음 날 고가 114 ≥ 103×1.1 → 익절
    env = SimpleNamespace(cal=[d1, d2], cal_idx={d1: 0, d2: 1}, bars=lambda code: bars)
    ex = BF.resim_band_touch("000001", d1, 103.0, env, X.ExitRules(0.10, 0.10, 10), lambda pos, d: None)
    assert ex.reason == "tp" and ex.exit_date == d2
    assert ex.price == pytest.approx(113.3) and ex.ret_pct == pytest.approx(10.0)


@dataclass
class _Ex:
    exit_date: date
    reason: str
    hold_days: int
    ret_pct: float
    flags: list


def _led(rows):
    cols = ["strategy", "scan_date", "stock_code", "rank", "score", "n_passed", "band_hi", "entry_date",
            "entry_price", "exit_date", "exit_reason", "hold_days", "ret_pct", "flags"]
    return pd.DataFrame(rows, columns=cols)


def test_arena_rows_open_band_none_and_rank_cut():
    led = _led([
        (BA.STRATEGY, "2026-01-02", "1", 1, 9.0, 30, 103.0, "2026-01-05", 102.0, "2026-01-07", "tp", 2, 10.0, "a"),
        (BA.STRATEGY, "2026-01-02", "2", 2, 8.0, 30, 103.0, "2026-01-05", 106.0, "2026-01-06", "sl", 1, -10.0, "b"),
        (BA.STRATEGY, "2026-01-02", "3", 3, 7.0, 30, 103.0, "2026-01-05", 106.0, "2026-01-06", "sl", 1, -10.0, "c"),
        (BA.STRATEGY, "2026-01-02", "4", 21, 1.0, 30, 103.0, "2026-01-05", 102.0, "2026-01-07", "tp", 2, 10.0, "d"),
    ])
    lows = {("000002", date(2026, 1, 5)): 101.0, ("000003", date(2026, 1, 5)): 104.0}
    calls = []

    def resim(code, d1, price):
        calls.append((code, d1, price))
        return _Ex(date(2026, 1, 8), "max_hold", 3, 1.5, ["x"])

    rows = BA.arena_rows(led, lambda c, d: lows.get((c, d)), resim)
    by = {r["stock_code"]: r for r in rows}
    assert set(by) == {"000001", "000002", "000003"}                       # rank 21 제외
    assert by["000001"]["fill"] == "open" and by["000001"]["ret_net"] == pytest.approx(9.75)
    assert by["000002"]["fill"] == "band_touch" and by["000002"]["entry_price"] == 103.0
    assert by["000002"]["ret_pct"] == 1.5 and by["000002"]["ret_net"] == pytest.approx(1.25)
    assert calls == [("000002", date(2026, 1, 5), 103.0)]
    assert by["000003"]["fill"] == "none"


def test_arena_rows_no_bar_and_none_fill_have_blank_returns():
    led = _led([(BA.STRATEGY, "2026-01-02", "5", 1, 9.0, 3, 103.0, None, None, None, None, None, None, "no_open")])
    r = BA.arena_rows(led, lambda c, d: None, lambda *a: None)[0]
    assert r["fill"] == "no_bar" and r["ret_pct"] == "" and r["ret_net"] == ""


def test_arena_rows_normalizes_stock_code():
    led = _led([(BA.STRATEGY, "2026-01-02", "5930", 1, 9.0, 3, 103.0, "2026-01-05", 102.0, "2026-01-06",
                 "tp", 1, 10.0, "")])
    assert BA.arena_rows(led, lambda c, d: None, lambda *a: None)[0]["stock_code"] == "005930"


def test_filled_keeps_only_bought_rows_with_returns():
    a = pd.DataFrame({"fill": ["open", "band_touch", "none", "open"], "ret_net": [1.0, 2.0, None, None]})
    assert BF.filled(a)["ret_net"].tolist() == [1.0, 2.0]
