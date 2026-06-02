"""2-트랙 PIT(Point-In-Time) 시장국면 판별 패키지.

트랙A(daily) = 스윙(일봉 장기): KOSPI SMA120 + 20일기울기 + %above MA120 breadth
              + 20일RV 252일 trailing 백분위 + forward-only confirm 디바운스.
트랙B(minute) = 데이트레이딩(당일·장중): 대형주 합성지수 누적수익/VWAP + 개장범위(OR)
              + 분봉 breadth + 갭/장중RV. 진입봉 시점까지 누적.

★절대조건: No Look-Ahead — 판정 시점(≤T 또는 ≤t) 데이터로만.
데이터 SSOT: daily_prices(stock_code='KOSPI') + minute_candles.
market_index(frozen)·market_regime.peak_trough(look-ahead) 사용 금지.

설계 출처:
  reports/books_research/_EXPERT_regime_methods.md (트랙A)
  reports/books_research/_EXPERT_regime_daytrading_2track.md (트랙B + 통합스펙)
"""
from core.regime.regime_classifier import (
    DailyRegimeParams,
    IntradayRegimeParams,
    classify_daily,
    classify_intraday,
    regime_at,
)

__all__ = [
    "DailyRegimeParams",
    "IntradayRegimeParams",
    "classify_daily",
    "classify_intraday",
    "regime_at",
]
