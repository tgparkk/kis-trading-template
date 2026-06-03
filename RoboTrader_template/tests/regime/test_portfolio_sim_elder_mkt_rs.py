"""회귀 동등성 + no-lookahead — portfolio_sim_elder 의 mkt_rs 진입 게이트.

★보장 1 (회귀)★: entry_gate=None 이면 simulate_portfolio 결과가 게이트 도입 전과
  바이트동일(=baseline). 게이트는 신호 수락 직전 AND-필터일 뿐, 미주입 시 미평가.
★보장 2 (no-lookahead)★: build_mkt_rs_gate(code, i) 판정은 데이터를 i 봉까지로
  절단해도 불변(미래 데이터 무관). entry_filters.filter_cache_mkt_rs 와 per-bar 동치.
★보장 3 (단조)★: 게이트는 진입을 줄이거나 같게만 만든다(거래수 ≤ baseline).

DB 불필요(합성 데이터). 거래비용/청산은 정본 _elder_exit_reason 그대로 사용.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

import scripts.portfolio_sim_elder as P
from scripts.entry_filters import filter_cache_mkt_rs
from strategies.base import Signal, SignalType


def _make_df(seed: int, n: int = 200, drift: float = 0.001):
    rng = np.random.default_rng(seed)
    dates = pd.bdate_range("2023-01-02", periods=n)
    lr = drift + rng.normal(0, 0.02, n)
    close = 10000 * np.exp(np.cumsum(lr))
    o = close * (1 - rng.uniform(0, 0.004, n))
    h = np.maximum(o, close) * 1.01
    l = np.minimum(o, close) * 0.99
    vol = rng.integers(1000, 5000, n)
    return pd.DataFrame({"datetime": dates, "open": o, "high": h, "low": l,
                         "close": close, "volume": vol})


def _make_kospi(n: int = 200):
    rng = np.random.default_rng(99)
    dates = pd.bdate_range("2023-01-02", periods=n)
    return pd.Series(2400 * np.exp(np.cumsum(0.0003 + rng.normal(0, 0.01, n))),
                     index=dates, name="close")


class _AlwaysBuyStrategy:
    """warmup 이후 매 bar BUY (게이팅만 측정)."""
    def generate_signal_with_extra_ctx(self, code, window, timeframe, extra):
        return Signal(signal_type=SignalType.BUY, stock_code=code, confidence=100,
                      reasons=["always"])


def _data_and_calendar(n=200):
    data = {f"S{k:02d}": _make_df(seed=10 + k, drift=(0.002 if k % 2 == 0 else -0.001), n=n)
            for k in range(6)}
    calendar = P._build_calendar(data)
    return data, calendar


def _simulate(entry_gate):
    data, calendar = _data_and_calendar()
    return P.simulate_portfolio(
        data=data, calendar=calendar, strategy=_AlwaysBuyStrategy(),
        exit_reason_fn=P._elder_exit_reason, exit_params=P.ELDER_A_PARAMS,
        max_positions=20, use_buy_stop=True, entry_gate=entry_gate,
    )


def test_gate_none_byte_identical():
    """entry_gate=None (기본) → 게이트 미도입 동작과 동일(자기 일관성: 두 호출 동일)."""
    r1 = _simulate(None)
    r2 = _simulate(None)
    assert r1["equity_curve"] == r2["equity_curve"]
    assert [t for t in r1["trades"]] == [t for t in r2["trades"]]


def test_gate_reduces_or_equals_trades():
    """mkt_rs 게이트는 진입을 AND-필터 → 매수 거래수 ≤ baseline."""
    base = _simulate(None)
    data, _ = _data_and_calendar()
    gate = P.build_mkt_rs_gate(data, _make_kospi(), n=20)
    gated = _simulate(gate)
    n_buy_base = sum(1 for t in base["trades"] if t["side"] == "buy")
    n_buy_gated = sum(1 for t in gated["trades"] if t["side"] == "buy")
    assert n_buy_gated <= n_buy_base, f"게이트가 매수 증가 {n_buy_gated} > {n_buy_base}"


def test_gate_no_lookahead_truncation_invariant():
    """gate(code,i) 는 데이터를 i 봉까지 절단해도 동일 판정(미래 무관)."""
    data, _ = _data_and_calendar()
    kospi = _make_kospi()
    n = 20
    gate_full = P.build_mkt_rs_gate(data, kospi, n=n)
    code = "S00"
    df = data[code]
    for i in (60, 90, 120, 150):
        # 종목·KOSPI 데이터를 i 봉까지로 절단한 별도 게이트
        trunc_data = {code: df.iloc[: i + 1].reset_index(drop=True)}
        t_date = pd.Timestamp(df["datetime"].iloc[i]).normalize()
        trunc_kospi = kospi[kospi.index <= t_date]
        gate_trunc = P.build_mkt_rs_gate(trunc_data, trunc_kospi, n=n)
        assert gate_full(code, i) == gate_trunc(code, i), f"룩어헤드: bar {i} 절단 판정 불일치"


def test_gate_matches_entry_filters_per_bar():
    """gate 판정이 entry_filters.filter_cache_mkt_rs 의 per-bar keep 결정과 1:1 동치."""
    data, _ = _data_and_calendar()
    kospi = _make_kospi()
    n = 20
    gate = P.build_mkt_rs_gate(data, kospi, n=n)
    # 각 종목 warmup 이후 전 bar 를 후보로 한 cache → filter_cache_mkt_rs 의 kept 와 비교
    cache = {c: list(range(n + 5, len(df))) for c, df in data.items()}
    kept = filter_cache_mkt_rs(data, cache, kospi_close=kospi, n=n)
    for code, bars in cache.items():
        kept_set = set(kept[code])
        for i in bars:
            assert gate(code, i) == (i in kept_set), \
                f"{code} bar {i}: gate={gate(code, i)} filter_cache={i in kept_set}"
