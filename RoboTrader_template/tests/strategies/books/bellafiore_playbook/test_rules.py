"""Bellafiore 6규칙 + ALL_RULES export 단위 테스트."""

import numpy as np
import pandas as pd
import pytest

from strategies.books.bellafiore_playbook import rules as bel


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


def test_second_day_play_triggers_on_strong_setup_then_breakout():
    # 첫 30봉: 100→106 (+6%) 상승 → setup_strong=True
    # 31번째 봉 close=107 > setup_high(106.1) → breakout=True
    setup_closes = [100 + i * (6.0 / 29) for i in range(30)]
    setup_high = max(setup_closes) + 0.1  # high = close + 0.1
    last_close = setup_high + 0.5  # 돌파
    closes = setup_closes + [last_close]
    df = _df(closes)
    res = bel.rule_second_day_play().evaluate(df, {})
    assert res.triggered
    assert res.side == "buy"


def test_second_day_play_no_trigger_weak_setup():
    # 첫 30봉: +2% 상승 (min_pct=0.05 미달)
    setup_closes = [100 + i * (2.0 / 29) for i in range(30)]
    closes = setup_closes + [110.0]
    df = _df(closes)
    res = bel.rule_second_day_play().evaluate(df, {})
    assert not res.triggered


def test_bull_flag_bellafiore_triggers_on_pole_flag_breakout():
    # pole_bars=2, flag_bars=5, flag_range_pct=0.015
    # rule 인덱싱: pole_start = iloc[-(flag_bars+pole_bars+1)] = iloc[-8]
    #             pole_end   = iloc[-(flag_bars+1)]            = iloc[-6]
    # 앞에 패딩 봉 1개 추가해 총 9봉 (패딩1 + pole2 + flag5 + last1)
    # paddig: 99.0, pole: 99.0→101.5 (+2.5% >= 1%), flag 5봉 좁은 range, last: 돌파
    padding = [99.0]
    pole = [99.0, 101.5]   # pole_start=99.0, pole_end=101.5 → +2.5%
    flag_closes = [101.4, 101.3, 101.4, 101.3, 101.4]  # 5봉
    last = [102.0]
    closes = padding + pole + flag_closes + last
    # flag 구간 high/low: range=0.4/101.6≈0.39% < 1.5%
    pad_highs = [99.1]; pad_lows = [98.9]
    pole_highs = [99.1, 101.6]; pole_lows = [98.9, 101.4]
    flag_highs = [101.55] * 5; flag_lows = [101.25] * 5
    last_highs = [102.1]; last_lows = [101.9]
    highs = pad_highs + pole_highs + flag_highs + last_highs
    lows  = pad_lows  + pole_lows  + flag_lows  + last_lows
    df = pd.DataFrame({
        "datetime": pd.date_range("2026-04-01 09:00", periods=len(closes), freq="1min"),
        "open": closes, "high": highs, "low": lows,
        "close": closes, "volume": [1000] * len(closes),
    })
    res = bel.rule_bull_flag_bellafiore().evaluate(df, {})
    assert res.triggered


def test_range_trade_triggers_on_support_bounce():
    # window=90, tol=0.003, min_range_pct=0.01
    # 직전 90봉: high=105.0, low=95.0 → range=10/105≈9.5% >= 1%
    # 마지막 봉: low≈95.0 (near_low), open < close (bullish)
    n_window = 90
    closes = [100.0] * n_window + [95.5]  # 마지막 봉 양봉
    opens = [100.0] * n_window + [95.3]
    highs = [100.5] * (n_window - 1) + [105.0] + [95.8]
    lows = [99.5] * (n_window // 3) + [95.0] + [99.5] * (n_window - n_window // 3 - 1) + [95.1]
    df = _df(closes, opens=opens, highs=highs, lows=lows)
    res = bel.rule_range_trade(window=90, tol=0.005).evaluate(df, {})
    assert res.triggered


def test_fade_vwap_triggers_on_oversold():
    # deviation_pct=0.02, rsi_oversold=15 (테스트용 완화)
    # 20봉 평균 VWAP≈100, 마지막 3봉 급락 → VWAP 대비 -3%+ 이격
    # 급락으로 RSI(2) 매우 낮음
    closes = [100.0] * 20 + [98.5, 97.0, 95.0]
    df = _df(closes)
    res = bel.rule_fade_vwap(deviation_pct=0.02, rsi_oversold=15).evaluate(df, {})
    assert res.triggered
    assert res.side == "buy"


def test_opening_consolidation_breakout_triggers():
    # consolidation_bars=10, box_range_pct=0.015
    # 첫 10봉: 좁은 range (100.2~100.8 = 0.6/100.8≈0.6% < 1.5%)
    # 거래량 감소: 앞 5봉 2000, 뒤 5봉 800
    # 11번째: 박스 고가(100.8+0.1=100.9) 초과 close=101.5
    closes = [100.2, 100.5, 100.8, 100.7, 100.6, 100.9, 100.6, 100.7, 100.5, 100.8, 101.5]
    volumes = [2000, 2000, 2000, 2000, 2000, 800, 800, 800, 800, 800, 1500]
    highs = [c + 0.05 for c in closes]
    lows = [c - 0.05 for c in closes]
    df = pd.DataFrame({
        "datetime": pd.date_range("2026-04-01 09:00", periods=len(closes), freq="1min"),
        "open": closes, "high": highs, "low": lows,
        "close": closes, "volume": volumes,
    })
    res = bel.rule_opening_consolidation_breakout(consolidation_bars=10).evaluate(df, {})
    assert res.triggered


def test_catalyst_gap_triggers_on_gap_and_rvol():
    # setup_bars=30, gap_pct=0.03, rvol_min=1.5 (완화)
    # rvol = cumulative_vol / (setup_vol_avg * elapsed)
    # setup(30봉) avg_vol=1000, 마지막 봉 vol=20000 → 총합=30*1000+20000=50000
    # expected=1000*31=31000 → rvol=50000/31000≈1.61 >= 1.5
    # 첫 봉 open=110, setup avg_close≈100 → gap=10% >= 3%
    # last_close(110.6) > first_open(110) → above_first=True
    n = 31
    opens = [110.0] + [100.0] * (n - 1)
    closes = [110.0] + [100.0] * 29 + [110.6]
    volumes = [1000] * 30 + [20000]  # 마지막 봉 거래량 폭증 → rvol≈1.61
    highs = [max(o, c) + 0.1 for o, c in zip(opens, closes)]
    lows = [min(o, c) - 0.1 for o, c in zip(opens, closes)]
    df = pd.DataFrame({
        "datetime": pd.date_range("2026-04-01 09:00", periods=n, freq="1min"),
        "open": opens, "high": highs, "low": lows,
        "close": closes, "volume": volumes,
    })
    res = bel.rule_catalyst_gap(gap_pct=0.03, rvol_min=1.5).evaluate(df, {})
    assert res.triggered


def test_all_rules_export_present():
    assert len(bel.ALL_RULES) == 6
    names = {r().name for r in bel.ALL_RULES}
    assert names == {
        "second_day_play", "bull_flag_bellafiore", "range_trade",
        "fade_vwap", "opening_consolidation_breakout", "catalyst_gap",
    }
