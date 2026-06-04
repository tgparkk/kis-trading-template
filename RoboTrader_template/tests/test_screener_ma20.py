# tests/test_screener_ma20.py
import pandas as pd
from strategies.book_pullback_ma20.screener import BookPullbackMa20ScreenerAdapter


def _ma20_pullback_df():
    """급등 후 20일선 부근 눌림 양봉.

    surge_lookback=30, surge_pct=0.25 조건:
      df.iloc[-(30+1):-1] 내 저점 대비 고점 >= +25%
    MA20 터치 조건:
      last_low 이 ma20 ±2% 이내 AND close >= ma20*(1-0.02) AND 양봉
    룰 최소길이 guard: max(ma_window=20, surge_lookback=30)+2 = 32봉 필요.
    """
    # 9봉 평탄 + 20봉 단조상승(+60/봉) + 눌림 3봉 = 32봉
    closes = [1000.0] * 9 + [1000.0 + i * 60.0 for i in range(20)] + [2100.0, 2050.0, 2080.0]
    n = len(closes)  # 32봉

    # MA20 계산해서 마지막 봉 low를 정확히 ma20 부근으로 설정
    close_series = pd.Series(closes, dtype=float)
    ma20_val = float(close_series.rolling(20).mean().iloc[-1])

    opens = [c - 30.0 for c in closes]
    opens[-1] = closes[-1] - 40.0  # 마지막 봉 양봉: close(2080) > open(2040)
    highs = [c + 20.0 for c in closes]
    # low[-1] = ma20 * 1.005 → ±2% 이내 터치, close(2080) >= ma20*(0.98) 만족
    lows = [c - 40.0 for c in closes[:-1]] + [ma20_val * 1.005]

    return pd.DataFrame({
        "date": pd.date_range("2026-01-01", periods=n),
        "open": opens,
        "high": highs,
        "low": lows,
        "close": closes,
        "volume": [1000] * n,
    })


def test_match_triggers_on_pullback():
    a = BookPullbackMa20ScreenerAdapter()
    df = _ma20_pullback_df()
    verdict = a.match(df, a.default_params())
    assert verdict is not None
    score, reason = verdict
    assert isinstance(score, float)
    assert "ma20" in reason.lower()


def test_base_filter_excludes_megacap():
    a = BookPullbackMa20ScreenerAdapter()
    universe = [
        {"code": "S", "name": "small", "market": "KOSPI", "market_cap": 1e11, "trading_value": 1e9},
        {"code": "M", "name": "mega",  "market": "KOSPI", "market_cap": 5e13, "trading_value": 1e9},
    ]
    kept = [u["code"] for u in a.base_filter(universe)]
    assert "S" in kept and "M" not in kept
