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
        elif strategy_name == "sample":
            from strategies.sample.screener import SampleScreenerAdapter
            return SampleScreenerAdapter()
        elif strategy_name == "elder_ema_pullback":
            from strategies.elder_ema_pullback.screener import ElderEmaPullbackScreenerAdapter
            return ElderEmaPullbackScreenerAdapter(config=config, broker=broker, db_manager=db_manager)
        elif strategy_name == "minervini_volume_dryup":
            from strategies.minervini_volume_dryup.screener import MinerviniVolumeDryupScreenerAdapter
            return MinerviniVolumeDryupScreenerAdapter(config=config, broker=broker, db_manager=db_manager)
        elif strategy_name == "book_pullback_ma20":
            from strategies.book_pullback_ma20.screener import BookPullbackMa20ScreenerAdapter
            return BookPullbackMa20ScreenerAdapter(config=config, broker=broker, db_manager=db_manager)
        elif strategy_name == "book_pullback_ma5":
            from strategies.book_pullback_ma5.screener import BookPullbackMa5ScreenerAdapter
            return BookPullbackMa5ScreenerAdapter(config=config, broker=broker, db_manager=db_manager)
        elif strategy_name == "daytrading_3methods_breakout":
            from strategies.daytrading_3methods_breakout.screener import Daytrading3MethodsBreakoutScreenerAdapter
            return Daytrading3MethodsBreakoutScreenerAdapter(config=config, broker=broker, db_manager=db_manager)
        elif strategy_name == "book_envelope_200d":
            from strategies.book_envelope_200d.screener import BookEnvelope200dScreenerAdapter
            return BookEnvelope200dScreenerAdapter(config=config, broker=broker, db_manager=db_manager)
        elif strategy_name == "rs_leader":
            from strategies.rs_leader.screener import RSLeaderScreenerAdapter
            return RSLeaderScreenerAdapter(config=config, broker=broker, db_manager=db_manager)
        elif strategy_name == "deep_mr_dev20":
            from strategies.deep_mr_dev20.screener import DeepMrDev20ScreenerAdapter
            return DeepMrDev20ScreenerAdapter(config=config, broker=broker, db_manager=db_manager)
        else:
            _LOGGER.warning("알 수 없는 전략: %s", strategy_name)
            return None
    except Exception as e:
        _LOGGER.error("어댑터 생성 실패 (%s): %s", strategy_name, e)
        return None
