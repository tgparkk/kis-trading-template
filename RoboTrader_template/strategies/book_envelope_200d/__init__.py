"""
Book Envelope 200d High Strategy — 『트레이딩 전략서』(Book 19) 200일 신고가+Envelope 돌파 실전 전략.

백테스트 정본(quant 일봉) 재측정 + OOS 홀드아웃(train 1.20 / test 1.82) 강건 확인 후
6번째 페이퍼 전략으로 추가. 진입 신호는 백테스트 룰(rule_envelope_200d_high)을 직접
재사용하여 1:1 일치를 보장하며, 200봉 요구에 맞춰 진입 평가용 일봉은 quant 에서 조회한다.
"""

from .strategy import BookEnvelope200dStrategy

__all__ = ["BookEnvelope200dStrategy"]
