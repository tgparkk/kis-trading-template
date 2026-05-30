"""
Minervini Volume Dry-up Strategy (Variant B) — 페이퍼 전략

백테스트 검증판(strategies/books/minervini_vcp/rules.py rule_volume_dryup)을
실전 파이프라인용으로 코드화. 진입 신호는 rule_volume_dryup.evaluate를 직접
재사용하여 백테스트와 1:1 일치를 보장한다. 청산은 variant B(sl/tp/max_hold만,
trail·trend_flip 없음).
"""

from .strategy import MinerviniVolumeDryupStrategy

__all__ = ["MinerviniVolumeDryupStrategy"]
