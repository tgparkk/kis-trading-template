"""HoldingCap — 보유기간 상한 초과 강제 청산 판단."""
from __future__ import annotations
from datetime import date
from typing import TYPE_CHECKING, Protocol, runtime_checkable

if TYPE_CHECKING:
    from RoboTrader_template.multiverse.composable.paramset import ParamSet


@runtime_checkable
class HoldingCap(Protocol):
    """보유기간이 paramset.holding_max_days를 초과하면 True 반환."""
    def should_force_exit_by_age(
        self, position: dict, current_date: date, paramset: "ParamSet"
    ) -> bool: ...


class StubHoldingCap:
    """더미 — Phase 7에서 페르소나별 구현 예정."""
    def should_force_exit_by_age(self, position, current_date, paramset):
        raise NotImplementedError("Phase 7에서 페르소나별 구현")
