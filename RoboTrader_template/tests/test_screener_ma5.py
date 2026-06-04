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


def test_base_filter_excludes_megacap():
    a = BookPullbackMa5ScreenerAdapter()
    universe = [
        {"code": "S", "name": "s", "market": "KOSDAQ", "market_cap": 5e10, "trading_value": 1e9},
        {"code": "M", "name": "m", "market": "KOSPI",  "market_cap": 5e13, "trading_value": 1e9},
    ]
    kept = [u["code"] for u in a.base_filter(universe)]
    assert "S" in kept and "M" not in kept
