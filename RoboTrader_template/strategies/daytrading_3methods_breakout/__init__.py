"""
DayTrading 3Methods Breakout Strategy — 유지윤 『데이트레이딩 3대 타법』 돌파 타법 실전 전략

백테스트 검증판(strategies/books/daytrading_3methods/rules.py
rule_breakout_prev_high)을 실전 파이프라인용으로 코드화. 진입 신호는 백테스트
룰을 직접 재사용하여 1:1 일치를 보장한다.
"""

from .strategy import DayTrading3MethodsBreakoutStrategy

__all__ = ["DayTrading3MethodsBreakoutStrategy"]
