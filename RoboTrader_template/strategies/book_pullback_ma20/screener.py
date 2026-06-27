"""MA20 눌림목 전략 EOD 스크리너 어댑터."""
from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

import pandas as pd

from strategies._rule_screener_base import RuleScreenerBase
from strategies.books.haru_silijeon.rules_daily import rule_daily_ma20_pullback


class BookPullbackMa20ScreenerAdapter(RuleScreenerBase):
    strategy_name = "book_pullback_ma20"
    lookback_days = 90

    def default_params(self) -> Dict[str, Any]:
        return {
            "max_market_cap": 3_000_000_000_000,  # 중소형: 3조 이하
            "min_trading_value": 1_000_000_000,
            "max_candidates": 10,
        }

    def base_filter(self, universe: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        # KOSPI+KOSDAQ 모두 허용 — 중소형(3조 이하) 시총만 필터(눌림목은 시장 무관).
        # 시총 결측(0/None)이면 검증 불가 → fail-closed 제외(상한형 `0 > max` 회귀 방지).
        p = self.default_params()
        out = []
        for u in universe:
            if not self._passes_market_cap(
                u.get("market_cap"), max_cap=p["max_market_cap"], max_inclusive=True
            ):
                continue
            if u.get("trading_value", 0) < p["min_trading_value"]:
                continue
            out.append(u)
        return out

    def match(self, df: pd.DataFrame, params: Dict[str, Any]) -> Optional[Tuple[float, str]]:
        res = rule_daily_ma20_pullback().evaluate(df, {})
        if not getattr(res, "triggered", False):
            return None
        reason = "; ".join(getattr(res, "reasons", []) or ["daily_ma20_pullback"])
        score = float(df["volume"].iloc[-20:].mean())
        return (score, reason)
