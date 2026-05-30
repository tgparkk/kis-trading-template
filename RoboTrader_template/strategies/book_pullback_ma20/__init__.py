"""
Book Pullback MA20 Strategy — 강창권 『단기 트레이딩의 정석』 A-07 실전 전략

백테스트 검증판(strategies/books/haru_silijeon/rules_daily.py
rule_daily_ma20_pullback)을 실전 파이프라인용으로 코드화. 진입 신호는
백테스트 룰을 직접 재사용하여 1:1 일치를 보장한다.
"""

from .strategy import BookPullbackMa20Strategy

__all__ = ["BookPullbackMa20Strategy"]
