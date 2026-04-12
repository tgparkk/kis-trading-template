"""
Constants 유효성 검증 테스트
"""
from config.constants import (
    OHLCV_LOOKBACK_DAYS,
    CANDIDATE_MIN_DAILY_DATA,
)


def test_ohlcv_lookback_covers_min_data():
    """OHLCV_LOOKBACK_DAYS가 전략 최소 요구 일봉 수를 충분히 커버하는지 검증.

    달력일 → 영업일 환산: OHLCV_LOOKBACK_DAYS * 5/7
    조건: 영업일 환산값 >= CANDIDATE_MIN_DAILY_DATA + 5 (여유분)
    현재 CANDIDATE_MIN_DAILY_DATA = 22 → 요구 최소 = 27 영업일 → OHLCV_LOOKBACK_DAYS >= 38 달력일
    """
    business_days_approx = OHLCV_LOOKBACK_DAYS * 5 / 7
    required = CANDIDATE_MIN_DAILY_DATA + 5
    assert business_days_approx >= required, (
        f"OHLCV_LOOKBACK_DAYS={OHLCV_LOOKBACK_DAYS}일 → "
        f"영업일 환산 약 {business_days_approx:.1f}일이 "
        f"최소 요구({CANDIDATE_MIN_DAILY_DATA}+5={required}일)에 미달. "
        f"OHLCV_LOOKBACK_DAYS를 최소 {int(required * 7 / 5) + 1}로 올려야 합니다."
    )
