"""Minervini 거래량 건조 전략 EOD 스크리너 어댑터."""
from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

import pandas as pd

from strategies._rule_screener_base import RuleScreenerBase
from strategies.books.minervini_vcp.rules import rule_volume_dryup


class MinerviniVolumeDryupScreenerAdapter(RuleScreenerBase):
    strategy_name = "minervini_volume_dryup"
    lookback_days = 90

    def default_params(self) -> Dict[str, Any]:
        return {
            "recent_window": 10,
            "base_window": 30,
            "ratio_max": 0.70,
            "min_market_cap": 300_000_000_000,
            "min_trading_value": 3_000_000_000,
            "max_candidates": 10,
        }

    def base_filter(self, universe: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        p = self.default_params()
        return [
            u for u in universe
            if u.get("market") == "KOSPI"
            and u.get("market_cap", 0) >= p["min_market_cap"]
            and u.get("trading_value", 0) >= p["min_trading_value"]
        ]

    def match(self, df: pd.DataFrame, params: Dict[str, Any]) -> Optional[Tuple[float, str]]:
        rule = rule_volume_dryup(
            recent_window=int(params.get("recent_window", 10)),
            base_window=int(params.get("base_window", 30)),
            ratio_max=float(params.get("ratio_max", 0.70)),
        )
        res = rule.evaluate(df, {})
        if not getattr(res, "triggered", False):
            return None
        reason = "; ".join(getattr(res, "reasons", []) or ["volume_dryup"])
        score = float(df["volume"].iloc[-30:].mean())  # 유동성 큰 쪽 우선(동률 깨기)
        return (score, reason)
