"""4전략 어댑터. 진입 메커니즘·청산종류·ctx주입·그리드를 캡슐화."""
from __future__ import annotations
import itertools
from dataclasses import dataclass
from typing import Callable, Dict, List, Optional
import pandas as pd

from scripts.exit_multiverse import exits


@dataclass
class StrategyAdapter:
    name: str
    entry_mechanism: str          # "stop"(elder 매수스톱) | "market"(다음날 시가)
    warmup_bars: int
    exit_kind: str                # "elder" | "simple_ma"
    build_strategy: Callable[[], object]
    build_grid: Callable[[], List[dict]]
    make_extra_ctx_fn: Callable[[Dict[str, pd.DataFrame]], Callable[[str, pd.Timestamp], dict]]

    def exit_reason(self, df, i, position, params) -> Optional[str]:
        if self.exit_kind == "elder":
            return exits.exit_reason_elder(
                df, i, position,
                stop_loss_pct=params["stop_loss_pct"],
                take_profit_pct=params["take_profit_pct"],
                max_hold_bars=params["max_hold_bars"],
                trail_ema=params.get("trail_ema"),
                trend_flip_exit=params.get("trend_flip_exit", False))
        return exits.exit_reason_simple_ma(
            df, i, position,
            stop_loss_pct=params["stop_loss_pct"],
            take_profit_pct=params["take_profit_pct"],
            max_hold_bars=params["max_hold_bars"],
            trail_ma=params.get("trail_ma"))


def _grid(**axes) -> List[dict]:
    keys = list(axes.keys())
    return [dict(zip(keys, combo)) for combo in itertools.product(*axes.values())]


def _elder_strategy():
    from strategies.books.elder_triple_screen.strategy import build_strategy
    return build_strategy(mode="single", target_rule="triple_screen_ema_pullback")


def _elder_grid() -> List[dict]:
    return _grid(stop_loss_pct=[0.06, 0.08, 0.10],
                 take_profit_pct=[0.20, 0.30, 0.40],
                 max_hold_bars=[60, 100, 150],
                 trail_ema=[13, None],
                 trend_flip_exit=[True, False])


def _minervini_strategy():
    from strategies.books.minervini_vcp.strategy import build_strategy
    return build_strategy(mode="single", target_rule="volume_dryup")


def _minervini_grid() -> List[dict]:
    return _grid(stop_loss_pct=[0.06, 0.08, 0.10],
                 take_profit_pct=[0.10, 0.12, 0.15],
                 max_hold_bars=[15, 20, 30])


def _minervini_ctx_factory(data: Dict[str, pd.DataFrame]):
    from strategies.books.minervini_vcp.rules import compute_rs_percentile_12w
    series = {code: df.set_index("datetime")["close"] for code, df in data.items()}
    wide = pd.DataFrame(series)
    wide.index = pd.to_datetime(wide.index)
    wide = wide.sort_index()
    rs_wide = compute_rs_percentile_12w(wide)

    def _ctx(code: str, dt: pd.Timestamp) -> dict:
        if code in rs_wide.columns and dt in rs_wide.index:
            val = float(rs_wide.loc[dt, code])
        else:
            val = float("nan")
        return {"rs_value": val}
    return _ctx


def _ma20_strategy():
    from strategies.books.haru_silijeon.strategy_daily import build_strategy_daily
    return build_strategy_daily(mode="single", target_rule="daily_ma20_pullback")


def _ma20_grid() -> List[dict]:
    return _grid(stop_loss_pct=[0.06, 0.08, 0.10],
                 take_profit_pct=[0.08, 0.10, 0.15],
                 max_hold_bars=[30, 50, 80],
                 trail_ma=[20, None])


def _ma5_strategy():
    from strategies.books.trading_legends.strategy_daily import build_strategy_daily
    return build_strategy_daily(mode="single", target_rule="ma5_pullback")


def _ma5_grid() -> List[dict]:
    return _grid(stop_loss_pct=[0.03, 0.05, 0.08],
                 take_profit_pct=[0.12, 0.15, 0.20],
                 max_hold_bars=[20, 30, 50],
                 trail_ma=[5, None])


def _empty_ctx_factory(data):
    return lambda code, dt: {}


ADAPTERS: Dict[str, StrategyAdapter] = {
    "elder_ema_pullback": StrategyAdapter(
        name="elder_ema_pullback", entry_mechanism="stop", warmup_bars=70,
        exit_kind="elder", build_strategy=_elder_strategy, build_grid=_elder_grid,
        make_extra_ctx_fn=_empty_ctx_factory),
    "minervini_volume_dryup": StrategyAdapter(
        name="minervini_volume_dryup", entry_mechanism="market", warmup_bars=60,
        exit_kind="simple_ma", build_strategy=_minervini_strategy, build_grid=_minervini_grid,
        make_extra_ctx_fn=_minervini_ctx_factory),
    "book_pullback_ma20": StrategyAdapter(
        name="book_pullback_ma20", entry_mechanism="market", warmup_bars=20,
        exit_kind="simple_ma", build_strategy=_ma20_strategy, build_grid=_ma20_grid,
        make_extra_ctx_fn=_empty_ctx_factory),
    "book_pullback_ma5": StrategyAdapter(
        name="book_pullback_ma5", entry_mechanism="market", warmup_bars=20,
        exit_kind="simple_ma", build_strategy=_ma5_strategy, build_grid=_ma5_grid,
        make_extra_ctx_fn=_empty_ctx_factory),
}
