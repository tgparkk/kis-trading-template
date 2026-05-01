"""데이터 품질 가드 회귀 테스트 — 5건."""
from __future__ import annotations

from datetime import date, datetime

import pandas as pd
import pytest

from RoboTrader_template.multiverse.data.quality import (
    check_extreme_returns,
    check_minute_gaps,
    check_missing_streaks,
)


def test_missing_streaks_detects_gap():
    """월~금 5일 + 다음주 +10일 후 → 5거래일 초과 결측 검출."""
    dates = [
        date(2026, 1, 5),
        date(2026, 1, 6),
        date(2026, 1, 7),
        date(2026, 1, 8),
        date(2026, 1, 9),
        # 2주 누락 후
        date(2026, 1, 23),
    ]
    df = pd.DataFrame({"date": pd.to_datetime(dates)})
    gaps = check_missing_streaks(df, max_streak=5)
    assert len(gaps) >= 1


def test_missing_streaks_normal_weekend_not_flagged():
    """금요일→다음 월요일은 정상(주말). 결측 아님."""
    dates = [date(2026, 1, 9), date(2026, 1, 12)]  # 금 → 월
    df = pd.DataFrame({"date": pd.to_datetime(dates)})
    gaps = check_missing_streaks(df, max_streak=5)
    assert len(gaps) == 0


def test_extreme_returns_flags_split():
    """50:1 분할 같은 -98% 점프 검출."""
    df = pd.DataFrame(
        {
            "date": pd.date_range("2026-01-01", periods=3),
            "close": [2_640_000.0, 52_800.0, 53_000.0],
        }
    )
    flagged = check_extreme_returns(df, threshold=0.30)
    assert len(flagged) >= 1
    assert flagged[0][1] < -0.95  # ~-98%


def test_extreme_returns_normal_no_flag():
    """일반 ±2% 변동은 검출 안 됨."""
    df = pd.DataFrame(
        {
            "date": pd.date_range("2026-01-01", periods=10),
            "close": [100.0 * (1.02**i) for i in range(10)],
        }
    )
    flagged = check_extreme_returns(df, threshold=0.30)
    assert len(flagged) == 0


def test_minute_gaps_detects_long_gap():
    """5분봉 정상 + 30분 누락 → 1건 검출."""
    times = [
        datetime(2026, 1, 5, 9, 0),
        datetime(2026, 1, 5, 9, 5),
        datetime(2026, 1, 5, 9, 10),
        datetime(2026, 1, 5, 9, 40),  # 30분 점프
        datetime(2026, 1, 5, 9, 45),
    ]
    df = pd.DataFrame({"datetime": times})
    gaps = check_minute_gaps(df, max_gap_minutes=5)
    assert len(gaps) >= 1
