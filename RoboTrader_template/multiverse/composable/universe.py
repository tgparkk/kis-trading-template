"""Universe — 매매 후보풀 선정."""
from __future__ import annotations
from typing import TYPE_CHECKING, Protocol, runtime_checkable

if TYPE_CHECKING:
    from RoboTrader_template.multiverse.engine.pit_engine import PITContext
    from RoboTrader_template.multiverse.composable.paramset import ParamSet


@runtime_checkable
class Universe(Protocol):
    """팩터 상위 N + corp_events 필터로 매매 후보풀 반환."""
    def select(self, ctx: "PITContext", paramset: "ParamSet") -> list[str]: ...


class StubUniverse:
    """더미 — Phase 7에서 페르소나별 4종(퀀트/스윙/중장기/단타) 구현 예정."""
    def select(self, ctx, paramset):
        raise NotImplementedError("Phase 7에서 페르소나별 Universe 구현")
