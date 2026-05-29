"""Greenblatt Magic Formula — Rule 집합.

규칙들 (모두 롱 전용, 일봉 해상도, 펀더멘털 단독 진입):
- rule_magic_formula_top       : 주력. 횡단면 순위(EY+ROC rank 합산) 상위 top_n 매수.
- rule_magic_formula_threshold : per-stock. EY>0.10 AND ROC>0.25 (Magic 임계).
- rule_high_roc_value          : 품질 틸트. EY>0.08 AND ROC>0.40.

재무/순위 주입:
- run 스크립트가 거래일 i에 대응하는 point-in-time `fund` dict(ey/roc 포함)와
  횡단면 `magic_rank`, `n_eligible`를 사전계산해 ctx로 전달.
- 룰은 ctx["fund"]["ey"]/["roc"], ctx["magic_rank"], ctx["n_eligible"]만 읽는다(재조회 금지).
- fund 또는 필수 키가 None/NaN이면 RuleResult(triggered=False).

헬퍼:
- _num : fund[key]를 안전 float 캐스트(None/NaN→None). Lynch 재사용.
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
# 진입 룰 3종 (롱 전용, side="buy", 펀더멘털/순위 단독 — ctx만 읽음)
# --------------------------------------------------------------------------- #
@dataclass
class rule_magic_formula_top(Rule):
    """Magic Formula 주력 — 횡단면 순위 상위.

    magic_rank is not None AND n_eligible>=min_eligible AND magic_rank<=top_n
    (run 스크립트가 거래일별 EY rank + ROC rank 합산 정렬 → dense ordinal magic_rank 주입.)
    """
    name: str = "magic_formula_top"
    top_n: int = 20
    min_eligible: int = 10

    def evaluate(self, df: pd.DataFrame, ctx: Dict[str, Any]) -> RuleResult:
        mr = ctx.get("magic_rank")
        ne = ctx.get("n_eligible")
        if mr is None or ne is None:
            return RuleResult(triggered=False)
        try:
            mr_i = int(mr)
            ne_i = int(ne)
        except (TypeError, ValueError):
            return RuleResult(triggered=False)
        if ne_i < self.min_eligible:
            return RuleResult(triggered=False)
        if not (mr_i <= self.top_n):
            return RuleResult(triggered=False)

        return RuleResult(
            triggered=True, side="buy", confidence=75.0,
            reasons=[f"magic_formula_top rank={mr_i} n_eligible={ne_i} top_n={self.top_n}"],
            metadata={"magic_rank": mr_i, "n_eligible": ne_i},
        )


@dataclass
class rule_magic_formula_threshold(Rule):
    """per-stock 임계 — EY>0.10 AND ROC>0.25.

    fund["ey"]/fund["roc"]는 run 스크립트가 사전계산(가드 통과 시만 값, 아니면 None).
    """
    name: str = "magic_formula_threshold"
    ey_min: float = 0.10
    roc_min: float = 0.25

    def evaluate(self, df: pd.DataFrame, ctx: Dict[str, Any]) -> RuleResult:
        fund = ctx.get("fund")
        if fund is None:
            return RuleResult(triggered=False)

        ey = _num(fund, "ey")
        roc = _num(fund, "roc")
        if ey is None or roc is None:
            return RuleResult(triggered=False)
        if not (ey > self.ey_min and roc > self.roc_min):
            return RuleResult(triggered=False)

        return RuleResult(
            triggered=True, side="buy", confidence=70.0,
            reasons=[f"magic_formula_threshold ey={ey:.3f} roc={roc:.3f}"],
            metadata={"ey": ey, "roc": roc},
        )


@dataclass
class rule_high_roc_value(Rule):
    """품질 틸트 — EY>0.08 AND ROC>0.40."""
    name: str = "high_roc_value"
    ey_min: float = 0.08
    roc_min: float = 0.40

    def evaluate(self, df: pd.DataFrame, ctx: Dict[str, Any]) -> RuleResult:
        fund = ctx.get("fund")
        if fund is None:
            return RuleResult(triggered=False)

        ey = _num(fund, "ey")
        roc = _num(fund, "roc")
        if ey is None or roc is None:
            return RuleResult(triggered=False)
        if not (ey > self.ey_min and roc > self.roc_min):
            return RuleResult(triggered=False)

        return RuleResult(
            triggered=True, side="buy", confidence=68.0,
            reasons=[f"high_roc_value ey={ey:.3f} roc={roc:.3f}"],
            metadata={"ey": ey, "roc": roc},
        )


ALL_RULES = [
    rule_magic_formula_top,
    rule_magic_formula_threshold,
    rule_high_roc_value,
]
