"""Sizer — 매수 수량 산출."""
from __future__ import annotations
from typing import TYPE_CHECKING, Protocol, runtime_checkable

if TYPE_CHECKING:
    from RoboTrader_template.multiverse.composable.paramset import ParamSet


@runtime_checkable
class Sizer(Protocol):
    """가용자본과 종목 점수를 입력받아 매수 수량(주)을 반환."""
    def size(self, capital: float, score: float, paramset: "ParamSet") -> int: ...


class StubSizer:
    """더미 — Phase 7에서 페르소나별 구현 예정."""
    def size(self, capital, score, paramset):
        raise NotImplementedError("Phase 7에서 페르소나별 구현")
