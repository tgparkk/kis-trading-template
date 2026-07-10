"""
lib/signals/vwap.py — VWAP 시그널 (F-32/F-33/F-34, minute_candles 기반 PIT-safe)
====================================================================================

카탈로그 출처:
  - reports/10pct_strategy/phase5_signals/03_trendlines_sr.md  (F. VWAP 카드)
  - reports/10pct_strategy/phase5_signals/04_flow.md           (F-32/F-33)

PIT 강제 규칙:
  - cumsum()은 인과적(causal) — t 시점 VWAP는 t 시점까지의 분봉만 사용.
  - shift(-N) 절대 금지.
  - 다일(Multi-day) 데이터 사용 시 일자별 누적 리셋 필수 — 미처리 시 Look-Ahead.
  - 입력 minute_df는 dt(datetime) 오름차순 정렬 전제.

데이터 소스:
  - robotrader.minute_candles: stock_code, dt(datetime), open, high, low, close, volume
  - 장 시간: 09:00~15:30 (한국), 점심 12:00~13:00은 거래량=0으로 자연 처리.
  - 분봉 첫 행: vwap = typical_price (분자=분모, 같은 값).

함수 목록:
  - intraday_vwap        : 일중 누적 VWAP (일자별 리셋)
  - vwap_position        : +1(위) / -1(아래) / 0(동일)
  - vwap_bands           : VWAP ± n_sigma 밴드 (upper, lower)
  - anchored_vwap        : 특정 이벤트 시점 앵커 VWAP
"""

from __future__ import annotations

import numpy as np
import pandas as pd


# ---------------------------------------------------------------------------
# 내부 헬퍼
# ---------------------------------------------------------------------------

def _typical_price(df: pd.DataFrame) -> pd.Series:
    """Typical Price = (high + low + close) / 3.

    high/low 컬럼이 없으면 close만 사용 (분봉 데이터 품질 보호).
    """
    if "high" in df.columns and "low" in df.columns:
        return (df["high"] + df["low"] + df["close"]) / 3.0
    return df["close"].astype(float)


def _validate_minute_df(df: pd.DataFrame) -> None:
    """입력 검증 — 필수 컬럼 존재 확인."""
    required = {"close", "volume"}
    missing = required - set(df.columns)
    if missing:
        raise ValueError(f"intraday_vwap: 필수 컬럼 누락 — {missing}")


# ---------------------------------------------------------------------------
# 공개 API
# ---------------------------------------------------------------------------

def intraday_vwap(
    minute_df: pd.DataFrame,
    dt_col: str = "dt",
    close_col: str = "close",
    high_col: str = "high",
    low_col: str = "low",
    volume_col: str = "volume",
) -> pd.Series:
    """일중 누적 VWAP — 일자별 리셋 (PIT-safe).

    정의 (카탈로그 F-01 / F-32):
        typical_price_t = (high_t + low_t + close_t) / 3
        VWAP_t = cumsum(typical_price * volume, 장_시작~t)
                / cumsum(volume, 장_시작~t)

    PIT 강제:
        - cumsum()은 t 시점까지만 누적 → 자연스럽게 PIT-safe.
        - groupby(date)로 일자별 독립 누적 → 전일 분봉 누출 차단.
        - 점심 시간(volume=0) 행: 분자/분모 모두 0 기여 → VWAP 변동 없음.
        - 첫 분봉: vwap = typical_price (분모=volume, 분자=typical*volume).

    Parameters
    ----------
    minute_df : pd.DataFrame
        분봉 데이터. dt_col(datetime), close_col, volume_col 필수.
        high_col, low_col 없으면 close만으로 typical_price 계산.
        날짜 오름차순 정렬 필수.
    dt_col : str
        datetime 컬럼명 (기본값 "dt").
    close_col, high_col, low_col, volume_col : str
        각 OHLCV 컬럼명.

    Returns
    -------
    pd.Series
        minute_df.index와 동일한 index의 VWAP 시리즈.
        거래량 누적합이 0인 구간은 NaN.

    No Look-Ahead 검증:
        "마지막 N분봉을 잘라내도 직전 분 VWAP 불변" — cumsum 인과성 보장.

    예시
    ----
    >>> import pandas as pd
    >>> from lib.signals.vwap import intraday_vwap
    >>> df = pd.DataFrame({
    ...     "dt": pd.to_datetime(["2024-01-02 09:00", "2024-01-02 09:01", "2024-01-02 09:02"]),
    ...     "high":  [101, 102, 103],
    ...     "low":   [99,  100, 101],
    ...     "close": [100, 101, 102],
    ...     "volume": [1000, 2000, 1500],
    ... })
    >>> intraday_vwap(df)
    """
    _validate_minute_df(minute_df)

    # dt_col이 컬럼에 있으면 date 파싱, 없으면 index를 dt로 사용
    if dt_col in minute_df.columns:
        dt_series = pd.to_datetime(minute_df[dt_col])
    else:
        dt_series = pd.to_datetime(minute_df.index)

    date_key = dt_series.dt.date

    # 컬럼명 리맵 (유연성)
    df_work = minute_df.rename(columns={
        close_col: "close",
        volume_col: "volume",
    })
    if high_col in minute_df.columns:
        df_work = df_work.rename(columns={high_col: "high"})
    if low_col in minute_df.columns:
        df_work = df_work.rename(columns={low_col: "low"})

    tp = _typical_price(df_work).values.astype(float)
    vol = df_work["volume"].values.astype(float)

    # 점심 시간 처리: volume=0이면 분자/분모 기여 0 → VWAP 값 유지
    # (cumsum에서 자연스럽게 처리됨. 명시적 조작 불필요)

    result = np.full(len(minute_df), np.nan, dtype=float)
    dates = date_key.values  # numpy array for speed

    # 일자별 누적 리셋
    i = 0
    n = len(minute_df)
    while i < n:
        # 같은 날짜 구간 찾기
        current_date = dates[i]
        j = i
        while j < n and dates[j] == current_date:
            j += 1
        # [i, j) 는 같은 날짜의 분봉들
        tp_day  = tp[i:j]
        vol_day = vol[i:j]

        cum_pv  = np.cumsum(tp_day * vol_day)
        cum_vol = np.cumsum(vol_day)

        # volume 누적이 0이면 NaN (거래 없음)
        with np.errstate(invalid="ignore", divide="ignore"):
            vwap_day = np.where(cum_vol > 0, cum_pv / cum_vol, np.nan)

        result[i:j] = vwap_day
        i = j

    return pd.Series(result, index=minute_df.index, name="vwap")


def vwap_position(
    minute_df: pd.DataFrame,
    dt_col: str = "dt",
    close_col: str = "close",
    high_col: str = "high",
    low_col: str = "low",
    volume_col: str = "volume",
) -> pd.Series:
    """VWAP 대비 현재가 위치 판단 — PIT-safe.

    정의 (카탈로그 F-32/F-33):
        +1 : close > VWAP  (매수세 우위 — 기관 매수 구간 편승)
        -1 : close < VWAP  (매도세 우위 — 분배 구간)
         0 : close == VWAP (동일)

    Parameters
    ----------
    minute_df : pd.DataFrame
        분봉 데이터 (intraday_vwap와 동일 스펙).

    Returns
    -------
    pd.Series
        int8 시리즈 (+1 / -1 / 0). NaN VWAP 구간은 0 처리.

    예시
    ----
    >>> pos = vwap_position(df)
    >>> signal_long = pos == 1   # VWAP 위 = 매수 구간
    """
    vwap = intraday_vwap(
        minute_df,
        dt_col=dt_col,
        close_col=close_col,
        high_col=high_col,
        low_col=low_col,
        volume_col=volume_col,
    )

    close = minute_df[close_col].astype(float)

    pos = pd.Series(0, index=minute_df.index, dtype="int8", name="vwap_position")
    valid = vwap.notna()
    pos[valid & (close > vwap)] =  1
    pos[valid & (close < vwap)] = -1

    return pos


def vwap_bands(
    minute_df: pd.DataFrame,
    n_sigma: float = 1.0,
    dt_col: str = "dt",
    close_col: str = "close",
    high_col: str = "high",
    low_col: str = "low",
    volume_col: str = "volume",
) -> tuple[pd.Series, pd.Series]:
    """VWAP ± n_sigma 표준편차 밴드 — PIT-safe.

    정의 (카탈로그 F-01 수식):
        cumvar_t = cumsum(volume * (typical - VWAP_t)^2) / cumsum(volume)
        VWAP_std_t = sqrt(cumvar_t)
        upper = VWAP_t + n_sigma * VWAP_std_t
        lower = VWAP_t - n_sigma * VWAP_std_t

    PIT 강제:
        - cumsum 기반 누적 분산 → 인과적, 미래 참조 없음.
        - 일자별 리셋 (intraday_vwap와 동일 구조).

    Parameters
    ----------
    minute_df : pd.DataFrame
        분봉 데이터.
    n_sigma : float
        밴드 배수 (기본값 1.0 → ±1σ). 2.0 → ±2σ.

    Returns
    -------
    tuple[pd.Series, pd.Series]
        (upper, lower) — VWAP 기준 상단/하단 밴드.
        NaN VWAP 구간은 NaN.

    예시
    ----
    >>> upper, lower = vwap_bands(df, n_sigma=2.0)
    >>> oversold = df["close"] < lower   # 하단 이탈 = 매수 기회
    """
    _validate_minute_df(minute_df)

    if dt_col in minute_df.columns:
        dt_series = pd.to_datetime(minute_df[dt_col])
    else:
        dt_series = pd.to_datetime(minute_df.index)

    date_key = dt_series.dt.date

    df_work = minute_df.rename(columns={
        close_col: "close",
        volume_col: "volume",
    })
    if high_col in minute_df.columns:
        df_work = df_work.rename(columns={high_col: "high"})
    if low_col in minute_df.columns:
        df_work = df_work.rename(columns={low_col: "low"})

    tp  = _typical_price(df_work).values.astype(float)
    vol = df_work["volume"].values.astype(float)

    n = len(minute_df)
    upper_arr = np.full(n, np.nan, dtype=float)
    lower_arr = np.full(n, np.nan, dtype=float)
    dates = date_key.values

    i = 0
    while i < n:
        current_date = dates[i]
        j = i
        while j < n and dates[j] == current_date:
            j += 1

        tp_day  = tp[i:j]
        vol_day = vol[i:j]

        cum_pv  = np.cumsum(tp_day * vol_day)
        cum_vol = np.cumsum(vol_day)

        with np.errstate(invalid="ignore", divide="ignore"):
            vwap_day = np.where(cum_vol > 0, cum_pv / cum_vol, np.nan)

        # 누적 분산: cumsum(vol * (tp - vwap)^2) / cumsum(vol)
        # vwap_day가 NaN인 구간은 분산도 NaN
        diff_sq  = (tp_day - vwap_day) ** 2
        cum_var_num = np.cumsum(vol_day * diff_sq)

        with np.errstate(invalid="ignore", divide="ignore"):
            cum_var = np.where(cum_vol > 0, cum_var_num / cum_vol, np.nan)

        std_day = np.sqrt(cum_var)

        upper_arr[i:j] = vwap_day + n_sigma * std_day
        lower_arr[i:j] = vwap_day - n_sigma * std_day
        i = j

    upper = pd.Series(upper_arr, index=minute_df.index, name=f"vwap_upper_{n_sigma}s")
    lower = pd.Series(lower_arr, index=minute_df.index, name=f"vwap_lower_{n_sigma}s")
    return upper, lower


def anchored_vwap(
    minute_df: pd.DataFrame,
    anchor_dt: pd.Timestamp,
    dt_col: str = "dt",
    close_col: str = "close",
    high_col: str = "high",
    low_col: str = "low",
    volume_col: str = "volume",
) -> pd.Series:
    """Anchored VWAP — 특정 이벤트 시점부터 누적 VWAP (PIT-safe).

    정의 (카탈로그 F-02):
        anchor_dt 이후 분봉부터 cumsum(typical * volume) / cumsum(volume) 누적.
        anchor_dt 이전 행은 NaN.

    활용 예시:
        - 전일 종가 시점 앵커 (갭 발생일)
        - 52주 신고가 시점 앵커
        - corp_events 테이블의 주식분할/합병 날짜 앵커

    PIT 강제:
        - anchor_dt 이후 데이터만 사용 → 미래 참조 없음.
        - cumsum은 인과적 → 완전 PIT-safe.

    Parameters
    ----------
    minute_df : pd.DataFrame
        분봉 데이터. anchor_dt 이전/이후 행 모두 포함 가능.
        dt_col이 컬럼으로 존재하거나 index가 datetime이어야 함.
    anchor_dt : pd.Timestamp
        VWAP 누적 시작 시점 (이 시점의 분봉부터 포함).

    Returns
    -------
    pd.Series
        minute_df.index와 동일한 index의 Anchored VWAP.
        anchor_dt 이전 행은 NaN.

    예시
    ----
    >>> anchor = pd.Timestamp("2024-01-15 09:00")
    >>> avwap = anchored_vwap(df, anchor_dt=anchor)
    >>> above_avwap = df["close"] > avwap  # 앵커 기준 매수세 우위
    """
    _validate_minute_df(minute_df)

    if dt_col in minute_df.columns:
        dt_series = pd.to_datetime(minute_df[dt_col])
    else:
        dt_series = pd.to_datetime(minute_df.index)

    df_work = minute_df.rename(columns={
        close_col: "close",
        volume_col: "volume",
    })
    if high_col in minute_df.columns:
        df_work = df_work.rename(columns={high_col: "high"})
    if low_col in minute_df.columns:
        df_work = df_work.rename(columns={low_col: "low"})

    tp  = _typical_price(df_work).astype(float)
    vol = df_work["volume"].astype(float)

    anchor_mask = dt_series >= pd.Timestamp(anchor_dt)

    result = pd.Series(np.nan, index=minute_df.index, name="anchored_vwap")

    if not anchor_mask.any():
        return result

    tp_anchor  = tp[anchor_mask]
    vol_anchor = vol[anchor_mask]

    cum_pv  = (tp_anchor * vol_anchor).cumsum()
    cum_vol = vol_anchor.cumsum()

    with np.errstate(invalid="ignore", divide="ignore"):
        vwap_anchor = cum_pv / cum_vol.replace(0, np.nan)

    result[anchor_mask] = vwap_anchor.values
    return result
