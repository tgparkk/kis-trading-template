"""Mike Bellafiore - One Good Trade / The PlayBook: 6개 매매 규칙.

한국 분봉 코드화 가능한 셋업만 선별. Tape Reading 의존도 높은 4개 (Opening Drive,
Pullback, Trade2Hold, Intraday RS) 는 제외.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Optional

import numpy as np
import pandas as pd

from strategies.books._base_book_strategy import Rule, RuleResult


# ---------------------------------------------------------------------------
# 1. Second Day Play
# ---------------------------------------------------------------------------

@dataclass
class rule_second_day_play(Rule):
    """첫 30봉을 D-1 근사로 사용. 첫 30봉 +5% 이상 상승 + 후속 봉이 첫 30봉 고가 돌파 시 매수.

    책 의도: D-1 강한 모멘텀 + 거래량 폭증 종목이 D+1에 같은 방향으로 연장.
    분봉 근사: D-1 정보 없이 분봉 첫 30봉을 'D-1 마지막 30분' 근사로 활용.
    """
    name: str = "second_day_play"
    setup_bars: int = 30
    min_pct: float = 0.05

    def evaluate(self, df: pd.DataFrame, ctx: Dict[str, Any]) -> RuleResult:
        if len(df) < self.setup_bars + 1:
            return RuleResult(triggered=False)
        setup = df.iloc[: self.setup_bars]
        first_open = float(setup["open"].iloc[0])
        last_setup_close = float(setup["close"].iloc[-1])
        setup_high = float(setup["high"].max())
        last_close = float(df["close"].iloc[-1])

        setup_strong = (last_setup_close - first_open) / max(first_open, 1e-9) >= self.min_pct
        breakout = last_close > setup_high
        if setup_strong and breakout:
            return RuleResult(
                triggered=True, side="buy", confidence=65.0,
                reasons=[f"2day_play setup_high={setup_high:.2f} brk close={last_close:.2f}"],
            )
        return RuleResult(triggered=False)


# ---------------------------------------------------------------------------
# 2. Bull Flag (Bellafiore variant)
# ---------------------------------------------------------------------------

@dataclass
class rule_bull_flag_bellafiore(Rule):
    """폴(1~2봉 1% 이상 상승) + 좁은 박스 5봉 + 돌파. 아지즈보다 폴 짧고 박스 길게."""
    name: str = "bull_flag_bellafiore"
    pole_bars: int = 2
    pole_pct: float = 0.01
    flag_bars: int = 5
    flag_range_pct: float = 0.015

    def evaluate(self, df: pd.DataFrame, ctx: Dict[str, Any]) -> RuleResult:
        total = self.pole_bars + self.flag_bars + 2
        if len(df) < total:
            return RuleResult(triggered=False)
        pole_start = float(df["close"].iloc[-(self.flag_bars + self.pole_bars + 1)])
        pole_end = float(df["close"].iloc[-(self.flag_bars + 1)])
        flag = df.iloc[-(self.flag_bars + 1):-1]
        flag_high = float(flag["high"].max())
        flag_low = float(flag["low"].min())
        last_close = float(df["close"].iloc[-1])

        pole_ok = (pole_end - pole_start) / max(pole_start, 1e-9) >= self.pole_pct
        flag_range = (flag_high - flag_low) / max(flag_high, 1e-9)
        flag_ok = flag_range <= self.flag_range_pct
        breakout = last_close > flag_high
        if pole_ok and flag_ok and breakout:
            return RuleResult(
                triggered=True, side="buy", confidence=68.0,
                reasons=[f"bull_flag_bel pole={pole_ok} range={flag_range:.4f}"],
            )
        return RuleResult(triggered=False)


# ---------------------------------------------------------------------------
# 3. Range Trade (long at support)
# ---------------------------------------------------------------------------

@dataclass
class rule_range_trade(Rule):
    """직전 N봉 range 식별 + 하단 근접 + 양봉. 아지즈 s/r와 유사하지만 윈도우 길고 양봉 조건 강함."""
    name: str = "range_trade"
    window: int = 90
    tol: float = 0.003
    min_range_pct: float = 0.01

    def evaluate(self, df: pd.DataFrame, ctx: Dict[str, Any]) -> RuleResult:
        if len(df) < self.window + 1:
            return RuleResult(triggered=False)
        recent = df.iloc[-(self.window + 1):-1]
        r_low = float(recent["low"].min())
        r_high = float(recent["high"].max())
        last = df.iloc[-1]
        last_low = float(last["low"])
        last_open = float(last["open"])
        last_close = float(last["close"])

        range_pct = (r_high - r_low) / max(r_high, 1e-9)
        wide_enough = range_pct >= self.min_range_pct
        near_low = abs(last_low - r_low) / max(r_low, 1e-9) <= self.tol
        bullish = last_close > last_open
        if wide_enough and near_low and bullish:
            return RuleResult(
                triggered=True, side="buy", confidence=62.0,
                reasons=[f"range r=[{r_low:.2f},{r_high:.2f}] last_low={last_low:.2f}"],
            )
        return RuleResult(triggered=False)


# ---------------------------------------------------------------------------
# 4. Fade VWAP (long at oversold)
# ---------------------------------------------------------------------------

@dataclass
class rule_fade_vwap(Rule):
    """VWAP 하단 -2% 이격 + RSI(2) < 10 → 매수 (long-only fade)."""
    name: str = "fade_vwap"
    deviation_pct: float = 0.02
    rsi_period: int = 2
    rsi_oversold: float = 10.0

    def evaluate(self, df: pd.DataFrame, ctx: Dict[str, Any]) -> RuleResult:
        if len(df) < self.rsi_period + 5:
            return RuleResult(triggered=False)
        tp = (df["high"] + df["low"] + df["close"]) / 3.0
        vwap = (tp * df["volume"]).cumsum() / df["volume"].cumsum().replace(0, np.nan)
        last_vwap = float(vwap.bfill().iloc[-1])
        last_close = float(df["close"].iloc[-1])
        below_pct = (last_vwap - last_close) / max(last_vwap, 1e-9)

        # RSI(rsi_period)
        delta = df["close"].diff()
        up = delta.clip(lower=0)
        down = -delta.clip(upper=0)
        ru = up.rolling(self.rsi_period).mean()
        rd = down.rolling(self.rsi_period).mean()
        rs = ru / rd.replace(0, np.nan)
        rsi = (100 - 100 / (1 + rs)).fillna(50.0)
        last_rsi = float(rsi.iloc[-1])

        if below_pct >= self.deviation_pct and last_rsi < self.rsi_oversold:
            return RuleResult(
                triggered=True, side="buy", confidence=60.0,
                reasons=[f"fade_vwap vwap={last_vwap:.2f} close={last_close:.2f} rsi={last_rsi:.1f}"],
            )
        return RuleResult(triggered=False)


# ---------------------------------------------------------------------------
# 5. Opening Consolidation Breakout
# ---------------------------------------------------------------------------

@dataclass
class rule_opening_consolidation_breakout(Rule):
    """첫 10봉 통합 박스 + 거래량 감소 추세 + 박스 고가 돌파."""
    name: str = "opening_consolidation_breakout"
    consolidation_bars: int = 10
    box_range_pct: float = 0.015

    def evaluate(self, df: pd.DataFrame, ctx: Dict[str, Any]) -> RuleResult:
        if len(df) < self.consolidation_bars + 1:
            return RuleResult(triggered=False)
        box = df.iloc[: self.consolidation_bars]
        box_high = float(box["high"].max())
        box_low = float(box["low"].min())
        box_range = (box_high - box_low) / max(box_high, 1e-9)
        last_close = float(df["close"].iloc[-1])

        # 거래량 감소 추세 (box 후반 < box 전반)
        half = self.consolidation_bars // 2
        early_vol = float(box["volume"].iloc[:half].mean())
        late_vol = float(box["volume"].iloc[half:].mean())

        narrow_box = box_range <= self.box_range_pct
        vol_decreasing = late_vol < early_vol
        breakout = last_close > box_high
        if narrow_box and vol_decreasing and breakout:
            return RuleResult(
                triggered=True, side="buy", confidence=66.0,
                reasons=[f"opening_consolidation box=[{box_low:.2f},{box_high:.2f}] brk close={last_close:.2f}"],
            )
        return RuleResult(triggered=False)


# ---------------------------------------------------------------------------
# 6. Catalyst Gap (gap up + RVOL proxy)
# ---------------------------------------------------------------------------

@dataclass
class rule_catalyst_gap(Rule):
    """첫 봉 시가가 첫 30봉 평균보다 +3% 이상 + 첫 30봉 누적 거래량이 평균의 2배 이상.

    분봉 데이터 한정으로 'gap + RVOL' 근사. 본질: 첫 봉이 상대적으로 고점에서 시작 + 거래량 폭증.
    """
    name: str = "catalyst_gap"
    setup_bars: int = 30
    gap_pct: float = 0.03
    rvol_min: float = 2.0

    def evaluate(self, df: pd.DataFrame, ctx: Dict[str, Any]) -> RuleResult:
        if len(df) < self.setup_bars + 1:
            return RuleResult(triggered=False)
        first_open = float(df["open"].iloc[0])
        setup_avg_close = float(df["close"].iloc[: self.setup_bars].mean())
        setup_vol_avg = float(df["volume"].iloc[: self.setup_bars].mean())
        # RVOL proxy: 현재 봉까지의 누적 거래량 / (평균 거래량 × 경과 봉수)
        elapsed = len(df)
        cumulative_vol = float(df["volume"].sum())
        expected_vol = setup_vol_avg * elapsed
        rvol = cumulative_vol / max(expected_vol, 1e-9)
        last_close = float(df["close"].iloc[-1])

        gap_up = (first_open - setup_avg_close) / max(setup_avg_close, 1e-9) >= self.gap_pct
        rvol_strong = rvol >= self.rvol_min
        above_first = last_close > first_open

        if gap_up and rvol_strong and above_first:
            return RuleResult(
                triggered=True, side="buy", confidence=64.0,
                reasons=[f"catalyst_gap gap={gap_up} rvol={rvol:.2f} above_first={above_first}"],
            )
        return RuleResult(triggered=False)


# 책 전체 규칙
ALL_RULES = [
    rule_second_day_play,
    rule_bull_flag_bellafiore,
    rule_range_trade,
    rule_fade_vwap,
    rule_opening_consolidation_breakout,
    rule_catalyst_gap,
]
