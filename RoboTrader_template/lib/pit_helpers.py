"""
PIT (Point-In-Time) 헬퍼 — No Look-Ahead 강제 유틸리티
==========================================================

사장님 대원칙:
① 미래 데이터 보지 않기 (No Look-Ahead, PIT 강제)
② 시계열 순서로 진행하기 (Chronological Walk-Forward)

모든 시그널/필터/출구 함수는 이 모듈의 함수를 경유해야 합니다.
직접 shift(-N)을 시그널·필터에 쓰는 것은 절대 금지.

사용 예시
---------
>>> from lib.pit_helpers import safe_lag, pit_quantile, forward_return
>>>
>>> # 종목별 전일 종가 (1일 lag)
>>> df["close_lag1"] = safe_lag(df, "close", n=1)
>>>
>>> # 날짜별 cross-section 시총 5분위
>>> df["cap_quintile"] = pit_quantile(df, "market_cap", "date", n_bins=5)
>>>
>>> # 5일 선행 수익률 — 평가/레이블링 전용 (시그널 사용 금지!)
>>> df["fwd_ret_5d"] = forward_return(df, "close", n_days=5)
"""

from __future__ import annotations

import warnings
from typing import Optional

import pandas as pd


# ---------------------------------------------------------------------------
# safe_lag
# ---------------------------------------------------------------------------

def safe_lag(
    df: pd.DataFrame,
    col: str,
    n: int,
    group_col: str = "stock_code",
) -> pd.Series:
    """종목별 groupby 후 n일 과거 shift (No Look-Ahead 강제).

    Parameters
    ----------
    df : pd.DataFrame
        종목 시계열 데이터. ``group_col`` 과 ``col`` 컬럼 필수.
        날짜 오름차순으로 정렬되어 있어야 합니다.
    col : str
        shift 대상 컬럼명.
    n : int
        lag 크기. **반드시 n ≥ 1** (n=0이면 당일 값 그대로, n<0이면 ValueError).
        n=1 → 전일 값, n=2 → 전전일 값, ...
    group_col : str, optional
        종목 구분 컬럼명. 기본값 ``"stock_code"``.
        ``group_col`` 이 df에 없으면 전체를 하나의 그룹으로 처리합니다.

    Returns
    -------
    pd.Series
        df.index와 동일한 index. 종목의 첫 n행은 NaN.

    Raises
    ------
    ValueError
        n < 0 인 경우. forward shift는 미래 데이터이므로 절대 허용하지 않습니다.
        (forward return 계산은 ``forward_return()`` 을 사용하세요.)

    금기사항
    --------
    - n < 0 절대 불가 — forward leak 발생.
    - 이 함수의 결과를 ``forward_return()`` 의 입력으로 쓰지 마세요.

    예시
    ----
    >>> df["close_lag1"] = safe_lag(df, "close", n=1)
    >>> df["volume_lag3"] = safe_lag(df, "volume", n=3)
    """
    if n < 0:
        raise ValueError(
            f"safe_lag: n={n} < 0 is NOT allowed. "
            "Forward shift leaks future data into signals/filters. "
            "If you need forward returns for EVALUATION only, use forward_return()."
        )

    if group_col in df.columns:
        return df.groupby(group_col, sort=False)[col].shift(n)
    else:
        # group_col 없으면 전체 단일 그룹 처리
        return df[col].shift(n)


# ---------------------------------------------------------------------------
# pit_quantile
# ---------------------------------------------------------------------------

def pit_quantile(
    df: pd.DataFrame,
    value_col: str,
    date_col: str,
    n_bins: int = 5,
) -> pd.Series:
    """날짜별 cross-section에서만 분위수 계산 (PIT 강제).

    전 기간 통합 분위수는 미래 데이터 포함 → look-ahead 발생.
    이 함수는 각 날짜(T)의 단면만으로 분위를 매겨 leak을 원천 차단합니다.

    Parameters
    ----------
    df : pd.DataFrame
        ``date_col`` 과 ``value_col`` 컬럼 필수.
    value_col : str
        분위수를 매길 값 컬럼 (예: ``"market_cap"``, ``"volume"``).
    date_col : str
        날짜 컬럼명 (예: ``"date"``).
    n_bins : int, optional
        분위 수. 기본값 5 (quintile). n_bins=4 이면 quartile.

    Returns
    -------
    pd.Series
        1 ~ n_bins 범위의 정수 분위 레이블. df.index와 동일한 index.
        같은 날짜 내에서만 상대 순위를 매깁니다.
        NaN 값은 NaN 그대로 반환.

    금기사항
    --------
    - 전체 기간 df에 바로 ``pd.qcut`` / ``pd.cut`` 적용 금지.
      → 미래 종목의 시총이 현재 분위 경계에 영향을 줌.
    - 이 함수 결과를 T+1 이전 날짜의 시그널에 사용 금지
      (T 시점 cross-section이므로 T+1 진입 결정에 사용하는 것은 합법).

    예시
    ----
    >>> df["cap_quintile"] = pit_quantile(df, "market_cap", "date", n_bins=5)
    >>> df["vol_quartile"] = pit_quantile(df, "volume", "date", n_bins=4)
    """

    def _rank_within_date(group: pd.Series) -> pd.Series:
        # percentile rank (0~1), NaN 제외
        pct = group.rank(pct=True, na_option="keep")
        # 1~n_bins 정수 bin으로 변환
        # pd.cut의 경계: (0, 1/n_bins], ..., ((n_bins-1)/n_bins, 1]
        import numpy as np
        bins = [i / n_bins for i in range(n_bins + 1)]
        bins[0] = -1e-10  # rank 0 이하 처리 (실제로는 없지만 방어)
        labels = list(range(1, n_bins + 1))
        cut = pd.cut(pct, bins=bins, labels=labels)
        return cut.astype("Int64")

    result = df.groupby(date_col, sort=False)[value_col].transform(_rank_within_date)
    return result


# ---------------------------------------------------------------------------
# forward_return
# ---------------------------------------------------------------------------

def forward_return(
    df: pd.DataFrame,
    price_col: str,
    n_days: int,
    group_col: str = "stock_code",
) -> pd.Series:
    """n일 선행 수익률 계산 — 평가·레이블링 전용.

    .. warning::
        **이 함수는 EVALUATION / LABELING 전용입니다.**
        시그널·필터·출구 함수의 입력으로 절대 사용하지 마세요.
        미래 종가를 직접 사용하므로 현실에서 불가능한 값입니다.

    사용 시 ``FutureLeakWarning`` 을 자동 발생시켜
    시그널 모듈에서 잘못 사용하는 것을 조기에 감지합니다.

    Parameters
    ----------
    df : pd.DataFrame
        종목 시계열 데이터. 날짜 오름차순 정렬 필수.
    price_col : str
        기준 가격 컬럼명 (예: ``"close"``, ``"adj_close"``).
    n_days : int
        선행 일수. 양수만 허용 (n_days=5 → 5일 후 종가 기준 수익률).
    group_col : str, optional
        종목 구분 컬럼명. 기본값 ``"stock_code"``.

    Returns
    -------
    pd.Series
        (future_price / current_price) - 1. 마지막 n_days행은 NaN.

    Raises
    ------
    ValueError
        n_days < 1 인 경우.

    FutureLeakWarning
        항상 발생 — 이 함수 호출 자체가 경고 신호입니다.
        시그널 코드에서 이 경고가 보이면 즉시 제거하세요.

    금기사항 (CRITICAL)
    -------------------
    - 이 함수의 반환값을 시그널/필터/출구 함수 입력으로 사용 금지.
    - 이 함수를 ``strategies/``, ``multiverse/``, ``screener/`` 모듈에서
      import 금지. ``check_no_lookahead.py`` lint 룰이 이를 감시합니다.

    예시
    ----
    >>> # EDA / 레이블링 전용
    >>> df["fwd_ret_5d"] = forward_return(df, "close", n_days=5)
    >>> df["fwd_ret_20d"] = forward_return(df, "close", n_days=20)
    """
    if n_days < 1:
        raise ValueError(
            f"forward_return: n_days={n_days} < 1 is not valid. "
            "Use positive integer for forward window."
        )

    warnings.warn(
        "forward_return() uses future data (shift(-n)). "
        "ONLY use for evaluation/labeling — NEVER for signal/filter/exit inputs. "
        "If you see this warning in a signal module, remove it immediately.",
        FutureLeakWarning,
        stacklevel=2,
    )

    if group_col in df.columns:
        future_price = df.groupby(group_col, sort=False)[price_col].shift(-n_days)
    else:
        future_price = df[price_col].shift(-n_days)

    current_price = df[price_col]
    return (future_price / current_price) - 1.0


# ---------------------------------------------------------------------------
# Custom warning class
# ---------------------------------------------------------------------------

class FutureLeakWarning(UserWarning):
    """forward_return() 호출 시 발생하는 경고.

    시그널/필터 모듈에서 이 경고가 보이면 즉시 제거해야 합니다.
    """
    pass
