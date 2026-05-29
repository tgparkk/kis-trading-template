"""Lynch One Up on Wall Street — 일봉 펀더멘털 전략."""
from __future__ import annotations

from typing import List, Optional

from strategies.books._base_book_strategy import BookStrategy
from strategies.books.lynch_one_up.rules import ALL_RULES


BOOK_META = {
    "id": "lynch_one_up",
    "name": "Lynch One Up on Wall Street",
    "category": "fundamental_garp",
    "data_granularity": "daily",
}


class LynchOneUpStrategy(BookStrategy):
    name = "LynchOneUpStrategy"
    version = "1.0.0"
    description = "Peter Lynch GARP (6카테고리 → PEG/성장/품질 기반 4룰)"
    holding_period = "swing"


def build_strategy(
    mode: str = "single",
    target_rule: Optional[str] = None,
    or_members: Optional[List[str]] = None,
) -> LynchOneUpStrategy:
    return LynchOneUpStrategy(
        rules=[cls() for cls in ALL_RULES],
        mode=mode,
        target_rule=target_rule,
        or_members=or_members,
    )
