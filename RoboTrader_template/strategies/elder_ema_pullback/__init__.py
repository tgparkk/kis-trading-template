"""
Elder EMA Pullback Strategy — Triple Screen (Variant A) 실전 전략

백테스트 검증판(scripts/run_elder_triple_screen.py --variant A,
rule=triple_screen_ema_pullback)을 실전 파이프라인용으로 코드화.
진입 신호는 strategies/books/elder_triple_screen/rules.py의 헬퍼를
직접 재사용하여 백테스트와 1:1 일치를 보장한다.
"""

from .strategy import ElderEmaPullbackStrategy

__all__ = ["ElderEmaPullbackStrategy"]
