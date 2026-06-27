# tests/test_screener_daytrading.py
import pandas as pd
from strategies.daytrading_3methods_breakout.screener import Daytrading3MethodsBreakoutScreenerAdapter


def _breakout_df():
    # 직전 20봉 고가 ~1100, 마지막 봉 종가 1300 돌파 + 거래량 폭증 + 양봉
    # rule requires len(df) >= high_window + 2 = 22, so 22 bars total
    closes = [1000 + (i % 5) * 20 for i in range(21)] + [1300]
    n = len(closes)  # 22
    vols = [1000] * 21 + [3000]
    return pd.DataFrame({
        "date": pd.date_range("2026-01-01", periods=n),
        "open": [c - 5 for c in closes[:-1]] + [1250],
        "high": [1100] * 21 + [1320],
        "low": [c - 10 for c in closes],
        "close": closes,
        "volume": vols,
    })


def test_match_triggers_on_breakout():
    a = Daytrading3MethodsBreakoutScreenerAdapter()
    verdict = a.match(_breakout_df(), a.default_params())
    assert verdict is not None
    assert "breakout" in verdict[1].lower()


def test_base_filter_excludes_when_market_cap_unknown():
    """market_cap=0(미상)이면 시총 컨셉(중소형) 검증 불가 → fail-closed 제외.

    상한형(>=)은 결측(0)이 `0 >= max` False 라 과거엔 조용히 통과했었음 — 회귀 방지.
    """
    a = Daytrading3MethodsBreakoutScreenerAdapter()
    universe = [
        {"code": "X", "name": "unknown", "market_cap": 0, "trading_value": 1e9},
        {"code": "Y", "name": "low_tv",  "market_cap": 0, "trading_value": 1e5},  # trading_value 미달
        {"code": "Z", "name": "none",                     "trading_value": 1e9},  # 키 결측
    ]
    kept = [u["code"] for u in a.base_filter(universe)]
    assert kept == []


def test_base_filter_smallcap_only():
    a = Daytrading3MethodsBreakoutScreenerAdapter()
    universe = [
        {"code": "K", "name": "k", "market_cap": 3e11, "trading_value": 1e9},   # 소형 통과
        {"code": "B", "name": "b", "market_cap": 1e12, "trading_value": 1e9},   # 대형 제외
    ]
    kept = [u["code"] for u in a.base_filter(universe)]
    assert "K" in kept
    assert "B" not in kept


def test_base_filter_max_cap_exclusive_boundary_live_equivalence():
    """채워진 시총엔 기존과 동일한 상한 컷('미만'=exclusive >=). 경계값(정확히 max)은 제외."""
    a = Daytrading3MethodsBreakoutScreenerAdapter()
    p = a.default_params()
    tv = p["min_trading_value"] * 2
    universe = [
        {"code": "LO", "name": "lo", "market_cap": p["max_market_cap"] - 1, "trading_value": tv},  # 통과
        {"code": "EQ", "name": "eq", "market_cap": p["max_market_cap"],     "trading_value": tv},  # 경계 제외(>=)
        {"code": "HI", "name": "hi", "market_cap": p["max_market_cap"] + 1, "trading_value": tv},  # 제외
    ]
    kept = [u["code"] for u in a.base_filter(universe)]
    assert kept == ["LO"]


def test_default_high_window_matches_validated_live_rule():
    """스크리너 high_window=15 — 라이브 config/strategy 검증값과 일치(멀티버스 rank1).
    이전 20은 후보 선정이 더 엄격해 진입 정의와 불일치였음(감사 2026-06-23)."""
    p = Daytrading3MethodsBreakoutScreenerAdapter().default_params()
    assert p["high_window"] == 15
    assert p["vol_lookback"] == 20
    assert p["vol_mult"] == 2.0
