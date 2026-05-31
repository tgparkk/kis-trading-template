"""유지윤 『하루 만에 수익 내는 데이트레이딩 3대 타법』 — 일봉 바닥/지지/돌파 전략.

3대 타법(바닥·지지·돌파)을 일봉으로 환원한 4종 룰. 다른 한국 책 일봉 전략
(trading_legends / dino_surge)과 동일 구조.
"""

from __future__ import annotations

from typing import List, Optional

from strategies.books._base_book_strategy import BookStrategy
from strategies.books.daytrading_3methods.rules import ALL_RULES


BOOK_META = {
    "id": "daytrading_3methods",
    "name": "하루 만에 수익 내는 데이트레이딩 3대 타법 (유지윤)",
    "category": "swing",
    "data_granularity": "daily",
}


class DayTrading3MethodsStrategy(BookStrategy):
    name = "DayTrading3MethodsStrategy"
    version = "1.0.0"
    description = "유지윤 데이트레이딩 3대 타법 (바닥 3×3/2지지·지지 10캔들·돌파 전고점, 거래량 폭증 트리거)"
    author = "kis-template"
    holding_period = "swing"


def build_strategy(
    mode: str = "single",
    target_rule: Optional[str] = None,
    or_members: Optional[List[str]] = None,
) -> DayTrading3MethodsStrategy:
    return DayTrading3MethodsStrategy(
        rules=[cls() for cls in ALL_RULES],
        mode=mode,
        target_rule=target_rule,
        or_members=or_members,
    )
