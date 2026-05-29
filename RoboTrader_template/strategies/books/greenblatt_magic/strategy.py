"""Greenblatt Magic Formula — 일봉 펀더멘털 횡단면 순위 전략."""
from __future__ import annotations

from typing import List, Optional

from strategies.books._base_book_strategy import BookStrategy
from strategies.books.greenblatt_magic.rules import ALL_RULES


BOOK_META = {
    "id": "greenblatt_magic",
    "name": "Greenblatt Magic Formula (The Little Book That Beats the Market)",
    "category": "fundamental_quality_value",
    "data_granularity": "daily",
}


class GreenblattMagicStrategy(BookStrategy):
    name = "GreenblattMagicStrategy"
    version = "1.0.0"
    description = "Joel Greenblatt Magic Formula (EY+ROC 횡단면 순위 + per-stock 임계)"
    holding_period = "swing"


def build_strategy(
    mode: str = "single",
    target_rule: Optional[str] = None,
    or_members: Optional[List[str]] = None,
) -> GreenblattMagicStrategy:
    return GreenblattMagicStrategy(
        rules=[cls() for cls in ALL_RULES],
        mode=mode,
        target_rule=target_rule,
        or_members=or_members,
    )
