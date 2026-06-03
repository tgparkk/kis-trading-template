"""신규 진입 필터 (PIT / no-lookahead) — 백테스트 측정 전용.

★용도: book_portfolio_multiverse.py 의 진입 신호 캐시(종목별 triggered bar 인덱스)에
   추가 게이팅을 건다. 신호는 그대로 두고 "필터 통과분만 진입"하는 AND-필터다.
   라이브 전략(strategies/*/strategy.py·config.yaml)은 절대 건드리지 않는다.

설계 원칙(core/regime/regime_classifier.py 컨벤션 계승):
  - DB 호출 없음. 데이터(종목별 OHLCV df, KOSPI 종가)는 호출자가 주입.
  - 모든 통계는 trailing(≤t) 윈도우만 — No Look-Ahead.
  - 필터는 (data, signal_cache) → filtered_cache 형태. 각 (code, bar i) 의 keep/drop
    판정은 df.iloc[:i+1] (와 횡단면/시장 시계열의 ≤t 슬라이스)만 사용한다.

필터 3종:
  1. rs_rank   : 종목 N일 수익률의 유니버스 내 횡단면 백분위 ≥ threshold (진입봉 t 단면).
  2. mkt_rs    : 종목 N일 수익률 − KOSPI N일 수익률 > 0 (시장 아웃퍼폼).
  3. adx       : ADX(14) ≥ threshold (추세강도).
     ma_slope  : 종가 > MA(slope_window) 이고 MA 기울기 > 0.

no-lookahead 보장:
  - rs_rank: 각 종목 N일 수익률 시계열을 datetime 인덱스로 1회 산출(전부 trailing).
    timestamp t 단면 랭크는 "그 시점 값을 가진 종목들"의 t-값만 비교 → t 이후 데이터 무관.
  - mkt_rs: KOSPI N일 수익률을 date 인덱스로 산출. 진입봉 datetime 의 날짜 ≤t 값을 매핑.
  - adx/ma_slope: rolling/EWM 전부 trailing(min_periods 충족 전엔 NaN→drop).
"""
from __future__ import annotations

from typing import Dict, List, Optional

import numpy as np
import pandas as pd

FILTER_CHOICES = ("none", "rs_rank", "mkt_rs", "adx", "ma_slope")


# ============================================================================
# 종목별 trailing 지표 (전부 ≤t)
# ============================================================================

def _nday_return(close: pd.Series, n: int) -> pd.Series:
    """N봉 수익률 close[t]/close[t-n] - 1. trailing(현재봉 종가 vs n봉전 종가)."""
    return close / close.shift(n) - 1.0


def compute_adx(df: pd.DataFrame, period: int = 14) -> pd.Series:
    """Wilder ADX(period). 전부 trailing(rolling/EWM, min_periods 충족 전 NaN).

    high/low/close 컬럼 사용. +DI/-DI → DX → ADX(Wilder smoothing=EWM alpha=1/period).
    index 는 df 의 RangeIndex 를 그대로 사용(bar 위치).
    """
    high = df["high"].astype(float)
    low = df["low"].astype(float)
    close = df["close"].astype(float)

    up_move = high.diff()
    down_move = -low.diff()
    plus_dm = pd.Series(np.where((up_move > down_move) & (up_move > 0), up_move, 0.0),
                        index=df.index)
    minus_dm = pd.Series(np.where((down_move > up_move) & (down_move > 0), down_move, 0.0),
                         index=df.index)

    prev_close = close.shift(1)
    tr = pd.concat([
        high - low,
        (high - prev_close).abs(),
        (low - prev_close).abs(),
    ], axis=1).max(axis=1)

    # Wilder smoothing ≈ EWM(alpha=1/period). min_periods=period 로 워밍업 전 NaN.
    atr = tr.ewm(alpha=1.0 / period, min_periods=period, adjust=False).mean()
    plus_di = 100.0 * plus_dm.ewm(alpha=1.0 / period, min_periods=period, adjust=False).mean() / atr
    minus_di = 100.0 * minus_dm.ewm(alpha=1.0 / period, min_periods=period, adjust=False).mean() / atr
    di_sum = (plus_di + minus_di).replace(0.0, np.nan)
    dx = 100.0 * (plus_di - minus_di).abs() / di_sum
    adx = dx.ewm(alpha=1.0 / period, min_periods=period, adjust=False).mean()
    return adx


def compute_ma_slope_ok(df: pd.DataFrame, window: int = 50, slope_lb: int = 10) -> pd.Series:
    """종가 > MA(window) 이고 MA 기울기(MA[t]/MA[t-slope_lb]-1) > 0 인 bar=True. trailing."""
    close = df["close"].astype(float)
    ma = close.rolling(window, min_periods=window).mean()
    slope = ma / ma.shift(slope_lb) - 1.0
    return (close > ma) & (slope > 0)


# ============================================================================
# 횡단면 RS 랭크 시계열 (PIT)
# ============================================================================

def build_rs_return_panel(data: Dict[str, pd.DataFrame], n: int) -> Dict[str, pd.Series]:
    """종목별 N봉 수익률 시계열(index=datetime). 전부 trailing.

    data: {code: df(datetime, open, high, low, close, volume)}.
    반환: {code: Series(index=datetime, value=N봉 수익률)}. NaN(워밍업) 포함.
    """
    out: Dict[str, pd.Series] = {}
    for code, df in data.items():
        s = _nday_return(df["close"].astype(float), n)
        s.index = pd.to_datetime(df["datetime"])
        out[code] = s
    return out


def build_kospi_nday_return(kospi_close: pd.Series, n: int) -> pd.Series:
    """KOSPI N일 수익률(index=date→Timestamp). trailing."""
    cs = kospi_close.sort_index()
    cs.index = pd.to_datetime(cs.index)
    return _nday_return(cs, n)


# ============================================================================
# 필터 적용 — signal_cache(종목→bar 인덱스 리스트) 게이팅
# ============================================================================

def filter_cache_rs_rank(
    data: Dict[str, pd.DataFrame], cache: Dict[str, List[int]],
    n: int, threshold: float,
) -> Dict[str, List[int]]:
    """RS 랭크 필터: 진입봉 t 에서 종목 N봉수익률의 횡단면 백분위 ≥ threshold 만 통과.

    no-lookahead: 각 종목 N봉수익률은 trailing. timestamp t 단면 랭크는 그 시점 값을
    가진 종목들의 t-값만 비교(미래 무관). rank(pct=True) 는 [1/m, 1] 범위.
    """
    panel = build_rs_return_panel(data, n)
    # timestamp → {code: ret} (그 시점 값이 유효한 종목만)
    # 효율: 전 종목 시계열을 wide DataFrame 으로 합쳐 행(시점)별 pct 랭크 1회.
    wide = pd.DataFrame(panel)
    # 각 행(시점)에서 횡단면 pct 랭크. NaN(워밍업)은 랭크에서 제외(자동).
    rank = wide.rank(axis=1, pct=True)
    out: Dict[str, List[int]] = {}
    for code, bars in cache.items():
        df = data[code]
        dts = pd.to_datetime(df["datetime"])
        if code not in rank.columns:
            out[code] = []
            continue
        col = rank[code]
        kept: List[int] = []
        for i in bars:
            t = dts.iloc[i]
            r = col.get(t)
            if r is not None and pd.notna(r) and r >= threshold:
                kept.append(i)
        out[code] = kept
    return out


def filter_cache_mkt_rs(
    data: Dict[str, pd.DataFrame], cache: Dict[str, List[int]],
    kospi_close: pd.Series, n: int,
) -> Dict[str, List[int]]:
    """시장상대강도 필터: 종목 N봉수익률 − KOSPI N일수익률 > 0 (아웃퍼폼) 만 통과.

    no-lookahead: 종목·KOSPI 모두 trailing N봉/일 수익률. 진입봉 datetime 의 '날짜' 로
    KOSPI 수익률(일봉)을 asof(≤t) 매핑. KOSPI 값 없으면(워밍업) drop(보수적).
    """
    kospi_ret = build_kospi_nday_return(kospi_close, n)  # index=Timestamp(date)
    kospi_ret = kospi_ret.sort_index()
    out: Dict[str, List[int]] = {}
    for code, bars in cache.items():
        df = data[code]
        s = _nday_return(df["close"].astype(float), n)
        dts = pd.to_datetime(df["datetime"])
        kept: List[int] = []
        for i in bars:
            stock_ret = s.iloc[i]
            if pd.isna(stock_ret):
                continue
            t = dts.iloc[i]
            # ≤t 의 최신 KOSPI 일수익률 (asof). 분봉이면 당일 날짜<=t 이전봉으로 매핑.
            t_date = pd.Timestamp(t).normalize()
            sub = kospi_ret[kospi_ret.index <= t_date]
            if sub.empty or pd.isna(sub.iloc[-1]):
                continue
            if (stock_ret - float(sub.iloc[-1])) > 0:
                kept.append(i)
        out[code] = kept
    return out


def filter_cache_adx(
    data: Dict[str, pd.DataFrame], cache: Dict[str, List[int]],
    threshold: float, period: int = 14,
) -> Dict[str, List[int]]:
    """추세강도 필터: ADX(period) ≥ threshold 인 진입봉만 통과. trailing."""
    out: Dict[str, List[int]] = {}
    for code, bars in cache.items():
        df = data[code]
        adx = compute_adx(df, period)
        kept = [i for i in bars if pd.notna(adx.iloc[i]) and float(adx.iloc[i]) >= threshold]
        out[code] = kept
    return out


def filter_cache_ma_slope(
    data: Dict[str, pd.DataFrame], cache: Dict[str, List[int]],
    window: int = 50, slope_lb: int = 10,
) -> Dict[str, List[int]]:
    """추세강도(대안) 필터: 종가>MA(window) & MA기울기>0 인 진입봉만 통과. trailing."""
    out: Dict[str, List[int]] = {}
    for code, bars in cache.items():
        df = data[code]
        ok = compute_ma_slope_ok(df, window, slope_lb)
        kept = [i for i in bars if bool(ok.iloc[i])]
        out[code] = kept
    return out


def apply_entry_filter(
    data: Dict[str, pd.DataFrame], cache: Dict[str, List[int]],
    filt: str, threshold: float, n: int,
    kospi_close: Optional[pd.Series] = None,
    adx_period: int = 14, ma_window: int = 50, ma_slope_lb: int = 10,
) -> Dict[str, List[int]]:
    """디스패처. filt='none' 이면 입력 캐시 그대로 반환(회귀 동등성 보장)."""
    if filt == "none":
        return cache
    if filt == "rs_rank":
        return filter_cache_rs_rank(data, cache, n=n, threshold=threshold)
    if filt == "mkt_rs":
        return filter_cache_mkt_rs(data, cache, kospi_close=kospi_close, n=n)
    if filt == "adx":
        return filter_cache_adx(data, cache, threshold=threshold, period=adx_period)
    if filt == "ma_slope":
        return filter_cache_ma_slope(data, cache, window=ma_window, slope_lb=ma_slope_lb)
    raise ValueError(f"unknown entry filter {filt!r}. choices={FILTER_CHOICES}")
