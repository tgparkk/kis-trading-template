"""태쏘 『데이트레이딩 바이블 2』 기법 B — 종가배팅 일봉 스윙 전략.

장대양봉(D0) → 단봉조정(D1) → D1 종가(≈익일 시가) 매수 → 익일 오전 +2~3% 익절.
다른 한국 책 일봉 전략(dino_surge / moonbyungro_metric)과 동일 구조.
"""

from __future__ import annotations

from typing import List, Optional

from strategies.books._base_book_strategy import BookStrategy
from strategies.books.close_betting.rules import ALL_RULES


BOOK_META = {
    "id": "close_betting",
    "name": "데이트레이딩 바이블 2 — 종가배팅 (태쏘)",
    "category": "surge_pullback_kr",
    "data_granularity": "daily",
}


class CloseBettingStrategy(BookStrategy):
    name = "CloseBettingStrategy"
    version = "1.0.0"
    description = "태쏘 종가배팅 (장대양봉→단봉조정→종가매수, 익일 +2~3% 익절)"
    author = "kis-template"
    holding_period = "swing"


def build_strategy(
    mode: str = "single",
    target_rule: Optional[str] = None,
    or_members: Optional[List[str]] = None,
) -> CloseBettingStrategy:
    return CloseBettingStrategy(
        rules=[cls() for cls in ALL_RULES],
        mode=mode,
        target_rule=target_rule,
        or_members=or_members,
    )
