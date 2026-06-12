"""Deep MR Dev20 전략 EOD 스크리너 어댑터.

match = MeanReversionMA20Rule(-20%/RSI<30) 통과 종목의 |이탈깊이| 를 score 로 반환 →
RuleScreenerBase.scan 의 정렬+topK = "더 깊은 폭락 우선" 후보 선정.
유동성 컷(min_trading_value)으로 게이트 검증 유니버스(top_volume:300)를 근사 —
검증상 top500+ 로 풀을 넓히면 엣지가 희석·소멸하므로(확장 런) 컷을 보수적으로 유지.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

import pandas as pd

from strategies._rule_screener_base import RuleScreenerBase
from scripts.discovery.rules import MeanReversionMA20Rule


class DeepMrDev20ScreenerAdapter(RuleScreenerBase):
    strategy_name = "deep_mr_dev20"
    lookback_days = 45  # MA20 + RSI14 워밍업 + 여유

    def default_params(self) -> Dict[str, Any]:
        return {
            "ma_period": 20, "entry_deviation_pct": -20.0,
            "rsi_period": 14, "rsi_oversold": 30,
            # 유동성 컷 — 게이트 유니버스(top_volume:300) 근사. top500+ 확장 시 엣지 소멸 확인.
            "min_trading_value": 10_000_000_000,
            "min_price": 1_000, "max_price": 500_000,
            "max_candidates": 10,
        }

    def base_filter(self, universe: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        p = self.default_params()
        return [u for u in universe if u.get("trading_value", 0) >= p["min_trading_value"]]

    def match(self, df: pd.DataFrame, params: Dict[str, Any]) -> Optional[Tuple[float, str]]:
        close = df["close"].astype(float)
        last = float(close.iloc[-1])
        if last < params.get("min_price", 1_000) or last > params.get("max_price", 500_000):
            return None
        rule = MeanReversionMA20Rule(
            ma_period=int(params.get("ma_period", 20)),
            entry_deviation_pct=float(params.get("entry_deviation_pct", -20.0)),
            rsi_period=int(params.get("rsi_period", 14)),
            rsi_oversold=float(params.get("rsi_oversold", 30)),
        )
        sig = rule.generate_signal("_", df, "daily")
        if sig is None:
            return None
        ma_period = int(params.get("ma_period", 20))
        ma_val = float(close.rolling(ma_period).mean().iloc[-1])
        depth = abs((last - ma_val) / ma_val) if ma_val > 0 else 0.0
        reason = f"폭락 평균회귀: MA{ma_period} 대비 {-depth * 100:.1f}% 이탈 + RSI 과매도"
        return (float(depth), reason)  # score=이탈깊이 → 깊은 폭락 우선
