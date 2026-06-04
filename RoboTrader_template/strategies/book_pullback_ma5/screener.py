"""MA5 단기 눌림목 전략 EOD 스크리너 어댑터."""
from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

import pandas as pd

from strategies._rule_screener_base import RuleScreenerBase
from strategies.books.trading_legends.rules_daily import rule_ma5_pullback


class BookPullbackMa5ScreenerAdapter(RuleScreenerBase):
    strategy_name = "book_pullback_ma5"
    lookback_days = 60

    def default_params(self) -> Dict[str, Any]:
        return {
            "max_market_cap": 3_000_000_000_000,
            "min_trading_value": 1_000_000_000,
            "max_candidates": 10,
        }

    def base_filter(self, universe: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        # KOSPI+KOSDAQ 모두 허용 — 중소형 시총만 필터(눌림목은 시장 무관)
        p = self.default_params()
        return [
            u for u in universe
            if 0 < u.get("market_cap", 0) <= p["max_market_cap"]
            and u.get("trading_value", 0) >= p["min_trading_value"]
        ]

    def match(self, df: pd.DataFrame, params: Dict[str, Any]) -> Optional[Tuple[float, str]]:
        res = rule_ma5_pullback().evaluate(df, {})
        if not getattr(res, "triggered", False):
            return None
        reason = "; ".join(getattr(res, "reasons", []) or ["ma5_pullback"])
        score = float(df["volume"].iloc[-5:].mean())
        return (score, reason)
