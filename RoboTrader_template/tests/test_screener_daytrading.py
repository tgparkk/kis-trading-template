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


def test_base_filter_passes_when_market_cap_unknown():
    """market_cap=0(미상)이어도 trading_value 충족 시 통과해야 한다 (시장 라벨 무관)."""
    a = Daytrading3MethodsBreakoutScreenerAdapter()
    universe = [
        {"code": "X", "name": "unknown", "market_cap": 0, "trading_value": 1e9},
        {"code": "Y", "name": "low_tv",  "market_cap": 0, "trading_value": 1e5},  # trading_value 미달
    ]
    kept = [u["code"] for u in a.base_filter(universe)]
    assert "X" in kept
    assert "Y" not in kept


def test_base_filter_smallcap_only():
    a = Daytrading3MethodsBreakoutScreenerAdapter()
    universe = [
        {"code": "K", "name": "k", "market_cap": 3e11, "trading_value": 1e9},   # 소형 통과
        {"code": "B", "name": "b", "market_cap": 1e12, "trading_value": 1e9},   # 대형 제외
    ]
    kept = [u["code"] for u in a.base_filter(universe)]
    assert "K" in kept
    assert "B" not in kept
