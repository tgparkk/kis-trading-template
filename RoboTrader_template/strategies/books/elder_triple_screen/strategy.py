"""Elder Triple Screen — 일봉 전략.

Screen 1(추세)을 일봉 65일 EMA proxy로 근사 → 종목 자기완결(지수·ctx 불필요).
Screen 3(매수스톱) 체결은 run 스크립트가 처리, rule은 Screen 1+2 신호만 판정한다.
"""
from __future__ import annotations

from typing import List, Optional

from strategies.books._base_book_strategy import BookStrategy
from strategies.books.elder_triple_screen.rules import ALL_RULES


BOOK_META = {
    "id": "elder_triple_screen",
    "name": "Elder Triple Screen (Trading for a Living)",
    "category": "multi_timeframe_trend",
    "data_granularity": "daily",
}


class ElderTripleScreenStrategy(BookStrategy):
    name = "ElderTripleScreenStrategy"
    version = "1.0.0"
    description = "Elder Triple Screen — EMA65 추세 + 일봉 오실레이터 눌림 진입 4종"
    holding_period = "swing"


def build_strategy(
    mode: str = "single",
    target_rule: Optional[str] = None,
    or_members: Optional[List[str]] = None,
) -> ElderTripleScreenStrategy:
    return ElderTripleScreenStrategy(
        rules=[cls() for cls in ALL_RULES],
        mode=mode,
        target_rule=target_rule,
        or_members=or_members,
    )
