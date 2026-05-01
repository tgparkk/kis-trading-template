"""퀀트 페르소나 — Lynch(PEG) + Momentum 합성, 포트폴리오 5~10종목.

알고리즘 요약:
  - Universe: corp_events 필터 후 factor_top_n 상위
  - Scorer: value(PER 역수) + quality(ROE) + momentum(252일 수익률) 가중합
  - Regime: global_risk_mode != risk_off_avoid 이면 risk_on
  - SignalGen: 팩터 점수 > tech_score_threshold 이면 BUY
  - Sizer: max_weight_per_stock 비율, 평균 주가 7만원 가정
  - ExitRule: 보유 60일 초과 청산
  - Rebalancer: daily/weekly/biweekly/monthly 파라미터 따름
  - HoldingCap: holding_max_days 초과 강제 청산
"""
from __future__ import annotations

from datetime import date

from RoboTrader_template.multiverse.composable.paramset import ParamSet
from RoboTrader_template.multiverse.composable.strategy import ComposableStrategy
from RoboTrader_template.multiverse.engine.pit_engine import PITContext


class _QuantUniverse:
    def __init__(self, candidate_symbols: list[str]) -> None:
        self.candidates = candidate_symbols

    def select(self, ctx: PITContext, paramset: ParamSet) -> list[str]:
        from RoboTrader_template.multiverse.data import corp_events
        filtered = corp_events.filter_universe(self.candidates, ctx.as_of_date)
        return filtered[: paramset.factor_top_n]


class _QuantScorer:
    def score(self, ctx: PITContext, symbol: str, paramset: ParamSet) -> float:
        """팩터 가중합 — value(PER 역수) + quality(ROE) + momentum(252d 수익률)."""
        ratio = ctx.read_financial_ratio(symbol=symbol) or {}
        per = float(ratio.get("per") or 0) or 999.0
        roe = float(ratio.get("roe") or 0)

        df = ctx.read_daily(symbol=symbol, lookback_days=260)
        if df is None or df.empty or len(df) < 200:
            return 0.0
        try:
            mom_252 = float(df["close"].iloc[-1] / df["close"].iloc[0] - 1)
        except Exception:
            mom_252 = 0.0

        v = (1.0 / per) if per > 0 else 0.0
        q = roe / 100.0 if roe else 0.0
        m = max(min(mom_252, 1.0), -1.0)
        g = 0.0  # growth 데이터 없으면 0

        return (
            paramset.w_value * v
            + paramset.w_quality * q
            + paramset.w_momentum * m
            + paramset.w_growth * g
        )


class _QuantRegime:
    def is_risk_on(self, ctx: PITContext, paramset: ParamSet) -> bool:
        return paramset.global_risk_mode != "risk_off_avoid"


class _QuantSignalGen:
    def generate(self, ctx: PITContext, symbol: str, paramset: ParamSet) -> str:
        scorer = _QuantScorer()
        if scorer.score(ctx, symbol, paramset) > paramset.tech_score_threshold:
            return "BUY"
        return "HOLD"


class _QuantSizer:
    def size(self, capital: float, score: float, paramset: ParamSet) -> int:
        target_value = capital * paramset.max_weight_per_stock
        qty = int(target_value / 70_000)  # 평균 주가 7만원 가정
        return max(qty, 1)


class _QuantExitRule:
    def should_exit(
        self, ctx: PITContext, position: dict, paramset: ParamSet
    ) -> tuple[bool, str]:
        held_days = position.get("held_days", 0)
        if held_days > 60:
            return True, "long_hold"
        return False, ""


class _QuantRebalancer:
    def should_rebalance(self, current_date: date, paramset: ParamSet) -> bool:
        freq = paramset.rebalance_frequency
        if freq == "monthly":
            return current_date.day <= 7
        if freq == "weekly":
            return current_date.weekday() == 0  # 월요일
        if freq == "biweekly":
            return current_date.weekday() == 0 and (
                current_date.isocalendar()[1] % 2 == 0
            )
        return True  # daily


class _QuantHoldingCap:
    def should_force_exit_by_age(
        self, position: dict, current_date: date, paramset: ParamSet
    ) -> bool:
        cap = paramset.holding_max_days
        if cap is None:
            return False
        return position.get("held_days", 0) >= cap


def build_quant_strategy(
    paramset: ParamSet, candidate_symbols: list[str]
) -> ComposableStrategy:
    """퀀트 페르소나 ComposableStrategy 팩토리."""
    return ComposableStrategy(
        paramset=paramset,
        universe=_QuantUniverse(candidate_symbols),
        scorer=_QuantScorer(),
        regime=_QuantRegime(),
        signal_gen=_QuantSignalGen(),
        sizer=_QuantSizer(),
        exit_rule=_QuantExitRule(),
        rebalancer=_QuantRebalancer(),
        holding_cap=_QuantHoldingCap(),
    )
