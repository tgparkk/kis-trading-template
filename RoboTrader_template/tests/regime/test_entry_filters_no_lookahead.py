"""No Look-Ahead 검증 — 신규 진입 필터 (scripts/entry_filters.py).

★합격 핵심★. 3종 필터(rs_rank·mkt_rs·adx·ma_slope)의 진입봉 keep/drop 판정이
판정 시점(≤t)의 데이터만 사용함을 증명한다.

1. 절단 불변성: 진입봉 i 의 판정 == bars 0..i 만으로 계산한 값
2. 미래 불변성: i 이후 데이터를 극단 변조해도 i 판정 불변
3. 횡단면(rs_rank): t 단면 랭크는 t 이후 타종목 데이터 변경에 불변
4. 시장(mkt_rs): t 이후 KOSPI 변경이 t 판정에 무영향
5. none 필터 항등성 + 기본 동작
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from scripts.entry_filters import (
    apply_entry_filter,
    compute_adx,
    compute_ma_slope_ok,
    filter_cache_adx,
    filter_cache_ma_slope,
    filter_cache_mkt_rs,
    filter_cache_rs_rank,
)


# ============================================================================
# Fixtures
# ============================================================================

def _make_stock_df(seed: int, n: int = 200, drift: float = 0.001, start_px: float = 10000.0):
    rng = np.random.default_rng(seed)
    dates = pd.bdate_range("2023-01-02", periods=n)
    lr = drift + rng.normal(0, 0.015, n)
    close = start_px * np.exp(np.cumsum(lr))
    o = close * (1 - rng.uniform(0, 0.004, n))
    h = np.maximum(o, close) * (1 + rng.uniform(0, 0.006, n))
    l = np.minimum(o, close) * (1 - rng.uniform(0, 0.006, n))
    vol = rng.integers(1000, 5000, n)
    return pd.DataFrame({
        "datetime": dates, "open": o, "high": h, "low": l, "close": close, "volume": vol,
    })


def _make_universe(n_codes: int = 12, n: int = 200):
    data = {}
    for k in range(n_codes):
        drift = 0.0015 if k % 2 == 0 else -0.0005
        data[f"S{k:02d}"] = _make_stock_df(seed=100 + k, n=n, drift=drift)
    return data


def _make_kospi(n: int = 200, seed: int = 7):
    rng = np.random.default_rng(seed)
    dates = pd.bdate_range("2023-01-02", periods=n)
    lr = 0.0005 + rng.normal(0, 0.008, n)
    close = pd.Series(2400 * np.exp(np.cumsum(lr)), index=dates, name="close")
    return close


def _full_cache(data, lo=30, step=7):
    """각 종목의 [lo, n-2] 구간에서 step 간격 bar 를 신호로 가정."""
    out = {}
    for code, df in data.items():
        n = len(df)
        out[code] = list(range(lo, n - 1, step))
    return out


# ============================================================================
# 1. ADX 절단/미래 불변성
# ============================================================================

def test_adx_truncation_invariance():
    df = _make_stock_df(seed=1)
    full = compute_adx(df, period=14)
    for ti in [40, 80, 150, len(df) - 1]:
        trunc = compute_adx(df.iloc[: ti + 1].reset_index(drop=True), period=14)
        a, b = full.iloc[ti], trunc.iloc[-1]
        if pd.isna(a):
            assert pd.isna(b)
        else:
            assert a == pytest.approx(b, rel=1e-9, abs=1e-9), f"ADX 절단 위반 @ {ti}"


def test_adx_future_immutability():
    df = _make_stock_df(seed=2)
    base = compute_adx(df, period=14)
    ti = 100
    df2 = df.copy()
    df2.loc[ti + 1:, ["open", "high", "low", "close"]] *= 0.4  # 미래 폭락 변조
    pert = compute_adx(df2, period=14)
    for j in range(20, ti + 1):
        a, b = base.iloc[j], pert.iloc[j]
        if pd.isna(a):
            assert pd.isna(b)
        else:
            assert a == pytest.approx(b, rel=1e-9, abs=1e-9), f"ADX 미래누설 @ {j}"


def test_filter_adx_keeps_only_strong_trend():
    data = _make_universe()
    cache = _full_cache(data)
    out_hi = filter_cache_adx(data, cache, threshold=25.0)
    out_lo = filter_cache_adx(data, cache, threshold=0.0)
    # threshold 0 이면 (워밍업 통과분) 거의 전부, 25 이면 부분집합
    tot_hi = sum(len(v) for v in out_hi.values())
    tot_lo = sum(len(v) for v in out_lo.values())
    assert tot_hi <= tot_lo
    for code in cache:
        assert set(out_hi[code]).issubset(set(cache[code]))


# ============================================================================
# 2. ma_slope 절단/미래 불변성
# ============================================================================

def test_ma_slope_truncation_invariance():
    df = _make_stock_df(seed=3)
    full = compute_ma_slope_ok(df, window=50, slope_lb=10)
    for ti in [70, 120, len(df) - 1]:
        trunc = compute_ma_slope_ok(df.iloc[: ti + 1].reset_index(drop=True), window=50, slope_lb=10)
        assert bool(full.iloc[ti]) == bool(trunc.iloc[-1]), f"ma_slope 절단 위반 @ {ti}"


def test_ma_slope_future_immutability():
    df = _make_stock_df(seed=4)
    base = compute_ma_slope_ok(df, window=50, slope_lb=10)
    ti = 110
    df2 = df.copy()
    df2.loc[ti + 1:, "close"] *= 3.0
    pert = compute_ma_slope_ok(df2, window=50, slope_lb=10)
    for j in range(60, ti + 1):
        assert bool(base.iloc[j]) == bool(pert.iloc[j]), f"ma_slope 미래누설 @ {j}"


# ============================================================================
# 3. rs_rank 횡단면 PIT
# ============================================================================

def test_rs_rank_future_immutability_cross_section():
    """t 이후 타종목 데이터를 변조해도 t 단면 랭크(=keep/drop) 불변."""
    data = _make_universe(n_codes=10)
    cache = _full_cache(data)
    base = filter_cache_rs_rank(data, cache, n=60, threshold=0.5)

    # 한 종목의 미래 구간만 극단 변조 → t<=cut 판정 불변이어야
    data2 = {c: df.copy() for c, df in data.items()}
    cut = 120
    victim = "S03"
    data2[victim].loc[cut + 1:, "close"] *= 10.0
    pert = filter_cache_rs_rank(data2, cache, n=60, threshold=0.5)

    for code in data:
        df = data[code]
        dts = pd.to_datetime(df["datetime"])
        base_keep = [i for i in base[code] if i <= cut]
        pert_keep = [i for i in pert[code] if i <= cut]
        assert base_keep == pert_keep, f"rs_rank 횡단면 미래누설 @ {code}"


def test_rs_rank_truncation_invariance():
    """진입봉 i 의 keep/drop == data 를 i 까지 절단해 계산한 값."""
    data = _make_universe(n_codes=8)
    cache = _full_cache(data, lo=70, step=11)
    full = filter_cache_rs_rank(data, cache, n=60, threshold=0.5)
    # 검사 시점 (충분히 쌓인 곳)
    for ti in [80, 120, 160]:
        data_tr = {c: df.iloc[: ti + 1].reset_index(drop=True) for c, df in data.items()}
        cache_tr = {c: [i for i in bars if i <= ti] for c, bars in cache.items()}
        trunc = filter_cache_rs_rank(data_tr, cache_tr, n=60, threshold=0.5)
        for code in data:
            assert (ti in full[code]) == (ti in trunc.get(code, [])), \
                f"rs_rank 절단 위반 @ {code} bar {ti}"


def test_rs_rank_threshold_monotone():
    data = _make_universe(n_codes=12)
    cache = _full_cache(data)
    lo = filter_cache_rs_rank(data, cache, n=60, threshold=0.3)
    hi = filter_cache_rs_rank(data, cache, n=60, threshold=0.7)
    assert sum(len(v) for v in hi.values()) <= sum(len(v) for v in lo.values())


# ============================================================================
# 4. mkt_rs 시장 PIT
# ============================================================================

def test_mkt_rs_future_immutability():
    """t 이후 KOSPI 변조가 t 판정에 무영향."""
    data = _make_universe(n_codes=6)
    cache = _full_cache(data)
    kospi = _make_kospi()
    base = filter_cache_mkt_rs(data, cache, kospi_close=kospi, n=60)

    kospi2 = kospi.copy()
    cut_date = kospi.index[150]
    kospi2.loc[kospi2.index > cut_date] *= 0.2
    pert = filter_cache_mkt_rs(data, cache, kospi_close=kospi2, n=60)

    for code in data:
        df = data[code]
        dts = pd.to_datetime(df["datetime"])
        base_keep = [i for i in base[code] if dts.iloc[i] <= cut_date]
        pert_keep = [i for i in pert[code] if dts.iloc[i] <= cut_date]
        assert base_keep == pert_keep, f"mkt_rs KOSPI 미래누설 @ {code}"


def test_mkt_rs_outperform_semantics():
    """종목 수익률이 KOSPI 보다 크면 통과, 작으면 drop (단조)."""
    # 강상승 종목 vs 약세 KOSPI → 대부분 통과
    data = {"UP": _make_stock_df(seed=50, drift=0.004)}
    cache = {"UP": list(range(70, 198, 5))}
    flat_kospi = pd.Series(2400.0, index=pd.bdate_range("2023-01-02", periods=200))
    out = filter_cache_mkt_rs(data, cache, kospi_close=flat_kospi, n=60)
    assert len(out["UP"]) > 0
    assert set(out["UP"]).issubset(set(cache["UP"]))


# ============================================================================
# 5. none 항등성 + 디스패처
# ============================================================================

def test_none_filter_identity():
    data = _make_universe()
    cache = _full_cache(data)
    out = apply_entry_filter(data, cache, filt="none", threshold=0.5, n=60)
    assert out is cache  # 동일 객체 — 회귀 바이트동일 보장


def test_dispatcher_routes_all():
    data = _make_universe()
    cache = _full_cache(data)
    kospi = _make_kospi()
    for filt in ("rs_rank", "mkt_rs", "adx", "ma_slope"):
        out = apply_entry_filter(data, cache, filt=filt, threshold=0.5, n=60, kospi_close=kospi)
        for code in cache:
            assert set(out[code]).issubset(set(cache[code]))


def test_unknown_filter_raises():
    data = _make_universe()
    cache = _full_cache(data)
    with pytest.raises(ValueError):
        apply_entry_filter(data, cache, filt="bogus", threshold=0.5, n=60)
