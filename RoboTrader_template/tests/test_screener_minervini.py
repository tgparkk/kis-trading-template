# tests/test_screener_minervini.py
import pandas as pd
from strategies.minervini_volume_dryup.screener import MinerviniVolumeDryupScreenerAdapter


def _dryup_df():
    # 직전 30봉 거래량 1000, 최근 10봉 거래량 500 → ratio 0.5 <= 0.70
    vols = [1000] * 30 + [500] * 10
    n = len(vols)
    closes = [1000 + i for i in range(n)]
    return pd.DataFrame({
        "date": pd.date_range("2026-01-01", periods=n),
        "open": closes, "high": [c + 1 for c in closes], "low": [c - 1 for c in closes],
        "close": closes, "volume": vols,
    })


def test_match_triggers_on_volume_dryup():
    a = MinerviniVolumeDryupScreenerAdapter()
    df = _dryup_df()
    verdict = a.match(df, a.default_params())
    assert verdict is not None
    assert "dryup" in verdict[1].lower()


def test_match_none_when_volume_not_dry():
    a = MinerviniVolumeDryupScreenerAdapter()
    df = _dryup_df()
    df.loc[df.index[-10:], "volume"] = 1000  # 최근도 1000 → ratio 1.0
    assert a.match(df, a.default_params()) is None
