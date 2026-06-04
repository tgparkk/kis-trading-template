# tests/test_screener_elder.py
import pandas as pd
from datetime import date
from strategies.elder_ema_pullback.screener import ElderEmaPullbackScreenerAdapter


def _uptrend_pullback_df(n=90):
    """EMA65 상승 추세 + 마지막 봉이 EMA13 부근 눌림 양봉.

    screen1_uptrend: ema65[-1] > ema65[-6] 조건을 만족시키도록
    단조상승 시계열을 사용하고, 마지막 봉을 EMA13 터치 후 반등으로 구성.
    """
    import numpy as np

    # 단조상승: close = 1000 + i*10 (70봉이면 EMA65 기울기 양수 확실)
    closes = [1000.0 + i * 10.0 for i in range(n)]

    # 마지막 봉: EMA13 부근 눌림(low <= ema13*touch_band) + close > ema13
    # EMA13 값은 대략 close[-1] 근방이므로 low를 close[-1]*0.995 로 설정해 터치
    close_series = pd.Series(closes, dtype=float)
    ema13_series = close_series.ewm(span=13, adjust=False).mean()
    last_ema13 = float(ema13_series.iloc[-1])

    opens = [c - 2.0 for c in closes]
    # low[-1] = ema13 * 1.005 (≤ ema13*1.02 터치, close > ema13 만족)
    lows = [c - 8.0 for c in closes[:-1]] + [last_ema13 * 1.005]
    highs = [c + 5.0 for c in closes]
    # close[-1] > ema13: 단조상승이라 close[-1] > ema13 자명

    rows = {
        "date": pd.date_range("2026-01-01", periods=n),
        "open": opens,
        "high": highs,
        "low":  lows,
        "close": closes,
        "volume": [1000] * n,
    }
    return pd.DataFrame(rows)


def test_base_filter_market_cap_tier():
    a = ElderEmaPullbackScreenerAdapter()
    p = a.default_params()
    universe = [
        {"code": "A", "name": "large",   "market_cap": p["min_market_cap"] * 2, "trading_value": p["min_trading_value"] * 2},
        {"code": "B", "name": "small",   "market_cap": p["min_market_cap"] / 2, "trading_value": p["min_trading_value"] * 2},
        {"code": "C", "name": "unknown", "market_cap": 0,                       "trading_value": p["min_trading_value"] * 2},
        {"code": "D", "name": "low_tv",  "market_cap": p["min_market_cap"] * 2, "trading_value": p["min_trading_value"] / 2},
    ]
    kept = [u["code"] for u in a.base_filter(universe)]
    assert "A" in kept       # 대형 통과
    assert "B" not in kept   # 소형 제외
    assert "C" in kept       # market_cap=0(미상) soft 통과
    assert "D" not in kept   # trading_value 미달 제외


def test_match_triggers_on_uptrend_pullback():
    a = ElderEmaPullbackScreenerAdapter()
    df = _uptrend_pullback_df()
    verdict = a.match(df, a.default_params())
    assert verdict is not None
    score, reason = verdict
    assert "ema" in reason.lower() or "triple" in reason.lower()


def test_base_filter_passes_when_market_cap_unknown():
    """market_cap=0(미상)이어도 trading_value 충족 시 통과해야 한다 (시장 라벨 무관)."""
    a = ElderEmaPullbackScreenerAdapter()
    universe = [
        {"code": "X", "name": "unknown", "market_cap": 0, "trading_value": 1e10},
        {"code": "Y", "name": "low_tv",  "market_cap": 0, "trading_value": 1e6},   # trading_value 미달
    ]
    kept = [u["code"] for u in a.base_filter(universe)]
    assert "X" in kept       # market_cap=0 이어도 통과
    assert "Y" not in kept   # trading_value 미달


def test_match_none_on_downtrend():
    a = ElderEmaPullbackScreenerAdapter()
    n = 90
    closes = [2000 - i * 5 for i in range(n)]  # 단조 하락 → screen1_uptrend 실패
    df = pd.DataFrame({
        "date": pd.date_range("2026-01-01", periods=n),
        "open": closes, "high": [c + 3 for c in closes],
        "low": [c - 3 for c in closes], "close": closes, "volume": [1000] * n,
    })
    assert a.match(df, a.default_params()) is None
