"""앤드류 아지즈 - How to Day Trade for a Living."""

from __future__ import annotations

from typing import List, Optional

from strategies.books._base_book_strategy import BookStrategy
from strategies.books.aziz_day_trade.rules import ALL_RULES


BOOK_META = {
    "id": "aziz_day_trade",
    "name": "How to Day Trade for a Living (Andrew Aziz)",
    "category": "intraday",
    "data_granularity": "minute",
}


def _all_rules():
    return [cls() for cls in ALL_RULES]


class AzizDayTradeStrategy(BookStrategy):
    name = "AzizDayTradeStrategy"
    version = "1.0.0"
    description = "Andrew Aziz - How to Day Trade for a Living (8 setups)"
    author = "kis-template"
    holding_period = "intraday"


def build_strategy(
    mode: str = "single",
    target_rule: Optional[str] = None,
    or_members: Optional[List[str]] = None,
) -> AzizDayTradeStrategy:
    return AzizDayTradeStrategy(
        rules=_all_rules(),
        mode=mode,
        target_rule=target_rule,
        or_members=or_members,
    )
