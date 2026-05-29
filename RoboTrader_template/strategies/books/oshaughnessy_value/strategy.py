"""O'Shaughnessy What Works on Wall Street — 일봉 펀더멘털 횡단면 순위 전략."""
from __future__ import annotations

from typing import List, Optional

from strategies.books._base_book_strategy import BookStrategy
from strategies.books.oshaughnessy_value.rules import ALL_RULES


BOOK_META = {
    "id": "osullivan_what_works",
    "name": "O'Shaughnessy What Works on Wall Street",
    "category": "fundamental_factor_rank",
    "data_granularity": "daily",
}


class OShaughnessyValueStrategy(BookStrategy):
    name = "OShaughnessyValueStrategy"
    version = "1.0.0"
    description = "James O'Shaughnessy What Works on Wall Street (VC1 가치복합 + 추세가치 + 저PSR 횡단면 순위)"
    holding_period = "swing"


def build_strategy(
    mode: str = "single",
    target_rule: Optional[str] = None,
    or_members: Optional[List[str]] = None,
) -> OShaughnessyValueStrategy:
    return OShaughnessyValueStrategy(
        rules=[cls() for cls in ALL_RULES],
        mode=mode,
        target_rule=target_rule,
        or_members=or_members,
    )
