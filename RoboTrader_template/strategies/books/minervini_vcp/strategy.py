"""Minervini VCP — 일봉 전략."""
from __future__ import annotations

from typing import List, Optional

from strategies.books._base_book_strategy import BookStrategy
from strategies.books.minervini_vcp.rules import ALL_RULES


BOOK_META = {
    "id": "minervini_vcp",
    "name": "Minervini SEPA + VCP (Trade Like a Stock Market Wizard)",
    "category": "growth",
    "data_granularity": "daily",
}


class MinerviniVCPStrategy(BookStrategy):
    name = "MinerviniVCPStrategy"
    version = "1.0.0"
    description = "Minervini SEPA Trend Template + VCP breakout"
    holding_period = "swing"


def build_strategy(
    mode: str = "single",
    target_rule: Optional[str] = None,
    or_members: Optional[List[str]] = None,
) -> MinerviniVCPStrategy:
    return MinerviniVCPStrategy(
        rules=[cls() for cls in ALL_RULES],
        mode=mode,
        target_rule=target_rule,
        or_members=or_members,
    )
