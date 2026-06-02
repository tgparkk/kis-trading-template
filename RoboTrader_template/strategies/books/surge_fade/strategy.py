"""태쏘의 데이트레이딩 바이블 2 — 급등주 투매폭 매매법 (15분봉).

기법 A(급등주 투매폭) 단일 룰을 BookStrategy 로 코드화.
기법 B(종가배팅)는 일봉 트랙으로 별도.
"""

from __future__ import annotations

from typing import List, Optional

from strategies.books._base_book_strategy import BookStrategy
from strategies.books.surge_fade.rules import ALL_RULES


BOOK_META = {
    "id": "surge_fade",
    "name": "태쏘의 데이트레이딩 바이블 2 — 급등주 투매폭 매매법 (15분봉)",
    "category": "intraday",
    "data_granularity": "minute_15",
}


def _all_rules():
    return [cls() for cls in ALL_RULES]


class SurgeFadeStrategy(BookStrategy):
    name = "SurgeFadeStrategy"
    version = "1.0.0"
    description = "급등주 투매폭 매매법 (15분봉, 고점대비 적정 투매폭 눌림 + 지지확인 → +7% 반등)"
    author = "kis-template"
    holding_period = "intraday"


def build_strategy(
    mode: str = "single",
    target_rule: Optional[str] = None,
    or_members: Optional[List[str]] = None,
) -> SurgeFadeStrategy:
    return SurgeFadeStrategy(
        rules=_all_rules(),
        mode=mode,
        target_rule=target_rule,
        or_members=or_members,
    )
