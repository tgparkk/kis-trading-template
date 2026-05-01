"""4 페르소나 샘플 ComposableStrategy — 퀀트/스윙/중장기/단타.

각 페르소나는 ParamSet을 받아 ComposableStrategy를 조립하는 factory를 제공한다.
실제 알고리즘은 단순 데모 수준이며, Phase 8 이후 본격 멀티버스 실행에서 정교화된다.
"""
from RoboTrader_template.multiverse.composable.personas.quant import build_quant_strategy
from RoboTrader_template.multiverse.composable.personas.swing import build_swing_strategy
from RoboTrader_template.multiverse.composable.personas.long_term import build_long_term_strategy
from RoboTrader_template.multiverse.composable.personas.intraday import build_intraday_strategy

__all__ = [
    "build_quant_strategy",
    "build_swing_strategy",
    "build_long_term_strategy",
    "build_intraday_strategy",
]
