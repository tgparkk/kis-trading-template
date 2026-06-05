"""Book19 envelope_200d_high EOD 스크리너 어댑터 (quant 일봉, 200봉 룩백)."""
from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

import pandas as pd

from strategies._rule_screener_base import RuleScreenerBase
from strategies.books.trading_strategy_book.rules import rule_envelope_200d_high


class BookEnvelope200dScreenerAdapter(RuleScreenerBase):
    strategy_name = "book_envelope_200d"
    lookback_days = 230  # 200일 신고가 + 여유 (영업일≈거래일 환산)

    def default_params(self) -> Dict[str, Any]:
        return {
            "min_trading_value": 1_000_000_000,  # 1차 거래대금 게이트(룰 F=5일 50억 정밀 체크)
            "max_candidates": 10,
        }

    def base_filter(self, universe: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        # 돌파 전략 — 시총 상한 없음(소형주 한정 아님). 거래대금 하한만 1차 컷.
        p = self.default_params()
        out = []
        for u in universe:
            if u.get("trading_value", 0) < p["min_trading_value"]:
                continue
            out.append(u)
        return out

    def match(self, df: pd.DataFrame, params: Dict[str, Any]) -> Optional[Tuple[float, str]]:
        # 조건E(이등분선) today_mask 용 datetime 보강 (일봉=1일1봉이라 date 동치)
        if "datetime" not in df.columns and "date" in df.columns:
            df = df.assign(datetime=df["date"])
        res = rule_envelope_200d_high().evaluate(df, {})
        if not getattr(res, "triggered", False):
            return None
        reason = "; ".join(getattr(res, "reasons", []) or ["envelope_200d_high"])
        # 점수 = 당일 거래대금(유동성 높은 돌파 우선)
        last_close = float(df["close"].iloc[-1])
        last_vol = float(df["volume"].iloc[-1])
        score = last_close * last_vol
        return (score, reason)
