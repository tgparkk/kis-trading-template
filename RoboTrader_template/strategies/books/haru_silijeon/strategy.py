"""강창권 - 주식투자 단기 트레이딩의 정석 (분봉 묶음).

A등급 분봉 전략 6종을 BookStrategy 룰로 코드화.
일봉 묶음(5·10/20/60/240·480일선, 신고가, 스윙 등)은 별도.
"""

from __future__ import annotations

from typing import List, Optional

from strategies.books._base_book_strategy import BookStrategy
from strategies.books.haru_silijeon.rules import ALL_RULES


BOOK_META = {
    "id": "haru_silijeon",
    "name": "주식투자 단기 트레이딩의 정석 (강창권) — 분봉",
    "category": "intraday",
    "data_granularity": "minute",
}


def _all_rules():
    return [cls() for cls in ALL_RULES]


class HaruSilijeonStrategy(BookStrategy):
    name = "HaruSilijeonStrategy"
    version = "1.0.0"
    description = "강창권 - 단기 트레이딩의 정석 (분봉 6 setups, CK480 시그니처)"
    author = "kis-template"
    holding_period = "intraday"


def build_strategy(
    mode: str = "single",
    target_rule: Optional[str] = None,
    or_members: Optional[List[str]] = None,
) -> HaruSilijeonStrategy:
    return HaruSilijeonStrategy(
        rules=_all_rules(),
        mode=mode,
        target_rule=target_rule,
        or_members=or_members,
    )
