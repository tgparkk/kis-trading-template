"""No Look-Ahead 검증 — 2트랙 PIT 시장국면 판별 모듈.

★이 테스트가 합격 핵심★. 트랙A(일봉 스윙) / 트랙B(분봉 데이트레이딩)
국면 라벨이 판정 시점(≤T 또는 ≤t)의 데이터만 사용함을 증명한다.

1. 절단 불변성(A): 전체 시계열 regime_at(T) == T까지 절단한 시계열의 값
2. 미래 불변성(A): T 이후 데이터를 바꿔도 regime_at(T) 불변 (디바운스 포함)
3. 장중 절단 불변성(B): bar i 라벨 == bars 0..i 만으로 계산한 값
4. trailing 윈도우: breadth/백분위/RV가 전부 과거 윈도우만
5. 정상 케이스 + 경계(데이터부족 안전 디폴트)
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from core.regime.regime_classifier import (
    DailyRegimeParams,
    IntradayRegimeParams,
    classify_daily,
    classify_intraday,
    regime_at,
)


# ============================================================================
# Fixtures — 합성 시계열 (DB 불필요)
# ============================================================================

def _make_daily_series(n: int = 600, seed: int = 7) -> tuple[pd.Series, pd.DataFrame]:
    """추세상승(전반)→하락(중반)→상승(후반) KOSPI 종가 + breadth용 종목 패널."""
    rng = np.random.default_rng(seed)
    dates = pd.bdate_range("2021-01-04", periods=n)
    # 구간별 드리프트: 상승 / 하락 / 상승
    drift = np.concatenate([
        np.full(n // 3, 0.0015),
        np.full(n // 3, -0.0020),
        np.full(n - 2 * (n // 3), 0.0018),
    ])
    noise = rng.normal(0, 0.006, n)
    logret = drift + noise
    close = pd.Series(2000 * np.exp(np.cumsum(logret)), index=dates, name="close")

    # breadth 패널: 30 종목, 지수와 상관 있게 생성
    cols = {}
    for k in range(30):
        s_noise = rng.normal(0, 0.012, n)
        s_logret = drift * rng.uniform(0.6, 1.4) + s_noise
        cols[f"S{k:02d}"] = 1000 * np.exp(np.cumsum(s_logret))
    panel = pd.DataFrame(cols, index=dates)
    return close, panel


def _make_intraday_df(seed: int = 11, n_min: int = 200, n_codes: int = 20):
    """당일 분봉 패널 (09:00~) — 대형주 바스켓 포함."""
    rng = np.random.default_rng(seed)
    times = pd.date_range("2024-03-15 09:00:00", periods=n_min, freq="1min")
    basket = ["005930", "035420", "035720", "373220"]
    codes = basket + [f"O{k:03d}" for k in range(n_codes - len(basket))]
    rows = []
    for code in codes:
        drift = 0.00025 if code in basket else rng.normal(0.0001, 0.0003)
        lr = drift + rng.normal(0, 0.0009, n_min)
        px = 70000 * np.exp(np.cumsum(lr))
        vol = rng.integers(100, 1000, n_min)
        for i, t in enumerate(times):
            o = px[i] * (1 - 0.0003)
            rows.append({
                "stock_code": code, "datetime": t, "time": t.strftime("%H%M%S"),
                "open": o, "high": max(o, px[i]) * 1.0005,
                "low": min(o, px[i]) * 0.9995, "close": px[i], "volume": int(vol[i]),
            })
    df = pd.DataFrame(rows)
    prev_close = {c: float(df[df.stock_code == c].sort_values("datetime").open.iloc[0]) for c in codes}
    return df, basket, prev_close


# ============================================================================
# 1. 절단 불변성 (트랙A)
# ============================================================================

def test_daily_truncation_invariance():
    """전체 시계열로 계산한 regime_at(T) == T까지 절단한 시계열로 계산한 값."""
    close, panel = _make_daily_series()
    params = DailyRegimeParams()

    full = classify_daily(close, panel, params)
    # 윈도우가 충분히 쌓인 지점들에서 검사
    test_idxs = [200, 300, 400, 500, len(close) - 1]
    for ti in test_idxs:
        T = close.index[ti]
        truncated = classify_daily(close.iloc[: ti + 1], panel.iloc[: ti + 1], params)
        assert truncated["regime"].iloc[-1] == full["regime"].loc[T], (
            f"절단 불변성 위반 @ {T}: trunc={truncated['regime'].iloc[-1]} full={full['regime'].loc[T]}"
        )
        assert truncated["vol_class"].iloc[-1] == full["vol_class"].loc[T]


# ============================================================================
# 2. 미래 불변성 (트랙A) — 디바운스 포함
# ============================================================================

def test_daily_future_immutability():
    """T 이후 데이터를 임의로 바꿔도 regime_at(T) 불변 (디바운스가 미래를 안 봄)."""
    close, panel = _make_daily_series()
    params = DailyRegimeParams(confirm_days=3)
    base = classify_daily(close, panel, params)

    ti = 450
    T = close.index[ti]
    # T 이후를 극단적으로 변조 (폭락 시퀀스)
    close2 = close.copy()
    close2.iloc[ti + 1:] = close2.iloc[ti] * 0.3
    panel2 = panel.copy()
    panel2.iloc[ti + 1:] = panel2.iloc[ti].values * 0.3

    perturbed = classify_daily(close2, panel2, params)
    # T 및 그 이전 모든 라벨이 불변이어야
    for j in range(params.ma_window + 5, ti + 1):
        Tj = close.index[j]
        assert base["regime"].loc[Tj] == perturbed["regime"].loc[Tj], (
            f"미래 변조가 과거 라벨 변경 @ {Tj}"
        )
        assert base["vol_class"].loc[Tj] == perturbed["vol_class"].loc[Tj]


def test_daily_debounce_is_forward_only():
    """디바운스(confirm_days)가 forward-only — 미래 봉 변경이 과거 확정라벨에 무영향."""
    close, panel = _make_daily_series()
    params = DailyRegimeParams(confirm_days=5)
    full = classify_daily(close, panel, params)
    ti = 480
    T = close.index[ti]
    truncated = classify_daily(close.iloc[: ti + 1], panel.iloc[: ti + 1], params)
    assert truncated["regime"].iloc[-1] == full["regime"].loc[T]


# ============================================================================
# 3. 장중 절단 불변성 (트랙B)
# ============================================================================

def test_intraday_truncation_invariance():
    """bar i의 regime == bars 0..i 만으로 계산한 값. 이후 분봉 변경 무영향."""
    df, basket, prev_close = _make_intraday_df()
    params = IntradayRegimeParams(proxy_basket=basket)

    full = classify_intraday(df, prev_close, params)
    times = sorted(df["datetime"].unique())
    # OR 확정 이후 시점들 검사
    for ti in [30, 60, 120, len(times) - 1]:
        t = times[ti]
        df_trunc = df[df["datetime"] <= t]
        trunc = classify_intraday(df_trunc, prev_close, params)
        assert trunc["direction"].iloc[-1] == full["direction"].loc[t], (
            f"장중 절단 불변성 위반 @ {t}"
        )
        assert trunc["trendiness"].iloc[-1] == full["trendiness"].loc[t]


def test_intraday_future_immutability():
    """이후 분봉을 극단 변조해도 bar i 라벨 불변."""
    df, basket, prev_close = _make_intraday_df()
    params = IntradayRegimeParams(proxy_basket=basket)
    base = classify_intraday(df, prev_close, params)

    times = sorted(df["datetime"].unique())
    cut = times[80]
    df2 = df.copy()
    mask = df2["datetime"] > cut
    df2.loc[mask, ["open", "high", "low", "close"]] *= 0.5
    perturbed = classify_intraday(df2, prev_close, params)

    for ti in range(20, 81):
        t = times[ti]
        assert base["direction"].loc[t] == perturbed["direction"].loc[t], f"미래 변조 누설 @ {t}"
        assert base["trendiness"].loc[t] == perturbed["trendiness"].loc[t]


# ============================================================================
# 4. trailing 윈도우 검증
# ============================================================================

def test_breadth_uses_trailing_window_only():
    """breadth가 과거 윈도우만 — 미래 패널 변경이 과거 breadth에 무영향."""
    close, panel = _make_daily_series()
    params = DailyRegimeParams()
    full = classify_daily(close, panel, params)
    ti = 400
    T = close.index[ti]
    panel2 = panel.copy()
    panel2.iloc[ti + 1:] *= 5.0  # 미래 폭등
    full2 = classify_daily(close, panel2, params)
    assert full["breadth"].loc[T] == pytest.approx(full2["breadth"].loc[T], abs=1e-9)


def test_vol_percentile_uses_trailing_window_only():
    """변동성 백분위가 trailing — 미래 변동성 폭증이 과거 vol_pct에 무영향."""
    close, panel = _make_daily_series()
    params = DailyRegimeParams()
    full = classify_daily(close, panel, params)
    ti = 400
    T = close.index[ti]
    close2 = close.copy()
    # 미래에 변동성 큰 노이즈 주입
    rng = np.random.default_rng(99)
    close2.iloc[ti + 1:] *= (1 + rng.normal(0, 0.1, len(close2) - ti - 1)).cumprod()
    full2 = classify_daily(close2, panel, params)
    assert full["vol_pct"].loc[T] == pytest.approx(full2["vol_pct"].loc[T], abs=1e-9)


def test_intraday_rv_trailing():
    """장중 RV/누적 통계가 ≤t만 사용 (3번 테스트의 보강 — 명시적)."""
    df, basket, prev_close = _make_intraday_df()
    params = IntradayRegimeParams(proxy_basket=basket)
    full = classify_intraday(df, prev_close, params)
    times = sorted(df["datetime"].unique())
    t = times[100]
    df_trunc = df[df["datetime"] <= t]
    trunc = classify_intraday(df_trunc, prev_close, params)
    assert trunc["vol_class"].iloc[-1] == full["vol_class"].loc[t]


# ============================================================================
# 5. 정상 케이스 + 경계(데이터부족 안전 디폴트)
# ============================================================================

def test_uptrend_sequence_is_bull():
    """뚜렷한 추세 상승 + 광범위 breadth → BULL."""
    rng = np.random.default_rng(3)
    dates = pd.bdate_range("2021-01-04", periods=400)
    logret = 0.002 + rng.normal(0, 0.003, 400)
    close = pd.Series(2000 * np.exp(np.cumsum(logret)), index=dates)
    cols = {f"S{k}": 1000 * np.exp(np.cumsum(0.002 + rng.normal(0, 0.004, 400))) for k in range(20)}
    panel = pd.DataFrame(cols, index=dates)
    res = classify_daily(close, panel, DailyRegimeParams())
    assert res["regime"].iloc[-1] == "bull"


def test_downtrend_sequence_is_bear():
    rng = np.random.default_rng(5)
    dates = pd.bdate_range("2021-01-04", periods=400)
    logret = -0.002 + rng.normal(0, 0.003, 400)
    close = pd.Series(2000 * np.exp(np.cumsum(logret)), index=dates)
    cols = {f"S{k}": 1000 * np.exp(np.cumsum(-0.002 + rng.normal(0, 0.004, 400))) for k in range(20)}
    panel = pd.DataFrame(cols, index=dates)
    res = classify_daily(close, panel, DailyRegimeParams())
    assert res["regime"].iloc[-1] == "bear"


def test_insufficient_daily_data_safe_default():
    """데이터 부족 시 안전 디폴트(sideways/LOW), 예외 없이."""
    dates = pd.bdate_range("2021-01-04", periods=30)
    close = pd.Series(np.linspace(2000, 2100, 30), index=dates)
    panel = pd.DataFrame({f"S{k}": np.linspace(1000, 1010, 30) for k in range(5)}, index=dates)
    res = classify_daily(close, panel, DailyRegimeParams())  # ma_window=120 > 30
    assert res["regime"].iloc[-1] == "sideways"
    assert res["vol_class"].iloc[-1] == "LOW"


def test_insufficient_intraday_data_safe_default():
    """OR 미확정(첫 봉 직후) 시 안전 디폴트, 예외 없이."""
    df, basket, prev_close = _make_intraday_df(n_min=5)
    params = IntradayRegimeParams(proxy_basket=basket, or_minutes=15)
    res = classify_intraday(df, prev_close, params)
    # OR 미확정 → RANGE/NEUTRAL 안전 디폴트
    assert res["trendiness"].iloc[0] == "range"
    assert res["direction"].iloc[0] == "neutral"


# ============================================================================
# regime_at 디스패처 (시계열 입력 경로)
# ============================================================================

def test_regime_at_daily_dispatch():
    close, panel = _make_daily_series()
    T = close.index[400]
    out = regime_at(T, granularity="daily", close_series=close, breadth_panel=panel)
    assert out["regime"] in ("bull", "bear", "sideways")
    assert out["vol_class"] in ("HIGH", "LOW")
    assert out["asof"] == T


def _make_intraday_15min_df(seed: int = 1, n_bars: int = 26, n_codes: int = 20,
                            drift: float = 0.004):
    """15분봉 당일 패널 — 강한 추세 상승(트렌드 라벨 발화 확인용)."""
    rng = np.random.default_rng(seed)
    times = pd.date_range("2024-03-15 09:00:00", periods=n_bars, freq="15min")
    basket = ["005930", "035420", "035720", "373220"]
    codes = basket + [f"O{k:03d}" for k in range(n_codes - len(basket))]
    rows = []
    for code in codes:
        d = drift if code in basket else drift * 0.9
        lr = d + rng.normal(0, 0.0008, n_bars)
        px = 70000 * np.exp(np.cumsum(lr))
        for i, t in enumerate(times):
            o = px[i] * (1 - 0.0003)
            rows.append({
                "stock_code": code, "datetime": t,
                "open": o, "high": max(o, px[i]) * 1.0005,
                "low": min(o, px[i]) * 0.9995, "close": px[i], "volume": 500,
            })
    return pd.DataFrame(rows), basket, times


# ============================================================================
# 6. 봉 간격 인지(granularity-aware) — 15분봉
# ============================================================================

def test_intraday_15min_emits_trend_labels():
    """★15분봉에서 시간기반 윈도가 봉 개수로 환산돼 trend 라벨이 실제로 발화."""
    df, basket, _ = _make_intraday_15min_df()
    res = classify_intraday(df, None, IntradayRegimeParams(proxy_basket=basket))
    # 강추세 상승일이면 trend·up 이 0이 아니어야(전부 range 였던 구버그 회귀 방지)
    assert (res["trendiness"] == "trend").sum() > 0, "15분봉 trend 라벨 미발화(봉 환산 실패)"
    assert (res["direction"] == "up").sum() > 0


def test_intraday_bar_interval_autoinfer_matches_explicit():
    """bar_interval_min=None 자동추론 == 명시 지정 결과 (1분봉 하위호환 보장)."""
    df, basket, prev_close = _make_intraday_df()
    auto = classify_intraday(df, prev_close, IntradayRegimeParams(proxy_basket=basket))
    explicit = classify_intraday(
        df, prev_close, IntradayRegimeParams(proxy_basket=basket, bar_interval_min=1)
    )
    assert auto.equals(explicit)


def test_intraday_15min_truncation_invariance():
    """15분봉도 절단 불변성 유지 — bar i 라벨 == bars 0..i 만으로 계산한 값(PIT)."""
    df, basket, times = _make_intraday_15min_df()
    params = IntradayRegimeParams(proxy_basket=basket)
    full = classify_intraday(df, None, params)
    for ti in [4, 10, 18, len(times) - 1]:
        t = times[ti]
        trunc = classify_intraday(df[df["datetime"] <= t], None, params)
        assert trunc["trendiness"].iloc[-1] == full["trendiness"].loc[t], f"절단 위반 @ {t}"
        assert trunc["direction"].iloc[-1] == full["direction"].loc[t]


def test_regime_at_minute_dispatch():
    df, basket, prev_close = _make_intraday_df()
    t = sorted(df["datetime"].unique())[120]
    out = regime_at(
        t, granularity="minute", day_minute_df=df, prev_close=prev_close,
        params=IntradayRegimeParams(proxy_basket=basket),
    )
    assert out["direction"] in ("up", "down", "neutral")
    assert out["trendiness"] in ("trend", "range")
    assert out["vol_class"] in ("HIGH", "LOW")
