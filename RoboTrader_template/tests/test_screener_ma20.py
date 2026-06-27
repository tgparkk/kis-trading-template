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


def test_base_filter_excludes_when_market_cap_unknown():
    """market_cap=0(미상)이면 시총 컨셉(중소형) 검증 불가 → fail-closed 제외.

    상한형(>)은 결측(0)이 `0 > max` False 라 과거엔 조용히 통과했었음 — 회귀 방지.
    """
    a = BookPullbackMa20ScreenerAdapter()
    universe = [
        {"code": "X", "name": "unknown", "market": "KOSPI",  "market_cap": 0, "trading_value": 1e9},
        {"code": "Y", "name": "low_tv",  "market": "KOSPI",  "market_cap": 0, "trading_value": 1e5},  # trading_value 미달
        {"code": "Z", "name": "none",    "market": "KOSPI",                   "trading_value": 1e9},  # 키 결측
    ]
    kept = [u["code"] for u in a.base_filter(universe)]
    assert kept == []


def test_base_filter_excludes_megacap():
    a = BookPullbackMa20ScreenerAdapter()
    universe = [
        {"code": "S", "name": "small", "market": "KOSPI", "market_cap": 1e11, "trading_value": 1e9},
        {"code": "M", "name": "mega",  "market": "KOSPI", "market_cap": 5e13, "trading_value": 1e9},
    ]
    kept = [u["code"] for u in a.base_filter(universe)]
    assert "S" in kept and "M" not in kept


def test_base_filter_max_cap_inclusive_boundary_live_equivalence():
    """채워진 시총엔 기존과 동일한 상한 컷('이하'=inclusive >). 경계값(정확히 max)은 통과."""
    a = BookPullbackMa20ScreenerAdapter()
    p = a.default_params()
    tv = p["min_trading_value"] * 2
    universe = [
        {"code": "LO", "name": "lo", "market_cap": p["max_market_cap"] - 1, "trading_value": tv},  # 통과
        {"code": "EQ", "name": "eq", "market_cap": p["max_market_cap"],     "trading_value": tv},  # 경계 통과(>)
        {"code": "HI", "name": "hi", "market_cap": p["max_market_cap"] + 1, "trading_value": tv},  # 제외
    ]
    kept = [u["code"] for u in a.base_filter(universe)]
    assert kept == ["LO", "EQ"]
