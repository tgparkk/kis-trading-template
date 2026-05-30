"""
Book Pullback MA5 Strategy — 『트레이딩의 전설』(Book15) ma5_pullback 실전 전략

백테스트 검증판(strategies/books/trading_legends/rules_daily.py
rule_ma5_pullback)을 실전 파이프라인용으로 코드화. 진입 신호는 백테스트
룰을 직접 재사용하여 1:1 일치를 보장한다.
"""

from .strategy import BookPullbackMa5Strategy

__all__ = ["BookPullbackMa5Strategy"]
