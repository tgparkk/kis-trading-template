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


# ---------------------------------------------------------------------------
# _passes_market_cap — fail-closed 시총 가드 (결측이면 제외).
# 라이브 경로는 COALESCE(market_cap,0) 라 결측이 0 으로 들어온다 → 0/None/음수 = 제외.
# ---------------------------------------------------------------------------

def test_passes_market_cap_excludes_missing_both_sides():
    """결측(None/0/음수)은 하한·상한 어느 쪽이든 무조건 제외(False)."""
    f = RuleScreenerBase._passes_market_cap
    for missing in (None, 0, 0.0, -1):
        assert f(missing, min_cap=5e11) is False   # 하한형
        assert f(missing, max_cap=5e11) is False   # 상한형
        assert f(missing, max_cap=5e11, max_inclusive=True) is False
        assert f(missing) is False                 # 컷 없이도 결측은 제외


def test_passes_market_cap_min_cap_boundary():
    """하한형: mcap >= min_cap 통과, 미만 제외. 경계값(정확히 min)은 통과."""
    f = RuleScreenerBase._passes_market_cap
    assert f(5e11, min_cap=5e11) is True      # 경계 정확값 통과
    assert f(5e11 + 1, min_cap=5e11) is True
    assert f(5e11 - 1, min_cap=5e11) is False  # 미달 제외


def test_passes_market_cap_max_cap_exclusive_boundary():
    """상한 exclusive('미만', daytrading): mcap >= max_cap 제외. 경계값 제외."""
    f = RuleScreenerBase._passes_market_cap
    assert f(5e11 - 1, max_cap=5e11) is True
    assert f(5e11, max_cap=5e11) is False      # 경계 정확값 제외(>=)
    assert f(5e11 + 1, max_cap=5e11) is False


def test_passes_market_cap_max_cap_inclusive_boundary():
    """상한 inclusive('이하', ma5/ma20): mcap > max_cap 만 제외. 경계값 통과."""
    f = RuleScreenerBase._passes_market_cap
    assert f(3e12, max_cap=3e12, max_inclusive=True) is True   # 경계 정확값 통과(>)
    assert f(3e12 - 1, max_cap=3e12, max_inclusive=True) is True
    assert f(3e12 + 1, max_cap=3e12, max_inclusive=True) is False


