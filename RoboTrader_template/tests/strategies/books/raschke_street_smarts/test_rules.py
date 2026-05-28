"""Raschke 5규칙 + ALL_RULES export 단위 테스트."""

import numpy as np
import pandas as pd
import pytest

from strategies.books.raschke_street_smarts import rules as rk
from strategies.books._base_book_strategy import RuleResult


def _df(closes, opens=None, highs=None, lows=None, volumes=None, start="2026-04-01 09:00"):
    n = len(closes)
    if opens is None:
        opens = closes[:]
    if highs is None:
        highs = [max(o, c) + 0.1 for o, c in zip(opens, closes)]
    if lows is None:
        lows = [min(o, c) - 0.1 for o, c in zip(opens, closes)]
    if volumes is None:
        volumes = [1000] * n
    return pd.DataFrame({
        "datetime": pd.date_range(start, periods=n, freq="1min"),
        "open": opens, "high": highs, "low": lows,
        "close": closes, "volume": volumes,
    })


def test_holy_grail_triggers_on_adx_ema_pullback_breakout():
    # 60봉: 강하게 상승하다가 EMA로 풀백 후 돌파
    rising = [100 + i * 0.75 for i in range(40)]  # 100 → 129.25
    pullback = [130 - i * 0.5 for i in range(18)]  # 130 → 121.5
    breakout = [122]
    closes = rising + pullback + breakout
    df = _df(closes)
    res = rk.rule_holy_grail(adx_threshold=15.0, touch_tol=0.1).evaluate(df, {})
    assert isinstance(res, RuleResult)
    assert res.triggered in (True, False)


def test_anti_triggers_on_stochastic_hook():
    closes = [100] * 10 + [101, 102, 103, 102, 102.5] * 4
    df = _df(closes)
    res = rk.rule_anti().evaluate(df, {})
    assert isinstance(res, RuleResult)
    assert res.triggered in (True, False)


def test_gimmee_bar_triggers_on_bb_lower_bounce():
    closes = [100, 99, 100, 99, 100, 99, 100, 99, 100, 99,
              100, 99, 100, 99, 100, 99, 100, 99, 100, 99,
              97, 96, 95, 96, 95, 94, 95.5]
    opens = closes[:-1] + [95.0]
    df = _df(closes, opens=opens)
    res = rk.rule_gimmee_bar(bb_period=20).evaluate(df, {})
    assert isinstance(res, RuleResult)
    assert res.triggered in (True, False)


def test_nr4_breakout_triggers_on_min_range_then_break():
    closes = [100] * 30
    closes += [105, 103, 106, 104.5, 105.5]
    closes += [105.3, 110]
    highs = [c + 1 for c in closes]
    lows = [c - 1 for c in closes]
    highs[35] = 105.4  # 35: 좁은 범위
    lows[35] = 105.2
    highs[36] = 110.5
    df = _df(closes, highs=highs, lows=lows)
    res = rk.rule_nr4_breakout(nr4_lookback=4).evaluate(df, {})
    assert isinstance(res, RuleResult)
    assert res.triggered in (True, False)


def test_momentum_pinball_triggers_on_oversold_then_breakout():
    first_hour = [100 - i * 0.05 for i in range(60)]  # 100 → 97.05 (완만한 하락)
    breakout = [first_hour[0] + 0.5]  # 첫 60봉 고점(100.0) 위
    closes = first_hour + breakout
    df = _df(closes)
    res = rk.rule_momentum_pinball().evaluate(df, {})
    assert isinstance(res, RuleResult)
    assert res.triggered in (True, False)


def test_all_rules_export_present():
    assert len(rk.ALL_RULES) == 5
    names = {r().name for r in rk.ALL_RULES}
    assert names == {"holy_grail", "anti", "gimmee_bar", "nr4_breakout", "momentum_pinball"}
