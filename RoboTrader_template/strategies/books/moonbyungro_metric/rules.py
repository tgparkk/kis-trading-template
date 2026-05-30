"""문병로 메트릭 스튜디오 — Rule 집합.

규칙들 (모두 롱 전용, 일봉 해상도, 펀더멘털/순위 단독 진입):
- rule_low_pbr            : 시그니처. PBR 오름차순 순위 상위 top_n(저PBR). 문병로 "한국=저PBR 민감" 명제 검증.
- rule_value_composite_kr : 주력. 5팩터(PBR+PER+PSR+POR+PCR) 가치복합 순위 상위 top_n.
- rule_small_value        : 플래그십. 시총 하위 40% 게이트 ∩ 5팩터 가치복합 상위 top_n(소형주×가치).

순위 주입:
- run 스크립트가 거래일 i에 대응하는 횡단면 순위 `pbr_rank`/`vc_rank`/`smallvalue_rank`와
  `n_eligible`를 사전계산해 ctx로 전달.
- 룰은 ctx["pbr_rank"]/["vc_rank"]/["smallvalue_rank"], ctx["n_eligible"]만 읽는다(재조회 금지).
- 해당 순위가 None이면 RuleResult(triggered=False).

PCR(영업현금흐름) 관련 동작 (설계서 §"PCR NULL 처리"):
- vc_rank / smallvalue_rank 는 5팩터 모두 유효한 교집합 기준이므로,
  operating_cash_flow 가 NULL/<=0 인 종목·시점은 vc/smallvalue 적격에서 빠진다(4팩터 fallback 아님).
- 반면 rule_low_pbr 은 pbr_rank 만 보므로 PCR 유무와 무관하게 평가된다
  (pbr_rank 는 PBR 만 유효하면 산출됨 — run 스크립트의 pbr_rank 도 PCR 적격과 독립).

헬퍼:
- _num : fund[key]를 안전 float 캐스트(None/NaN→None). Greenblatt/Lynch/O'Shaughnessy 재사용.
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
class rule_low_pbr(Rule):
    """시그니처 — PBR 오름차순 순위 상위(저PBR). 문병로 "한국=저PBR 민감" 명제 검증.

    pbr_rank is not None AND n_eligible>=min_eligible AND pbr_rank<=top_n
    (run 스크립트가 거래일별 PBR 오름차순 → dense ordinal pbr_rank 주입; 1=최저 PBR.)

    NOTE: pbr_rank 는 PBR 만 유효하면 산출되므로 PCR(영업현금흐름) 유무와 무관하게 평가된다.
    """
    name: str = "low_pbr"
    top_n: int = 20
    min_eligible: int = 10

    def evaluate(self, df: pd.DataFrame, ctx: Dict[str, Any]) -> RuleResult:
        pr = ctx.get("pbr_rank")
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
            triggered=True, side="buy", confidence=72.0,
            reasons=[f"low_pbr pbr_rank={pr_i} n_eligible={ne_i} top_n={self.top_n}"],
            metadata={"pbr_rank": pr_i, "n_eligible": ne_i},
        )


@dataclass
class rule_value_composite_kr(Rule):
    """주력 — 5팩터(PBR+PER+PSR+POR+PCR) 가치복합 횡단면 순위 상위.

    vc_rank is not None AND n_eligible>=min_eligible AND vc_rank<=top_n
    (run 스크립트가 거래일별 5팩터 백분위 평균 → dense ordinal vc_rank 주입; 1=최저평가.)

    NOTE: vc_rank 는 5팩터(PCR 포함) 모두 유효한 교집합에서만 산출 → PCR 부재 종목은 부적격.
    """
    name: str = "value_composite_kr"
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
            reasons=[f"value_composite_kr vc_rank={vc_i} n_eligible={ne_i} top_n={self.top_n}"],
            metadata={"vc_rank": vc_i, "n_eligible": ne_i},
        )


@dataclass
class rule_small_value(Rule):
    """플래그십 — 소형주×가치(시총 하위 40% 게이트 ∩ 5팩터 가치복합 상위).

    smallvalue_rank is not None AND smallvalue_rank<=top_n
    (run 스크립트가 market_cap 하위 40% 부분집합에서 vc_score 내림차순 → dense ordinal smallvalue_rank 주입.)

    NOTE: smallvalue_rank 도 5팩터(PCR 포함) 교집합 기준 → PCR 부재 종목은 부적격.
    """
    name: str = "small_value"
    top_n: int = 20

    def evaluate(self, df: pd.DataFrame, ctx: Dict[str, Any]) -> RuleResult:
        sv = ctx.get("smallvalue_rank")
        if sv is None:
            return RuleResult(triggered=False)
        try:
            sv_i = int(sv)
        except (TypeError, ValueError):
            return RuleResult(triggered=False)
        if not (sv_i <= self.top_n):
            return RuleResult(triggered=False)

        return RuleResult(
            triggered=True, side="buy", confidence=78.0,
            reasons=[f"small_value smallvalue_rank={sv_i} top_n={self.top_n}"],
            metadata={"smallvalue_rank": sv_i},
        )


ALL_RULES = [
    rule_low_pbr,
    rule_value_composite_kr,
    rule_small_value,
]
