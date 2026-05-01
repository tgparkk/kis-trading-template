"""봇 재시작 시 ComposableStrategy + 포지션 상태 메모리 복원."""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Callable, Optional

from RoboTrader_template.multiverse.composable.paramset import ParamSet
from RoboTrader_template.multiverse.composable.strategy import ComposableStrategy
from RoboTrader_template.multiverse.persistence.paramset_store import (
    load_paramset,
    all_paramset_ids,
)
from RoboTrader_template.multiverse.persistence.position_store import (
    StoredPosition,
    load_all,
)

logger = logging.getLogger(__name__)


@dataclass
class RestoredState:
    """봇 재시작 시 한 paramset_id 단위 복원 결과."""

    paramset_id: str
    paramset: ParamSet
    config_hash_drift: bool  # True면 보수적 청산 모드 진입 권장
    positions: list  # list[StoredPosition]


def restore_all(
    strategy_factory: Optional[Callable[[ParamSet], ComposableStrategy]] = None,
) -> tuple:
    """모든 paramset과 포지션을 메모리로 복원.

    Returns:
        (restored_states, strategies)
        - restored_states: paramset_id → RestoredState (포지션 + drift 플래그)
        - strategies: paramset_id → ComposableStrategy (factory 호출 결과).
          factory None이면 빈 dict.

    config_hash drift 감지:
      load_paramset이 hash 불일치 시 경고 로그를 남김.
      본 함수는 그 정보를 RestoredState.config_hash_drift로 표면화.
    """
    states: dict = {}
    strategies: dict = {}

    all_positions = load_all()
    positions_by_paramset: dict = {}
    for p in all_positions:
        positions_by_paramset.setdefault(p.paramset_id, []).append(p)

    # 포지션이 있는 paramset만 복원
    relevant_ids = set(positions_by_paramset.keys())

    for paramset_id in relevant_ids:
        paramset = load_paramset(paramset_id)
        if paramset is None:
            logger.error(
                "paramset_id=%s 가 DB에 없음 — 데이터 정합성 깨짐", paramset_id
            )
            continue

        # config_hash drift 감지:
        # paramset_id == config_hash 이므로 재계산 값과 비교
        drift = paramset.config_hash() != paramset_id
        if drift:
            logger.warning(
                "config_hash drift 감지 — paramset_id=%s. "
                "보수적 청산 모드 권장(신규 진입 차단, 기존은 exit_rule만 적용)",
                paramset_id,
            )

        states[paramset_id] = RestoredState(
            paramset_id=paramset_id,
            paramset=paramset,
            config_hash_drift=drift,
            positions=positions_by_paramset[paramset_id],
        )

        if strategy_factory is not None:
            strategies[paramset_id] = strategy_factory(paramset)

    return states, strategies


def is_conservative_mode(state: RestoredState) -> bool:
    """보수적 청산 모드 여부 — config_hash drift면 True."""
    return state.config_hash_drift
