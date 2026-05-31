"""유지윤 『하루 만에 수익 내는 데이트레이딩 3대 타법』 — 일봉(daily) 매매 규칙.

책 3대 타법(바닥/지지/돌파)을 **일봉 단위로 정량화 가능한 4종**으로 환원 코드화.
원천: strategy_catalog.md / reading_notes.md (314p HQ 재판독, 2026-05-31).
trading_legends/rules_daily.py 와 동일한 Rule 인터페이스(evaluate(df, ctx)->RuleResult, no-lookahead).

입력 df는 일봉 OHLCV 시계열이며, run_daytrading_3methods.py 가 종목별 daily_prices 의
df.iloc[:i+1] 윈도우를 그대로 전달한다. 전고점/거래량/지지 캔들은 모두 trailing 계산되어
no-lookahead 가 유지된다. 컬럼: datetime, open, high, low, close, volume.

──────────────────────────────────────────────────────────────────────────
정량화 기준 (책 패턴 → 합리적 임계값, 분봉 트리거는 일봉 거래량 폭증으로 근사):

- "거래량 폭증" = 마지막 봉 거래량 >= 직전 N봉 평균/지지 평균 × 배수 (책 제1원칙).
- "급등/상한가권" = 과거 구간 저점 대비 고점 +surge_pct, 또는 전일 대비 +limitup_pct.
- "지지 캔들" = 종가/저가가 기준선(급등 고점·상한가 종가) 부근에서 무너지지 않고 유지.
- "전고점 돌파" = 종가가 직전 N봉(현재봉 제외) 고가 최대값 이상.
- "양봉" = close > open.
──────────────────────────────────────────────────────────────────────────
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict

import pandas as pd

from strategies.books._base_book_strategy import Rule, RuleResult


# ---------------------------------------------------------------------------
# 공통 헬퍼
# ---------------------------------------------------------------------------

def _is_bullish(bar) -> bool:
    return float(bar["close"]) > float(bar["open"])


# ---------------------------------------------------------------------------
# 1. 지지 타법 — 기본 지지(10캔들): 급등 후 지지 캔들 + 거래량 점감 → 폭증 진입
# ---------------------------------------------------------------------------

@dataclass
class rule_support_10candle(Rule):
    """급등(+25%↑) 후 지지 캔들 ~10개(거래량 점감) → 당일 거래량 폭증 양봉 진입.

    진입(카탈로그 §2 기본 지지):
      1. 급등 이력: pre_window(직전 급등 탐색 구간) 저점 대비 고점 >= +surge_pct(+25%)
      2. 지지 유지: 지지 10캔들 종가 최저가 >= pre_high × (1 - support_tol)
      3. 거래량 점감: 지지 구간 평균 거래량 < 급등 봉 거래량 × vol_decay(0.80)
      4. 당일 거래량 폭증 양봉: volume >= 지지 평균 × vol_spike_mult(2.0), close > open
    청산 TP +15% / SL -10% (run 스크립트 variant A).
    """
    name: str = "support_10candle"
    lookback_surge: int = 30
    surge_pct: float = 0.25
    support_candles: int = 10
    support_tol: float = 0.10
    vol_decay: float = 0.80
    vol_spike_mult: float = 2.0

    def evaluate(self, df: pd.DataFrame, ctx: Dict[str, Any]) -> RuleResult:
        need = self.lookback_surge + self.support_candles + 2
        if len(df) < need:
            return RuleResult(triggered=False)

        # 급등 탐색 구간 (지지 윈도우 직전)
        pre_window = df.iloc[-(self.lookback_surge + self.support_candles + 1): -(self.support_candles + 1)]
        if len(pre_window) < 2:
            return RuleResult(triggered=False)
        pre_low = float(pre_window["close"].min())
        pre_high = float(pre_window["close"].max())
        if pre_low <= 0:
            return RuleResult(triggered=False)
        surge_pct_actual = (pre_high - pre_low) / pre_low
        if surge_pct_actual < self.surge_pct:
            return RuleResult(triggered=False)

        # 지지 10캔들: 고점 부근 유지
        support_window = df.iloc[-(self.support_candles + 1):-1]
        if float(support_window["close"].min()) < pre_high * (1.0 - self.support_tol):
            return RuleResult(triggered=False)

        # 거래량 점감: 지지 평균 < 급등 봉 거래량 × vol_decay
        surge_argmax = int(pre_window["close"].values.argmax())
        surge_vol = float(pre_window["volume"].iloc[surge_argmax])
        avg_support_vol = float(support_window["volume"].mean())
        if not (avg_support_vol < surge_vol * self.vol_decay):
            return RuleResult(triggered=False)

        # 당일 거래량 폭증 양봉
        last = df.iloc[-1]
        bullish = _is_bullish(last)
        last_vol = float(last["volume"])
        vol_spike = avg_support_vol > 0 and last_vol >= avg_support_vol * self.vol_spike_mult

        if bullish and vol_spike:
            return RuleResult(
                triggered=True, side="buy", confidence=65.0,
                reasons=[f"support_10candle pre_high={pre_high:.2f} surge={surge_pct_actual:.2%} "
                         f"vol={last_vol:.0f}/{avg_support_vol:.0f}"],
                metadata={
                    "pre_high": pre_high,
                    "surge_pct_actual": surge_pct_actual,
                    "vol_ratio": last_vol / avg_support_vol if avg_support_vol > 0 else 0.0,
                },
            )
        return RuleResult(triggered=False)


# ---------------------------------------------------------------------------
# 2. 바닥 타법 — 3×3 패턴: 상승 3일 + 지지 3일 → 돌파 진입
# ---------------------------------------------------------------------------

@dataclass
class rule_floor_3x3(Rule):
    """상승 3봉(+5%↑) → 지지 3봉(횡보) → 당일 지지 고점 돌파 양봉 + 거래량 진입.

    진입(카탈로그 §1 3×3 패턴):
      1. 상승 3봉: 종가 단조증가 AND (마지막-처음)/처음 >= min_rise_pct(+5%)
      2. 지지 3봉: 저점 최저 >= 상승 마지막 종가 ×(1-support_tol), 고점 최고 <= ×(1+support_tol×2)
      3. 당일 돌파: 양봉 AND 종가 >= 지지 3봉 고점 최대 AND 거래량 >= 직전5봉 평균 × vol_mult(1.2)
    청산 TP 전고점/+10% (run 스크립트 variant A).
    """
    name: str = "floor_3x3"
    rise_bars: int = 3
    support_bars: int = 3
    min_rise_pct: float = 0.05
    support_tol: float = 0.05
    vol_mult: float = 1.2

    def evaluate(self, df: pd.DataFrame, ctx: Dict[str, Any]) -> RuleResult:
        need = self.rise_bars + self.support_bars + 6
        if len(df) < need:
            return RuleResult(triggered=False)

        # 상승 3봉
        rise_window = df.iloc[-(self.rise_bars + self.support_bars + 1): -(self.support_bars + 1)]
        rise_close = rise_window["close"].astype(float)
        increasing = bool((rise_close.diff().iloc[1:] > 0).all())
        first = float(rise_close.iloc[0])
        last_rise = float(rise_close.iloc[-1])
        if first <= 0:
            return RuleResult(triggered=False)
        rise_pct = (last_rise - first) / first
        if not (increasing and rise_pct >= self.min_rise_pct):
            return RuleResult(triggered=False)

        # 지지 3봉 (횡보)
        support_window = df.iloc[-(self.support_bars + 1):-1]
        floor_ok = float(support_window["low"].min()) >= last_rise * (1.0 - self.support_tol)
        ceil_ok = float(support_window["high"].max()) <= last_rise * (1.0 + self.support_tol * 2)
        if not (floor_ok and ceil_ok):
            return RuleResult(triggered=False)

        # 당일 돌파 양봉 + 거래량
        last = df.iloc[-1]
        breakout_level = float(support_window["high"].max())
        bullish = _is_bullish(last)
        breakout = float(last["close"]) >= breakout_level
        avg_vol = float(df["volume"].iloc[-6:-1].mean())
        vol_ok = avg_vol > 0 and float(last["volume"]) >= avg_vol * self.vol_mult

        if bullish and breakout and vol_ok:
            return RuleResult(
                triggered=True, side="buy", confidence=62.0,
                reasons=[f"floor_3x3 rise={rise_pct:.2%} breakout_level={breakout_level:.2f} "
                         f"close={float(last['close']):.2f}"],
                metadata={"rise_pct": rise_pct, "breakout_level": breakout_level},
            )
        return RuleResult(triggered=False)


# ---------------------------------------------------------------------------
# 3. 바닥 타법 — 2지지 패턴: 상한가 후 2회 지지 → 재공략
# ---------------------------------------------------------------------------

@dataclass
class rule_floor_2support(Rule):
    """직전 강한 양봉(상한가권 +20%↑) 후 2회 이상 지지 확인 → 당일 양봉 재공략.

    진입(카탈로그 §1 2지지 패턴):
      1. 직전 lookback(7)봉 내 강한 양봉(전일 대비 >= +limitup_pct(+20%)) = spike 봉 발견
      2. spike 이후(윈도우 내) min_supports(2)개 이상 봉이 지지: 저가 >= spike 종가×(1-support_tol),
         그리고 spike 고가 미돌파(조정)
      3. 당일: 양봉 AND 종가 > 전일 종가 AND 거래량 >= 직전5봉 평균 × vol_mult(1.2)
    청산 TP 전고점 (run 스크립트 variant A).
    """
    name: str = "floor_2support"
    lookback: int = 7
    limitup_pct: float = 0.20
    support_tol: float = 0.10
    min_supports: int = 2
    vol_mult: float = 1.2

    def evaluate(self, df: pd.DataFrame, ctx: Dict[str, Any]) -> RuleResult:
        need = self.lookback + 4
        if len(df) < need:
            return RuleResult(triggered=False)

        window = df.iloc[-(self.lookback + 1):-1]  # 현재봉 제외 직전 lookback 봉
        w = window.reset_index(drop=True)

        # 강한 양봉(spike) 탐색: 등락률(전일 대비) >= limitup_pct
        spike_pos = None
        for k in range(len(w)):
            # 전일 종가: 윈도우 내 직전 봉, 없으면 df 전체에서 참조
            if k == 0:
                global_idx = len(df) - (self.lookback + 1)
                if global_idx - 1 < 0:
                    continue
                prev_close = float(df["close"].iloc[global_idx - 1])
            else:
                prev_close = float(w["close"].iloc[k - 1])
            if prev_close <= 0:
                continue
            gain = float(w["close"].iloc[k]) / prev_close - 1.0
            if gain >= self.limitup_pct:
                spike_pos = k
                break

        if spike_pos is None:
            return RuleResult(triggered=False)

        spike_close = float(w["close"].iloc[spike_pos])
        spike_high = float(w["high"].iloc[spike_pos])
        if spike_close <= 0:
            return RuleResult(triggered=False)

        # spike 이후 지지 봉 카운트: 저가 유지 + spike 고가 미돌파
        n_supports = 0
        for k in range(spike_pos + 1, len(w)):
            held = float(w["low"].iloc[k]) >= spike_close * (1.0 - self.support_tol)
            no_breakout = float(w["high"].iloc[k]) <= spike_high
            if held and no_breakout:
                n_supports += 1
        if n_supports < self.min_supports:
            return RuleResult(triggered=False)

        # 당일 재공략
        last = df.iloc[-1]
        prev_close = float(df["close"].iloc[-2])
        bullish = _is_bullish(last)
        up = prev_close > 0 and float(last["close"]) > prev_close
        avg_vol = float(df["volume"].iloc[-6:-1].mean())
        vol_ok = avg_vol > 0 and float(last["volume"]) >= avg_vol * self.vol_mult

        if bullish and up and vol_ok:
            return RuleResult(
                triggered=True, side="buy", confidence=60.0,
                reasons=[f"floor_2support spike_close={spike_close:.2f} n_supports={n_supports} "
                         f"close={float(last['close']):.2f}"],
                metadata={"spike_close": spike_close, "n_supports": n_supports},
            )
        return RuleResult(triggered=False)


# ---------------------------------------------------------------------------
# 4. 돌파 타법 — 전고점 거래량 동반 돌파
# ---------------------------------------------------------------------------

@dataclass
class rule_breakout_prev_high(Rule):
    """종가가 직전 high_window(20)봉 전고점 돌파 + 거래량 직전 20봉 평균 × 2.0 양봉 → 진입.

    진입(카탈로그 §3 장기 고점 돌파):
      1. 종가 >= 직전 high_window(20)봉 고가 최대값 (전고점 돌파, 현재봉 제외)
      2. 당일 거래량 >= 직전 vol_lookback(20)봉 평균 × vol_mult(2.0) (전일 대비 폭증 근사)
      3. 양봉 (close > open)
    청산 TP +10% (run 스크립트 variant B 빠른 익절).
    """
    name: str = "breakout_prev_high"
    high_window: int = 20
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

        breakout = last_close >= prior_high
        vol_surge = avg_vol > 0 and last_vol >= avg_vol * self.vol_mult
        bullish = _is_bullish(last)

        if breakout and vol_surge and bullish:
            return RuleResult(
                triggered=True, side="buy", confidence=68.0,
                reasons=[f"breakout_prev_high close={last_close:.2f} prior20_high={prior_high:.2f} "
                         f"vol={last_vol:.0f}/{avg_vol:.0f}"],
                metadata={"prior_high": prior_high, "vol_ratio": last_vol / avg_vol if avg_vol > 0 else 0.0},
            )
        return RuleResult(triggered=False)


# 책 전체 일봉 규칙 (3대 타법 일봉 환원 4종)
ALL_RULES = [
    rule_support_10candle,    # 지지 타법 — 기본 지지(10캔들) + 거래량 점감→폭증
    rule_floor_3x3,           # 바닥 타법 — 3×3 (상승3+지지3 돌파)
    rule_floor_2support,      # 바닥 타법 — 2지지 (상한가 후 2회 지지 재공략)
    rule_breakout_prev_high,  # 돌파 타법 — 전고점 거래량 동반 돌파
]
