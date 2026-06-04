"""『트레이딩 전략서』 (Book 19) — 일봉 매수후보 스크리너 전략 래퍼.

다른 한국 책 일봉 전략(dino_surge / haru_silijeon_daily)과 동일 구조.
진입만 충실 코드화; 청산은 멀티버스 드라이버의 sl/tp/mh 가 담당.
"""

from __future__ import annotations

from typing import List, Optional

from strategies.books._base_book_strategy import BookStrategy
from strategies.books.trading_strategy_book.rules import ALL_RULES


BOOK_META = {
    "id": "trading_strategy_book",
    "name": "트레이딩 전략서 (일봉 조건식 A~I 스크리너)",
    "category": "high_breakout_kr",
    "data_granularity": "daily",
}


class TradingStrategyBookStrategy(BookStrategy):
    name = "TradingStrategyBookStrategy"
    version = "1.0.0"
    description = "트레이딩 전략서 — 200일 신고가 + Envelope 돌파 일봉 스크리너(조건식 A~I)"
    author = "kis-template"
    holding_period = "swing"


def build_strategy(
    mode: str = "single",
    target_rule: Optional[str] = None,
    or_members: Optional[List[str]] = None,
) -> TradingStrategyBookStrategy:
    return TradingStrategyBookStrategy(
        rules=[cls() for cls in ALL_RULES],
        mode=mode,
        target_rule=target_rule,
        or_members=or_members,
    )
