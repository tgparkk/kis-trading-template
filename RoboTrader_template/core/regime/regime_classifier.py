"""2-트랙 PIT 시장국면 판별 — 순수 함수 구현.

설계 원칙(regime_analysis.py 컨벤션 계승):
  - DB 호출 없음. KOSPI 종가/패널/분봉 fetch는 호출자 책임.
  - 모든 통계는 trailing(≤T) 윈도우만 — No Look-Ahead.
  - 파라미터는 dataclass로 외부 주입(멀티버스 스윕 대비).

트랙A(daily): classify_daily(close, breadth_panel, params)
트랙B(minute): classify_intraday(day_minute_df, prev_close, params)
공통 디스패처: regime_at(ts, granularity, ...)
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional

import numpy as np
import pandas as pd

# 트랙B 합성 프록시 기본 바스켓 (minute_candles 풀커버 대형주).
# 005930 삼성전자·035420 NAVER·035720 카카오·373220 LG엔솔.
DEFAULT_BIGCAP_BASKET: List[str] = ["005930", "035420", "035720", "373220"]


# ============================================================================
# 파라미터 (멀티버스 스윕 대비, 외부 주입)
# ============================================================================

@dataclass(frozen=True)
class DailyRegimeParams:
    """트랙A(스윙·일봉) 국면 파라미터."""
    ma_window: int = 120          # 추세 기준 SMA 길이
    slope_lb: int = 20            # MA 기울기 측정 구간(일)
    breadth_window: int = 120     # %above MA breadth 기준 SMA 길이
    breadth_hi: float = 0.55      # BULL 확정 breadth 하한
    breadth_lo: float = 0.45      # BEAR 확정 breadth 상한
    vol_window: int = 20          # 실현변동성 측정 구간
    vol_rank_window: int = 252    # 변동성 백분위 trailing 윈도우
    vol_rank_min: int = 60        # 백분위 최소 표본
    vol_pct_hi: float = 0.67      # HIGH_VOL 백분위 컷
    confirm_days: int = 3         # forward-only 디바운스(0=비활성)


@dataclass(frozen=True)
class IntradayRegimeParams:
    """트랙B(데이트레이딩·당일 장중) 국면 파라미터.

    ★봉 간격 인지(granularity-aware): or_minutes/vwap_slope_lb/vol_window 는 모두
    '분(minute)' 단위로 정의되며, classify_intraday 내부에서 입력 분봉의 실제 봉 간격
    (bar_interval_min)으로 나눠 '봉 개수'로 환산해 적용한다. bar_interval_min=None 이면
    df.datetime 의 중앙 간격에서 자동 추론(1분봉이면 1 → 기존과 동일, 하위호환).
    """
    proxy_basket: List[str] = field(default_factory=lambda: list(DEFAULT_BIGCAP_BASKET))
    or_minutes: int = 15          # 개장범위(OR) 길이(분, 시간기반)
    dir_thresh: float = 0.003     # UP/DOWN 누적수익 컷(±0.3%)
    breadth_hi: float = 0.60      # breadth 동조 강세 극단
    breadth_lo: float = 0.40      # breadth 동조 약세 극단
    vwap_slope_lb: int = 30       # VWAP 기울기 측정창(분 → 봉 개수로 환산)
    gap_atr_thr: float = 1.0      # 갭 분류 컷(|gap/ATR|)
    vol_window: int = 20          # 장중 RV 측정 구간(분 → 봉 개수로 환산)
    vol_pct_hi: float = 0.67      # HIGH_VOL 백분위 컷
    confirm_bars: int = 3         # 장중 forward-only 디바운스(봉 개수 — 분 아님)
    bar_interval_min: Optional[int] = None  # 입력 봉 간격(분). None=datetime서 자동추론


# ============================================================================
# 공통 헬퍼 — forward-only 디바운스
# ============================================================================

def _infer_bar_interval_min(times: pd.DatetimeIndex) -> int:
    """분봉 시각 인덱스에서 봉 간격(분)을 추론. 중앙 간격 사용(결측·갭 강건).

    봉이 1개 이하면 1분으로 폴백(기존 1분봉 동작과 동일). 0/음수 방어.
    """
    if times is None or len(times) < 2:
        return 1
    diffs = pd.Series(pd.to_datetime(pd.Index(times)).sort_values()).diff().dropna()
    if diffs.empty:
        return 1
    med = diffs.dt.total_seconds().median() / 60.0
    iv = int(round(med))
    return iv if iv >= 1 else 1


def _to_bars(minutes: int, bar_interval_min: int) -> int:
    """시간 기반 윈도(분)를 봉 개수로 환산. 최소 1봉 보장(0 윈도 방지)."""
    if bar_interval_min <= 0:
        bar_interval_min = 1
    return max(1, int(round(minutes / bar_interval_min)))


def _confirm_debounce(labels: pd.Series, n: int) -> pd.Series:
    """새 라벨이 n회 연속 유지될 때만 전환 — 과거만 사용(forward-only).

    각 위치 i의 출력은 labels[0..i]에만 의존하므로 PIT-safe.
    n<=1 이면 디바운스 비활성(입력 그대로).
    """
    if n <= 1 or len(labels) == 0:
        return labels.copy()
    vals = labels.tolist()
    cur = vals[0]
    prev = vals[0]
    run = 1
    out = []
    for v in vals:
        if v == prev:
            run += 1
        else:
            prev = v
            run = 1
        if run >= n:
            cur = v
        out.append(cur)
    return pd.Series(out, index=labels.index, name=labels.name)


# ============================================================================
# 트랙A — 일봉(스윙) 국면
# ============================================================================

def classify_daily(
    close_series: pd.Series,
    breadth_panel: Optional[pd.DataFrame],
    params: Optional[DailyRegimeParams] = None,
) -> pd.DataFrame:
    """KOSPI 종가 시계열을 일별 국면 라벨로 분류 (전부 trailing, PIT-safe).

    Args:
        close_series: KOSPI 종가 (index=date, 정렬 가정).
        breadth_panel: 전종목/큐레이션 풀 종가 패널 (index=date, columns=stock_code).
                       None 이면 breadth 확정 단계 생략(추세+기울기만).
        params: DailyRegimeParams.

    Returns:
        DataFrame(index=date) 컬럼:
          regime ∈ {bull, bear, sideways}, vol_class ∈ {HIGH, LOW},
          breadth(float|NaN), vol_pct(float|NaN), ma, slope, above(bool).
    """
    p = params or DailyRegimeParams()
    close = close_series.sort_index()
    idx = close.index

    # --- 추세(방향) 1차 판정 ---
    ma = close.rolling(p.ma_window, min_periods=p.ma_window).mean()
    slope = ma / ma.shift(p.slope_lb) - 1.0
    above = close > ma

    raw = pd.Series("sideways", index=idx, name="regime_raw")
    raw[(above) & (slope > 0)] = "bull"
    raw[(~above) & (slope < 0)] = "bear"
    # MA 미정의(초기 구간)는 안전 디폴트 sideways
    raw[ma.isna() | slope.isna()] = "sideways"

    # --- 시장폭(breadth) 확정 ---
    if breadth_panel is not None and not breadth_panel.empty:
        breadth = _breadth_above_ma(breadth_panel.reindex(idx), p.breadth_window)
    else:
        breadth = pd.Series(np.nan, index=idx)

    confirmed = raw.copy()
    has_b = breadth.notna()
    # BULL 인데 breadth 미충족 → SIDEWAYS 완화
    weak_bull = (raw == "bull") & has_b & (breadth < p.breadth_hi)
    confirmed[weak_bull] = "sideways"
    # BEAR 인데 breadth 미충족 → SIDEWAYS 완화
    weak_bear = (raw == "bear") & has_b & (breadth > p.breadth_lo)
    confirmed[weak_bear] = "sideways"

    # --- forward-only 디바운스 ---
    regime = _confirm_debounce(confirmed, p.confirm_days)
    regime.name = "regime"

    # --- 변동성 라벨(직교 축, trailing 백분위) ---
    vol_pct = _vol_percentile(close, p.vol_window, p.vol_rank_window, p.vol_rank_min)
    vol_class = pd.Series(
        np.where(vol_pct >= p.vol_pct_hi, "HIGH", "LOW"), index=idx, name="vol_class"
    )
    # 백분위 미정의 → 안전 디폴트 LOW (이미 np.where가 NaN>=hi=False 처리)

    return pd.DataFrame({
        "regime": regime,
        "vol_class": vol_class,
        "breadth": breadth,
        "vol_pct": vol_pct,
        "ma": ma,
        "slope": slope,
        "above": above,
    })


def _breadth_above_ma(panel: pd.DataFrame, win: int) -> pd.Series:
    """각 일자 (종목별 close > 종목 SMA(win)) 비율. 전부 trailing."""
    ma = panel.rolling(win, min_periods=win).mean()
    above = panel > ma
    valid = above.where(ma.notna())  # MA 미정의 종목은 분모서 제외
    num = valid.sum(axis=1, skipna=True)
    den = valid.count(axis=1)
    out = num / den.replace(0, np.nan)
    return out


def _vol_percentile(close: pd.Series, vol_win: int, rank_win: int, rank_min: int) -> pd.Series:
    """20일RV의 252일 trailing 백분위(마지막 값의 rank). 전부 ≤T."""
    lr = np.log(close / close.shift(1))
    vol = lr.rolling(vol_win, min_periods=vol_win).std() * np.sqrt(252)

    def _last_rank(x: np.ndarray) -> float:
        s = pd.Series(x).dropna()
        if len(s) < 2:
            return np.nan
        return s.rank(pct=True).iloc[-1]

    pct = vol.rolling(rank_win, min_periods=rank_min).apply(_last_rank, raw=True)
    return pct


# ============================================================================
# 트랙B — 분봉(데이트레이딩) 국면
# ============================================================================

def classify_intraday(
    day_minute_df: pd.DataFrame,
    prev_close: Optional[Dict[str, float]] = None,
    params: Optional[IntradayRegimeParams] = None,
) -> pd.DataFrame:
    """당일 분봉 패널을 분봉별 장중 국면으로 분류 (≤t 누적, PIT-safe).

    Args:
        day_minute_df: 당일 분봉 (columns: stock_code, datetime, open, high, low,
                       close, volume). 여러 종목·시각이 long 포맷으로 섞여 있음.
        prev_close: {stock_code: 전일 일봉 종가} — 갭 계산용. None이면 갭 FLAT.
        params: IntradayRegimeParams.

    Returns:
        DataFrame(index=datetime, time-bar 단위) 컬럼:
          direction ∈ {up, down, neutral}, trendiness ∈ {trend, range},
          vol_class ∈ {HIGH, LOW}, bias ∈ {gap_up, gap_down, flat},
          mkt_ret(누적), vwap_pos, adv_ratio.
    """
    p = params or IntradayRegimeParams()
    df = day_minute_df.copy()
    if df.empty:
        return pd.DataFrame(
            columns=["direction", "trendiness", "vol_class", "bias",
                     "mkt_ret", "vwap_pos", "adv_ratio"]
        )
    df["datetime"] = pd.to_datetime(df["datetime"])
    df = df.sort_values(["stock_code", "datetime"])
    basket = set(p.proxy_basket)

    # --- (a) 합성지수: 대형주 등가중 당일 누적수익 (현재봉까지) ---
    bdf = df[df["stock_code"].isin(basket)]
    if bdf.empty:
        # 바스켓 분봉 없음 → 유니버스 전체로 폴백
        bdf = df
    mkt = _synth_cum_return(bdf)              # index=datetime
    vwap_pos = _synth_vwap_pos(bdf)           # index=datetime

    # --- (b) 합성 시장폭(breadth): 전 유니버스 단면 누적수익>0 비율 ---
    adv = _adv_ratio(df)                       # index=datetime

    times = mkt.index
    # --- 봉 간격(분) 인지: 시간기반 윈도(vwap_slope_lb/vol_window)를 봉 개수로 환산 ---
    bar_iv = p.bar_interval_min if p.bar_interval_min else _infer_bar_interval_min(times)
    vwap_slope_bars = _to_bars(p.vwap_slope_lb, bar_iv)
    # RV std 는 ≥2 표본 필요 → 환산 후 최소 2봉 보장(거친 봉에서 vol_class 무효화 방지).
    vol_bars = max(2, _to_bars(p.vol_window, bar_iv))

    # --- 개장범위(OR): 첫 or_minutes 분, 바스켓 등가중 정규화가격 H/L (시간기반·간격무관) ---
    or_high, or_low, or_ready = _opening_range(bdf, times, p.or_minutes)

    # --- bias(개장전 확정): 바스켓 평균 갭 ---
    bias = _gap_bias(bdf, prev_close, p)

    # --- direction (≤t) ---
    direction = pd.Series("neutral", index=times, name="direction")
    up = (mkt > p.dir_thresh) & (vwap_pos > 0)
    down = (mkt < -p.dir_thresh) & (vwap_pos < 0)
    direction[up] = "up"
    direction[down] = "down"

    # --- VWAP 기울기 (최근 vwap_slope_lb 분 = vwap_slope_bars 봉, ≤t) ---
    vwap_slope = vwap_pos - vwap_pos.shift(vwap_slope_bars)

    # --- OR 돌파(합성 정규화가격 = mkt 누적수익을 가격축으로 사용) ---
    # mkt 자체가 등가중 누적수익이므로 OR도 같은 축으로 산출됨.
    or_break_up = or_ready & (mkt > or_high)
    or_break_dn = or_ready & (mkt < or_low)

    # --- trendiness (≤t): OR 돌파 + VWAP기울기 방향일치 + breadth 동조 극단 ---
    trend_up = or_break_up & (vwap_slope > 0) & (adv > p.breadth_hi)
    trend_dn = or_break_dn & (vwap_slope < 0) & (adv < p.breadth_lo)
    trendiness = pd.Series("range", index=times, name="trendiness")
    trendiness[trend_up | trend_dn] = "trend"
    # OR 미확정 구간은 무조건 range(안전 디폴트)
    trendiness[~or_ready] = "range"

    # --- 장중 변동성(시각정규화 백분위 대용: 당일 분봉수익 std의 self-trailing 백분위) ---
    vol_pct = _intraday_vol_pct(mkt, vol_bars)
    vol_class = pd.Series(
        np.where(vol_pct >= p.vol_pct_hi, "HIGH", "LOW"), index=times, name="vol_class"
    )

    # --- forward-only 장중 디바운스 ---
    direction = _confirm_debounce(direction, p.confirm_bars)
    trendiness = _confirm_debounce(trendiness, p.confirm_bars)

    return pd.DataFrame({
        "direction": direction,
        "trendiness": trendiness,
        "vol_class": vol_class,
        "bias": pd.Series(bias, index=times),
        "mkt_ret": mkt,
        "vwap_pos": vwap_pos,
        "adv_ratio": adv,
    })


def _synth_cum_return(bdf: pd.DataFrame) -> pd.Series:
    """바스켓 등가중 당일 누적수익 Mkt_t = mean_i(close_i,t / open_i,first - 1)."""
    out = {}
    for code, g in bdf.groupby("stock_code"):
        g = g.sort_values("datetime")
        base = float(g["open"].iloc[0]) if g["open"].iloc[0] else float(g["close"].iloc[0])
        if base == 0:
            continue
        out[code] = (g.set_index("datetime")["close"] / base - 1.0)
    if not out:
        return pd.Series(dtype=float)
    mkt = pd.DataFrame(out).mean(axis=1)
    mkt.name = "mkt_ret"
    return mkt.sort_index()


def _synth_vwap_pos(bdf: pd.DataFrame) -> pd.Series:
    """바스켓 평균 VWAP 위치: mean_i(close_i,t / vwap_i,t - 1). 누적(≤t)."""
    pos = {}
    for code, g in bdf.groupby("stock_code"):
        g = g.sort_values("datetime").set_index("datetime")
        cum_pv = (g["close"] * g["volume"]).cumsum()
        cum_v = g["volume"].cumsum().replace(0, np.nan)
        vwap = cum_pv / cum_v
        pos[code] = (g["close"] / vwap - 1.0)
    if not pos:
        return pd.Series(dtype=float)
    return pd.DataFrame(pos).mean(axis=1).sort_index()


def _adv_ratio(df: pd.DataFrame) -> pd.Series:
    """각 시각 t별 (당일 누적수익>0 종목수)/(전체). 현재봉 단면(≤t)."""
    g = df.sort_values(["stock_code", "datetime"]).copy()
    base = g.groupby("stock_code")["open"].transform("first")
    base = base.where(base != 0, g.groupby("stock_code")["close"].transform("first"))
    g["ret"] = g["close"] / base - 1.0
    g["adv"] = (g["ret"] > 0).astype(float)
    out = g.groupby("datetime")["adv"].mean()
    out.name = "adv_ratio"
    return out.sort_index()


def _opening_range(bdf: pd.DataFrame, times: pd.DatetimeIndex, or_min: int):
    """첫 or_min 분 동안의 합성지수(누적수익축) H/L. 이후 시점에만 유효(forward-only).

    or_ready[t] = (t가 OR 윈도우 종료 시각 이후)일 때만 True → OR 미확정 전엔 미사용.
    """
    if len(times) == 0:
        empty = pd.Series(dtype=bool)
        return np.nan, np.nan, empty
    t0 = times[0]
    or_end = t0 + pd.Timedelta(minutes=or_min)
    mkt = _synth_cum_return(bdf)
    in_or = mkt.index < or_end
    if in_or.sum() == 0:
        or_high = or_low = np.nan
    else:
        or_high = float(mkt[in_or].max())
        or_low = float(mkt[in_or].min())
    or_ready = pd.Series(mkt.index >= or_end, index=times)
    return or_high, or_low, or_ready


def _gap_bias(bdf: pd.DataFrame, prev_close: Optional[Dict[str, float]],
              p: IntradayRegimeParams) -> str:
    """개장전 확정 갭 bias. 바스켓 평균 (open_first - prev_close)/prev_close,
    당일 분봉 ATR 대용(첫 or_minutes 봉 평균 range)으로 정규화."""
    if not prev_close:
        return "flat"
    gaps = []
    ranges = []
    for code, g in bdf.groupby("stock_code"):
        pc = prev_close.get(code)
        if not pc:
            continue
        g = g.sort_values("datetime")
        op = float(g["open"].iloc[0])
        gaps.append(op / pc - 1.0)
        rng = (g["high"] - g["low"]) / pc
        ranges.append(float(rng.head(max(p.or_minutes, 1)).mean()))
    if not gaps:
        return "flat"
    gap = float(np.mean(gaps))
    atr = float(np.mean(ranges)) if ranges else 0.0
    norm = gap / atr if atr > 0 else gap
    if norm >= p.gap_atr_thr:
        return "gap_up"
    if norm <= -p.gap_atr_thr:
        return "gap_down"
    return "flat"


def _intraday_vol_pct(mkt: pd.Series, vol_win: int) -> pd.Series:
    """장중 분봉수익 std의 self-trailing 백분위(≤t). 시각정규화 1차 대용.

    full 시계열용 일배치(라이브 시각정규화는 과거 동일 분-of-day 분포 필요 — 후속).
    """
    ret = mkt.diff()
    vol = ret.rolling(vol_win, min_periods=max(2, vol_win // 2)).std()

    def _last_rank(x: np.ndarray) -> float:
        s = pd.Series(x).dropna()
        if len(s) < 2:
            return np.nan
        return s.rank(pct=True).iloc[-1]

    return vol.expanding(min_periods=max(2, vol_win)).apply(_last_rank, raw=True)


# ============================================================================
# 공통 디스패처
# ============================================================================

def regime_at(
    ts,
    granularity: str = "daily",
    *,
    close_series: Optional[pd.Series] = None,
    breadth_panel: Optional[pd.DataFrame] = None,
    day_minute_df: Optional[pd.DataFrame] = None,
    prev_close: Optional[Dict[str, float]] = None,
    params=None,
) -> dict:
    """판정 시점 ts의 국면 라벨(dict)을 반환. PIT: ts 이하 데이터만 사용.

    granularity='daily' → 트랙A (close_series[+breadth_panel] 필요)
    granularity='minute' → 트랙B (day_minute_df[+prev_close] 필요)

    반환(daily): {regime, vol_class, breadth, vol_pct, asof}
    반환(minute): {direction, trendiness, vol_class, bias, asof}
    데이터 없으면 안전 디폴트 반환(예외 없음).
    """
    if granularity == "daily":
        if close_series is None or len(close_series) == 0:
            return {"regime": "sideways", "vol_class": "LOW", "asof": ts}
        dp = params if isinstance(params, DailyRegimeParams) else DailyRegimeParams()
        cs = close_series.sort_index()
        cs = cs[cs.index <= ts]
        bp = None
        if breadth_panel is not None and not breadth_panel.empty:
            bp = breadth_panel[breadth_panel.index <= ts]
        if len(cs) == 0:
            return {"regime": "sideways", "vol_class": "LOW", "asof": ts}
        res = classify_daily(cs, bp, dp)
        last = res.iloc[-1]
        return {
            "regime": str(last["regime"]),
            "vol_class": str(last["vol_class"]),
            "breadth": None if pd.isna(last["breadth"]) else float(last["breadth"]),
            "vol_pct": None if pd.isna(last["vol_pct"]) else float(last["vol_pct"]),
            "asof": ts,
        }

    if granularity == "minute":
        ip = params if isinstance(params, IntradayRegimeParams) else IntradayRegimeParams()
        if day_minute_df is None or day_minute_df.empty:
            return {"direction": "neutral", "trendiness": "range",
                    "vol_class": "LOW", "bias": "flat", "asof": ts}
        df = day_minute_df[day_minute_df["datetime"] <= ts]
        if df.empty:
            return {"direction": "neutral", "trendiness": "range",
                    "vol_class": "LOW", "bias": "flat", "asof": ts}
        res = classify_intraday(df, prev_close, ip)
        last = res.iloc[-1]
        return {
            "direction": str(last["direction"]),
            "trendiness": str(last["trendiness"]),
            "vol_class": str(last["vol_class"]),
            "bias": str(last["bias"]),
            "asof": ts,
        }

    raise ValueError(f"granularity must be 'daily' or 'minute', got {granularity!r}")
