"""횡보장 RS 리더 전략 EOD 스크리너 어댑터.

match 가 절대상승추세 통과 종목의 120일 수익률을 score 로 반환 → RuleScreenerBase.scan
의 정렬+topK 가 곧 횡단면 RS 랭킹(별도 패널 불요). 진입 추세 판정은 검증에서 쓴
strategies.rs_leader.rule.RSLeaderRule 단일 소스를 재사용(DRY).
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

import pandas as pd

from strategies._rule_screener_base import RuleScreenerBase
from strategies.rs_leader.rule import RSLeaderRule


class RSLeaderScreenerAdapter(RuleScreenerBase):
    strategy_name = "rs_leader"
    lookback_days = 130  # MA60 + 120일 수익률 워밍업

    def default_params(self) -> Dict[str, Any]:
        return {
            "ma_short": 20, "ma_long": 60, "abs_lb": 60, "rs_lb": 120,
            "min_trading_value": 1_000_000_000,
            "min_price": 1_000, "max_price": 500_000,
            "max_candidates": 10,
        }

    def base_filter(self, universe: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        p = self.default_params()
        out = []
        for u in universe:
            if u.get("trading_value", 0) < p["min_trading_value"]:
                continue
            out.append(u)
        return out

    def match(self, df: pd.DataFrame, params: Dict[str, Any]) -> Optional[Tuple[float, str]]:
        rs_lb = int(params.get("rs_lb", 120))
        rule = RSLeaderRule(
            ma_short=int(params.get("ma_short", 20)),
            ma_long=int(params.get("ma_long", 60)),
            abs_lb=int(params.get("abs_lb", 60)),
        )
        close = df["close"].astype(float)
        last = float(close.iloc[-1])
        if last < params.get("min_price", 1_000) or last > params.get("max_price", 500_000):
            return None
        sig = rule.generate_signal("_", df, "daily")
        if sig is None:
            return None
        if len(close) <= rs_lb:
            return None
        ref = float(close.iloc[-1 - rs_lb])
        # RS 분모(과거 close) 0/NaN 가드: 손상된 일봉(과거 text-date 오염 등)이
        # ZeroDivisionError/NaN score 를 내지 않도록 방어. (rule.py 는 abs_lb 기준가만
        # 가드하고 screener 의 rs_lb 기준가는 미가드였음 — 감사 2026-06-23)
        if not (ref > 0):  # 0·음수·NaN 모두 차단(NaN 비교는 항상 False)
            return None
        rs_ret = last / ref - 1.0
        reason = f"RS리더: 절대상승추세 + {rs_lb}일수익률 {rs_ret * 100:+.1f}%"
        return (float(rs_ret), reason)  # score=RS수익률 → scan 정렬+topK = RS랭킹
