"""Raschke Street Smarts: 5개 일봉 매매 규칙.

Phase 2 — 일봉 데이터 기반 셋업.

규칙들:
- rule_turtle_soup: 20일 신저점 후 다음 봉 이전 저점 위 돌파
- rule_turtle_soup_plus_one: D+0 신저점 + 종가 < 이전 저점 → D+1 이전 저점 위 돌파
- rule_80_20: 전일 대형봉 + 시가 상위20%·종가 하위20% → 당일 전일 저점 돌파
- rule_adx_gapper: ADX(12)>30 + +DI(28)>-DI(28) + 갭다운 → 전일 저점에서 매수
- rule_2period_roc: 2일 ROC 음→양 전환 시 매수
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict

import numpy as np
import pandas as pd

from strategies.books._base_book_strategy import Rule, RuleResult


def _adx_di(df: pd.DataFrame, adx_period: int = 12, di_period: int = 28) -> tuple:
    high = df["high"]
    low = df["low"]
    close = df["close"]
    tr = pd.concat([
        (high - low),
        (high - close.shift()).abs(),
        (low - close.shift()).abs(),
    ], axis=1).max(axis=1)
    plus_dm = (high.diff()).where(lambda x: (x > 0) & (x > -low.diff()), 0.0).clip(lower=0)
    minus_dm = (-low.diff()).where(lambda x: (x > 0) & (x > high.diff()), 0.0).clip(lower=0)
    atr = tr.rolling(adx_period).mean().replace(0, np.nan)
    plus_di = 100 * plus_dm.rolling(di_period).mean() / atr
    minus_di = 100 * minus_dm.rolling(di_period).mean() / atr
    dx = (plus_di - minus_di).abs() / (plus_di + minus_di).replace(0, np.nan) * 100
    adx = dx.rolling(adx_period).mean().fillna(0.0)
    return adx, plus_di.fillna(0), minus_di.fillna(0)


# ---------------------------------------------------------------------------
# 1. Turtle Soup (20일 신저점 후 돌파)
# ---------------------------------------------------------------------------

@dataclass
class rule_turtle_soup(Rule):
    """오늘 20일 신저점 + 이전 저점이 최소 4일 이전 → 다음 봉 이전 저점 위 돌파 시 매수."""
    name: str = "turtle_soup"
    lookback: int = 20
    min_days_since_low: int = 4

    def evaluate(self, df: pd.DataFrame, ctx: Dict[str, Any]) -> RuleResult:
        if len(df) < self.lookback + 2:
            return RuleResult(triggered=False)
        # 이전 20일 (전 봉 기준 lookback)
        prev_window = df.iloc[-(self.lookback + 1):-1]
        prev_low = float(prev_window["low"].min())
        # 그 저점이 며칠 전인가
        days_since_low = self.lookback - prev_window["low"].argmin() - 1
        if days_since_low < self.min_days_since_low:
            return RuleResult(triggered=False)
        prev_bar_low = float(df["low"].iloc[-2])
        last_close = float(df["close"].iloc[-1])
        # 직전 봉이 20일 신저점 (low < prev_low) 이여야
        if prev_bar_low >= prev_low:
            return RuleResult(triggered=False)
        # 오늘 종가가 이전 저점(prev_low) 위 마감
        if last_close > prev_low:
            return RuleResult(
                triggered=True, side="buy", confidence=68.0,
                reasons=[f"turtle_soup prev_low={prev_low:.2f} prev_bar_low={prev_bar_low:.2f} close={last_close:.2f}"],
            )
        return RuleResult(triggered=False)


# ---------------------------------------------------------------------------
# 2. Turtle Soup Plus One
# ---------------------------------------------------------------------------

@dataclass
class rule_turtle_soup_plus_one(Rule):
    """D-1에 20일 신저점 + 종가 < 이전 저점 → 오늘 이전 저점 위 마감 시 매수."""
    name: str = "turtle_soup_plus_one"
    lookback: int = 20

    def evaluate(self, df: pd.DataFrame, ctx: Dict[str, Any]) -> RuleResult:
        if len(df) < self.lookback + 3:
            return RuleResult(triggered=False)
        # D-1 = df.iloc[-2], D = df.iloc[-1]
        prev_window = df.iloc[-(self.lookback + 2):-2]
        prev_low = float(prev_window["low"].min())
        d1_low = float(df["low"].iloc[-2])
        d1_close = float(df["close"].iloc[-2])
        last_close = float(df["close"].iloc[-1])

        # D-1이 20일 신저점 + 종가가 이전 저점 이하
        if d1_low >= prev_low or d1_close >= prev_low:
            return RuleResult(triggered=False)
        # D 종가가 이전 저점 위
        if last_close > prev_low:
            return RuleResult(
                triggered=True, side="buy", confidence=70.0,
                reasons=[f"turtle_soup_plus_one prev_low={prev_low:.2f} d1_close={d1_close:.2f} close={last_close:.2f}"],
            )
        return RuleResult(triggered=False)


# ---------------------------------------------------------------------------
# 3. 80-20 (전일 대형봉 반전)
# ---------------------------------------------------------------------------

@dataclass
class rule_80_20(Rule):
    """전일 대형봉 + 시가 상위 20%·종가 하위 20% → 오늘 전일 저점 위 마감 시 매수."""
    name: str = "rule_80_20"
    avg_range_window: int = 10

    def evaluate(self, df: pd.DataFrame, ctx: Dict[str, Any]) -> RuleResult:
        if len(df) < self.avg_range_window + 2:
            return RuleResult(triggered=False)
        prev = df.iloc[-2]
        prev_high = float(prev["high"])
        prev_low = float(prev["low"])
        prev_open = float(prev["open"])
        prev_close = float(prev["close"])
        prev_range = prev_high - prev_low
        if prev_range <= 0:
            return RuleResult(triggered=False)
        # 대형봉: 평균 범위 대비 초과
        avg_range = float((df["high"] - df["low"]).iloc[-(self.avg_range_window + 1):-1].mean())
        large_bar = prev_range > avg_range * 1.2
        # 시가 상위 20% + 종가 하위 20% (down day pattern)
        open_in_top20 = prev_open > prev_low + prev_range * 0.80
        close_in_bot20 = prev_close < prev_low + prev_range * 0.20
        # 오늘 종가가 전일 저점 위로 돌파
        last_close = float(df["close"].iloc[-1])
        bounced_back = last_close > prev_low
        if large_bar and open_in_top20 and close_in_bot20 and bounced_back:
            return RuleResult(
                triggered=True, side="buy", confidence=65.0,
                reasons=[f"80_20 prev_range={prev_range:.2f} avg={avg_range:.2f} close={last_close:.2f}>prev_low={prev_low:.2f}"],
            )
        return RuleResult(triggered=False)


# ---------------------------------------------------------------------------
# 4. ADX Gapper (강추세 + 역방향 갭)
# ---------------------------------------------------------------------------

@dataclass
class rule_adx_gapper(Rule):
    """ADX(12)>30 + +DI(28)>-DI(28) + 시가가 전일 저점 아래 갭다운 → 전일 저점 위 마감 시 매수."""
    name: str = "adx_gapper"
    adx_threshold: float = 30.0

    def evaluate(self, df: pd.DataFrame, ctx: Dict[str, Any]) -> RuleResult:
        if len(df) < 30 + 2:
            return RuleResult(triggered=False)
        adx, plus_di, minus_di = _adx_di(df)
        last_adx = float(adx.iloc[-1])
        last_plus = float(plus_di.iloc[-1])
        last_minus = float(minus_di.iloc[-1])
        if last_adx < self.adx_threshold or last_plus <= last_minus:
            return RuleResult(triggered=False)
        prev_low = float(df["low"].iloc[-2])
        last_open = float(df["open"].iloc[-1])
        last_close = float(df["close"].iloc[-1])
        gap_down = last_open < prev_low
        recovered = last_close > prev_low
        if gap_down and recovered:
            return RuleResult(
                triggered=True, side="buy", confidence=64.0,
                reasons=[f"adx_gapper adx={last_adx:.1f} prev_low={prev_low:.2f} open={last_open:.2f}<prev_low close={last_close:.2f}>prev_low"],
            )
        return RuleResult(triggered=False)


# ---------------------------------------------------------------------------
# 5. 2-Period ROC (2일 ROC 음→양 전환)
# ---------------------------------------------------------------------------

@dataclass
class rule_2period_roc(Rule):
    """2일 ROC가 음에서 양으로 전환 시 매수 (종가)."""
    name: str = "two_period_roc"

    def evaluate(self, df: pd.DataFrame, ctx: Dict[str, Any]) -> RuleResult:
        if len(df) < 5:
            return RuleResult(triggered=False)
        roc = df["close"].pct_change(2)
        prev_roc = float(roc.iloc[-2])
        last_roc = float(roc.iloc[-1])
        if prev_roc < 0 and last_roc >= 0:
            return RuleResult(
                triggered=True, side="buy", confidence=62.0,
                reasons=[f"2period_roc prev_roc={prev_roc:.4f} → last_roc={last_roc:.4f}"],
            )
        return RuleResult(triggered=False)


ALL_RULES_DAILY = [
    rule_turtle_soup,
    rule_turtle_soup_plus_one,
    rule_80_20,
    rule_adx_gapper,
    rule_2period_roc,
]
