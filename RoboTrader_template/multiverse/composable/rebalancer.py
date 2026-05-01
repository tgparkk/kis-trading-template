"""Rebalancer — 리밸런싱 주기 판단."""
from __future__ import annotations
from datetime import date
from typing import TYPE_CHECKING, Protocol, runtime_checkable

if TYPE_CHECKING:
    from RoboTrader_template.multiverse.composable.paramset import ParamSet


@runtime_checkable
class Rebalancer(Protocol):
    """현재 날짜 기준으로 리밸런싱 실행 여부를 반환."""
    def should_rebalance(
        self, current_date: date, paramset: "ParamSet"
    ) -> bool: ...


class StubRebalancer:
    """더미 — Phase 7에서 페르소나별 구현 예정."""
    def should_rebalance(self, current_date, paramset):
        raise NotImplementedError("Phase 7에서 페르소나별 구현")
