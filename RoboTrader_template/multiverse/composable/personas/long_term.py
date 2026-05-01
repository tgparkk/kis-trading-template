"""중장기 페르소나 — Lynch 가치/성장 스크리닝.

알고리즘 요약:
  - Universe: corp_events 필터 후 factor_top_n 상위
  - Scorer: 펀더멘털 종합 (PER 역수 + PBR 역수 + ROE 정규화)
  - Regime: global_risk_mode 기반 (risk_off_avoid 이면 회피)
  - SignalGen: PER < 15 AND ROE > 15% 이면 BUY (린치 기본 조건)
  - Sizer: score 비례 할당
  - ExitRule: PER > 30 (펀더멘털 악화) OR holding_max_days 초과
  - Rebalancer: 매월 첫 주 (monthly)
  - HoldingCap: 분기 보유 가능 (holding_max_days None 시 무제한)
"""
from __future__ import annotations

from datetime import date

from RoboTrader_template.multiverse.composable.paramset import ParamSet
from RoboTrader_template.multiverse.composable.strategy import ComposableStrategy
from RoboTrader_template.multiverse.engine.pit_engine import PITContext

_PER_BUY_THRESHOLD = 15.0
_PER_SELL_THRESHOLD = 30.0
_ROE_BUY_THRESHOLD = 15.0


class _LongTermUniverse:
    def __init__(self, candidate_symbols: list[str]) -> None:
        self.candidates = candidate_symbols

    def select(self, ctx: PITContext, paramset: ParamSet) -> list[str]:
        from RoboTrader_template.multiverse.data import corp_events
        filtered = corp_events.filter_universe(self.candidates, ctx.as_of_date)
        return filtered[: paramset.factor_top_n]


class _LongTermScorer:
    def score(self, ctx: PITContext, symbol: str, paramset: ParamSet) -> float:
        """펀더멘털 종합 — PER 역수(value) + PBR 역수(asset) + ROE(quality) 가중합."""
        ratio = ctx.read_financial_ratio(symbol=symbol) or {}
        per = float(ratio.get("per") or 0) or 999.0
        pbr = float(ratio.get("pbr") or 0) or 999.0
        roe = float(ratio.get("roe") or 0)

        v = (1.0 / per) if per > 0 else 0.0
        a = (1.0 / pbr) if pbr > 0 else 0.0
        q = roe / 100.0 if roe else 0.0

        return (
            paramset.w_value * v
            + paramset.w_quality * q
            + paramset.w_momentum * a  # momentum 가중치를 자산가치에 재활용
            + paramset.w_growth * 0.0
        )


class _LongTermRegime:
    def is_risk_on(self, ctx: PITContext, paramset: ParamSet) -> bool:
        return paramset.global_risk_mode != "risk_off_avoid"


class _LongTermSignalGen:
    def generate(self, ctx: PITContext, symbol: str, paramset: ParamSet) -> str:
        """PER < 15 AND ROE > 15% 이면 BUY — 린치 기본 가치 조건."""
        ratio = ctx.read_financial_ratio(symbol=symbol) or {}
        per = float(ratio.get("per") or 0)
        roe = float(ratio.get("roe") or 0)

        if per <= 0:
            return "HOLD"
        if per < _PER_BUY_THRESHOLD and roe > _ROE_BUY_THRESHOLD:
            return "BUY"
        return "HOLD"


class _LongTermSizer:
    def size(self, capital: float, score: float, paramset: ParamSet) -> int:
        """스코어 비례 할당 — score가 낮으면 최소 수량."""
        target_value = capital * paramset.max_weight_per_stock * max(score, 0.1)
        qty = int(target_value / 60_000)  # 평균 주가 6만원 가정
        return max(qty, 1)


class _LongTermExitRule:
    def should_exit(
        self, ctx: PITContext, position: dict, paramset: ParamSet
    ) -> tuple[bool, str]:
        """PER > 30 (펀더멘털 악화) 또는 손절."""
        symbol = position.get("symbol", "")
        if symbol:
            ratio = ctx.read_financial_ratio(symbol=symbol) or {}
            per = float(ratio.get("per") or 0)
            if per > _PER_SELL_THRESHOLD:
                return True, "per_deterioration"

        entry_price = position.get("entry_price", 0.0)
        current_price = position.get("current_price", entry_price)
        if entry_price > 0:
            ret = (current_price - entry_price) / entry_price
            if ret < paramset.hard_stop_pct:
                return True, "hard_stop"

        return False, ""


class _LongTermRebalancer:
    def should_rebalance(self, current_date: date, paramset: ParamSet) -> bool:
        """매월 첫 주 (1~7일) 리밸런싱."""
        return current_date.day <= 7


class _LongTermHoldingCap:
    def should_force_exit_by_age(
        self, position: dict, current_date: date, paramset: ParamSet
    ) -> bool:
        cap = paramset.holding_max_days
        if cap is None:
            return False
        return position.get("held_days", 0) >= cap


def build_long_term_strategy(
    paramset: ParamSet, candidate_symbols: list[str]
) -> ComposableStrategy:
    """중장기(Lynch 가치/성장) 페르소나 ComposableStrategy 팩토리."""
    return ComposableStrategy(
        paramset=paramset,
        universe=_LongTermUniverse(candidate_symbols),
        scorer=_LongTermScorer(),
        regime=_LongTermRegime(),
        signal_gen=_LongTermSignalGen(),
        sizer=_LongTermSizer(),
        exit_rule=_LongTermExitRule(),
        rebalancer=_LongTermRebalancer(),
        holding_cap=_LongTermHoldingCap(),
    )
