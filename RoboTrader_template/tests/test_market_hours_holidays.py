"""
해외시장 공휴일 + KRX 공휴일 MarketHours 통합 테스트
======================================================
- KRX: 근로자의날, 설날 → is_market_open=False
- NYSE/NASDAQ: 독립기념일, 크리스마스 → is_market_open=False
- TSE: 일본 공휴일 → is_market_open=False
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest
import pytz
from datetime import datetime

KST = pytz.timezone('Asia/Seoul')
ET = pytz.timezone('America/New_York')
JST = pytz.timezone('Asia/Tokyo')


def kst_dt(year, month, day, hour=10, minute=0):
    return KST.localize(datetime(year, month, day, hour, minute))


def et_dt(year, month, day, hour=11, minute=0):
    return ET.localize(datetime(year, month, day, hour, minute))


def jst_dt(year, month, day, hour=10, minute=0):
    return JST.localize(datetime(year, month, day, hour, minute))


# ---------------------------------------------------------------------------
# KRX 공휴일
# ---------------------------------------------------------------------------

class TestKRXHolidays:
    """KRX 공휴일 시 장 마감 확인"""

    def test_krx_labor_day_closed(self):
        """근로자의 날(2026-05-01) KRX 장 마감"""
        from config.market_hours import MarketHours
        dt = kst_dt(2026, 5, 1, 10, 0)
        assert not MarketHours.is_market_open('KRX', dt), \
            "근로자의 날은 KRX 휴장이어야 한다"

    def test_krx_lunar_new_year_closed(self):
        """설날(2026-02-17) KRX 장 마감"""
        from config.market_hours import MarketHours
        dt = kst_dt(2026, 2, 17, 10, 0)
        assert not MarketHours.is_market_open('KRX', dt)

    def test_krx_chuseok_closed(self):
        """추석(2026-09-25) KRX 장 마감"""
        from config.market_hours import MarketHours
        dt = kst_dt(2026, 9, 25, 10, 0)
        assert not MarketHours.is_market_open('KRX', dt)

    def test_krx_normal_day_open(self):
        """평일 장중 KRX 장 개장"""
        from config.market_hours import MarketHours
        # 2026-04-27 월요일 10시 (공휴일 없음)
        dt = kst_dt(2026, 4, 27, 10, 0)
        assert MarketHours.is_market_open('KRX', dt)

    def test_krx_labor_day_phase_closed(self):
        """근로자의 날 get_market_phase = CLOSED"""
        from config.market_hours import MarketHours, MarketPhase
        dt = kst_dt(2026, 5, 1, 10, 0)
        assert MarketHours.get_market_phase('KRX', dt) == MarketPhase.CLOSED

    def test_krx_holiday_status(self):
        """근로자의 날 get_market_status = holiday"""
        from config.market_hours import MarketHours
        dt = kst_dt(2026, 5, 1, 10, 0)
        assert MarketHours.get_market_status('KRX', dt) == "holiday"


# ---------------------------------------------------------------------------
# NYSE / NASDAQ 공휴일
# ---------------------------------------------------------------------------

class TestNYSEHolidays:
    """NYSE/NASDAQ 공휴일 시 장 마감 확인"""

    def test_nyse_independence_day_closed(self):
        """독립기념일(2025-07-04) NYSE 장 마감"""
        from config.market_hours import MarketHours
        dt = et_dt(2025, 7, 4, 11, 0)
        assert not MarketHours.is_market_open('NYSE', dt), \
            "독립기념일은 NYSE 휴장이어야 한다"

    def test_nyse_christmas_closed(self):
        """크리스마스(2025-12-25) NYSE 장 마감"""
        from config.market_hours import MarketHours
        dt = et_dt(2025, 12, 25, 11, 0)
        assert not MarketHours.is_market_open('NYSE', dt)

    def test_nasdaq_independence_day_closed(self):
        """독립기념일(2025-07-04) NASDAQ 장 마감"""
        from config.market_hours import MarketHours
        dt = et_dt(2025, 7, 4, 11, 0)
        assert not MarketHours.is_market_open('NASDAQ', dt)

    def test_nyse_normal_day_open(self):
        """NYSE 평일 장중 개장"""
        from config.market_hours import MarketHours
        # 2025-07-07 월요일 11시 ET
        dt = et_dt(2025, 7, 7, 11, 0)
        assert MarketHours.is_market_open('NYSE', dt)

    def test_nyse_is_holiday_helper(self):
        """_is_holiday 헬퍼 — NYSE 독립기념일 True"""
        from config.market_hours import MarketHours
        dt = et_dt(2025, 7, 4, 11, 0)
        assert MarketHours._is_holiday('NYSE', dt)

    def test_nyse_is_holiday_helper_normal(self):
        """_is_holiday 헬퍼 — NYSE 평일 False"""
        from config.market_hours import MarketHours
        dt = et_dt(2025, 7, 7, 11, 0)
        assert not MarketHours._is_holiday('NYSE', dt)


# ---------------------------------------------------------------------------
# TSE 공휴일
# ---------------------------------------------------------------------------

class TestTSEHolidays:
    """TSE(도쿄) 공휴일 시 장 마감 확인"""

    def test_tse_new_year_closed(self):
        """신정(2026-01-01) TSE 장 마감"""
        from config.market_hours import MarketHours
        dt = jst_dt(2026, 1, 1, 10, 0)
        assert not MarketHours.is_market_open('TSE', dt), \
            "일본 신정은 TSE 휴장이어야 한다"

    def test_tse_labor_thanksgiving_closed(self):
        """근로감사의 날(2026-11-23) TSE 장 마감"""
        from config.market_hours import MarketHours
        dt = jst_dt(2026, 11, 23, 10, 0)
        assert not MarketHours.is_market_open('TSE', dt)

    def test_tse_is_holiday_helper(self):
        """_is_holiday 헬퍼 — TSE 신정 True"""
        from config.market_hours import MarketHours
        dt = jst_dt(2026, 1, 1, 10, 0)
        assert MarketHours._is_holiday('TSE', dt)
