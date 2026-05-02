"""ComposableStrategy — 8 모듈 조립 + Phase 2 signal_fn 어댑터."""
from __future__ import annotations
from typing import TYPE_CHECKING

from RoboTrader_template.multiverse.engine.pit_engine import Signal
from RoboTrader_template.multiverse.composable.universe import Universe
from RoboTrader_template.multiverse.composable.scorer import Scorer
from RoboTrader_template.multiverse.composable.regime import Regime
from RoboTrader_template.multiverse.composable.signal_gen import SignalGenerator
from RoboTrader_template.multiverse.composable.sizer import Sizer
from RoboTrader_template.multiverse.composable.exit_rule import ExitRule
from RoboTrader_template.multiverse.composable.rebalancer import Rebalancer
from RoboTrader_template.multiverse.composable.holding_cap import HoldingCap

if TYPE_CHECKING:
    from RoboTrader_template.multiverse.engine.pit_engine import PITContext
    from RoboTrader_template.multiverse.composable.paramset import ParamSet


def _check_protocol(obj: object, proto: type, name: str) -> None:
    """obj가 proto Protocol을 만족하지 않으면 TypeError raise.

    Python의 @runtime_checkable Protocol은 메서드 이름 존재 여부만 체크하므로
    인자 갯수/타입까지는 검증하지 않는다. 그래도 메서드 자체 누락은 조기에 잡을 수 있다.
    """
    if not isinstance(obj, proto):
        raise TypeError(
            f"{name} must implement {proto.__name__} Protocol "
            f"(got {type(obj).__name__})"
        )


class ComposableStrategy:
    """8 모듈을 조립해 Phase 2의 signal_fn 인터페이스를 구현하는 컨테이너.

    실제 모듈 알고리즘은 Phase 7에서 4 페르소나 샘플로 구체화.
    본 Phase는 골격(어댑터 흐름)만.
    """
    def __init__(
        self,
        paramset: "ParamSet",
        universe: "Universe",
        scorer: "Scorer",
        regime: "Regime",
        signal_gen: "SignalGenerator",
        sizer: "Sizer",
        exit_rule: "ExitRule",
        rebalancer: "Rebalancer",
        holding_cap: "HoldingCap",
    ) -> None:
        _check_protocol(universe, Universe, "universe")
        _check_protocol(scorer, Scorer, "scorer")
        _check_protocol(regime, Regime, "regime")
        _check_protocol(signal_gen, SignalGenerator, "signal_gen")
        _check_protocol(sizer, Sizer, "sizer")
        _check_protocol(exit_rule, ExitRule, "exit_rule")
        _check_protocol(rebalancer, Rebalancer, "rebalancer")
        _check_protocol(holding_cap, HoldingCap, "holding_cap")

        self.paramset = paramset
        self.universe = universe
        self.scorer = scorer
        self.regime = regime
        self.signal_gen = signal_gen
        self.sizer = sizer
        self.exit_rule = exit_rule
        self.rebalancer = rebalancer
        self.holding_cap = holding_cap

    def signal_fn(
        self,
        ctx: "PITContext",
        *,
        symbol: str,
        position: dict | None = None,
        capital: float = 0.0,
    ) -> Signal:
        """Phase 2 signal_fn 어댑터.

        흐름:
          1. 보유 중이면: holding_cap → exit_rule 순으로 청산 검사
          2. 미보유 + regime risk_on이면: signal_gen + scorer → 진입 결정
        """
        # 1. 보유 중 청산 검사
        if position is not None:
            if self.holding_cap.should_force_exit_by_age(
                position, ctx.as_of_date, self.paramset
            ):
                return Signal(action="SELL", qty=position.get("qty", 0))
            should_exit, _reason = self.exit_rule.should_exit(
                ctx, position, self.paramset
            )
            if should_exit:
                return Signal(action="SELL", qty=position.get("qty", 0))
            return Signal(action="HOLD")

        # 2. 미보유 진입 검사
        if not self.regime.is_risk_on(ctx, self.paramset):
            return Signal(action="HOLD")

        decision = self.signal_gen.generate(ctx, symbol, self.paramset)
        if decision != "BUY":
            return Signal(action="HOLD")

        score = self.scorer.score(ctx, symbol, self.paramset)
        qty = self.sizer.size(capital, score, self.paramset)
        if qty <= 0:
            return Signal(action="HOLD")

        return Signal(action="BUY", qty=qty)
