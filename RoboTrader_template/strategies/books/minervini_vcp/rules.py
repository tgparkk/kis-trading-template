"""Minervini VCP — Rule 집합.

규칙들:
- rule_trend_template: SEPA Trend Template 8조건
- rule_vcp_breakout: VCP 베이스 + 피벗 돌파
- rule_tight_closes: 3주 변동폭 ≤ 1.5%
- rule_volume_dryup: 거래량 dry-up + tightness

헬퍼:
- compute_rs_percentile_12w: universe 12주 수익률 백분위
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict

import numpy as np
import pandas as pd

from strategies.books._base_book_strategy import Rule, RuleResult


def compute_rs_percentile_12w(universe_close: pd.DataFrame) -> pd.DataFrame:
    """universe 종목 12주(60거래일) 수익률을 0~99 백분위로 변환.

    Args:
        universe_close: index=date, columns=stock_code, values=close.
    Returns:
        같은 shape의 DataFrame. 각 행은 해당 날짜의 RS 백분위 (0~99).
    """
    ret_12w = universe_close.pct_change(60)
    rank = ret_12w.rank(axis=1, pct=True, na_option="keep")
    return (rank * 99).round().astype("Int64")


@dataclass
class rule_trend_template(Rule):
    """SEPA Trend Template 8조건. ctx['rs_value'] 필요."""
    name: str = "trend_template"
    rs_threshold: float = 70.0
    high_52w_drawdown_max: float = 0.25
    low_52w_advance_min: float = 0.30

    def evaluate(self, df: pd.DataFrame, ctx: Dict[str, Any]) -> RuleResult:
        if len(df) < 220:
            return RuleResult(triggered=False)
        close = df["close"].astype(float)
        ma50 = close.rolling(50).mean()
        ma150 = close.rolling(150).mean()
        ma200 = close.rolling(200).mean()
        last_close = float(close.iloc[-1])
        last_ma50 = float(ma50.iloc[-1])
        last_ma150 = float(ma150.iloc[-1])
        last_ma200 = float(ma200.iloc[-1])
        ma200_20d_ago = float(ma200.iloc[-21])
        high_52w = float(close.iloc[-252:].max()) if len(close) >= 252 else float(close.max())
        low_52w = float(close.iloc[-252:].min()) if len(close) >= 252 else float(close.min())
        rs_value = ctx.get("rs_value")
        if rs_value is None or pd.isna(rs_value):
            return RuleResult(triggered=False)

        c1 = last_close > last_ma150 and last_close > last_ma200
        c2 = last_ma150 > last_ma200
        c3 = last_ma200 > ma200_20d_ago
        c4 = last_ma50 > last_ma150 > last_ma200
        c5 = last_close > last_ma50
        c6 = (high_52w - last_close) / high_52w <= self.high_52w_drawdown_max if high_52w > 0 else False
        c7 = (last_close - low_52w) / low_52w >= self.low_52w_advance_min if low_52w > 0 else False
        c8 = float(rs_value) >= self.rs_threshold

        if c1 and c2 and c3 and c4 and c5 and c6 and c7 and c8:
            return RuleResult(
                triggered=True, side="buy", confidence=72.0,
                reasons=[f"TT close={last_close:.0f} ma50={last_ma50:.0f} ma200={last_ma200:.0f} rs={rs_value}"],
                metadata={"rs": float(rs_value)},
            )
        return RuleResult(triggered=False)
