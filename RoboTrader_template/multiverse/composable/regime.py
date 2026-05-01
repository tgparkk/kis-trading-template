"""Regime — 시장 국면(Risk-On / Risk-Off) 판단."""
from __future__ import annotations
from typing import TYPE_CHECKING, Protocol, runtime_checkable

if TYPE_CHECKING:
    from RoboTrader_template.multiverse.engine.pit_engine import PITContext
    from RoboTrader_template.multiverse.composable.paramset import ParamSet


@runtime_checkable
class Regime(Protocol):
    """시장 국면이 Risk-On이면 True 반환."""
    def is_risk_on(self, ctx: "PITContext", paramset: "ParamSet") -> bool: ...


class StubRegime:
    """더미 — Phase 7에서 페르소나별 구현 예정."""
    def is_risk_on(self, ctx, paramset):
        raise NotImplementedError("Phase 7에서 페르소나별 구현")
