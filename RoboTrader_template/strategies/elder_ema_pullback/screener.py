"""Elder EMA 눌림 전략 EOD 스크리너 어댑터."""
from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

import pandas as pd

from strategies._rule_screener_base import RuleScreenerBase
from strategies.books.elder_triple_screen.rules import rule_triple_screen_ema_pullback


class ElderEmaPullbackScreenerAdapter(RuleScreenerBase):
    strategy_name = "elder_ema_pullback"
    lookback_days = 160  # EMA65 + 여유

    def default_params(self) -> Dict[str, Any]:
        return {
            "touch_band": 1.02,
            "min_market_cap": 500_000_000_000,   # 대형 5천억 이상
            "min_trading_value": 5_000_000_000,  # 거래대금 50억 이상
            "max_candidates": 10,
        }

    def base_filter(self, universe: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        p = self.default_params()
        out = []
        for u in universe:
            # 시총 결측(0/None)이면 '대형' 컨셉 검증 불가 → fail-closed 제외.
            if not self._passes_market_cap(u.get("market_cap"), min_cap=p["min_market_cap"]):
                continue
            if u.get("trading_value", 0) < p["min_trading_value"]:
                continue
            out.append(u)
        return out

    def match(self, df: pd.DataFrame, params: Dict[str, Any]) -> Optional[Tuple[float, str]]:
        rule = rule_triple_screen_ema_pullback(touch_band=float(params.get("touch_band", 1.02)))
        res = rule.evaluate(df, {})
        if not getattr(res, "triggered", False):
            return None
        score = float(df["trading_value"].iloc[-1]) if "trading_value" in df else float(df["close"].iloc[-1])
        reason = "; ".join(getattr(res, "reasons", []) or ["triple_screen_ema_pullback"])
        return (score, reason)
