"""scan.py 단위 — 설계서 §2-3(창·가드) · §2-4(정렬·절단·동점)."""
from __future__ import annotations

import pandas as pd
import pytest

from backtest.concept_axes.replayer import scan


# ── §2-4 정렬·절단·동점 ─────────────────────────────────────────────────────

def test_rank_is_score_desc_then_code_asc_stable():
    scored = [("000300", 5.0), ("000100", 5.0), ("000200", 9.0)]
    out = scan.rank_and_truncate(scored, max_candidates=20)
    assert [c for c, _ in out] == ["000200", "000100", "000300"]


def test_truncation_at_max_candidates_20():
    scored = [(f"{i:06d}", float(1000 - i)) for i in range(50)]
    out = scan.rank_and_truncate(scored, max_candidates=20)
    assert len(out) == 20
    assert out[0][0] == "000000"


def test_tie_at_boundary_20_is_counted():
    """20위 경계 동점 건수는 «게이트 리포트에 인쇄»해야 하므로 세어 돌려준다."""
    scored = [(f"{i:06d}", float(100 - i)) for i in range(19)]
    scored += [("900001", 1.0), ("900002", 1.0), ("900003", 1.0)]
    out, n_tie = scan.rank_and_truncate(scored, max_candidates=20, count_boundary_tie=True)
    assert len(out) == 20
    assert n_tie == 3


def test_tie_inside_topk_but_not_at_boundary_is_zero():
    """리뷰 L-3 — 동점이 상위 «안» 에만 있으면 경계는 흔리지 않는다."""
    scored = [("000001", 100.0), ("000002", 100.0)]          # 상위 안 동점
    scored += [(f"{i:06d}", float(50 - i)) for i in range(3, 25)]
    _, n_tie = scan.rank_and_truncate(scored, max_candidates=20,
                                      count_boundary_tie=True)
    assert n_tie == 0


def test_no_tie_at_boundary_reports_zero():
    scored = [(f"{i:06d}", float(100 - i)) for i in range(25)]
    _, n_tie = scan.rank_and_truncate(scored, max_candidates=20, count_boundary_tie=True)
    assert n_tie == 0


# ── §2-3 창 자르기 — 라이브 `_load_daily(days=lookback)` + `<= D` 와 같은 창 ──

def test_window_is_last_lookback_bars_up_to_d_inclusive():
    g = pd.DataFrame({"close": list(range(100))})
    win = scan.window_slice(g, i=99, lookback=90)
    assert len(win) == 90
    assert win["close"].iloc[-1] == 99
    assert win["close"].iloc[0] == 10


def test_window_shorter_than_lookback_at_series_start():
    g = pd.DataFrame({"close": list(range(10))})
    win = scan.window_slice(g, i=5, lookback=90)
    assert len(win) == 6


# ── base_filter 경계 — 라이브 어댑터를 «그대로» 부른다(§2-2) ─────────────────

def test_base_filter_max_inclusive_differs_between_strategies():
    from strategies.book_pullback_ma20.screener import BookPullbackMa20ScreenerAdapter
    from strategies.daytrading_3methods_breakout.screener import (
        Daytrading3MethodsBreakoutScreenerAdapter,
    )
    ma20 = BookPullbackMa20ScreenerAdapter()
    day = Daytrading3MethodsBreakoutScreenerAdapter()
    rec = lambda mc: [{"code": "000001", "name": "000001",
                       "market_cap": mc, "trading_value": 2e9}]
    # ma20: `≤ 3조` (max_inclusive=True) → 경계값 통과
    assert len(ma20.base_filter(rec(3_000_000_000_000))) == 1
    assert len(ma20.base_filter(rec(3_000_000_000_001))) == 0
    # daytrading: `< 5천억` (max_inclusive=False) → 경계값 탈락
    assert len(day.base_filter(rec(500_000_000_000))) == 0
    assert len(day.base_filter(rec(499_999_999_999))) == 1


def test_missing_market_cap_is_fail_closed():
    from strategies.book_pullback_ma20.screener import BookPullbackMa20ScreenerAdapter
    ma20 = BookPullbackMa20ScreenerAdapter()
    for mc in (None, 0, -1):
        assert ma20.base_filter([{"code": "000001", "name": "000001",
                                  "market_cap": mc, "trading_value": 2e9}]) == []


def test_eligible_by_date_uses_live_base_filter():
    from strategies.book_pullback_ma20.screener import BookPullbackMa20ScreenerAdapter
    uni = {pd.Timestamp("2026-01-09"): {
        "000001": (1e12, 2e9),          # 통과
        "000002": (4e12, 2e9),          # 시총 초과
        "000003": (1e12, 5e8),          # 거래대금 미달
    }}
    elig = scan.eligible_by_date(uni, BookPullbackMa20ScreenerAdapter())
    assert elig[pd.Timestamp("2026-01-09")] == {"000001"}


# ── 불가능봉 가드 — 라이브와 «같은 창»·«같은 문턱» ──────────────────────────

def test_impossible_drop_guard_excludes_stock():
    from utils.data_sanity import IMPOSSIBLE_DROP_PCT
    assert IMPOSSIBLE_DROP_PCT == -0.35
    win = pd.DataFrame({
        "date": pd.date_range("2024-01-01", periods=3),
        "close": [100.0, 50.0, 55.0],       # −50%
    })
    assert scan.is_impossible(win) is True
    ok = pd.DataFrame({
        "date": pd.date_range("2024-01-01", periods=3),
        "close": [100.0, 72.0, 75.0],       # −28%
    })
    assert scan.is_impossible(ok) is False


# ── 결정성 (V5) ────────────────────────────────────────────────────────────

def test_rank_and_truncate_is_deterministic_under_input_permutation():
    scored = [("000300", 5.0), ("000100", 5.0), ("000200", 5.0)]
    a = scan.rank_and_truncate(scored, max_candidates=20)
    b = scan.rank_and_truncate(list(reversed(scored)), max_candidates=20)
    assert a == b
