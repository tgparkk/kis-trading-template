# tests/test_screener_ma5.py
import pandas as pd
from strategies.book_pullback_ma5.screener import BookPullbackMa5ScreenerAdapter


def test_match_triggers_on_pullback():
    a = BookPullbackMa5ScreenerAdapter()
    closes = [1000.0] * 5 + [1000.0 + i * 60.0 for i in range(15)] + [1900.0, 1870.0, 1890.0]
    n = len(closes)

    # MA5 계산해서 마지막 봉 low를 정확히 ma5 부근으로 설정
    close_series = pd.Series(closes, dtype=float)
    ma5_val = float(close_series.rolling(5).mean().iloc[-1])

    opens = [c - 20.0 for c in closes]
    opens[-1] = closes[-1] - 30.0  # 마지막 봉 양봉: close(1890) > open(1860)
    highs = [c + 15.0 for c in closes]
    # low[-1] = ma5 * 1.005 → ±2% 이내 터치, close(1890) >= ma5*(0.98) 만족
    lows = [c - 25.0 for c in closes[:-1]] + [ma5_val * 1.005]

    df = pd.DataFrame({
        "date": pd.date_range("2026-01-01", periods=n),
        "open": opens, "high": highs,
        "low": lows, "close": closes, "volume": [1000] * n,
    })
    verdict = a.match(df, a.default_params())
    assert verdict is not None
    score, reason = verdict
    assert isinstance(score, float)
    assert "ma5" in reason.lower()


def test_base_filter_excludes_when_market_cap_unknown():
    """market_cap=0(미상)이면 시총 컨셉(중소형) 검증 불가 → fail-closed 제외.

    상한형(>)은 결측(0)이 `0 > max` False 라 과거엔 조용히 통과했었음 — 회귀 방지.
    """
    a = BookPullbackMa5ScreenerAdapter()
    universe = [
        {"code": "X", "name": "unknown", "market": "KOSPI",  "market_cap": 0, "trading_value": 1e9},
        {"code": "Y", "name": "low_tv",  "market": "KOSDAQ", "market_cap": 0, "trading_value": 1e5},  # trading_value 미달
        {"code": "Z", "name": "none",    "market": "KOSPI",                   "trading_value": 1e9},  # 키 결측
    ]
    kept = [u["code"] for u in a.base_filter(universe)]
    assert kept == []


def test_base_filter_excludes_megacap():
    a = BookPullbackMa5ScreenerAdapter()
    universe = [
        {"code": "S", "name": "s", "market": "KOSDAQ", "market_cap": 5e10, "trading_value": 1e9},
        {"code": "M", "name": "m", "market": "KOSPI",  "market_cap": 5e13, "trading_value": 1e9},
    ]
    kept = [u["code"] for u in a.base_filter(universe)]
    assert "S" in kept and "M" not in kept


def test_base_filter_max_cap_inclusive_boundary_live_equivalence():
    """채워진 시총엔 기존과 동일한 상한 컷('이하'=inclusive >). 경계값(정확히 max)은 통과."""
    a = BookPullbackMa5ScreenerAdapter()
    p = a.default_params()
    tv = p["min_trading_value"] * 2
    universe = [
        {"code": "LO", "name": "lo", "market_cap": p["max_market_cap"] - 1, "trading_value": tv},  # 통과
        {"code": "EQ", "name": "eq", "market_cap": p["max_market_cap"],     "trading_value": tv},  # 경계 통과(>)
        {"code": "HI", "name": "hi", "market_cap": p["max_market_cap"] + 1, "trading_value": tv},  # 제외
    ]
    kept = [u["code"] for u in a.base_filter(universe)]
    assert kept == ["LO", "EQ"]
