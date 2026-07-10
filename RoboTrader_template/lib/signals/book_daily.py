"""
lib/signals/book_daily.py — 책 3권 기반 일봉 PIT-safe 시그널
=============================================================

출처:
  - 책 1 강창권 「주식투자 단기 트레이딩의 정석」
  - 책 3 Andrew Aziz「How to Day Trade for a Living」(번역판)

PIT 강제 규칙:
  - 모든 rolling/cumsum은 T 기준 과거 데이터만 사용
  - shift(-N) 절대 금지 (forward leak)
  - 입력 df는 종목별 날짜 오름차순 정렬 전제
  - rolling/cumsum 사용 시 min_periods=window 강제

No Look-Ahead 검증:
  - "마지막 N행을 잘라내도 직전 행까지의 결과가 동일" 원칙 적용

함수 목록:
  - new_high_breakout : 52주 신고가 돌파 + 거래량 동반
  - volume_spike_3x   : 거래량 ×3배 급증 + 양봉 조건
  - ma20_pullback     : 20일선 눌림목 매수 시그널
  - closing_bet       : 종가 베팅 (T종가 강세 → T+1 갭상승 노림)
"""

from __future__ import annotations

import numpy as np
import pandas as pd


def new_high_breakout(
    prices: pd.DataFrame,
    window: int = 252,
    vol_mult: float = 1.5,
    group_col: str = "stock_code",
    close_col: str = "close",
    volume_col: str = "volume",
) -> pd.Series:
    """52주(252일) 신고가 돌파 시그널 — PIT-safe.

    정의 (책 1 강창권 / 책 3 Bulkowski):
        T일 close > rolling_max(close, window일) 직전값 AND
        T일 volume >= rolling_mean(volume, window일) × vol_mult

    PIT 강제:
        rolling(window).max().shift(1) — T-1까지의 최고가 비교 (T 자신 제외).
        shift(1)은 backward shift (미래 참조 없음).
        rolling min_periods=window 강제.

    Parameters
    ----------
    prices : pd.DataFrame
        종목 시계열 데이터. 날짜 오름차순 정렬 필수.
        ``group_col``, ``close_col``, ``volume_col`` 컬럼 필요.
    window : int
        신고가 비교 기간 (기본값 252 = 52주).
    vol_mult : float
        거래량 배수 임계값 (기본값 1.5).
    group_col : str
        종목 구분 컬럼. 기본값 ``"stock_code"``.
    close_col : str
        종가 컬럼. 기본값 ``"close"``.
    volume_col : str
        거래량 컬럼. 기본값 ``"volume"``.

    Returns
    -------
    pd.Series[bool]
        True: T일 신고가 돌파 + 거래량 동반 시그널.
        초기 window행 또는 데이터 부족 구간은 False.

    Stage 매핑: Stage B (매수 시그널)
        신고가 돌파 = 저항 → 지지 전환 → 추세 지속 확인 신호
    """
    if window < 1:
        raise ValueError(f"new_high_breakout: window={window} < 1 is not valid.")

    def _signal_single(grp: pd.DataFrame) -> pd.Series:
        close = grp[close_col].astype(float)
        volume = grp[volume_col].astype(float)

        # T-1까지의 최고가 (T 자신 제외 → shift(1) 적용)
        prev_max = close.rolling(window, min_periods=window).max().shift(1)
        # T일 거래량 평균 (T 자신 포함한 window일 평균을 shift(1) — T 이전 평균)
        avg_vol = volume.rolling(window, min_periods=window).mean().shift(1)

        high_break = close > prev_max
        vol_confirm = volume >= avg_vol * vol_mult

        signal = high_break & vol_confirm
        # NaN 구간은 False
        signal = signal.fillna(False)
        return signal.astype(bool)

    if group_col in prices.columns:
        parts = []
        for _, grp in prices.groupby(group_col, sort=False):
            parts.append(_signal_single(grp))
        result = pd.concat(parts).sort_index()
        result = result.reindex(prices.index)
    else:
        result = _signal_single(prices)

    return result.fillna(False).astype(bool)


def volume_spike_3x(
    prices: pd.DataFrame,
    window: int = 20,
    mult: float = 3.0,
    require_up: bool = True,
    group_col: str = "stock_code",
    close_col: str = "close",
    open_col: str = "open",
    volume_col: str = "volume",
) -> pd.Series:
    """거래량 ×3배 급증 시그널 — PIT-safe.

    정의 (책 1 강창권):
        T일 volume > avg(volume, window일) × mult AND
        (require_up=True이면) close > open (양봉)

    PIT 강제:
        rolling(window).mean().shift(1) — T-1까지의 평균 거래량 기준.
        shift(1)은 backward shift (미래 참조 없음).
        rolling min_periods=window 강제.

    Parameters
    ----------
    prices : pd.DataFrame
        종목 시계열 데이터. 날짜 오름차순 정렬 필수.
        ``group_col``, ``close_col``, ``open_col``, ``volume_col`` 컬럼 필요.
    window : int
        평균 거래량 계산 기간 (기본값 20일).
    mult : float
        거래량 배수 임계값 (기본값 3.0).
    require_up : bool
        True이면 양봉 조건 추가 (close > open). 기본값 True.
    group_col : str
        종목 구분 컬럼. 기본값 ``"stock_code"``.
    close_col : str
        종가 컬럼. 기본값 ``"close"``.
    open_col : str
        시가 컬럼. 기본값 ``"open"``.
    volume_col : str
        거래량 컬럼. 기본값 ``"volume"``.

    Returns
    -------
    pd.Series[bool]
        True: 거래량 급증 (+ 양봉) 시그널.
        초기 window행 또는 데이터 부족 구간은 False.

    Stage 매핑: Stage B (매수 시그널)
        거래량 급증 = 방향성 추종 신호
    """
    if window < 1:
        raise ValueError(f"volume_spike_3x: window={window} < 1 is not valid.")

    def _signal_single(grp: pd.DataFrame) -> pd.Series:
        close = grp[close_col].astype(float)
        volume = grp[volume_col].astype(float)

        # T-1까지의 평균 거래량 (T 자신 제외)
        avg_vol = volume.rolling(window, min_periods=window).mean().shift(1)

        vol_spike = volume > avg_vol * mult

        if require_up and open_col in grp.columns:
            open_ = grp[open_col].astype(float)
            up_candle = close > open_
            signal = vol_spike & up_candle
        else:
            signal = vol_spike

        signal = signal.fillna(False)
        return signal.astype(bool)

    if group_col in prices.columns:
        parts = []
        for _, grp in prices.groupby(group_col, sort=False):
            parts.append(_signal_single(grp))
        result = pd.concat(parts).sort_index()
        result = result.reindex(prices.index)
    else:
        result = _signal_single(prices)

    return result.fillna(False).astype(bool)


def ma20_pullback(
    prices: pd.DataFrame,
    tolerance_pct: float = 1.0,
    lookback_above: int = 5,
    group_col: str = "stock_code",
    close_col: str = "close",
) -> pd.Series:
    """20일선 눌림목 매수 시그널 — PIT-safe.

    정의 (책 1 강창권):
        1. 정배열 조건: MA20 > MA60 (중기 상승 추세)
        2. 눌림목 조건: |close - MA20| / MA20 <= tolerance_pct / 100
           (close가 MA20에 ±tolerance_pct% 이내 접근)
        3. 최근 lookback_above일 동안 close > MA20 이었음
           (눌림목 전까지 위에 있었음을 확인)

    PIT 강제:
        rolling(N).mean() — T 기준 과거만 참조, 인과적.
        rolling min_periods=max_window 강제.
        종목 경계: groupby로 종목 간 누출 차단.

    Parameters
    ----------
    prices : pd.DataFrame
        종목 시계열 데이터. 날짜 오름차순 정렬 필수.
        ``group_col``, ``close_col`` 컬럼 필요.
    tolerance_pct : float
        MA20 접근 허용 오차 (%). 기본값 1.0 → ±1%.
    lookback_above : int
        눌림목 직전 close > MA20 확인 기간 (일). 기본값 5.
    group_col : str
        종목 구분 컬럼. 기본값 ``"stock_code"``.
    close_col : str
        종가 컬럼. 기본값 ``"close"``.

    Returns
    -------
    pd.Series[bool]
        True: 정배열 상태에서 MA20 눌림목 시그널.
        초기 60일 미만 또는 데이터 부족 구간은 False.

    Stage 매핑: Stage B (매수 시그널)
        중기 상승 추세 유지 중 단기 눌림목 = 저점 매수 기회
    """
    if lookback_above < 1:
        raise ValueError(
            f"ma20_pullback: lookback_above={lookback_above} < 1 is not valid."
        )

    def _signal_single(grp: pd.DataFrame) -> pd.Series:
        close = grp[close_col].astype(float)

        ma20 = close.rolling(20, min_periods=20).mean()
        ma60 = close.rolling(60, min_periods=60).mean()

        # 정배열: MA20 > MA60
        aligned = ma20 > ma60

        # 눌림목: close가 MA20에 ±tolerance_pct% 이내
        tol = tolerance_pct / 100.0
        near_ma20 = (close - ma20).abs() / ma20 <= tol

        # 직전 lookback_above일 동안 close > MA20 였는지 확인
        # shift(1)로 T-1부터 T-lookback_above까지 모두 True여야 함
        # rolling(lookback_above).min()로 구간 내 최솟값이 1이면 모두 True
        above_ma20 = (close > ma20).astype(float)
        # T 포함하지 않고 직전 lookback_above일 → shift(1) 후 rolling
        prev_above_min = above_ma20.shift(1).rolling(
            lookback_above, min_periods=lookback_above
        ).min()
        was_above = prev_above_min == 1.0

        signal = aligned & near_ma20 & was_above
        signal = signal.fillna(False)
        return signal.astype(bool)

    if group_col in prices.columns:
        parts = []
        for _, grp in prices.groupby(group_col, sort=False):
            parts.append(_signal_single(grp))
        result = pd.concat(parts).sort_index()
        result = result.reindex(prices.index)
    else:
        result = _signal_single(prices)

    return result.fillna(False).astype(bool)


def closing_bet(
    prices: pd.DataFrame,
    vol_mult: float = 1.2,
    group_col: str = "stock_code",
    close_col: str = "close",
    open_col: str = "open",
    volume_col: str = "volume",
) -> pd.Series:
    """종가 베팅 시그널 — T일 종가 강세 → T+1 시초 갭상승 노림 (PIT-safe).

    정의 (책 1 강창권 4장):
        T일 조건 (모두 충족 시 T일 종가 매수):
          1. close > open (양봉)
          2. close > MA5 (단기 상승 추세)
          3. volume >= avg(volume, 20일) × vol_mult (거래량 동반)

        시그널은 T일에 발생 → T+1 시초가에 청산하는 전략.
        (이 함수는 T일 시그널만 반환. T+1 갭 계산은 별도.)

    PIT 강제:
        MA5: rolling(5, min_periods=5).mean() — T 포함 과거 5일.
        avg_vol: rolling(20, min_periods=20).mean().shift(1) — T-1까지 평균.
        shift(-N) 절대 금지.

    Parameters
    ----------
    prices : pd.DataFrame
        종목 시계열 데이터. 날짜 오름차순 정렬 필수.
        ``group_col``, ``close_col``, ``open_col``, ``volume_col`` 컬럼 필요.
    vol_mult : float
        거래량 배수 임계값 (기본값 1.2).
    group_col : str
        종목 구분 컬럼. 기본값 ``"stock_code"``.
    close_col : str
        종가 컬럼. 기본값 ``"close"``.
    open_col : str
        시가 컬럼. 기본값 ``"open"``.
    volume_col : str
        거래량 컬럼. 기본값 ``"volume"``.

    Returns
    -------
    pd.Series[bool]
        True: T일 종가 베팅 시그널 (T+1 시초가 청산 전략 진입).
        초기 20일 미만 또는 데이터 부족 구간은 False.

    Stage 매핑: Stage B (매수 시그널)
        T일 종가 매수 → T+1 시초가 갭상승 노림 오버나잇 전략
    """
    if vol_mult <= 0:
        raise ValueError(f"closing_bet: vol_mult={vol_mult} must be > 0.")

    def _signal_single(grp: pd.DataFrame) -> pd.Series:
        close = grp[close_col].astype(float)
        volume = grp[volume_col].astype(float)

        # 조건 1: 양봉
        if open_col in grp.columns:
            open_ = grp[open_col].astype(float)
            up_candle = close > open_
        else:
            # open 컬럼 없으면 양봉 조건 스킵
            up_candle = pd.Series(True, index=grp.index)

        # 조건 2: close > MA5 (T 포함 5일 평균)
        ma5 = close.rolling(5, min_periods=5).mean()
        above_ma5 = close > ma5

        # 조건 3: 거래량 >= 직전 20일 평균 × vol_mult
        avg_vol = volume.rolling(20, min_periods=20).mean().shift(1)
        vol_confirm = volume >= avg_vol * vol_mult

        signal = up_candle & above_ma5 & vol_confirm
        signal = signal.fillna(False)
        return signal.astype(bool)

    if group_col in prices.columns:
        parts = []
        for _, grp in prices.groupby(group_col, sort=False):
            parts.append(_signal_single(grp))
        result = pd.concat(parts).sort_index()
        result = result.reindex(prices.index)
    else:
        result = _signal_single(prices)

    return result.fillna(False).astype(bool)
