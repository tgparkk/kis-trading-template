"""Scorer — 종목 점수 산출."""
from __future__ import annotations
from typing import TYPE_CHECKING, Protocol, runtime_checkable

if TYPE_CHECKING:
    from RoboTrader_template.multiverse.engine.pit_engine import PITContext
    from RoboTrader_template.multiverse.composable.paramset import ParamSet


@runtime_checkable
class Scorer(Protocol):
    """팩터 가중합으로 종목 점수(0~1)를 반환."""
    def score(self, ctx: "PITContext", symbol: str, paramset: "ParamSet") -> float: ...


class StubScorer:
    """더미 — Phase 7에서 페르소나별 구현 예정."""
    def score(self, ctx, symbol, paramset):
        raise NotImplementedError("Phase 7에서 페르소나별 구현")
