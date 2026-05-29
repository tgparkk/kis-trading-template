"""Weinstein Stage Analysis — 주봉 전략.

설계서 §10b 권장 패턴:
  run_weinstein_stages.py 단에서 일봉→주봉 변환 후 주봉 df를 넘긴다.
  이 strategy는 "받은 df가 이미 주봉" 이라고 가정한다.
  (Variant B는 일봉 df를 그대로 받음)

ctx에 반드시 포함해야 하는 키:
  ma30w_series : 주봉 MA30 시리즈 (pd.Series)
  slope_series : MA30 기울기 시리즈 (pd.Series)
  mrs_series   : Mansfield RS 시리즈 (pd.Series)
  stage_series : Stage 1/2/3/4 라벨 시리즈 (pd.Series)
"""
from __future__ import annotations

from typing import List, Optional

from strategies.books._base_book_strategy import BookStrategy
from strategies.books.weinstein_stages.rules import ALL_RULES

BOOK_META = {
    "id": "weinstein_stages",
    "name": "Weinstein Stage Analysis (Secrets for Profiting in Bull and Bear Markets)",
    "category": "trend_following",
    "data_granularity": "weekly",  # Variant B는 daily
}


class WeinsteinStagesStrategy(BookStrategy):
    """Weinstein Stage Analysis 전략.

    Variant A/Light: 주봉 df 입력 (run script 단에서 변환).
    Variant B      : 일봉 df 입력 (Minervini와 동일 파이프라인).
    """

    name = "WeinsteinStagesStrategy"
    version = "1.0.0"
    description = "Weinstein 4-Stage Analysis — Stage 2 진입 셋업 3종"
    holding_period = "swing"


def build_strategy(
    mode: str = "single",
    target_rule: Optional[str] = None,
    or_members: Optional[List[str]] = None,
) -> WeinsteinStagesStrategy:
    """WeinsteinStagesStrategy 팩토리.

    Args:
        mode        : "single" | "all_AND" | "top_K_OR"
        target_rule : mode="single" 일 때 룰 이름.
        or_members  : mode="top_K_OR" 일 때 룰 이름 리스트.

    Returns:
        WeinsteinStagesStrategy 인스턴스.
    """
    return WeinsteinStagesStrategy(
        rules=[cls() for cls in ALL_RULES],
        mode=mode,
        target_rule=target_rule,
        or_members=or_members,
    )
