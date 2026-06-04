# tests/test_rule_screener_base.py
import pandas as pd
from datetime import date
from strategies._rule_screener_base import RuleScreenerBase
from core.candidate_selector import CandidateStock


class _StubScreener(RuleScreenerBase):
    strategy_name = "stub"

    def __init__(self, universe, frames):
        self._universe = universe
        self._frames = frames

    def base_filter(self, universe):
        return [u for u in universe if u["market"] == "KOSPI"]

    def match(self, df, params):
        last = float(df["close"].iloc[-1])
        if last >= 1000:
            return (last, f"close={last}")
        return None

    def _load_universe(self, scan_date):
        return self._universe

    def _load_daily(self, code, scan_date):
        return self._frames.get(code)


def _df(closes):
    return pd.DataFrame({
        "date": pd.to_datetime([f"2026-05-{i+1:02d}" for i in range(len(closes))]),
        "open": closes, "high": closes, "low": closes,
        "close": closes, "volume": [100] * len(closes),
    })


def test_scan_filters_ranks_and_limits():
    universe = [
        {"code": "A", "name": "Aco", "market": "KOSPI", "market_cap": 1, "trading_value": 1},
        {"code": "B", "name": "Bco", "market": "KOSPI", "market_cap": 1, "trading_value": 1},
        {"code": "C", "name": "Cco", "market": "KOSDAQ", "market_cap": 1, "trading_value": 1},
    ]
    frames = {"A": _df([500, 1500]), "B": _df([500, 2000]), "C": _df([500, 3000])}
    s = _StubScreener(universe, frames)
    out = s.scan(date(2026, 5, 2), {"max_candidates": 10})
    codes = [c.code for c in out]
    assert codes == ["B", "A"]
    assert isinstance(out[0], CandidateStock)
    assert out[0].score == 2000.0


def test_no_lookahead_truncates_future_bars():
    universe = [{"code": "A", "name": "Aco", "market": "KOSPI", "market_cap": 1, "trading_value": 1}]
    frames = {"A": _df([1500, 2000, 3000])}
    s = _StubScreener(universe, frames)
    out = s.scan(date(2026, 5, 1), {})
    assert out[0].score == 1500.0


from datetime import date as _date


def test_window_days_covers_past_scan_date():
    from strategies._rule_screener_base import RuleScreenerBase

    class _S(RuleScreenerBase):
        strategy_name = "s"
        lookback_days = 100

        def base_filter(self, u):
            return u

        def match(self, df, p):
            return None

    s = _S()
    from utils.korean_time import now_kst
    today = now_kst().date()
    # 오늘 기준: gap=0, max(100, 0+100)=100
    assert s._window_days(today) == 100
    # 과거 30일: gap=30, max(100, 30+100)=130
    past = today.fromordinal(today.toordinal() - 30)
    assert s._window_days(past) == 130
