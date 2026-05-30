"""홍용찬 실전 퀀트투자 — Rule 집합.

규칙들 (모두 롱 전용, 일봉 해상도, 펀더멘털/순위 단독 진입):
- rule_value4_low      : 시그니처. 4선 저밸류(PER+PBR+PCR+PSR) 가치복합 순위 상위 top_n. 문병로 5팩터 직접 대조군.
- rule_small_value4    : 플래그십. 시총 하위 20% 게이트 ∩ 4선 저밸류 복합 상위 top_n(소형주×가치).
- rule_hong_combo      : 주력. 소형주 하위20% ∩ 흑자 ∩ (성장YoY>0) ∩ 마진/부채 게이트 ∩ 4선 저밸류 상위 top_n.
                         홍용찬 멀티팩터 완전체(밸류×성장×퀄리티). 배당 전략은 사장님 방침으로 제외.

순위 주입:
- run 스크립트가 거래일 i에 대응하는 횡단면 순위 `v4_rank`/`smallv4_rank`/`hong_rank`와
  `n_eligible`를 사전계산해 ctx로 전달.
- 룰은 ctx["v4_rank"]/["smallv4_rank"]/["hong_rank"], ctx["n_eligible"]만 읽는다(재조회 금지).
- 해당 순위가 None이면 RuleResult(triggered=False).

4선 저밸류 / 게이트 동작 (설계서 §1~3):
- v4_rank / smallv4_rank / hong_rank 는 4선(PER+PBR+PCR+PSR) 모두 유효한 교집합 기준이므로,
  per/pbr<=0, revenue<=0, operating_cash_flow<=0, market_cap<=0 인 종목·시점은 적격에서 빠진다.
- hong_rank 는 추가로 흑자(op>0 & ni>0) ∩ (성장YoY>0) ∩ 마진/부채 게이트를 통과한 부분집합에서만 산출.
  게이트 지표(roe/operating_margin/debt_ratio)는 부분 커버리지라 run 스크립트가 "데이터 있는 종목만 적용,
  없으면 통과"(skip-missing) 정책으로 처리한다(§9 사장님 결정 (a) 완화).

헬퍼:
- _num : fund[key]를 안전 float 캐스트(None/NaN→None). 문병로/Greenblatt/Lynch 재사용.
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
class rule_value4_low(Rule):
    """시그니처 — 4선 저밸류(PER+PBR+PCR+PSR) 가치복합 횡단면 순위 상위.

    v4_rank is not None AND n_eligible>=min_eligible AND v4_rank<=top_n
    (run 스크립트가 거래일별 4선 백분위 평균 → dense ordinal v4_rank 주입; 1=최저평가.)

    NOTE: v4_rank 는 4선(PCR 포함) 모두 유효한 교집합에서만 산출.
          문병로 vc_rank(5팩터, POR 포함) 직접 대조군.
    """
    name: str = "value4_low"
    top_n: int = 20
    min_eligible: int = 10

    def evaluate(self, df: pd.DataFrame, ctx: Dict[str, Any]) -> RuleResult:
        v4 = ctx.get("v4_rank")
        ne = ctx.get("n_eligible")
        if v4 is None or ne is None:
            return RuleResult(triggered=False)
        try:
            v4_i = int(v4)
            ne_i = int(ne)
        except (TypeError, ValueError):
            return RuleResult(triggered=False)
        if ne_i < self.min_eligible:
            return RuleResult(triggered=False)
        if not (v4_i <= self.top_n):
            return RuleResult(triggered=False)

        return RuleResult(
            triggered=True, side="buy", confidence=73.0,
            reasons=[f"value4_low v4_rank={v4_i} n_eligible={ne_i} top_n={self.top_n}"],
            metadata={"v4_rank": v4_i, "n_eligible": ne_i},
        )


@dataclass
class rule_small_value4(Rule):
    """플래그십 — 소형주×4선 밸류(시총 하위 20% 게이트 ∩ 4선 저밸류 상위).

    smallv4_rank is not None AND smallv4_rank<=top_n
    (run 스크립트가 market_cap 하위 20% 부분집합에서 v4_score 내림차순 → dense ordinal smallv4_rank 주입.)

    NOTE: smallv4_rank 도 4선(PCR 포함) 교집합 기준. 홍용찬 대표 전략.
          문병로 small_value(40% 게이트, 5팩터)와 A/B(게이트 강도·POR 효과 분리).
    """
    name: str = "small_value4"
    top_n: int = 20

    def evaluate(self, df: pd.DataFrame, ctx: Dict[str, Any]) -> RuleResult:
        sv = ctx.get("smallv4_rank")
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
            reasons=[f"small_value4 smallv4_rank={sv_i} top_n={self.top_n}"],
            metadata={"smallv4_rank": sv_i},
        )


@dataclass
class rule_hong_combo(Rule):
    """주력 — 홍용찬 멀티팩터 완전체.

    소형주 하위20% ∩ 흑자(op>0 & ni>0) ∩ (성장YoY>0) ∩ 마진/부채 게이트 ∩ 4선 저밸류 상위.

    hong_rank is not None AND hong_rank<=top_n
    (run 스크립트가 게이트 통과 부분집합에서 v4_score 내림차순 → dense ordinal hong_rank 주입.)

    NOTE: hong_rank 는 4선(PCR 포함) 교집합 ∩ 게이트 기준.
          게이트 지표(roe/operating_margin/debt_ratio) 부분 커버리지는
          "데이터 있는 종목만 적용, 없으면 통과"(skip-missing) 정책 — run 스크립트에서 처리.
          순수 밸류(value4_low) 대비 성장/퀄리티 게이트가 알파를 추가하는지 검증.
    """
    name: str = "hong_combo"
    top_n: int = 20

    def evaluate(self, df: pd.DataFrame, ctx: Dict[str, Any]) -> RuleResult:
        hr = ctx.get("hong_rank")
        if hr is None:
            return RuleResult(triggered=False)
        try:
            hr_i = int(hr)
        except (TypeError, ValueError):
            return RuleResult(triggered=False)
        if not (hr_i <= self.top_n):
            return RuleResult(triggered=False)

        return RuleResult(
            triggered=True, side="buy", confidence=80.0,
            reasons=[f"hong_combo hong_rank={hr_i} top_n={self.top_n}"],
            metadata={"hong_rank": hr_i},
        )


ALL_RULES = [
    rule_value4_low,
    rule_small_value4,
    rule_hong_combo,
]
