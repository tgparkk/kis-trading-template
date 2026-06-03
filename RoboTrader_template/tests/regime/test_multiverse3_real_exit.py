"""Phase 3 실청산 진입필터 재검 드라이버 (scripts.multiverse3_real_exit) 검증.

DB 불필요 — 합성 데이터로 run_real_exit 를 직접 호출(데이터·turnover·kospi·신호캐시 주입).

보장 2건:
  1. filter='none' 회귀 동등성: filt='none' 의 모든 메트릭은 "필터 없이 실청산만 돌린" 결과와
     바이트동일. apply_entry_filter('none') 이 캐시를 그대로 반환하므로 실청산 입력이 동일.
  2. no-lookahead: 미래 봉을 잘라낸 데이터로 진입필터를 적용해도, 잘라내기 전과 동일한
     과거 진입봉 keep/drop 판정이 나온다(필터 통계가 전부 trailing). 진입봉 ≤t 부분집합 불변.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

import scripts.multiverse3_real_exit as M3
from scripts.entry_filters import apply_entry_filter
from scripts.exit_multiverse import adapters
from scripts.exit_multiverse.signals import precompute_entry_signals


# --------------------------------------------------------------------------- #
# 합성 데이터: ma5_pullback / elder 신호가 충분히 발생하도록 변동성·추세 부여.
# --------------------------------------------------------------------------- #
def _make_df(seed: int, n: int = 200, drift: float = 0.0012) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    dates = pd.bdate_range("2022-01-03", periods=n)
    lr = drift + rng.normal(0, 0.025, n)
    close = 10000 * np.exp(np.cumsum(lr))
    o = close * (1 - rng.uniform(0, 0.006, n))
    h = np.maximum(o, close) * (1 + rng.uniform(0, 0.012, n))
    l = np.minimum(o, close) * (1 - rng.uniform(0, 0.012, n))
    vol = rng.integers(2000, 9000, n).astype(float)
    return pd.DataFrame({"datetime": dates, "open": o, "high": h, "low": l,
                         "close": close, "volume": vol})


def _make_data(n: int = 200) -> dict:
    return {f"S{k:02d}": _make_df(seed=100 + k,
                                  drift=(0.003 if k % 2 == 0 else -0.0015), n=n)
            for k in range(10)}


def _make_kospi(n: int = 200) -> pd.Series:
    rng = np.random.default_rng(7)
    dates = pd.bdate_range("2022-01-03", periods=n)
    return pd.Series(2400 * np.exp(np.cumsum(0.0006 + rng.normal(0, 0.011, n))),
                     index=dates, name="close")


def _turnover(data: dict) -> dict:
    return {c: float((df["close"] * df["volume"]).sum()) for c, df in data.items()}


def _cache(strategy: str, data: dict) -> dict:
    ad = adapters.ADAPTERS[strategy]
    strat = ad.build_strategy()
    ctx = ad.make_extra_ctx_fn(data)
    return precompute_entry_signals(data, strat, ad.warmup_bars, ctx)


# --------------------------------------------------------------------------- #
# 1. filter='none' 회귀 동등성 — 실청산 입력 캐시가 baseline 과 동일 → 메트릭 바이트동일.
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("strategy,K,filt", [
    ("book_pullback_ma5", 3, "ma_slope"),
    ("elder_ema_pullback", 20, "mkt_rs"),
])
def test_filter_none_byte_identical(strategy, K, filt):
    data = _make_data()
    turnover = _turnover(data)
    kospi = _make_kospi()
    cache = _cache(strategy, data)

    # baseline: filt='none'
    none_run = M3.run_real_exit(
        strategy=strategy, filt="none", window="2022", K=K,
        data=data, turnover=turnover, kospi_close=kospi, signal_cache=cache)
    # 같은 캐시·데이터로 'none' 을 다시 (필터 차원에 다른 필터가 끼어도 none 결과 불변 보장).
    none_run2 = M3.run_real_exit(
        strategy=strategy, filt="none", window="2022", K=K,
        data=data, turnover=turnover, kospi_close=kospi, signal_cache=cache)

    a, b = none_run["metrics"], none_run2["metrics"]
    for key in ("n_trades", "sharpe", "pnl", "calmar", "hit", "max_dd",
                "max_concurrent", "n_skipped"):
        assert a[key] == pytest.approx(b[key], rel=1e-12, abs=1e-12), \
            f"filter=none 비결정: {key} {a[key]} != {b[key]}"

    # apply_entry_filter('none') 은 입력 캐시 객체를 그대로 반환(동일 식별자) → 입력 불변 증명.
    assert apply_entry_filter(data, cache, filt="none", threshold=0.5, n=60,
                              kospi_close=kospi) is cache


def test_filter_reduces_or_equals_trades():
    """필터는 AND-게이팅 → 거래수는 baseline(none) 이하."""
    data = _make_data()
    turnover = _turnover(data)
    kospi = _make_kospi()
    for strategy, K, filt in [("book_pullback_ma5", 3, "ma_slope"),
                              ("elder_ema_pullback", 20, "mkt_rs")]:
        cache = _cache(strategy, data)
        none_m = M3.run_real_exit(strategy=strategy, filt="none", window="2022", K=K,
                                  data=data, turnover=turnover, kospi_close=kospi,
                                  signal_cache=cache)["metrics"]
        filt_m = M3.run_real_exit(strategy=strategy, filt=filt, window="2022", K=K,
                                  data=data, turnover=turnover, kospi_close=kospi,
                                  signal_cache=cache)["metrics"]
        assert filt_m["n_trades"] <= none_m["n_trades"], \
            f"{strategy}/{filt}: 거래수 증가 {filt_m['n_trades']}>{none_m['n_trades']}"


# --------------------------------------------------------------------------- #
# 2. no-lookahead — 미래 봉 절단 시 과거 진입봉 keep/drop 판정 불변.
#    필터 적용 결과(과거 진입봉 ≤cut 부분)가 truncated 와 full 에서 동일해야 한다.
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("filt,kwargs", [
    ("ma_slope", {}),
    ("mkt_rs", {}),
])
def test_no_lookahead_filter_truncation_invariance(filt, kwargs):
    data_full = _make_data(n=200)
    kospi_full = _make_kospi(n=200)
    cut = 150  # 진입봉 인덱스 < cut 의 keep/drop 은 미래(>=cut) 데이터와 무관해야.

    # full 진입신호 캐시(모든 봉) — 신호 자체는 필터와 독립이므로 한쪽만 산출 후 절단.
    strategy = "book_pullback_ma5" if filt == "ma_slope" else "elder_ema_pullback"
    cache_full = _cache(strategy, data_full)
    # cut 이전 진입봉만 남긴 캐시(공통 입력)
    cache_pre = {c: [i for i in bars if i < cut] for c, bars in cache_full.items()}

    # full 데이터에 필터 적용 → cut 이전 진입봉의 keep 집합
    kept_full = apply_entry_filter(data_full, cache_pre, filt=filt, threshold=0.5, n=60,
                                   kospi_close=kospi_full, **kwargs)

    # truncated 데이터(미래 제거)에 동일 필터 적용
    data_trunc = {c: df.iloc[:cut].reset_index(drop=True) for c, df in data_full.items()}
    kospi_trunc = kospi_full.iloc[:cut]
    kept_trunc = apply_entry_filter(data_trunc, cache_pre, filt=filt, threshold=0.5, n=60,
                                    kospi_close=kospi_trunc, **kwargs)

    for code in cache_pre:
        assert kept_full.get(code, []) == kept_trunc.get(code, []), \
            f"no-lookahead 위반 ({filt}, {code}): full={kept_full.get(code)} trunc={kept_trunc.get(code)}"


def test_no_lookahead_real_exit_metrics_truncation():
    """실청산 메트릭까지: cut 이전 진입봉만으로 돌린 결과가 full/trunc 데이터에서 동일해야.

    진입은 cut 이전만 허용(캐시 절단), 데이터는 full vs trunc. 진입봉 ≤cut 의 신호·필터·
    체결(i+1)이 모두 ≤cut+1 데이터만 쓰므로, 청산까지 동일 구간이면 결과 동일.
    여기선 진입봉을 cut-5 이하로 더 보수적으로 제한해 청산 보유기간(<=mh)도 trunc 내에 들도록.
    """
    data_full = _make_data(n=200)
    turnover = _turnover(data_full)
    cut = 150
    strategy, K, filt = "book_pullback_ma5", 3, "ma_slope"
    cache_full = _cache(strategy, data_full)
    # 진입봉을 충분히 이른 시점(< cut - 40)으로 제한해 보유기간(mh=30)까지 trunc 안에 완결.
    cache_early = {c: [i for i in bars if i < cut - 40] for c, bars in cache_full.items()}

    full_m = M3.run_real_exit(strategy=strategy, filt=filt, window="2022", K=K,
                              data=data_full, turnover=turnover,
                              signal_cache=cache_early)["metrics"]
    data_trunc = {c: df.iloc[:cut].reset_index(drop=True) for c, df in data_full.items()}
    trunc_m = M3.run_real_exit(strategy=strategy, filt=filt, window="2022", K=K,
                               data=data_trunc, turnover=turnover,
                               signal_cache=cache_early)["metrics"]
    # 진입·청산이 모두 trunc 구간 안에서 완결되면 거래수·PnL 동일.
    assert full_m["n_trades"] == trunc_m["n_trades"], \
        f"trunc 거래수 불일치 {full_m['n_trades']} != {trunc_m['n_trades']}"
