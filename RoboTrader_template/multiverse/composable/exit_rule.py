"""ExitRule — 청산 조건 판단."""
from __future__ import annotations
from typing import TYPE_CHECKING, Protocol, runtime_checkable

if TYPE_CHECKING:
    from RoboTrader_template.multiverse.engine.pit_engine import PITContext
    from RoboTrader_template.multiverse.composable.paramset import ParamSet


@runtime_checkable
class ExitRule(Protocol):
    """보유 포지션의 청산 여부와 사유를 반환.

    Returns:
        (should_exit, reason) — reason은 청산 사유 문자열.
    """
    def should_exit(
        self, ctx: "PITContext", position: dict, paramset: "ParamSet"
    ) -> tuple[bool, str]: ...


class StubExitRule:
    """더미 — Phase 7에서 페르소나별 구현 예정."""
    def should_exit(self, ctx, position, paramset):
        raise NotImplementedError("Phase 7에서 페르소나별 구현")
