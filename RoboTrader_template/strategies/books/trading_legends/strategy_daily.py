"""『트레이딩의 전설』(키움영웅전 9인 트레이더) — 일봉 묶음.

일봉 단위로 정량화한 6종 기법을 BookStrategy 룰로 코드화.
haru_silijeon/strategy_daily.py 패턴과 1:1 동일.
"""

from __future__ import annotations

from typing import List, Optional

from strategies.books._base_book_strategy import BookStrategy
from strategies.books.trading_legends.rules_daily import ALL_DAILY_RULES


BOOK_META_DAILY = {
    "id": "trading_legends_daily",
    "name": "트레이딩의 전설 (키움영웅전 9인) — 일봉",
    "category": "swing",
    "data_granularity": "daily",
}


def _all_rules():
    return [cls() for cls in ALL_DAILY_RULES]


class TradingLegendsDailyStrategy(BookStrategy):
    name = "TradingLegendsDailyStrategy"
    version = "1.0.0"
    description = "트레이딩의 전설 (키움영웅전 9인 일봉 6 setups: 종가매매/상따/전고점 돌파 외)"
    author = "kis-template"
    holding_period = "swing"


def build_strategy_daily(
    mode: str = "single",
    target_rule: Optional[str] = None,
    or_members: Optional[List[str]] = None,
) -> TradingLegendsDailyStrategy:
    return TradingLegendsDailyStrategy(
        rules=_all_rules(),
        mode=mode,
        target_rule=target_rule,
        or_members=or_members,
    )
