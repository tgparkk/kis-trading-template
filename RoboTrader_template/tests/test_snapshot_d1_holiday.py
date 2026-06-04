"""
Task 11: D-1 휴장일 폴백 검증
===========================
2026-06-03은 지방선거로 휴장. 06-04의 직전 거래일은 06-02여야 한다.

import 경로: utils.korean_time.get_previous_trading_day
  - 실제 구현은 config.market_hours 정상 import 시 utils.korean_holidays.is_holiday 사용
  - _SPECIAL_HOLIDAYS에 "2026-06-03": "지방선거" 등록됨 → 올바르게 건너뜀 확인
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from datetime import datetime
from utils.korean_time import get_previous_trading_day


def test_previous_trading_day_skips_holiday():
    """2026-06-04(수) → 직전 거래일은 2026-06-02(월) (06-03 지방선거 휴장 건너뜀)"""
    d = datetime(2026, 6, 4, 9, 0)
    prev = get_previous_trading_day(d)
    assert prev.strftime("%Y-%m-%d") == "2026-06-02", (
        f"직전 거래일이 2026-06-02여야 하는데 {prev.strftime('%Y-%m-%d')} 반환 — "
        "korean_holidays._SPECIAL_HOLIDAYS에 2026-06-03 등록 여부 확인 필요"
    )


def test_previous_trading_day_skips_weekend():
    """2026-06-08(월) → 직전 거래일은 2026-06-05(금) (토/일 건너뜀)"""
    d = datetime(2026, 6, 8, 9, 0)
    prev = get_previous_trading_day(d)
    assert prev.strftime("%Y-%m-%d") == "2026-06-05", (
        f"직전 거래일이 2026-06-05여야 하는데 {prev.strftime('%Y-%m-%d')} 반환"
    )


def test_previous_trading_day_normal_weekday():
    """2026-06-04(수) 기준은 이미 위에서 검증; 추가로 평일 연속 확인"""
    d = datetime(2026, 6, 5, 9, 0)
    prev = get_previous_trading_day(d)
    assert prev.strftime("%Y-%m-%d") == "2026-06-04"
