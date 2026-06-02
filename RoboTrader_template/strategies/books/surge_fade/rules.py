"""태쏘의 데이트레이딩 바이블 2 — 급등주 투매폭 매매법 (15분봉) 규칙.

카탈로그 "기법 A — 급등주 투매폭 매매법" 절을 코드화한다.

개념:
  직전 저점→고점으로 강하게 상승한 급등주가, 상승폭에 대응하는 "적정 투매폭(%)"
  만큼 고점 대비 눌릴 때, 지지 확인 후 매수 → 저점 대비 +7% 반등을 노린다.

시간프레임 = 혼합이나 본 코드화는 **15분봉 단일 트랙**으로 근사한다:
  - 상승폭/투매폭(원래 일봉 성격)은 BookBacktester 가 전달하는 종목별 **다일(multi-day)
    연속 15분봉** 윈도우 df.iloc[:i+1] 에서 rally_lookback 봉 구간의 저점→고점으로 측정한다.
  - MA20(원래 20일선) 게이트는 15분봉 다일연속 환산 ma_gate_window(기본 480봉 ≈ 20거래일×24봉)
    의 trailing 이평으로 근사한다 (no-lookahead 유지).
  - 진입/지지확인/청산 타이밍은 15분봉.

각 함수/클래스는 Rule 인스턴스. evaluate(df, ctx) 에서 t 시점(df 마지막 행)만 평가하며
t+1 이후 데이터에 접근하지 않는다 (no-lookahead).

datetime 컬럼: pandas Timestamp (timezone-naive, KST).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

from strategies.books._base_book_strategy import Rule, RuleResult


# ---------------------------------------------------------------------------
# 투매폭 매트릭스 (상승폭 → 고점대비 적정 하락폭 (min, max))
# ---------------------------------------------------------------------------

# (rally_min_inclusive, (fade_min, fade_max)) — rally 가 큰 버킷부터 내림차순 평가.
_FADE_MATRIX: List[Tuple[float, Tuple[float, float]]] = [
    (1.01, (0.26, 0.34)),   # 101%+
    (0.91, (0.25, 0.28)),   # 91~100%
    (0.81, (0.24, 0.27)),   # 81~90%
    (0.71, (0.21, 0.24)),   # 71~80%
    (0.61, (0.20, 0.25)),   # 61~70%
    (0.51, (0.18, 0.24)),   # 51~60%
    (0.41, (0.15, 0.21)),   # 41~50%
    (0.31, (0.14, 0.18)),   # 31~40%
    (0.20, (0.10, 0.15)),   # 20~30%
]

# 매트릭스 최소 상승폭 (이 미만이면 급등주 자격 미달).
MIN_RALLY = 0.20


def fade_band_for_rally(rally: float) -> Optional[Tuple[float, float]]:
    """상승폭(저점→고점, 예 0.50=+50%) → 고점대비 적정 투매폭 (min, max).

    매트릭스 버킷에 매핑. 20% 미만 상승은 자격 미달로 None.
    101% 이상은 최상위 버킷(0.26~0.34)으로 캡.
    """
    if rally is None or rally < MIN_RALLY:
        return None
    for lower, band in _FADE_MATRIX:
        if rally >= lower:
            return band
    return None


# ---------------------------------------------------------------------------
# 공통 헬퍼
# ---------------------------------------------------------------------------

def _rsi(close: pd.Series, n: int) -> Optional[float]:
    """마지막 봉 기준 Wilder RSI(n). 데이터 부족 시 None."""
    if len(close) < n + 1:
        return None
    delta = close.diff()
    gain = delta.clip(lower=0.0)
    loss = (-delta).clip(lower=0.0)
    avg_gain = gain.ewm(alpha=1.0 / n, adjust=False, min_periods=n).mean()
    avg_loss = loss.ewm(alpha=1.0 / n, adjust=False, min_periods=n).mean()
    ag = float(avg_gain.iloc[-1])
    al = float(avg_loss.iloc[-1])
    if not np.isfinite(ag) or not np.isfinite(al):
        return None
    if al <= 0:
        return 100.0
    rs = ag / al
    return float(100.0 - 100.0 / (1.0 + rs))


# ---------------------------------------------------------------------------
# 기법 A — 급등주 투매폭 매매법 ★시그니처★
# ---------------------------------------------------------------------------

@dataclass
class rule_surge_fade(Rule):
    """급등주 고점대비 적정 투매폭 눌림 + 지지확인 매수.

    진입 (모두 충족):
      1. rally_lookback 구간에서 저점→고점 상승폭(rally)이 매트릭스 버킷에 매핑
         (rally >= MIN_RALLY).
      2. 현재 고점대비 하락폭(fade)이 해당 버킷 [fade_min, fade_max] 범위 안.
      3. fade <= max_fade (고점대비 30% 초과 하락은 추세이탈로 제외).
      4. MA20 게이트: 종가가 ma_gate_window trailing 이평 위 (이탈 시 매매 금지).
      5. 지지확인 (택1 이상):
           a. RSI(rsi_n) 가 과매도(rsi_oversold) 탈출 (직전봉 <= oversold < 현재봉)
           b. 거래량 급감 (마지막 봉 vol <= 구간 최대 vol * vol_dryup_ratio)
           c. 마지막 봉 양봉 + 종가가 확인저점 +support_buffer 이내 (확인 저점 반등)

    청산은 BookBacktester sl/tp (저점대비 +7% 익절 = tp≈0.07, 지지저점 이탈 = sl).
    """
    name: str = "surge_fade"
    rsi_n: int = 14
    rsi_oversold: float = 30.0
    vol_dryup_ratio: float = 0.25       # 구간 최대거래량 × 1/4 이하 = 급감
    support_buffer: float = 0.03        # 확인 저점 +1~3% 진입 영역
    max_fade: float = 0.30              # 고점대비 30% 초과 하락 제외
    rally_lookback: int = 64            # 저점→고점 측정 구간 (15분봉 ≈ 2~3거래일)
    ma_gate_window: int = 480           # MA20(20일선) 15분봉 환산 (≈20거래일×24봉)
    min_bars: int = 30                  # 평가에 필요한 최소 봉 수

    def evaluate(self, df: pd.DataFrame, ctx: Dict[str, Any]) -> RuleResult:
        need = max(self.rally_lookback, self.rsi_n) + 2
        if len(df) < max(need, self.min_bars):
            return RuleResult(triggered=False)

        close = df["close"].astype(float)
        high = df["high"].astype(float)
        low = df["low"].astype(float)
        vol = df["volume"].astype(float)

        last_close = float(close.iloc[-1])
        last_open = float(df["open"].iloc[-1])
        last_low = float(low.iloc[-1])

        # 1. 상승폭(rally): rally_lookback 구간의 저점 → 그 저점 이후 고점.
        seg_low_s = low.iloc[-self.rally_lookback:]
        seg_high_s = high.iloc[-self.rally_lookback:]
        rally_low = float(seg_low_s.min())
        low_pos = int(seg_low_s.values.argmin())
        # 저점 이후 구간에서의 고점 (상승폭의 고점은 저점 뒤에 있어야 함)
        after_low_high = seg_high_s.iloc[low_pos:]
        if len(after_low_high) < 2:
            return RuleResult(triggered=False)
        rally_high = float(after_low_high.max())
        if rally_low <= 0 or rally_high <= rally_low:
            return RuleResult(triggered=False)
        rally = (rally_high - rally_low) / rally_low

        band = fade_band_for_rally(rally)
        if band is None:
            return RuleResult(triggered=False)
        fade_min, fade_max = band

        # 2~3. 현재 고점대비 하락폭(fade)
        fade = (rally_high - last_close) / rally_high
        if fade > self.max_fade:
            return RuleResult(triggered=False)
        if not (fade_min <= fade <= fade_max):
            return RuleResult(triggered=False)

        # 4. MA20 게이트 (15분봉 환산 trailing 이평)
        if len(close) >= self.ma_gate_window:
            ma_gate = float(close.rolling(self.ma_gate_window).mean().iloc[-1])
            if np.isfinite(ma_gate) and ma_gate > 0 and last_close < ma_gate:
                return RuleResult(triggered=False)

        # 5. 지지확인 (택1 이상)
        # a. RSI 과매도 탈출
        rsi_now = _rsi(close, self.rsi_n)
        rsi_prev = _rsi(close.iloc[:-1], self.rsi_n)
        rsi_recover = (
            rsi_now is not None and rsi_prev is not None
            and rsi_prev <= self.rsi_oversold < rsi_now
        )
        # b. 거래량 급감
        seg_vol = vol.iloc[-self.rally_lookback:]
        max_vol = float(seg_vol.max())
        last_vol = float(vol.iloc[-1])
        vol_dryup = max_vol > 0 and last_vol <= max_vol * self.vol_dryup_ratio
        # c. 확인 저점 반등 (양봉 + 종가가 직전 확인저점 +buffer 이내)
        recent_low = float(low.iloc[-self.rsi_n:].min())
        bullish = last_close > last_open
        near_support = (
            recent_low > 0
            and last_close <= recent_low * (1.0 + self.support_buffer)
            and last_low <= recent_low * (1.0 + self.support_buffer)
        )
        support_rebound = bullish and near_support

        if not (rsi_recover or vol_dryup or support_rebound):
            return RuleResult(triggered=False)

        confirmations = []
        if rsi_recover:
            confirmations.append("rsi")
        if vol_dryup:
            confirmations.append("vol_dryup")
        if support_rebound:
            confirmations.append("support")

        return RuleResult(
            triggered=True, side="buy", confidence=70.0,
            reasons=[
                f"surge_fade rally={rally:.2%} fade={fade:.2%} "
                f"band=({fade_min:.0%}~{fade_max:.0%}) confirm={'+'.join(confirmations)}"
            ],
            metadata={
                "rally": rally,
                "fade": fade,
                "rally_high": rally_high,
                "rally_low": rally_low,
                "confirmations": confirmations,
            },
        )


# 책 기법 A 단일 룰 (기법 B 종가배팅은 일봉 트랙 별도).
ALL_RULES = [
    rule_surge_fade,
]
