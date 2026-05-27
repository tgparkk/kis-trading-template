"""아지즈 — How to Day Trade for a Living: 8개 매매 규칙.

각 함수는 호출 시 Rule 인스턴스를 반환한다 (dataclass).
evaluate(df, ctx)에서 t 시점 평가 — t+1 데이터 접근 금지.
입력 df는 분봉 OHLCV 시계열.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Optional

import numpy as np
import pandas as pd

from strategies.books._base_book_strategy import Rule, RuleResult


# ---------------------------------------------------------------------------
# 1. ABCD 패턴
# ---------------------------------------------------------------------------

@dataclass
class rule_abcd(Rule):
    """A leg up → B pullback → C leg up → D breakout above C high.

    파라미터:
        lookback: 패턴 탐지에 사용할 직전 봉 수 (default 15)
    """
    name: str = "abcd"
    lookback: int = 15

    def evaluate(self, df: pd.DataFrame, ctx: Dict[str, Any]) -> RuleResult:
        if len(df) < self.lookback + 1:
            return RuleResult(triggered=False)
        seg = df.iloc[-(self.lookback + 1):].reset_index(drop=True)
        third = len(seg) // 3
        a_high = float(seg["high"].iloc[:third].max())
        b_low = float(seg["low"].iloc[third:2 * third].min())
        c_segment = seg["high"].iloc[2 * third:-1]
        if len(c_segment) == 0:
            return RuleResult(triggered=False)
        c_high = float(c_segment.max())
        last = float(seg["close"].iloc[-1])
        if a_high <= b_low or c_high <= b_low:
            return RuleResult(triggered=False)
        if last > c_high and last > a_high:
            return RuleResult(
                triggered=True,
                side="buy",
                confidence=72.0,
                reasons=[f"abcd a={a_high:.2f} b={b_low:.2f} c={c_high:.2f} d={last:.2f}"],
                metadata={"a": a_high, "b": b_low, "c": c_high, "d": last},
            )
        return RuleResult(triggered=False)


# ---------------------------------------------------------------------------
# 2. Bull Flag
# ---------------------------------------------------------------------------

@dataclass
class rule_bull_flag(Rule):
    name: str = "bull_flag"
    spike_pct: float = 0.04
    flag_bars: int = 3
    flag_range_pct: float = 0.02

    def evaluate(self, df: pd.DataFrame, ctx: Dict[str, Any]) -> RuleResult:
        if len(df) < self.flag_bars + 2:
            return RuleResult(triggered=False)
        pre_flag_close = float(df["close"].iloc[-(self.flag_bars + 2)])
        flag = df.iloc[-(self.flag_bars + 1):-1]
        flag_high = float(flag["high"].max())
        flag_low = float(flag["low"].min())
        last_close = float(df["close"].iloc[-1])

        spike_ok = (flag_high - pre_flag_close) / max(pre_flag_close, 1e-9) >= self.spike_pct
        flag_range = (flag_high - flag_low) / max(flag_high, 1e-9)
        flag_ok = flag_range <= self.flag_range_pct
        breakout_ok = last_close > flag_high

        if spike_ok and flag_ok and breakout_ok:
            return RuleResult(
                triggered=True,
                side="buy",
                confidence=70.0,
                reasons=[f"bull_flag spike={spike_ok} range={flag_range:.4f} brk={last_close:.2f}>flag={flag_high:.2f}"],
            )
        return RuleResult(triggered=False)


# ---------------------------------------------------------------------------
# 3. VWAP Reversal
# ---------------------------------------------------------------------------

@dataclass
class rule_vwap_reversal(Rule):
    name: str = "vwap_reversal"
    dip_pct: float = 0.005

    def evaluate(self, df: pd.DataFrame, ctx: Dict[str, Any]) -> RuleResult:
        if len(df) < 5:
            return RuleResult(triggered=False)
        tp = (df["high"] + df["low"] + df["close"]) / 3.0
        vwap = (tp * df["volume"]).cumsum() / df["volume"].cumsum().replace(0, np.nan)
        vwap = vwap.bfill()
        last_close = float(df["close"].iloc[-1])
        last_vwap = float(vwap.iloc[-1])

        lookback = min(20, len(df))
        recent = df["close"].iloc[-lookback:-1]
        vwap_recent = vwap.iloc[-lookback:-1]
        dipped = bool((recent < vwap_recent * (1.0 - self.dip_pct)).any())
        recovered = last_close > last_vwap

        if dipped and recovered:
            return RuleResult(
                triggered=True,
                side="buy",
                confidence=68.0,
                reasons=[f"vwap_reversal last={last_close:.2f} vwap={last_vwap:.2f}"],
            )
        return RuleResult(triggered=False)


# ---------------------------------------------------------------------------
# 4. Opening Range Breakout
# ---------------------------------------------------------------------------

@dataclass
class rule_opening_range_breakout(Rule):
    name: str = "orb"
    orb_bars: int = 5

    def evaluate(self, df: pd.DataFrame, ctx: Dict[str, Any]) -> RuleResult:
        if len(df) < self.orb_bars + 1:
            return RuleResult(triggered=False)
        orb_high = float(df["high"].iloc[: self.orb_bars].max())
        last_close = float(df["close"].iloc[-1])
        if last_close > orb_high:
            return RuleResult(
                triggered=True,
                side="buy",
                confidence=66.0,
                reasons=[f"orb {self.orb_bars}봉 high={orb_high:.2f}, brk close={last_close:.2f}"],
            )
        return RuleResult(triggered=False)


# ---------------------------------------------------------------------------
# 5. Red-to-Green
# ---------------------------------------------------------------------------

@dataclass
class rule_red_to_green(Rule):
    name: str = "red_to_green"
    prev_close: Optional[float] = None

    def evaluate(self, df: pd.DataFrame, ctx: Dict[str, Any]) -> RuleResult:
        if len(df) < 2:
            return RuleResult(triggered=False)
        prev_close = self.prev_close if self.prev_close is not None else ctx.get("prev_close")
        if prev_close is None:
            prev_close = float(df["open"].iloc[0]) * 1.01
        first_open = float(df["open"].iloc[0])
        last_close = float(df["close"].iloc[-1])
        red_start = first_open < prev_close * 0.998
        green_cross = last_close >= prev_close
        if red_start and green_cross:
            return RuleResult(
                triggered=True,
                side="buy",
                confidence=64.0,
                reasons=[f"rtg open={first_open:.2f}<prev_close={prev_close:.2f}, last={last_close:.2f}"],
            )
        return RuleResult(triggered=False)


# ---------------------------------------------------------------------------
# 6. Top Reversal (sell)
# ---------------------------------------------------------------------------

@dataclass
class rule_top_reversal(Rule):
    name: str = "top_reversal"
    doji_body_pct: float = 0.001
    vol_drop_pct: float = 0.5

    def evaluate(self, df: pd.DataFrame, ctx: Dict[str, Any]) -> RuleResult:
        if len(df) < 2:
            return RuleResult(triggered=False)
        last = df.iloc[-1]
        prev = df.iloc[-2]
        body = abs(float(last["close"]) - float(last["open"])) / max(float(last["open"]), 1e-9)
        is_doji = body <= self.doji_body_pct
        vol_drop = float(last["volume"]) < float(prev["volume"]) * self.vol_drop_pct
        if is_doji and vol_drop:
            return RuleResult(
                triggered=True,
                side="sell",
                confidence=62.0,
                reasons=[f"top_rev doji_body={body:.4f}, vol={last['volume']}<{prev['volume']}*{self.vol_drop_pct}"],
            )
        return RuleResult(triggered=False)


# ---------------------------------------------------------------------------
# 7. Support/Resistance Bounce
# ---------------------------------------------------------------------------

@dataclass
class rule_support_resistance(Rule):
    name: str = "support_resistance"
    window: int = 60
    tol: float = 0.003

    def evaluate(self, df: pd.DataFrame, ctx: Dict[str, Any]) -> RuleResult:
        if len(df) < self.window + 1:
            return RuleResult(triggered=False)
        recent_low = float(df["low"].iloc[-(self.window + 1):-1].min())
        last_low = float(df["low"].iloc[-1])
        last_open = float(df["open"].iloc[-1])
        last_close = float(df["close"].iloc[-1])
        near_support = abs(last_low - recent_low) / max(recent_low, 1e-9) <= self.tol
        bullish_bar = last_close > last_open
        if near_support and bullish_bar:
            return RuleResult(
                triggered=True,
                side="buy",
                confidence=60.0,
                reasons=[f"s/r support={recent_low:.2f} last_low={last_low:.2f}"],
            )
        return RuleResult(triggered=False)


# ---------------------------------------------------------------------------
# 8. Moving Average Trend (9/20 EMA + VWAP)
# ---------------------------------------------------------------------------

@dataclass
class rule_ma_trend(Rule):
    """VWAP 위 + 9EMA 또는 20EMA 터치 후 양봉 반등."""
    name: str = "ma_trend"
    short_ema: int = 9
    long_ema: int = 20
    ema_touch_tol: float = 0.01

    def evaluate(self, df: pd.DataFrame, ctx: Dict[str, Any]) -> RuleResult:
        if len(df) < self.long_ema + 1:
            return RuleResult(triggered=False)
        last_close = float(df["close"].iloc[-1])
        last_open = float(df["open"].iloc[-1])
        last_low = float(df["low"].iloc[-1])

        # VWAP (누적)
        tp = (df["high"] + df["low"] + df["close"]) / 3.0
        vwap_series = (tp * df["volume"]).cumsum() / df["volume"].cumsum().replace(0, np.nan)
        last_vwap = float(vwap_series.bfill().iloc[-1])

        # EMA — 마지막 봉을 제외한 이전 봉들의 EMA (룩어헤드 방지)
        prev_close = df["close"].iloc[:-1]
        ema_short = float(prev_close.ewm(span=self.short_ema, adjust=False).mean().iloc[-1])
        ema_long = float(prev_close.ewm(span=self.long_ema, adjust=False).mean().iloc[-1])

        above_vwap = last_close > last_vwap
        bullish = last_close > last_open
        touch_short = abs(last_low - ema_short) / max(ema_short, 1e-9) <= self.ema_touch_tol
        touch_long = abs(last_low - ema_long) / max(ema_long, 1e-9) <= self.ema_touch_tol

        if above_vwap and bullish and (touch_short or touch_long):
            return RuleResult(
                triggered=True,
                side="buy",
                confidence=58.0,
                reasons=[f"ma_trend vwap={last_vwap:.2f} ema9={ema_short:.2f} ema20={ema_long:.2f}"],
                metadata={"vwap": last_vwap, "ema_short": ema_short, "ema_long": ema_long},
            )
        return RuleResult(triggered=False)


# 책 전체 규칙
ALL_RULES = [
    rule_abcd,
    rule_bull_flag,
    rule_vwap_reversal,
    rule_opening_range_breakout,
    rule_red_to_green,
    rule_top_reversal,
    rule_support_resistance,
    rule_ma_trend,
]
