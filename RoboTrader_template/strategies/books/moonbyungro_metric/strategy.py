"""문병로 메트릭 스튜디오 — 일봉 펀더멘털 5팩터 횡단면 순위 전략."""
from __future__ import annotations

from typing import List, Optional

from strategies.books._base_book_strategy import BookStrategy
from strategies.books.moonbyungro_metric.rules import ALL_RULES


BOOK_META = {
    "id": "moonbyungro_metric",
    "name": "문병로 메트릭 스튜디오",
    "category": "fundamental_factor_rank_kr",
    "data_granularity": "daily",
}


class MoonByungroMetricStrategy(BookStrategy):
    name = "MoonByungroMetricStrategy"
    version = "1.0.0"
    description = "문병로 메트릭 스튜디오 (5팩터 PBR+PER+PSR+POR+PCR 가치복합 + 저PBR + 소형주×가치 횡단면 순위)"
    holding_period = "swing"


def build_strategy(
    mode: str = "single",
    target_rule: Optional[str] = None,
    or_members: Optional[List[str]] = None,
) -> MoonByungroMetricStrategy:
    return MoonByungroMetricStrategy(
        rules=[cls() for cls in ALL_RULES],
        mode=mode,
        target_rule=target_rule,
        or_members=or_members,
    )
