"""
lib/signals — PIT-safe 시그널 함수 패키지
==========================================

No Look-Ahead 절대 대원칙:
- 모든 함수는 T시점까지의 데이터만 사용
- shift(-N) 사용 금지 (forward_return 모듈만 허용)
- 추측 임계값 추가 금지, 카탈로그에 명시된 표준만
"""

from .flow import obv, cmf
from .trend import ma_alignment_score
from .roe_filter import roe_pit, roe_quintile, roe_filter
from .vwap import intraday_vwap, vwap_position, vwap_bands, anchored_vwap
from .calendar_tom import get_trading_calendar, is_tom_window, tom_signal
from .book_daily import new_high_breakout, volume_spike_3x, ma20_pullback, closing_bet
from .book_minute import abcd_pattern, bull_flag, opening_range_breakout, red_to_green

__all__ = [
    "obv", "cmf", "ma_alignment_score",
    "roe_pit", "roe_quintile", "roe_filter",
    "intraday_vwap", "vwap_position", "vwap_bands", "anchored_vwap",
    "get_trading_calendar", "is_tom_window", "tom_signal",
    "new_high_breakout", "volume_spike_3x", "ma20_pullback", "closing_bet",
    "abcd_pattern", "bull_flag", "opening_range_breakout", "red_to_green",
]
