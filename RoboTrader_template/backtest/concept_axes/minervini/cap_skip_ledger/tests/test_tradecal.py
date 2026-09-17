"""후보 달력 조인 — D 의 후보는 «직전 거래일» 스냅샷이다(휴장 다음 날 포함)."""
from datetime import date

from backtest.concept_axes.minervini.cap_skip_ledger.tradecal import (
    days_after, days_in_range, last_n_days, prev_trading_day,
)

# 2026-08 실측 KOSPI 달력 일부: 08-15(토)·08-16(일)·08-17(월, 광복절 대체휴일) 없음.
CAL = [date(2026, 8, 13), date(2026, 8, 14), date(2026, 8, 18), date(2026, 8, 19),
       date(2026, 9, 11), date(2026, 9, 14), date(2026, 9, 15)]


def test_prev_trading_day_ordinary():
    assert prev_trading_day(CAL, date(2026, 8, 19)) == date(2026, 8, 18)


def test_prev_trading_day_after_weekend():
    # 월요일 09-14 의 후보 = 금요일 09-11 스냅샷
    assert prev_trading_day(CAL, date(2026, 9, 14)) == date(2026, 9, 11)


def test_prev_trading_day_after_holiday():
    # 대체휴일(08-17) 다음 날 08-18 의 후보 = 08-14 스냅샷 (실측: scan_date 2026-08-14 행 created_at 08-18 09:00)
    assert prev_trading_day(CAL, date(2026, 8, 18)) == date(2026, 8, 14)


def test_prev_trading_day_on_non_trading_day_input():
    # 휴장일 자체를 넣어도 «엄격히 이전» 거래일
    assert prev_trading_day(CAL, date(2026, 8, 17)) == date(2026, 8, 14)


def test_prev_trading_day_none_at_start():
    assert prev_trading_day(CAL, date(2026, 8, 13)) is None


def test_prev_trading_day_unsorted_input():
    assert prev_trading_day(list(reversed(CAL)), date(2026, 9, 15)) == date(2026, 9, 14)


def test_range_helpers():
    assert days_in_range(CAL, date(2026, 8, 14), date(2026, 8, 18)) == [date(2026, 8, 14), date(2026, 8, 18)]
    assert last_n_days(CAL, date(2026, 8, 19), 2) == [date(2026, 8, 18), date(2026, 8, 19)]
    assert days_after(CAL, date(2026, 8, 14), 2) == [date(2026, 8, 18), date(2026, 8, 19)]
