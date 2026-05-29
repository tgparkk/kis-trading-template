"""O'Shaughnessy What Works on Wall Street — Rule 집합.

규칙들 (모두 롱 전용, 일봉 해상도, 펀더멘털/순위 단독 진입):
- rule_value_composite : 주력. VC1식 4팩터(PSR+PE+PB+EV/EBIT) 가치복합 순위 상위 top_n 매수.
- rule_trending_value  : 플래그십. 가치복합 상위 게이트 ∩ 3개월 모멘텀 순위 상위 top_n.
- rule_low_psr         : 시그니처. PSR 오름차순 순위 상위 top_n(저PSR).

순위 주입:
- run 스크립트가 거래일 i에 대응하는 횡단면 순위 `vc_rank`/`tv_rank`/`psr_rank`와
  `n_eligible`를 사전계산해 ctx로 전달.
- 룰은 ctx["vc_rank"]/["tv_rank"]/["psr_rank"], ctx["n_eligible"]만 읽는다(재조회 금지).
- 해당 순위가 None이면 RuleResult(triggered=False).

헬퍼:
- _num : fund[key]를 안전 float 캐스트(None/NaN→None). Greenblatt/Lynch 재사용.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, Dict, Optional

import pandas as pd

from strategies.books._base_book_strategy import Rule, RuleResult


# --------------------------------------------------------------------------- #
# 유효성 헬퍼
# --------------------------------------------------------------------------- #
def _num(fund: Dict[str, Any], key: str) -> Optional[float]:
    """fund[key]를 float로. None/NaN이면 None."""
    if fund is None:
        return None
    val = fund.get(key)
    if val is None:
        return None
    try:
        f = float(val)
    except (TypeError, ValueError):
        return None
    if math.isnan(f):
        return None
    return f


# --------------------------------------------------------------------------- #
# 진입 룰 3종 (롱 전용, side="buy", 순위 단독 — ctx만 읽음)
# --------------------------------------------------------------------------- #
@dataclass
class rule_value_composite(Rule):
    """주력 — VC1식 4팩터 가치복합 횡단면 순위 상위.

    vc_rank is not None AND n_eligible>=min_eligible AND vc_rank<=top_n
    (run 스크립트가 거래일별 PSR/PE/PB/EV-EBIT 백분위 평균 → dense ordinal vc_rank 주입; 1=최저평가.)
    """
    name: str = "value_composite"
    top_n: int = 20
    min_eligible: int = 10

    def evaluate(self, df: pd.DataFrame, ctx: Dict[str, Any]) -> RuleResult:
        vc = ctx.get("vc_rank")
        ne = ctx.get("n_eligible")
        if vc is None or ne is None:
            return RuleResult(triggered=False)
        try:
            vc_i = int(vc)
            ne_i = int(ne)
        except (TypeError, ValueError):
            return RuleResult(triggered=False)
        if ne_i < self.min_eligible:
            return RuleResult(triggered=False)
        if not (vc_i <= self.top_n):
            return RuleResult(triggered=False)

        return RuleResult(
            triggered=True, side="buy", confidence=75.0,
            reasons=[f"value_composite vc_rank={vc_i} n_eligible={ne_i} top_n={self.top_n}"],
            metadata={"vc_rank": vc_i, "n_eligible": ne_i},
        )


@dataclass
class rule_trending_value(Rule):
    """플래그십 — 가치복합 상위 게이트 ∩ 3개월 모멘텀 순위 상위.

    tv_rank is not None AND tv_rank<=top_n
    (run 스크립트가 vc_score 상위 40% 게이트 부분집합에서 mom63 내림차순 → dense ordinal tv_rank 주입.)
    """
    name: str = "trending_value"
    top_n: int = 20

    def evaluate(self, df: pd.DataFrame, ctx: Dict[str, Any]) -> RuleResult:
        tv = ctx.get("tv_rank")
        if tv is None:
            return RuleResult(triggered=False)
        try:
            tv_i = int(tv)
        except (TypeError, ValueError):
            return RuleResult(triggered=False)
        if not (tv_i <= self.top_n):
            return RuleResult(triggered=False)

        return RuleResult(
            triggered=True, side="buy", confidence=78.0,
            reasons=[f"trending_value tv_rank={tv_i} top_n={self.top_n}"],
            metadata={"tv_rank": tv_i},
        )


@dataclass
class rule_low_psr(Rule):
    """시그니처 — PSR 오름차순 순위 상위(저PSR).

    psr_rank is not None AND n_eligible>=min_eligible AND psr_rank<=top_n
    (run 스크립트가 거래일별 PSR 오름차순 → dense ordinal psr_rank 주입; 1=최저 PSR.)
    """
    name: str = "low_psr"
    top_n: int = 20
    min_eligible: int = 10

    def evaluate(self, df: pd.DataFrame, ctx: Dict[str, Any]) -> RuleResult:
        pr = ctx.get("psr_rank")
        ne = ctx.get("n_eligible")
        if pr is None or ne is None:
            return RuleResult(triggered=False)
        try:
            pr_i = int(pr)
            ne_i = int(ne)
        except (TypeError, ValueError):
            return RuleResult(triggered=False)
        if ne_i < self.min_eligible:
            return RuleResult(triggered=False)
        if not (pr_i <= self.top_n):
            return RuleResult(triggered=False)

        return RuleResult(
            triggered=True, side="buy", confidence=70.0,
            reasons=[f"low_psr psr_rank={pr_i} n_eligible={ne_i} top_n={self.top_n}"],
            metadata={"psr_rank": pr_i, "n_eligible": ne_i},
        )


ALL_RULES = [
    rule_value_composite,
    rule_trending_value,
    rule_low_psr,
]
