"""데이터 품질 가드 — 결측/이상치/분봉 누락 검출."""
from __future__ import annotations

import logging
from datetime import date
from typing import Any

import pandas as pd

logger = logging.getLogger(__name__)


def check_missing_streaks(
    df: pd.DataFrame,
    date_col: str = "date",
    max_streak: int = 5,
) -> list[tuple[date, date]]:
    """연속 결측 거래일 구간 검출.

    df는 date_col 컬럼이 있어야 함. 영업일 기준 연속 max_streak 거래일 초과하여
    빠진 구간 리스트를 반환한다 [(start, end), ...].
    빠진 구간이 없으면 [].

    내부 구현: 정렬된 date_col에서 인접 날짜 차이가 max_streak 초과인 구간을
    pandas bdate_range로 비즈니스 데이 차이를 계산해 필터한다. 주말은 자동 제외.
    """
    if df.empty or date_col not in df.columns:
        return []

    dates = pd.to_datetime(df[date_col]).sort_values().dt.date.unique().tolist()
    if len(dates) < 2:
        return []

    gaps: list[tuple[date, date]] = []
    for i in range(1, len(dates)):
        prev = dates[i - 1]
        curr = dates[i]
        # bdate_range로 비즈니스 데이 차이 계산 (양 끝 포함이므로 -1)
        bdays = pd.bdate_range(prev, curr).size - 1
        if bdays > max_streak:
            gaps.append((prev, curr))
            logger.warning(
                "결측 거래일 %d일 (%s ~ %s) — max_streak=%d 초과",
                bdays,
                prev,
                curr,
                max_streak,
            )
    return gaps


def check_extreme_returns(
    df: pd.DataFrame,
    close_col: str = "close",
    date_col: str = "date",
    threshold: float = 0.30,
) -> list[tuple[date, float]]:
    """단일 종목 일간 수익률 ±threshold 초과 검출 (수정주가 미조정 의심).

    Returns [(date, return_pct), ...].
    threshold=0.30 — 액면분할 50:1이면 -98%로 튀는 케이스를 잡는다.
    상한가/하한가(±30%)는 임계 정확히 일치이므로 체크에 걸리지 않음.
    threshold > 0.30이면 분할 의심으로 간주.
    """
    if df.empty or close_col not in df.columns:
        return []

    sorted_df = df.sort_values(date_col).reset_index(drop=True)
    closes = sorted_df[close_col].astype(float)
    returns = closes.pct_change().fillna(0.0)

    flagged: list[tuple[date, float]] = []
    for i, r in enumerate(returns):
        if abs(r) > threshold:
            d = pd.to_datetime(sorted_df[date_col].iloc[i]).date()
            flagged.append((d, float(r)))
            logger.warning(
                "이상 수익률 감지 — %s: %.2f%% (threshold=±%.0f%%, 수정주가 미조정 의심)",
                d,
                r * 100,
                threshold * 100,
            )
    return flagged


def check_minute_gaps(
    df: pd.DataFrame,
    datetime_col: str = "datetime",
    max_gap_minutes: int = 5,
) -> list[tuple[Any, Any]]:
    """분봉 시계열에서 max_gap_minutes 초과 누락 구간 검출.

    Returns [(prev_dt, curr_dt), ...]. 거래시간 09:00~15:30만 고려.
    단순화: 단일 거래일 안에서만 gap 측정 (거래일 바뀌면 skip).
    """
    if df.empty or datetime_col not in df.columns:
        return []

    sorted_df = df.sort_values(datetime_col).reset_index(drop=True)
    dts = pd.to_datetime(sorted_df[datetime_col])

    gaps: list[tuple[Any, Any]] = []
    for i in range(1, len(dts)):
        prev, curr = dts.iloc[i - 1], dts.iloc[i]
        if prev.date() != curr.date():
            continue  # 거래일 바뀌면 skip
        gap_min = (curr - prev).total_seconds() / 60
        if gap_min > max_gap_minutes:
            gaps.append((prev, curr))
            logger.info(
                "분봉 누락 구간 — %s ~ %s (%d분, max=%d)",
                prev,
                curr,
                int(gap_min),
                max_gap_minutes,
            )
    return gaps
