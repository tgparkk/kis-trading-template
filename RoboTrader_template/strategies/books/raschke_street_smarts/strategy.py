"""Linda Raschke - Street Smarts."""

from __future__ import annotations

from typing import List, Optional

from strategies.books._base_book_strategy import BookStrategy
from strategies.books.raschke_street_smarts.rules import ALL_RULES


BOOK_META = {
    "id": "raschke_street_smarts",
    "name": "Street Smarts (Linda Raschke & Larry Connors)",
    "category": "intraday",  # Phase 1 분봉 5개만
    "data_granularity": "minute",
}


def _all_rules():
    return [cls() for cls in ALL_RULES]


class RaschkeStreetSmartsStrategy(BookStrategy):
    name = "RaschkeStreetSmartsStrategy"
    version = "1.0.0"
    description = "Linda Raschke - Street Smarts (5 분봉 셋업)"
    author = "kis-template"
    holding_period = "intraday"


def build_strategy(
    mode: str = "single",
    target_rule: Optional[str] = None,
    or_members: Optional[List[str]] = None,
) -> RaschkeStreetSmartsStrategy:
    return RaschkeStreetSmartsStrategy(
        rules=_all_rules(),
        mode=mode,
        target_rule=target_rule,
        or_members=or_members,
    )
