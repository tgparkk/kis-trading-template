"""Linda Raschke - Street Smarts: 5개 분봉 매매 규칙.

Phase 1 — 분봉 백테스터로 코드화 가능한 셋업:
- rule_holy_grail (Raschke 본인 추천, 여전히 유효)
- rule_anti (스토캐스틱 훅)
- rule_gimmee_bar (볼린저밴드 횡보)
- rule_nr4_breakout (변동성 압축 후 돌파)
- rule_momentum_pinball (LBR/RSI + 첫 1시간봉 돌파)

일봉 전용 셋업 (Turtle Soup, 80-20, ADX Gapper, 2-Period ROC, Turtle Soup +1) 은 Phase 2에서.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict

import numpy as np
import pandas as pd

from strategies.books._base_book_strategy import Rule, RuleResult


def _ema(series: pd.Series, span: int) -> pd.Series:
    return series.ewm(span=span, adjust=False).mean()


def _rsi(series: pd.Series, period: int) -> pd.Series:
    delta = series.diff()
    up = delta.clip(lower=0)
    down = -delta.clip(upper=0)
    ru = up.rolling(period).mean()
    rd = down.rolling(period).mean()
    rs = ru / rd.replace(0, np.nan)
    return (100 - 100 / (1 + rs)).fillna(50.0)


def _adx(df: pd.DataFrame, period: int = 14) -> pd.Series:
    """단순화된 ADX (Wilder's smoothing 근사)."""
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
    atr = tr.rolling(period).mean().replace(0, np.nan)
    plus_di = 100 * plus_dm.rolling(period).mean() / atr
    minus_di = 100 * minus_dm.rolling(period).mean() / atr
    dx = (plus_di - minus_di).abs() / (plus_di + minus_di).replace(0, np.nan) * 100
    return dx.rolling(period).mean().fillna(0.0)


def _stochastic(df: pd.DataFrame, k_period: int, d_period: int) -> tuple:
    high_n = df["high"].rolling(k_period).max()
    low_n = df["low"].rolling(k_period).min()
    k = 100 * (df["close"] - low_n) / (high_n - low_n).replace(0, np.nan)
    k = k.fillna(50.0)
    d = k.rolling(d_period).mean()
    return k, d


# ---------------------------------------------------------------------------
# 1. Holy Grail
# ---------------------------------------------------------------------------

@dataclass
class rule_holy_grail(Rule):
    """ADX(14) > 30 + 상승 추세 + 20EMA 첫 풀백 + 풀백봉 고가 돌파.

    Raschke 본인 추천 — 2010년대 이후에도 유효성 유지된다고 언급.
    """
    name: str = "holy_grail"
    adx_period: int = 14
    adx_threshold: float = 30.0
    ema_period: int = 20
    touch_tol: float = 0.005

    def evaluate(self, df: pd.DataFrame, ctx: Dict[str, Any]) -> RuleResult:
        if len(df) < max(self.adx_period * 2, self.ema_period) + 2:
            return RuleResult(triggered=False)
        adx = _adx(df, self.adx_period)
        last_adx = float(adx.iloc[-1])
        prev_adx = float(adx.iloc[-2])
        if last_adx < self.adx_threshold or last_adx < prev_adx:
            return RuleResult(triggered=False)

        ema = _ema(df["close"], self.ema_period)
        last_ema = float(ema.iloc[-1])
        last_close = float(df["close"].iloc[-1])
        prev_high = float(df["high"].iloc[-2])

        # EMA 위 + 추세 상승 가정
        if last_close <= last_ema:
            return RuleResult(triggered=False)
        # 풀백 확인: 직전 봉 저점이 EMA 근처
        prev_low = float(df["low"].iloc[-2])
        touched_ema = abs(prev_low - last_ema) / max(last_ema, 1e-9) <= self.touch_tol
        breakout = last_close > prev_high

        if touched_ema and breakout:
            return RuleResult(
                triggered=True, side="buy", confidence=72.0,
                reasons=[f"holy_grail adx={last_adx:.1f} ema={last_ema:.2f} brk={last_close:.2f}>prev_high={prev_high:.2f}"],
            )
        return RuleResult(triggered=False)


# ---------------------------------------------------------------------------
# 2. Anti (Stochastic Hook)
# ---------------------------------------------------------------------------

@dataclass
class rule_anti(Rule):
    """%K(7)/%D(10) 스토캐스틱 훅 + 20EMA 추세 필터 + 임펄스 후."""
    name: str = "anti"
    k_period: int = 7
    d_period: int = 10
    ema_period: int = 20
    impulse_pct: float = 0.005

    def evaluate(self, df: pd.DataFrame, ctx: Dict[str, Any]) -> RuleResult:
        if len(df) < max(self.k_period + self.d_period, self.ema_period) + 5:
            return RuleResult(triggered=False)
        k, d = _stochastic(df, self.k_period, self.d_period)
        ema = _ema(df["close"], self.ema_period)
        last_close = float(df["close"].iloc[-1])
        last_ema = float(ema.iloc[-1])
        # 추세 필터: EMA 위 → 롱만
        if last_close <= last_ema:
            return RuleResult(triggered=False)
        # 임펄스 무브: 직전 5봉에서 +0.5% 이상 변동
        last5_chg = (last_close - float(df["close"].iloc[-6])) / float(df["close"].iloc[-6])
        if abs(last5_chg) < self.impulse_pct:
            return RuleResult(triggered=False)
        # %D 상승 추세 + %K 훅업 (직전 %K < 직전2 %K, 현재 %K > 직전 %K)
        d_rising = d.iloc[-1] > d.iloc[-3]
        k_hook = (k.iloc[-2] < k.iloc[-3]) and (k.iloc[-1] > k.iloc[-2])
        if d_rising and k_hook:
            return RuleResult(
                triggered=True, side="buy", confidence=66.0,
                reasons=[f"anti k_hook d_rising last_close={last_close:.2f} ema={last_ema:.2f}"],
            )
        return RuleResult(triggered=False)


# ---------------------------------------------------------------------------
# 3. Gimmee Bar (Bollinger Band Reversal)
# ---------------------------------------------------------------------------

@dataclass
class rule_gimmee_bar(Rule):
    """볼린저밴드 횡보 + 밴드 하단 터치 + 반전 양봉."""
    name: str = "gimmee_bar"
    bb_period: int = 20
    bb_stdev: float = 2.0
    band_slope_tol: float = 0.001

    def evaluate(self, df: pd.DataFrame, ctx: Dict[str, Any]) -> RuleResult:
        if len(df) < self.bb_period + 3:
            return RuleResult(triggered=False)
        ma = df["close"].rolling(self.bb_period).mean()
        std = df["close"].rolling(self.bb_period).std()
        lower = ma - self.bb_stdev * std
        upper = ma + self.bb_stdev * std  # noqa: F841
        # 횡보장 확인: ma 기울기 작음
        ma_slope = abs(ma.iloc[-1] - ma.iloc[-self.bb_period]) / max(ma.iloc[-1], 1e-9)
        if ma_slope > self.band_slope_tol:
            return RuleResult(triggered=False)
        # 직전 봉 또는 현재 봉이 밴드 하단 터치
        last_low = float(df["low"].iloc[-1])
        last_lower = float(lower.iloc[-1])
        prev_low = float(df["low"].iloc[-2])
        prev_lower = float(lower.iloc[-2])
        touched = (last_low <= last_lower * 1.001) or (prev_low <= prev_lower * 1.001)
        # 현재 봉이 양봉 + 시가보다 고점 위 + 종가 시가 위
        last_open = float(df["open"].iloc[-1])
        last_close = float(df["close"].iloc[-1])
        last_high = float(df["high"].iloc[-1])  # noqa: F841
        bullish = (last_close > last_open) and (last_high > last_open)
        # MA 위 아닌지 확인 (중심선 겹치면 무효)
        last_ma = float(ma.iloc[-1])
        not_at_center = last_close < last_ma
        if touched and bullish and not_at_center:
            return RuleResult(
                triggered=True, side="buy", confidence=64.0,
                reasons=[f"gimmee_bar lower={last_lower:.2f} close={last_close:.2f} ma_slope={ma_slope:.4f}"],
            )
        return RuleResult(triggered=False)


# ---------------------------------------------------------------------------
# 4. NR4 Breakout (분봉 변형)
# ---------------------------------------------------------------------------

@dataclass
class rule_nr4_breakout(Rule):
    """직전 30분 중 NR4 (4봉 중 최소 범위) + 다음 봉이 NR4 봉 고점 돌파.

    원서 일봉 NR4를 분봉 30분 단위로 변형.
    """
    name: str = "nr4_breakout"
    window: int = 30
    nr4_lookback: int = 4

    def evaluate(self, df: pd.DataFrame, ctx: Dict[str, Any]) -> RuleResult:
        if len(df) < self.window + 1:
            return RuleResult(triggered=False)
        # 직전 nr4_lookback 봉의 range
        ranges = (df["high"] - df["low"]).iloc[-(self.nr4_lookback + 1):-1]
        if len(ranges) < self.nr4_lookback:
            return RuleResult(triggered=False)
        last_range_idx = ranges.idxmin()
        # 직전 봉이 NR4여야 함
        last_index = ranges.index[-1]
        if last_range_idx != last_index:
            return RuleResult(triggered=False)
        nr4_high = float(df["high"].loc[last_index])
        last_close = float(df["close"].iloc[-1])
        if last_close > nr4_high:
            return RuleResult(
                triggered=True, side="buy", confidence=62.0,
                reasons=[f"nr4_breakout nr4_high={nr4_high:.2f} brk={last_close:.2f}"],
            )
        return RuleResult(triggered=False)


# ---------------------------------------------------------------------------
# 5. Momentum Pinball (LBR/RSI + 첫 1시간봉 돌파)
# ---------------------------------------------------------------------------

@dataclass
class rule_momentum_pinball(Rule):
    """전일 RSI(3) of ROC(1) < 30 → 롱 시그널 + 첫 1시간봉(09:00~10:00 = 60봉) 고점 돌파 시 진입.

    분봉 백테스터 컨텍스트: 첫 60봉 = '전일 RSI 신호 + 첫 1시간봉' 대용.
    분봉 첫 60봉의 LBR/RSI < 30 + 후속 봉이 첫 60봉 고점 돌파.
    """
    name: str = "momentum_pinball"
    first_hour_bars: int = 60
    roc_period: int = 1
    rsi_period: int = 3
    rsi_oversold: float = 30.0

    def evaluate(self, df: pd.DataFrame, ctx: Dict[str, Any]) -> RuleResult:
        if len(df) < self.first_hour_bars + 1:
            return RuleResult(triggered=False)
        first_hour = df.iloc[: self.first_hour_bars]
        # LBR/RSI: RSI(3) of ROC(1)
        roc = first_hour["close"].pct_change(self.roc_period)
        lbr_rsi = _rsi(roc, self.rsi_period)
        last_lbr = float(lbr_rsi.iloc[-1])
        if last_lbr >= self.rsi_oversold:
            return RuleResult(triggered=False)
        first_hour_high = float(first_hour["high"].max())
        last_close = float(df["close"].iloc[-1])
        if last_close > first_hour_high:
            return RuleResult(
                triggered=True, side="buy", confidence=60.0,
                reasons=[f"momentum_pinball lbr_rsi={last_lbr:.1f}<{self.rsi_oversold} brk={last_close:.2f}>1h_high={first_hour_high:.2f}"],
            )
        return RuleResult(triggered=False)


ALL_RULES = [
    rule_holy_grail,
    rule_anti,
    rule_gimmee_bar,
    rule_nr4_breakout,
    rule_momentum_pinball,
]
