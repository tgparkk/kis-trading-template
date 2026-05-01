"""SignalGenerator — 진입/청산 시그널 생성."""
from __future__ import annotations
from typing import TYPE_CHECKING, Literal, Protocol, runtime_checkable

if TYPE_CHECKING:
    from RoboTrader_template.multiverse.engine.pit_engine import PITContext
    from RoboTrader_template.multiverse.composable.paramset import ParamSet


@runtime_checkable
class SignalGenerator(Protocol):
    """기술적 조건 조합으로 BUY/SELL/HOLD 결정을 반환."""
    def generate(
        self, ctx: "PITContext", symbol: str, paramset: "ParamSet"
    ) -> Literal["BUY", "SELL", "HOLD"]: ...


class StubSignalGenerator:
    """더미 — Phase 7에서 페르소나별 구현 예정."""
    def generate(self, ctx, symbol, paramset):
        raise NotImplementedError("Phase 7에서 페르소나별 구현")
