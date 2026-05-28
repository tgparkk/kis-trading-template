"""Raschke Phase 2 — 일봉 전략."""

from __future__ import annotations

from typing import List, Optional

from strategies.books._base_book_strategy import BookStrategy
from strategies.books.raschke_street_smarts.rules_daily import ALL_RULES_DAILY


BOOK_META_DAILY = {
    "id": "raschke_street_smarts_daily",
    "name": "Street Smarts Daily (Linda Raschke)",
    "category": "swing",
    "data_granularity": "daily",
}


def _all_rules():
    return [cls() for cls in ALL_RULES_DAILY]


class RaschkeStreetSmartsDailyStrategy(BookStrategy):
    name = "RaschkeStreetSmartsDailyStrategy"
    version = "1.0.0"
    description = "Raschke Street Smarts — 5 daily setups (Phase 2)"
    holding_period = "swing"


def build_strategy_daily(
    mode: str = "single",
    target_rule: Optional[str] = None,
    or_members: Optional[List[str]] = None,
) -> RaschkeStreetSmartsDailyStrategy:
    return RaschkeStreetSmartsDailyStrategy(
        rules=_all_rules(),
        mode=mode,
        target_rule=target_rule,
        or_members=or_members,
    )
