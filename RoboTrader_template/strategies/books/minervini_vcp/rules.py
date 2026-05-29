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

import pandas as pd

from strategies.books._base_book_strategy import Rule, RuleResult


def compute_rs_percentile_12w(universe_close: pd.DataFrame) -> pd.DataFrame:
    """universe 종목 12주(60거래일) 수익률을 0~99 백분위로 변환.

    Args:
        universe_close: index=date, columns=stock_code, values=close.
    Returns:
        같은 shape의 DataFrame. 각 행은 해당 날짜의 RS 백분위 (0~99).
    """
    if universe_close.shape[1] < 2:
        raise ValueError(
            f"universe_close must have ≥ 2 stocks, got {universe_close.shape[1]}"
        )
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


@dataclass
class rule_vcp_breakout(Rule):
    """VCP 베이스(≥25일) + 진폭 수축 + 거래량 dry-up + 피벗 돌파 + RVOL."""
    name: str = "vcp_breakout"
    base_min_bars: int = 25
    rvol_threshold: float = 1.5
    dryup_ratio_max: float = 0.7  # 베이스 평균 거래량 / 직전 20일 평균 ≤ 0.7
    contraction_ratio_max: float = 0.6  # 후반 진폭 / 전반 진폭 ≤ 0.6

    def evaluate(self, df: pd.DataFrame, ctx: Dict[str, Any]) -> RuleResult:
        if len(df) < self.base_min_bars + 21:
            return RuleResult(triggered=False)

        base = df.iloc[-(self.base_min_bars + 1):-1]
        pre_base = df.iloc[-(self.base_min_bars + 21):-(self.base_min_bars + 1)]
        last = df.iloc[-1]

        pivot = float(base["high"].max())
        last_close = float(last["close"])
        last_vol = float(last["volume"])

        # 1. 피벗 돌파
        if last_close <= pivot:
            return RuleResult(triggered=False)

        # 2. RVOL (최근 봉 거래량 / 베이스 평균 거래량)
        base_avg_vol = float(base["volume"].mean())
        if base_avg_vol <= 0:
            return RuleResult(triggered=False)
        rvol = last_vol / base_avg_vol
        if rvol < self.rvol_threshold:
            return RuleResult(triggered=False)

        # 3. 거래량 dry-up: 베이스 평균 < pre_base 평균 × dryup_ratio_max
        pre_base_avg_vol = float(pre_base["volume"].mean())
        if pre_base_avg_vol <= 0 or base_avg_vol / pre_base_avg_vol > self.dryup_ratio_max:
            return RuleResult(triggered=False)

        # 4. 진폭 수축: 베이스 전반 12봉 진폭 vs 후반 12봉 진폭
        mid = len(base) // 2
        early_range = float((base["high"].iloc[:mid] - base["low"].iloc[:mid]).mean())
        late_range = float((base["high"].iloc[mid:] - base["low"].iloc[mid:]).mean())
        if early_range <= 0 or late_range / early_range > self.contraction_ratio_max:
            return RuleResult(triggered=False)

        return RuleResult(
            triggered=True, side="buy", confidence=75.0,
            reasons=[
                f"vcp_breakout pivot={pivot:.0f} close={last_close:.0f} rvol={rvol:.2f} "
                f"dryup={base_avg_vol/pre_base_avg_vol:.2f} contract={late_range/early_range:.2f}"
            ],
            metadata={"pivot": pivot, "rvol": rvol},
        )


@dataclass
class rule_tight_closes(Rule):
    """3주(15봉) 종가 변동폭 ≤ 1.5%."""
    name: str = "tight_closes"
    window: int = 15
    range_pct_max: float = 0.015

    def evaluate(self, df: pd.DataFrame, ctx: Dict[str, Any]) -> RuleResult:
        if len(df) < self.window:
            return RuleResult(triggered=False)
        recent_close = df["close"].astype(float).iloc[-self.window:]
        mean_close = recent_close.mean()
        if mean_close <= 0:
            return RuleResult(triggered=False)
        range_pct = (recent_close.max() - recent_close.min()) / mean_close
        if range_pct <= self.range_pct_max:
            return RuleResult(
                triggered=True, side="buy", confidence=60.0,
                reasons=[f"tight_closes range={range_pct:.3%} ≤ {self.range_pct_max:.1%}"],
            )
        return RuleResult(triggered=False)


@dataclass
class rule_volume_dryup(Rule):
    """최근 10봉 평균 거래량 ≤ 직전 30봉 평균의 70%."""
    name: str = "volume_dryup"
    recent_window: int = 10
    base_window: int = 30
    ratio_max: float = 0.7

    def evaluate(self, df: pd.DataFrame, ctx: Dict[str, Any]) -> RuleResult:
        if len(df) < self.recent_window + self.base_window:
            return RuleResult(triggered=False)
        vol = df["volume"].astype(float)
        recent_avg = float(vol.iloc[-self.recent_window:].mean())
        base_avg = float(vol.iloc[-(self.recent_window + self.base_window):-self.recent_window].mean())
        if base_avg <= 0:
            return RuleResult(triggered=False)
        ratio = recent_avg / base_avg
        if ratio <= self.ratio_max:
            return RuleResult(
                triggered=True, side="buy", confidence=58.0,
                reasons=[f"volume_dryup recent/base={ratio:.2f} ≤ {self.ratio_max:.2f}"],
            )
        return RuleResult(triggered=False)


ALL_RULES = [
    rule_trend_template,
    rule_vcp_breakout,
    rule_tight_closes,
    rule_volume_dryup,
]
