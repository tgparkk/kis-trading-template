"""디노(백새봄) 『돈이 된다! 급등주 투자법』 — 일봉 급등주 눌림 회전 전략.

Book 16. 눌린 우량 급등주(디노테스트) → +10% 무조건 익절 회전.
다른 한국 책 일봉 전략(haru_silijeon_daily / moonbyungro_metric)과 동일 구조.
"""

from __future__ import annotations

from typing import List, Optional

from strategies.books._base_book_strategy import BookStrategy
from strategies.books.dino_surge.rules import ALL_RULES


BOOK_META = {
    "id": "dino_surge",
    "name": "돈이 된다! 급등주 투자법 (디노/백새봄)",
    "category": "surge_pullback_kr",
    "data_granularity": "daily",
}


class DinoSurgeStrategy(BookStrategy):
    name = "DinoSurgeStrategy"
    version = "1.0.0"
    description = "디노 급등주 투자법 (눌린 급등주 디노테스트 + OBV/RSI 바닥반전, +10% 회전)"
    author = "kis-template"
    holding_period = "swing"


def build_strategy(
    mode: str = "single",
    target_rule: Optional[str] = None,
    or_members: Optional[List[str]] = None,
) -> DinoSurgeStrategy:
    return DinoSurgeStrategy(
        rules=[cls() for cls in ALL_RULES],
        mode=mode,
        target_rule=target_rule,
        or_members=or_members,
    )
