"""『트레이딩의 전설』(키움영웅전 9인 트레이더) — 일봉(daily) 매매 규칙.

신정재·청사진·뭐라도되겠지·불개미·캐리·방배동선수 등 키움영웅전 상위 입상 트레이더들의
공개 기법 중 **일봉 단위로 정량화 가능한 6종**을 코드화. haru_silijeon/rules_daily.py 와
동일한 Rule 인터페이스(evaluate(df, ctx)->RuleResult, no-lookahead).

입력 df는 일봉 OHLCV 시계열이며, run_trading_legends_daily.py 가 종목별 daily_prices 의
df.iloc[:i+1] 윈도우를 그대로 전달한다. 따라서 5/20/40/60일 이동평균/신고가/거래량은
df["close"].rolling(N) 등으로 trailing 계산되어 no-lookahead 가 유지된다.

datetime 컬럼: pandas Timestamp (일 단위). 컬럼: datetime, open, high, low, close, volume.

──────────────────────────────────────────────────────────────────────────
정량화 기준 (캡처 판독 기법 → 합리적 임계값, 불명확 항목은 기본값 + 주석):

- "등락률" = close / prev_close - 1 (전일 종가 대비). 거래대금=close*volume (별도 컬럼 없음).
- "신고가" = 종가가 직전 N봉(마지막 봉 제외) 고가 최대값 이상.
- "상한가권" = 등락률 +25% 이상(한국 일일 가격제한폭 ±30% 근사; 상따 트레이더 진입 영역).
- "거래량 급증" = 마지막 봉 거래량 >= 직전 N일 평균 × 배수.
- "5일선 터치" = 저가가 5일선 ±touch_tol(±2%) 안.
- "양봉" = close > open.
──────────────────────────────────────────────────────────────────────────
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Optional

import pandas as pd

from strategies.books._base_book_strategy import Rule, RuleResult


# ---------------------------------------------------------------------------
# 공통 헬퍼 (haru_silijeon/rules_daily.py 와 동일 시그니처)
# ---------------------------------------------------------------------------

def _ma(df: pd.DataFrame, window: int) -> Optional[float]:
    """trailing N일 단순이동평균(종가)의 마지막 값. NaN/비양수면 None."""
    if len(df) < window:
        return None
    val = df["close"].rolling(window).mean().iloc[-1]
    if pd.isna(val) or val <= 0:
        return None
    return float(val)


def _recent_surge(df: pd.DataFrame, lookback: int, surge_pct: float) -> bool:
    """직전 lookback 봉(마지막 봉 제외) 내 저점 대비 고점이 +surge_pct 이상 → 급등 이력."""
    if len(df) < lookback + 2:
        return False
    seg = df.iloc[-(lookback + 1):-1]
    seg_low = float(seg["low"].min())
    seg_high = float(seg["high"].max())
    if seg_low <= 0:
        return False
    return (seg_high - seg_low) / seg_low >= surge_pct


def _is_bullish(bar) -> bool:
    return float(bar["close"]) > float(bar["open"])


def _touch_ma(low: float, ma: float, tol: float) -> bool:
    """저가가 이평선 ±tol 안에서 터치(지지)했는지."""
    if ma <= 0:
        return False
    return abs(low - ma) / ma <= tol


def _change_pct(df: pd.DataFrame) -> Optional[float]:
    """마지막 봉 등락률 = close / prev_close - 1. 데이터 부족/비양수면 None."""
    if len(df) < 2:
        return None
    prev_close = float(df["close"].iloc[-2])
    if prev_close <= 0:
        return None
    return float(df["close"].iloc[-1]) / prev_close - 1.0


# ---------------------------------------------------------------------------
# 1. 종가매매 모멘텀 돌파 (신정재 + 청사진) — 오버나이트 의도
# ---------------------------------------------------------------------------

@dataclass
class rule_close_momentum_breakout(Rule):
    """당일 강한 상승 + 20일 신고가 갱신 양봉 → 종가 매수(익일 시가 청산 의도).

    진입:
      1. 당일 등락률 >= +up_pct(+5%) (강한 상승)
      2. 종가가 최근 high_window(20)일 신고가 갱신 (직전 20봉 고가 최대값 이상)
      3. 양봉 (close > open)
    오버나이트 의도 → run 스크립트 variant O(mh=1) 권장.
    """
    name: str = "close_momentum_breakout"
    up_pct: float = 0.05
    high_window: int = 20

    def evaluate(self, df: pd.DataFrame, ctx: Dict[str, Any]) -> RuleResult:
        if len(df) < self.high_window + 2:
            return RuleResult(triggered=False)

        chg = _change_pct(df)
        if chg is None:
            return RuleResult(triggered=False)

        last = df.iloc[-1]
        last_close = float(last["close"])
        prior_high = float(df["high"].iloc[-(self.high_window + 1):-1].max())

        strong_up = chg >= self.up_pct
        new_high = last_close >= prior_high
        bullish = _is_bullish(last)

        if strong_up and new_high and bullish:
            return RuleResult(
                triggered=True, side="buy", confidence=70.0,
                reasons=[f"close_momentum chg={chg:.2%} close={last_close:.2f} prior20_high={prior_high:.2f}"],
                metadata={"change_pct": chg, "prior_high": prior_high},
            )
        return RuleResult(triggered=False)


# ---------------------------------------------------------------------------
# 2. 상한가 따라잡기 (뭐라도되겠지) — 짧은 보유·타이트 손절(-3%)
# ---------------------------------------------------------------------------

@dataclass
class rule_limit_up_follow(Rule):
    """상한가권(+25%↑) 강한 양봉 + 시가 대비 종가 상승 → 상따 진입.

    진입:
      1. 당일 등락률 >= +limit_pct(+25%) (상한가권)
      2. 양봉 (close > open) — 과도 갭상승 후 음전 배제
      3. 시가 대비 종가 상승 (close > open, 위와 동치이나 명시적 확인)
    run 스크립트 RULE_SL_OVERRIDE 로 -3% 타이트 손절.
    """
    name: str = "limit_up_follow"
    limit_pct: float = 0.25

    def evaluate(self, df: pd.DataFrame, ctx: Dict[str, Any]) -> RuleResult:
        if len(df) < 2:
            return RuleResult(triggered=False)

        chg = _change_pct(df)
        if chg is None:
            return RuleResult(triggered=False)

        last = df.iloc[-1]
        last_open = float(last["open"])
        last_close = float(last["close"])

        limit_up = chg >= self.limit_pct
        bullish = _is_bullish(last)
        close_above_open = last_close > last_open

        if limit_up and bullish and close_above_open:
            return RuleResult(
                triggered=True, side="buy", confidence=72.0,
                reasons=[f"limit_up_follow chg={chg:.2%} open={last_open:.2f} close={last_close:.2f}"],
                metadata={"change_pct": chg},
            )
        return RuleResult(triggered=False)


# ---------------------------------------------------------------------------
# 3. 전고점 돌파 + 거래량 급증 (불개미 + 캐리) — 추세 보유
# ---------------------------------------------------------------------------

@dataclass
class rule_new_high_breakout(Rule):
    """종가가 60일 신고가 갱신 + 거래량 직전 20일 평균 × 2.0 이상 → 추세 진입.

    진입:
      1. 종가가 최근 high_window(60)일 신고가 (직전 60봉 고가 최대값 이상)
      2. 당일 거래량 >= 직전 vol_lookback(20)일 평균 × vol_mult(2.0)
    추세 보유 의도 → run 스크립트 trail_ma=20.
    """
    name: str = "new_high_breakout"
    high_window: int = 60
    vol_lookback: int = 20
    vol_mult: float = 2.0

    def evaluate(self, df: pd.DataFrame, ctx: Dict[str, Any]) -> RuleResult:
        if len(df) < self.high_window + 2:
            return RuleResult(triggered=False)

        last = df.iloc[-1]
        last_close = float(last["close"])
        prior_high = float(df["high"].iloc[-(self.high_window + 1):-1].max())
        last_vol = float(last["volume"])
        avg_vol = float(df["volume"].iloc[-(self.vol_lookback + 1):-1].mean())

        new_high = last_close >= prior_high
        vol_surge = avg_vol > 0 and last_vol >= avg_vol * self.vol_mult

        if new_high and vol_surge:
            return RuleResult(
                triggered=True, side="buy", confidence=70.0,
                reasons=[f"new_high60 close={last_close:.2f} prior60_high={prior_high:.2f} "
                         f"vol={last_vol:.0f}/{avg_vol:.0f}"],
                metadata={"prior_high": prior_high, "vol_ratio": last_vol / avg_vol if avg_vol > 0 else 0.0},
            )
        return RuleResult(triggered=False)


# ---------------------------------------------------------------------------
# 4. 전날 상한가 익일 눌림 반등 (캐리)
# ---------------------------------------------------------------------------

@dataclass
class rule_prev_limitup_pullback(Rule):
    """전일 상한가권(+25%↑) → 당일 전일 종가 이하로 눌렸다가 양봉 반등 진입.

    진입:
      1. 전일 등락률 >= +limit_pct(+25%) (전날 상한가권)
      2. 당일 저가 <= 전일 종가 (눌림 발생: low <= prev_close × 1.0)
      3. 당일 양봉 (close > open) AND 종가 > 전일 종가 (반등 마감)
    run 스크립트 trail_ma=10.
    """
    name: str = "prev_limitup_pullback"
    limit_pct: float = 0.25

    def evaluate(self, df: pd.DataFrame, ctx: Dict[str, Any]) -> RuleResult:
        if len(df) < 3:
            return RuleResult(triggered=False)

        prev_close = float(df["close"].iloc[-2])
        prev_prev_close = float(df["close"].iloc[-3])
        if prev_close <= 0 or prev_prev_close <= 0:
            return RuleResult(triggered=False)
        prev_chg = prev_close / prev_prev_close - 1.0

        last = df.iloc[-1]
        last_low = float(last["low"])
        last_close = float(last["close"])

        prev_limit_up = prev_chg >= self.limit_pct
        pulled = last_low <= prev_close * 1.0
        rebound = _is_bullish(last) and last_close > prev_close

        if prev_limit_up and pulled and rebound:
            return RuleResult(
                triggered=True, side="buy", confidence=68.0,
                reasons=[f"prev_limitup_pull prev_chg={prev_chg:.2%} low={last_low:.2f} "
                         f"prev_close={prev_close:.2f} close={last_close:.2f}"],
                metadata={"prev_change_pct": prev_chg, "prev_close": prev_close},
            )
        return RuleResult(triggered=False)


# ---------------------------------------------------------------------------
# 5. 눌림목 (방배동선수 + 신정재) — 급등 후 5일선 지지 반등
# ---------------------------------------------------------------------------

@dataclass
class rule_ma5_pullback(Rule):
    """최근 20일 +20% 급등 후 5일선 터치 지지 양봉 → 눌림목 진입.

    진입:
      1. 최근 surge_lookback(20)일 내 +surge_pct(+20%) 급등 이력
      2. 당일 저가가 5일선 부근 터치 (±touch_tol ±2%)
      3. 종가가 5일선 위 (지지 유효: close >= ma5 × (1 - below_tol))
      4. 양봉 (close > open)
    run 스크립트 trail_ma=5.
    """
    name: str = "ma5_pullback"
    ma_window: int = 5
    surge_lookback: int = 20
    surge_pct: float = 0.20
    touch_tol: float = 0.02
    below_tol: float = 0.02

    def evaluate(self, df: pd.DataFrame, ctx: Dict[str, Any]) -> RuleResult:
        if len(df) < self.surge_lookback + 2:
            return RuleResult(triggered=False)
        ma5 = _ma(df, self.ma_window)
        if ma5 is None:
            return RuleResult(triggered=False)

        last = df.iloc[-1]
        last_close = float(last["close"])
        last_low = float(last["low"])

        surged = _recent_surge(df, self.surge_lookback, self.surge_pct)
        touched = _touch_ma(last_low, ma5, self.touch_tol)
        above = last_close >= ma5 * (1.0 - self.below_tol)
        bullish = _is_bullish(last)

        if surged and touched and above and bullish:
            return RuleResult(
                triggered=True, side="buy", confidence=68.0,
                reasons=[f"ma5_pullback ma5={ma5:.2f} low={last_low:.2f} close={last_close:.2f}"],
                metadata={"ma5": ma5},
            )
        return RuleResult(triggered=False)


# ---------------------------------------------------------------------------
# 6. 바닥권 첫 양봉 (불개미) — 하락 후 거래량 동반 반등
# ---------------------------------------------------------------------------

@dataclass
class rule_bottom_first_bull(Rule):
    """60일 저점 부근 하락추세 후 거래량 동반 첫 양봉 → 바닥 반등 진입.

    진입:
      1. 직전 봉(마지막 제외) 종가가 60일 저점 부근 (저점 대비 +near_tol(+5%) 이내 = 바닥권)
      2. 당일 첫 양봉 (close > open)
      3. 당일 거래량 >= 직전 vol_lookback(20)일 평균 × vol_mult(1.5)
    하락추세 후 첫 반등 양봉 포착. run 스크립트 trail_ma=20.
    """
    name: str = "bottom_first_bull"
    low_window: int = 60
    near_tol: float = 0.05
    vol_lookback: int = 20
    vol_mult: float = 1.5

    def evaluate(self, df: pd.DataFrame, ctx: Dict[str, Any]) -> RuleResult:
        if len(df) < self.low_window + 2:
            return RuleResult(triggered=False)

        last = df.iloc[-1]
        last_close = float(last["close"])
        prev_close = float(df["close"].iloc[-2])

        # 1. 직전 봉(반등 전) 종가가 60일 저점 부근 = 바닥권 하락추세
        prior_low = float(df["low"].iloc[-(self.low_window + 1):-1].min())
        if prior_low <= 0:
            return RuleResult(triggered=False)
        near_bottom = prev_close <= prior_low * (1.0 + self.near_tol)

        # 2. 첫 양봉
        bullish = _is_bullish(last)

        # 3. 거래량 동반
        last_vol = float(last["volume"])
        avg_vol = float(df["volume"].iloc[-(self.vol_lookback + 1):-1].mean())
        vol_ok = avg_vol > 0 and last_vol >= avg_vol * self.vol_mult

        if near_bottom and bullish and vol_ok:
            return RuleResult(
                triggered=True, side="buy", confidence=66.0,
                reasons=[f"bottom_first_bull prior60_low={prior_low:.2f} prev_close={prev_close:.2f} "
                         f"close={last_close:.2f} vol={last_vol:.0f}/{avg_vol:.0f}"],
                metadata={"prior_low": prior_low, "vol_ratio": last_vol / avg_vol if avg_vol > 0 else 0.0},
            )
        return RuleResult(triggered=False)


# 책 전체 일봉 규칙 (키움영웅전 9인 기법 일봉 6종)
ALL_DAILY_RULES = [
    rule_close_momentum_breakout,   # 종가매매 (신정재+청사진) — 오버나이트
    rule_limit_up_follow,           # 상따 (뭐라도되겠지) — -3% 손절
    rule_new_high_breakout,         # 전고점 돌파 (불개미+캐리)
    rule_prev_limitup_pullback,     # 전날 상한가 익일 눌림 (캐리)
    rule_ma5_pullback,              # 눌림목 (방배동선수+신정재)
    rule_bottom_first_bull,         # 바닥권 첫 양봉 (불개미)
]
