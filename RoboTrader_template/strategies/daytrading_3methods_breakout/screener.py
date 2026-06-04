"""유지윤 전고 돌파 전략 EOD 스크리너 어댑터."""
from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

import pandas as pd

from strategies._rule_screener_base import RuleScreenerBase
from strategies.books.daytrading_3methods.rules import rule_breakout_prev_high


class Daytrading3MethodsBreakoutScreenerAdapter(RuleScreenerBase):
    strategy_name = "daytrading_3methods_breakout"
    lookback_days = 60

    def default_params(self) -> Dict[str, Any]:
        return {
            "high_window": 20,
            "vol_lookback": 20,
            "vol_mult": 2.0,
            "max_market_cap": 500_000_000_000,  # 5천억 미만
            "min_trading_value": 1_000_000_000,
            "max_candidates": 10,
        }

    def base_filter(self, universe: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        p = self.default_params()
        return [
            u for u in universe
            if u.get("market") == "KOSDAQ"
            and 0 < u.get("market_cap", 0) < p["max_market_cap"]
            and u.get("trading_value", 0) >= p["min_trading_value"]
        ]

    def match(self, df: pd.DataFrame, params: Dict[str, Any]) -> Optional[Tuple[float, str]]:
        rule = rule_breakout_prev_high(
            high_window=int(params.get("high_window", 20)),
            vol_lookback=int(params.get("vol_lookback", 20)),
            vol_mult=float(params.get("vol_mult", 2.0)),
        )
        res = rule.evaluate(df, {})
        if not getattr(res, "triggered", False):
            return None
        reason = "; ".join(getattr(res, "reasons", []) or ["breakout_prev_high"])
        score = float(df["volume"].iloc[-1])
        return (score, reason)
