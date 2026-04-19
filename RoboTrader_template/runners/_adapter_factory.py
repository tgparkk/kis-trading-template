"""
어댑터 팩토리 — 스크리너 어댑터 인스턴스 생성 공통 유틸.
screener_snapshot_collector 와 param_optimizer 에서 공용으로 사용한다.
"""
from __future__ import annotations

import logging
from typing import Optional

from strategies.screener_base import ScreenerBase

_LOGGER = logging.getLogger("runners.adapter_factory")


def build_adapter(
    strategy_name: str,
    broker=None,
    db_manager=None,
    config=None,
) -> Optional[ScreenerBase]:
    """전략명 → 어댑터 인스턴스. 실패 시 None 반환."""
    try:
        if strategy_name == "lynch":
            from strategies.lynch.screener import LynchScreenerAdapter
            return LynchScreenerAdapter(config=config, broker=broker, db_manager=db_manager)
        elif strategy_name == "sawkami":
            from strategies.sawkami.screener import SawkamiScreenerAdapter
            return SawkamiScreenerAdapter(config=config, broker=broker, db_manager=db_manager)
        elif strategy_name == "bb_reversion":
            from strategies.bb_reversion.screener import BBReversionScreenerAdapter
            return BBReversionScreenerAdapter()
        else:
            _LOGGER.warning("알 수 없는 전략: %s", strategy_name)
            return None
    except Exception as e:
        _LOGGER.error("어댑터 생성 실패 (%s): %s", strategy_name, e)
        return None
