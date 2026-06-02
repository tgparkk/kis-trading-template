"""Elder Triple Screen — Rule 집합.

규칙들 (롱 전용, 일봉 해상도):
- rule_triple_screen_force_index : 정통 Triple Screen (MACD-Hist 상승 + Force Index<0)
- rule_triple_screen_stochastic  : EMA65 상승 + 일봉 Stochastic 과매도 상향전환
- rule_triple_screen_elder_ray   : Impulse 비적색 + Elder-Ray Bear Power 상승 + EMA13 상승
- rule_triple_screen_ema_pullback: 단순화 EMA13 눌림 반등 (표본 최대·견고성 베이스라인)

헬퍼:
- ema / macd_hist / force_index / bull_power / bear_power / stochastic / impulse_color
- krx_tick : KRX 호가단위 (2023 개정)
- screen1_uptrend : Screen 1 추세 proxy (일봉 65일 EMA 기울기 > 0)
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Tuple

import numpy as np
import pandas as pd

from strategies.books._base_book_strategy import Rule, RuleResult


# --------------------------------------------------------------------------- #
# 지표 헬퍼 (모두 ewm(span=N, adjust=False) — Elder/차팅 일치)
# --------------------------------------------------------------------------- #
def ema(series: pd.Series, n: int) -> pd.Series:
    """지수이동평균 (adjust=False)."""
    return series.ewm(span=n, adjust=False).mean()


def macd_hist(close: pd.Series, fast: int = 12, slow: int = 26, signal: int = 9) -> pd.Series:
    """MACD 히스토그램 = (EMA_fast - EMA_slow) - EMA(그 차이, signal)."""
    macd_line = ema(close, fast) - ema(close, slow)
    signal_line = ema(macd_line, signal)
    return macd_line - signal_line


def force_index(close: pd.Series, volume: pd.Series, n: int) -> pd.Series:
    """Force Index = EMA((close - close.shift(1)) * volume, n)."""
    raw = (close - close.shift(1)) * volume
    return ema(raw, n)


def bull_power(high: pd.Series, close: pd.Series, n: int = 13) -> pd.Series:
    """Elder-Ray Bull Power = high - EMA(close, n)."""
    return high - ema(close, n)


def bear_power(low: pd.Series, close: pd.Series, n: int = 13) -> pd.Series:
    """Elder-Ray Bear Power = low - EMA(close, n)."""
    return low - ema(close, n)


def stochastic(
    high: pd.Series, low: pd.Series, close: pd.Series, n: int = 14, k: int = 3, d: int = 3
) -> Tuple[pd.Series, pd.Series]:
    """Stochastic (%K, %D). hh==ll 0除 가드: (hh-ll)==0 → NaN."""
    ll = low.rolling(n).min()
    hh = high.rolling(n).max()
    denom = (hh - ll).replace(0, np.nan)
    k_raw = 100 * (close - ll) / denom
    pct_k = k_raw.rolling(k).mean()
    pct_d = pct_k.rolling(d).mean()
    return pct_k, pct_d


def impulse_color(
    close: pd.Series, ema_n: int = 13, fast: int = 12, slow: int = 26, signal: int = 9
) -> pd.Series:
    """Impulse System 색상 시리즈 ('green'/'red'/'blue').

    green = EMA13 상승 AND Hist 상승, red = EMA13 하락 AND Hist 하락, 그 외 blue.
    """
    ema13 = ema(close, ema_n)
    hist = macd_hist(close, fast, slow, signal)
    ema_up = ema13 > ema13.shift(1)
    hist_up = hist > hist.shift(1)
    green = ema_up & hist_up
    red = (~ema_up) & (~hist_up)
    colors = pd.Series("blue", index=close.index, dtype=object)
    colors[green] = "green"
    colors[red] = "red"
    return colors


def krx_tick(price: float) -> int:
    """KRX 호가단위 (2023 개정)."""
    if price < 2_000:
        return 1
    if price < 5_000:
        return 5
    if price < 20_000:
        return 10
    if price < 50_000:
        return 50
    if price < 200_000:
        return 100
    if price < 500_000:
        return 500
    return 1_000


def screen1_uptrend(close: pd.Series) -> bool:
    """Screen 1 추세 proxy: 일봉 65일 EMA 기울기 > 0 (5일=1주 전 대비)."""
    ema65 = ema(close, 65)
    if len(ema65) < 6:
        return False  # 워밍업 부족 → 추세 미확인 = False (legacy 동작과 동일)
    return bool(ema65.iloc[-1] > ema65.iloc[-6])


# --------------------------------------------------------------------------- #
# 진입 룰 4종 (롱 전용, side="buy", no-lookahead: iloc[-1]==t)
# --------------------------------------------------------------------------- #
@dataclass
class rule_triple_screen_force_index(Rule):
    """Setup A — 정통 Triple Screen.

    1. screen1_uptrend (ema65 상승)
    2. 일봉 MACD-Hist(12,26,9) 상승 (hist[-1] > hist[-2])
    3. 일봉 Force Index(2일 EMA) < 0
    """
    name: str = "triple_screen_force_index"

    def evaluate(self, df: pd.DataFrame, ctx: Dict[str, Any]) -> RuleResult:
        if len(df) < 70:
            return RuleResult(triggered=False)
        close = df["close"].astype(float)
        volume = df["volume"].astype(float)

        if not screen1_uptrend(close):
            return RuleResult(triggered=False)

        hist = macd_hist(close)
        hist_up = float(hist.iloc[-1]) > float(hist.iloc[-2])

        fi2 = force_index(close, volume, 2)
        fi_neg = float(fi2.iloc[-1]) < 0

        if hist_up and fi_neg:
            return RuleResult(
                triggered=True, side="buy", confidence=72.0,
                reasons=[
                    f"triple_screen_force_index hist={float(hist.iloc[-1]):.2f}>{float(hist.iloc[-2]):.2f} "
                    f"fi2={float(fi2.iloc[-1]):.0f}<0"
                ],
                metadata={"hist": float(hist.iloc[-1]), "fi2": float(fi2.iloc[-1])},
            )
        return RuleResult(triggered=False)


@dataclass
class rule_triple_screen_stochastic(Rule):
    """Setup B — EMA65 상승 + 일봉 Stochastic 과매도 상향전환.

    1. screen1_uptrend
    2. Stochastic(14,3,3) %K < 30 AND %K[-1] > %D[-1]
    """
    name: str = "triple_screen_stochastic"
    k_threshold: float = 30.0

    def evaluate(self, df: pd.DataFrame, ctx: Dict[str, Any]) -> RuleResult:
        if len(df) < 70:
            return RuleResult(triggered=False)
        close = df["close"].astype(float)
        high = df["high"].astype(float)
        low = df["low"].astype(float)

        if not screen1_uptrend(close):
            return RuleResult(triggered=False)

        pct_k, pct_d = stochastic(high, low, close, 14, 3, 3)
        last_k = pct_k.iloc[-1]
        last_d = pct_d.iloc[-1]
        if pd.isna(last_k) or pd.isna(last_d):
            return RuleResult(triggered=False)
        oversold = float(last_k) < self.k_threshold
        turning_up = float(last_k) > float(last_d)

        if oversold and turning_up:
            return RuleResult(
                triggered=True, side="buy", confidence=68.0,
                reasons=[f"triple_screen_stochastic %K={float(last_k):.1f}<{self.k_threshold:.0f} >%D={float(last_d):.1f}"],
                metadata={"pct_k": float(last_k), "pct_d": float(last_d)},
            )
        return RuleResult(triggered=False)


@dataclass
class rule_triple_screen_elder_ray(Rule):
    """Setup C — Impulse 비적색 + Elder-Ray Bear Power 상승 + EMA13 상승.

    1. screen1_uptrend
    2. Impulse NOT red
    3. Bear Power < 0 AND Bear Power[-1] > Bear Power[-2]
    4. ema13[-1] > ema13[-2]
    """
    name: str = "triple_screen_elder_ray"

    def evaluate(self, df: pd.DataFrame, ctx: Dict[str, Any]) -> RuleResult:
        if len(df) < 70:
            return RuleResult(triggered=False)
        close = df["close"].astype(float)
        low = df["low"].astype(float)

        if not screen1_uptrend(close):
            return RuleResult(triggered=False)

        colors = impulse_color(close)
        not_red = str(colors.iloc[-1]) != "red"

        bp = bear_power(low, close, 13)
        bp_neg = float(bp.iloc[-1]) < 0
        bp_rising = float(bp.iloc[-1]) > float(bp.iloc[-2])

        ema13 = ema(close, 13)
        ema13_up = float(ema13.iloc[-1]) > float(ema13.iloc[-2])

        if not_red and bp_neg and bp_rising and ema13_up:
            return RuleResult(
                triggered=True, side="buy", confidence=66.0,
                reasons=[
                    f"triple_screen_elder_ray impulse={str(colors.iloc[-1])} "
                    f"bear={float(bp.iloc[-1]):.0f}(rising) ema13_up"
                ],
                metadata={"bear_power": float(bp.iloc[-1]), "impulse": str(colors.iloc[-1])},
            )
        return RuleResult(triggered=False)


@dataclass
class rule_triple_screen_ema_pullback(Rule):
    """Setup D — 단순화 EMA13 눌림 반등 (표본 최대·견고성 베이스라인).

    1. screen1_uptrend
    2. low[-1] <= ema13[-1]*1.01 AND close[-1] > ema13[-1]
    """
    name: str = "triple_screen_ema_pullback"
    touch_band: float = 1.01

    def evaluate(self, df: pd.DataFrame, ctx: Dict[str, Any]) -> RuleResult:
        if len(df) < 70:
            return RuleResult(triggered=False)
        close = df["close"].astype(float)
        low = df["low"].astype(float)

        if not screen1_uptrend(close):
            return RuleResult(triggered=False)

        ema13 = ema(close, 13)
        last_ema13 = float(ema13.iloc[-1])
        last_low = float(low.iloc[-1])
        last_close = float(close.iloc[-1])

        touched = last_low <= last_ema13 * self.touch_band
        recovered = last_close > last_ema13

        if touched and recovered:
            return RuleResult(
                triggered=True, side="buy", confidence=60.0,
                reasons=[
                    f"triple_screen_ema_pullback low={last_low:.0f}<=ema13*{self.touch_band:.2f} "
                    f"close={last_close:.0f}>ema13={last_ema13:.0f}"
                ],
                metadata={"ema13": last_ema13, "close": last_close},
            )
        return RuleResult(triggered=False)


ALL_RULES = [
    rule_triple_screen_force_index,
    rule_triple_screen_stochastic,
    rule_triple_screen_elder_ray,
    rule_triple_screen_ema_pullback,
]
