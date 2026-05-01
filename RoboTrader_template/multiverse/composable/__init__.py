"""multiverse.composable — Composable 5모듈 전략."""

from RoboTrader_template.multiverse.composable.paramset import ParamSet
from RoboTrader_template.multiverse.composable.strategy import ComposableStrategy
from RoboTrader_template.multiverse.composable.universe import Universe, StubUniverse
from RoboTrader_template.multiverse.composable.scorer import Scorer, StubScorer
from RoboTrader_template.multiverse.composable.regime import Regime, StubRegime
from RoboTrader_template.multiverse.composable.signal_gen import (
    SignalGenerator,
    StubSignalGenerator,
)
from RoboTrader_template.multiverse.composable.sizer import Sizer, StubSizer
from RoboTrader_template.multiverse.composable.exit_rule import ExitRule, StubExitRule
from RoboTrader_template.multiverse.composable.rebalancer import (
    Rebalancer,
    StubRebalancer,
)
from RoboTrader_template.multiverse.composable.holding_cap import (
    HoldingCap,
    StubHoldingCap,
)

from RoboTrader_template.multiverse.composable.personas import (
    build_quant_strategy,
    build_swing_strategy,
    build_long_term_strategy,
    build_intraday_strategy,
)

__all__ = [
    "ParamSet",
    "ComposableStrategy",
    "Universe", "StubUniverse",
    "Scorer", "StubScorer",
    "Regime", "StubRegime",
    "SignalGenerator", "StubSignalGenerator",
    "Sizer", "StubSizer",
    "ExitRule", "StubExitRule",
    "Rebalancer", "StubRebalancer",
    "HoldingCap", "StubHoldingCap",
    "build_quant_strategy",
    "build_swing_strategy",
    "build_long_term_strategy",
    "build_intraday_strategy",
]
