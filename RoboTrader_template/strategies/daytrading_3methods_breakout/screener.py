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
            # high_window=15: 라이브 config.yaml/strategy 검증값과 일치(멀티버스 2026-06-02
            # rank1). 이전 20은 스크리너만 더 엄격해 후보-진입 정의 불일치였음(감사 2026-06-23).
            "high_window": 15,
            "vol_lookback": 20,
            "vol_mult": 2.0,
            "max_market_cap": 500_000_000_000,  # 5천억 미만
            "min_trading_value": 1_000_000_000,
            "max_candidates": 10,
        }

    def base_filter(self, universe: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        # '중소형(5천억 미만)' 컨셉. 시총 결측(0/None)이면 검증 불가 → fail-closed 제외
        # (상한형은 `0 >= max` 가 False 라 과거엔 결측이 조용히 통과했음). 시장 라벨 게이트 없음.
        p = self.default_params()
        out = []
        for u in universe:
            if not self._passes_market_cap(u.get("market_cap"), max_cap=p["max_market_cap"]):
                continue
            if u.get("trading_value", 0) < p["min_trading_value"]:
                continue
            out.append(u)
        return out

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
        last_vol = float(df["volume"].iloc[-1])
        avg_vol = float(df["volume"].iloc[-21:-1].mean()) or 1.0
        score = last_vol / avg_vol
        return (score, reason)
