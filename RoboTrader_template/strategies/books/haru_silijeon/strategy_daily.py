"""강창권 - 주식투자 단기 트레이딩의 정석 (일봉 묶음).

A등급 일봉 전략 7종을 BookStrategy 룰로 코드화.
분봉 묶음(strategy.py / rules.py)과 별개 — 분봉 strategy 미수정.
"""

from __future__ import annotations

from typing import List, Optional

from strategies.books._base_book_strategy import BookStrategy
from strategies.books.haru_silijeon.rules_daily import ALL_DAILY_RULES


BOOK_META_DAILY = {
    "id": "haru_silijeon_daily",
    "name": "주식투자 단기 트레이딩의 정석 (강창권) — 일봉",
    "category": "swing",
    "data_granularity": "daily",
}


def _all_rules():
    return [cls() for cls in ALL_DAILY_RULES]


class HaruSilijeonDailyStrategy(BookStrategy):
    name = "HaruSilijeonDailyStrategy"
    version = "1.0.0"
    description = "강창권 - 단기 트레이딩의 정석 (일봉 7 setups: 20일선 눌림목 +10% 외)"
    author = "kis-template"
    holding_period = "swing"


def build_strategy_daily(
    mode: str = "single",
    target_rule: Optional[str] = None,
    or_members: Optional[List[str]] = None,
) -> HaruSilijeonDailyStrategy:
    return HaruSilijeonDailyStrategy(
        rules=_all_rules(),
        mode=mode,
        target_rule=target_rule,
        or_members=or_members,
    )
