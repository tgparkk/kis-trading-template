"""Mike Bellafiore - One Good Trade / The PlayBook."""

from __future__ import annotations

from typing import List, Optional

from strategies.books._base_book_strategy import BookStrategy
from strategies.books.bellafiore_playbook.rules import ALL_RULES


BOOK_META = {
    "id": "bellafiore_playbook",
    "name": "One Good Trade / The PlayBook (Mike Bellafiore)",
    "category": "intraday",
    "data_granularity": "minute",
}


def _all_rules():
    return [cls() for cls in ALL_RULES]


class BellafiorePlayBookStrategy(BookStrategy):
    name = "BellafiorePlayBookStrategy"
    version = "1.0.0"
    description = "Mike Bellafiore - One Good Trade / The PlayBook (6 setups)"
    author = "kis-template"
    holding_period = "intraday"


def build_strategy(
    mode: str = "single",
    target_rule: Optional[str] = None,
    or_members: Optional[List[str]] = None,
) -> BellafiorePlayBookStrategy:
    return BellafiorePlayBookStrategy(
        rules=_all_rules(),
        mode=mode,
        target_rule=target_rule,
        or_members=or_members,
    )
