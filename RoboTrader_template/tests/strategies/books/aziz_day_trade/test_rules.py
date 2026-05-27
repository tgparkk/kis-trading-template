"""아지즈 8개 규칙 단위 테스트."""

import numpy as np
import pandas as pd
import pytest

from strategies.books.aziz_day_trade import rules as az


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


def test_abcd_triggers_on_classic_shape():
    # lookback=15 → seg = 16봉. third=5 → A:0~4, B:5~9, C:10~14, D:15
    # A leg (0~4): 100→104, B pullback (5~9): 103→101, C leg (10~14): 102→106, D(15): 107
    closes = [100, 101, 102, 103, 104,         # A leg up (indices 0-4)
              103, 102, 101, 102, 103,         # B pullback (indices 5-9)
              104, 105, 106, 106.5, 106.8,    # C leg up (indices 10-14)
              107]                             # D breakout above A & C (index 15)
    df = _df(closes)
    res = az.rule_abcd().evaluate(df, {})
    assert res.triggered
    assert res.side == "buy"


def test_bull_flag_requires_prior_spike():
    # flag_bars=3: pre_flag_close = closes[-(3+2)] = closes[-5]
    # 스파이크: closes[-5] → flag 구간 고가 >= 4% 상승 필요
    # closes[-5]=100, flag 구간(closes[-4:-1])=[104.2, 104.1, 104.3] → spike=(104.3-100)/100=4.3% OK
    # flag_range=(high-low)/high 작아야 함, breakout: closes[-1] > flag_high
    closes = [95, 96, 97, 98, 100, 104.2, 104.1, 104.3, 104.5]
    df = _df(closes)
    res = az.rule_bull_flag().evaluate(df, {})
    assert res.triggered


def test_vwap_reversal_recovers_above_vwap():
    # 한 시간 평탄, 잠시 깊은 dip, 마지막 봉 vwap 위 회복
    closes = [100] * 30 + [98, 97, 100.5]
    df = _df(closes)
    res = az.rule_vwap_reversal().evaluate(df, {})
    assert res.triggered


def test_opening_range_breakout_triggers_after_orb_high():
    # 첫 5봉 고가 = 102, 6번째 봉 close = 102.5
    closes = [100, 101, 102, 101.5, 101.8, 102.5]
    highs = [c + 0.1 for c in closes]
    df = _df(closes, highs=highs)
    res = az.rule_opening_range_breakout(orb_bars=5).evaluate(df, {})
    assert res.triggered


def test_red_to_green_requires_prev_close_cross():
    # prev_close = 105, 시가 100(red), 마지막 close = 105.2(>=prev_close)
    df = _df([100, 101, 102, 103, 104, 105.2])
    res = az.rule_red_to_green(prev_close=105.0).evaluate(df, {"prev_close": 105.0})
    assert res.triggered
    assert res.side == "buy"


def test_top_reversal_emits_sell_on_doji_low_volume():
    # 마지막 봉이 도지(open≈close) + 직전봉의 50% 미만 볼륨
    closes = [100, 101, 102, 103, 104, 104.05]
    opens = [99, 100, 101, 102, 103, 104.04]
    volumes = [1000, 1000, 1000, 1000, 1000, 400]
    df = _df(closes, opens=opens, volumes=volumes)
    res = az.rule_top_reversal().evaluate(df, {})
    assert res.triggered
    assert res.side == "sell"


def test_support_resistance_bounces_off_low():
    # window=60: recent_low = df["low"].iloc[-(60+1):-1].min()
    # 총 62봉: 인덱스 0~61. recent_low 슬라이스 = iloc[-61:-1] = 인덱스 1~60
    # 인덱스 30에서 low=95.0(지지선), 마지막봉(idx 61): low=95.1(근처), open<close(양봉)
    closes = [96.0] * 62
    lows = [96.0] * 30 + [95.0] + [96.0] * 30 + [95.1]  # idx30=95.0(지지), idx61=95.1
    opens = [95.8] * 62   # 마지막봉 open=95.8 < close=96.0 → 양봉
    df = _df(closes, opens=opens, lows=lows)
    res = az.rule_support_resistance(window=60, tol=0.005).evaluate(df, {})
    assert res.triggered


def test_ma_trend_triggers_on_ema_touch_with_bullish_bar():
    """rule_ma_trend: 가격이 9/20 EMA에 터치 후 양봉으로 마감 + VWAP 위."""
    # 25봉 — 상승 추세, 마지막 봉이 EMA를 터치(저가) + 양봉
    closes = [100 + i * 0.3 for i in range(24)]
    closes.append(closes[-1] + 0.5)  # 마지막 봉 약간 상승
    df = _df(closes)
    # 마지막 봉을 명확한 양봉으로 + 저가를 EMA 근처(직전봉 종가 부근)로
    df.loc[df.index[-1], "open"] = closes[-2] + 0.05
    df.loc[df.index[-1], "close"] = closes[-2] + 0.6
    df.loc[df.index[-1], "low"] = closes[-2] - 0.2  # EMA 부근
    df.loc[df.index[-1], "high"] = closes[-2] + 0.7
    res = az.rule_ma_trend(ema_touch_tol=0.05).evaluate(df, {})
    assert res.triggered
    assert res.side == "buy"


def test_all_rules_export_present():
    """ALL_RULES 리스트는 8개 클래스를 가져야 한다."""
    assert len(az.ALL_RULES) == 8
    names = {r().name for r in az.ALL_RULES}
    assert names == {
        "abcd", "bull_flag", "vwap_reversal", "orb",
        "red_to_green", "top_reversal", "support_resistance", "ma_trend",
    }
