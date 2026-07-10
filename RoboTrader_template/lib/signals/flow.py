"""
lib/signals/flow.py — 수급 기반 PIT-safe 시그널 (F-23, F-25)
==============================================================

카탈로그 출처: reports/10pct_strategy/phase5_signals/04_flow.md

PIT 강제 규칙:
- 모든 rolling/cumsum은 T 기준 과거 데이터만 사용
- shift(-N) 절대 금지 (forward leak)
- 입력 df는 종목별 날짜 오름차순 정렬 전제

Stage 매핑:
- OBV (F-23): Stage B — 매수 시그널 (divergence / threshold)
- CMF (F-25): Stage B — 매수 시그널 (양수 = 매수 압력)

No Look-Ahead 검증:
- "마지막 N행을 잘라내도 직전 행까지의 결과가 동일" 원칙 적용
- cumsum/rolling은 인과적(causal) — 미래 참조 없음
"""

from __future__ import annotations

import numpy as np
import pandas as pd


def obv(
    prices: pd.DataFrame,
    group_col: str = "stock_code",
    close_col: str = "close",
    volume_col: str = "volume",
) -> pd.Series:
    """On-Balance Volume (OBV) — F-23.

    정의 (카탈로그 F-23):
        OBV = 누적합(상승일: +거래량, 하락일: -거래량, 보합일: 0)
        당일 종가 > 전일 종가 → +volume
        당일 종가 < 전일 종가 → -volume
        당일 종가 == 전일 종가 → 0

    PIT 강제:
        pct_change() = (close_t - close_{t-1}) / close_{t-1} — 과거만 참조.
        cumsum()은 T까지의 누적값 — 미래 참조 없음.
        종목 경계: groupby로 종목 간 누출 차단.

    Parameters
    ----------
    prices : pd.DataFrame
        종목 시계열 데이터. 날짜 오름차순 정렬 필수.
        ``group_col``, ``close_col``, ``volume_col`` 컬럼 필요.
    group_col : str
        종목 구분 컬럼. 기본값 ``"stock_code"``.
    close_col : str
        종가 컬럼. 기본값 ``"close"``.
    volume_col : str
        거래량 컬럼. 기본값 ``"volume"``.

    Returns
    -------
    pd.Series
        prices.index와 동일한 index의 OBV 시리즈.
        종목별 첫 행은 0 (기준값).
        종가 또는 거래량이 NaN인 행은 누적값이 전파됨.

    Stage 매핑: Stage B (매수 시그널)
        - OBV 상승 추세 + 가격 하락 = 강세 다이버전스 → 매수 신호
        - OBV 신고점 돌파 = 추세 지속 확인 신호

    예시
    ----
    >>> import pandas as pd
    >>> from lib.signals.flow import obv
    >>> prices = pd.DataFrame({
    ...     "stock_code": ["A", "A", "A"],
    ...     "date": pd.date_range("2024-01-01", periods=3),
    ...     "close": [100, 110, 105],
    ...     "volume": [1000, 2000, 1500],
    ... })
    >>> obv(prices)
    0       0
    1    2000
    2     500
    dtype: int64
    """
    def _obv_single(grp: pd.DataFrame) -> pd.Series:
        close  = grp[close_col].values.astype(float)
        volume = grp[volume_col].values.astype(float)
        n = len(close)
        obv_vals = np.zeros(n, dtype=float)

        for i in range(1, n):
            prev_c = close[i - 1]
            curr_c = close[i]
            vol_i  = volume[i]
            if np.isnan(curr_c) or np.isnan(prev_c) or np.isnan(vol_i):
                obv_vals[i] = obv_vals[i - 1]
            elif curr_c > prev_c:
                obv_vals[i] = obv_vals[i - 1] + vol_i
            elif curr_c < prev_c:
                obv_vals[i] = obv_vals[i - 1] - vol_i
            else:
                obv_vals[i] = obv_vals[i - 1]

        return pd.Series(obv_vals, index=grp.index, name=None)

    if group_col in prices.columns:
        parts = []
        for _, grp in prices.groupby(group_col, sort=False):
            parts.append(_obv_single(grp))
        result = pd.concat(parts).sort_index()
        result = result.reindex(prices.index)
    else:
        result = _obv_single(prices)

    return result


def cmf(
    prices: pd.DataFrame,
    window: int = 20,
    group_col: str = "stock_code",
    close_col: str = "close",
    high_col: str = "high",
    low_col: str = "low",
    volume_col: str = "volume",
) -> pd.Series:
    """Chaikin Money Flow (CMF) — F-25.

    정의 (카탈로그 F-25):
        Money Flow Multiplier (MFM) = ((close - low) - (high - close)) / (high - low)
                                    = (2*close - high - low) / (high - low)
        Money Flow Volume (MFV) = MFM × volume
        CMF_N = sum(MFV, N일) / sum(volume, N일)

    범위: -1 ~ +1
        양수(> 0) = 매수 압력 (축적)
        음수(< 0) = 매도 압력 (분배)
        일반적으로 |CMF| > 0.1 이면 유의미한 신호

    PIT 강제:
        rolling(window).sum() — 인과적 윈도우, 미래 참조 없음.
        high == low (데이터 이상) 시 MFM = 0 처리 (NaN 회피).
        종목 경계: groupby로 종목 간 누출 차단.

    Parameters
    ----------
    prices : pd.DataFrame
        종목 시계열 데이터. 날짜 오름차순 정렬 필수.
        ``group_col``, ``close_col``, ``high_col``, ``low_col``, ``volume_col``
        컬럼 필요.
    window : int
        CMF 계산 윈도우 (기본값 20일, 카탈로그 표준).
    group_col : str
        종목 구분 컬럼. 기본값 ``"stock_code"``.
    close_col : str
        종가 컬럼. 기본값 ``"close"``.
    high_col : str
        고가 컬럼. 기본값 ``"high"``.
    low_col : str
        저가 컬럼. 기본값 ``"low"``.
    volume_col : str
        거래량 컬럼. 기본값 ``"volume"``.

    Returns
    -------
    pd.Series
        prices.index와 동일한 index의 CMF 시리즈.
        초기 (window - 1)행은 NaN (데이터 부족).

    Stage 매핑: Stage B (매수 시그널)
        - CMF > 0 이고 상승 추세: 매수 압력 확인 신호
        - CMF > 0.1: 강한 매수 압력

    예시
    ----
    >>> import pandas as pd
    >>> from lib.signals.flow import cmf
    >>> prices = pd.DataFrame({
    ...     "stock_code": ["A"] * 25,
    ...     "date": pd.date_range("2024-01-01", periods=25),
    ...     "close": [100 + i for i in range(25)],
    ...     "high":  [102 + i for i in range(25)],
    ...     "low":   [98  + i for i in range(25)],
    ...     "volume": [1000] * 25,
    ... })
    >>> result = cmf(prices, window=20)
    >>> result.iloc[-1]  # 마지막 행은 NaN이 아니어야 함
    """
    if window < 1:
        raise ValueError(f"cmf: window={window} < 1 is not valid.")

    def _cmf_single(grp: pd.DataFrame) -> pd.Series:
        close  = grp[close_col]
        high   = grp[high_col]
        low    = grp[low_col]
        volume = grp[volume_col]

        hl_range = (high - low).replace(0, np.nan)
        mfm = (2 * close - high - low) / hl_range  # NaN when high==low
        mfm = mfm.fillna(0.0)                        # high==low → MFM = 0

        mfv = mfm * volume

        mfv_sum = mfv.rolling(window, min_periods=window).sum()
        vol_sum = volume.rolling(window, min_periods=window).sum()

        result = mfv_sum / vol_sum.replace(0, np.nan)
        return result

    if group_col in prices.columns:
        parts = []
        for _, grp in prices.groupby(group_col, sort=False):
            parts.append(_cmf_single(grp))
        result = pd.concat(parts).sort_index()
        result = result.reindex(prices.index)
    else:
        result = _cmf_single(prices)

    return result
