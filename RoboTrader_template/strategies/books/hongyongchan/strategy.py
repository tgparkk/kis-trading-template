"""홍용찬 실전 퀀트투자 — 일봉 펀더멘털 4선 저밸류 + 소형주 + 성장/퀄리티 게이트 횡단면 순위 전략."""
from __future__ import annotations

from typing import List, Optional

from strategies.books._base_book_strategy import BookStrategy
from strategies.books.hongyongchan.rules import ALL_RULES


BOOK_META = {
    "id": "hongyongchan",
    "name": "홍용찬 실전 퀀트투자",
    "category": "fundamental_multifactor_kr",
    "data_granularity": "daily",
}


class HongYongchanStrategy(BookStrategy):
    name = "HongYongchanStrategy"
    version = "1.0.0"
    description = "홍용찬 실전 퀀트투자 (4선 저밸류 PER+PBR+PCR+PSR + 소형주 하위20% + 성장/마진/부채 게이트)"
    holding_period = "swing"


def build_strategy(
    mode: str = "single",
    target_rule: Optional[str] = None,
    or_members: Optional[List[str]] = None,
) -> HongYongchanStrategy:
    return HongYongchanStrategy(
        rules=[cls() for cls in ALL_RULES],
        mode=mode,
        target_rule=target_rule,
        or_members=or_members,
    )
