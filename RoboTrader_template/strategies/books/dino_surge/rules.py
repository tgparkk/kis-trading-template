"""디노(백새봄) 『돈이 된다! 급등주 투자법』 — 일봉(daily) 매매 규칙.

카탈로그(reports/books_research/dino_surge/strategy_catalog.md) §5 코드화 매핑을 구현.
각 클래스는 Rule 인스턴스. evaluate(df, ctx)에서 t 시점(df 마지막 행 = t)만 평가 — t+1 데이터 접근 금지.

입력 df 는 일봉 OHLCV 시계열이며 run_dino_surge.py 가 종목별 daily_prices 의
df.iloc[:i+1] 윈도우를 그대로 전달한다. 따라서 OBV/RSI/MA(5/20/60/120)·고점/저점 룩백은
모두 df 윈도우(과거~t)만으로 trailing 계산되어 no-lookahead 가 유지된다.

datetime 컬럼: pandas Timestamp (일 단위). 컬럼: datetime, open, high, low, close, volume.

──────────────────────────────────────────────────────────────────────────
디노 점수(4축) 매핑 (카탈로그 §1):
- 축① 재무: revenue +10%↑ / operating_margin≥10% / 영업이익 흑자(유지·전환) / 유보율≥1000% / 부채↓
    → 정량화는 run 스크립트가 point-in-time financial_statements 로 fin_score(0~5)+이자보상배율
      근사 하드필터를 precompute 해 ctx["dino_fin"] 로 주입. 룰은 ctx 만 읽는다(재조회 금지).
      ctx["dino_fin"] 가 None(=재무 미주입/단위테스트)이면 재무축은 중립(통과)으로 본다.
- 축② 가격: 고점 대비 −20~−40% 눌림(가점) / 저점 대비 과열(감점) → df 윈도우에서 직접 계산.
- 축③ 기술: OBV 우상향 + RSI(또는 투자심리)≤30~40 침체 반등 → df 윈도우에서 직접 계산.
- 축④ 재료: 뉴스/공시 촉매(정량화 불가) → 코드화 생략(카탈로그 §6 명시).

미구현/근사(카탈로그 §6 + 데이터 한계):
- 이자보상배율(영업이익/이자비용): financial_statements 에 이자비용 컬럼 없음 →
  run 스크립트에서 debt_ratio·operating_profit 으로 좀비기업 근사 하드필터(주석 처리).
- 봉차트 13패턴: '바닥반전군'(아래꼬리 장대양봉 / 장대양봉+거래량)만 근사 코드화.
- 관리종목 제외: 별도 관리종목 플래그 데이터 없음 → universe(거래대금 상위)로 간접 회피.
──────────────────────────────────────────────────────────────────────────
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Optional

import numpy as np
import pandas as pd

from strategies.books._base_book_strategy import Rule, RuleResult


# ---------------------------------------------------------------------------
# 지표 헬퍼 (모두 trailing — no-lookahead)
# ---------------------------------------------------------------------------

def _ma(df: pd.DataFrame, window: int) -> Optional[float]:
    """trailing N일 단순이동평균(종가) 마지막 값. NaN/비양수면 None."""
    if len(df) < window:
        return None
    val = df["close"].rolling(window).mean().iloc[-1]
    if pd.isna(val) or val <= 0:
        return None
    return float(val)


def obv(close: pd.Series, volume: pd.Series) -> pd.Series:
    """On-Balance Volume. OBV_t = OBV_{t-1} + sign(close_t - close_{t-1}) * volume_t.

    종가 상승일 거래량 가산, 하락일 차감, 보합 0. 첫 봉 0 시작.
    """
    direction = np.sign(close.diff().fillna(0.0))
    return (direction * volume).cumsum()


def obv_rising(close: pd.Series, volume: pd.Series, lookback: int = 60) -> bool:
    """OBV 수급 양호(우상향/미이탈) 판정 — 디노 §1 축③.

    카탈로그: "주가하락 중 OBV 미이탈/급등 = 세력 진입(매집)". 즉 **매집(상승) 구간 대비
    OBV 가 무너지지 않음**(수급 양호)을 본다. 단순 국소(20봉) 기울기는 눌림 구간에서 항상
    음(-)이 되므로, 매집 구간을 포괄하는 더 긴 lookback(기본 60봉)으로 다음을 본다:

      (a) 우상향: 직전 lookback 봉 OBV 선형회귀 기울기 > 0, 또는
      (b) 미이탈(레벨 유지): OBV[-1] > OBV[-lookback]
                  (눌림에도 lookback 봉 전 매집 시점 OBV 레벨을 지킴 = 매물 미출회).

    둘 중 하나라도 충족이면 True. 지속 분산(distribution; OBV 우하향+레벨 이탈)은 둘 다 실패.
    """
    o = obv(close, volume)
    if len(o) < lookback + 1:
        return False
    seg = o.iloc[-(lookback + 1):].to_numpy(dtype=float)

    # (a) 정상 우상향 (회귀 기울기 > 0)
    x = np.arange(len(seg), dtype=float)
    if np.std(x) > 0:
        slope = float(np.polyfit(x, seg, 1)[0])
        if slope > 0:
            return True

    # (b) 눌림 중 레벨 유지 (매집 시점 대비 미이탈)
    return bool(seg[-1] > seg[0])


def rsi(close: pd.Series, n: int = 14) -> pd.Series:
    """Wilder RSI(n). EMA(alpha=1/n) 평활. 0除 가드(평균손실 0 → RSI 100)."""
    delta = close.diff()
    gain = delta.clip(lower=0.0)
    loss = (-delta).clip(lower=0.0)
    avg_gain = gain.ewm(alpha=1.0 / n, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1.0 / n, adjust=False).mean()
    rs = avg_gain / avg_loss.replace(0.0, np.nan)
    out = 100.0 - 100.0 / (1.0 + rs)
    out[avg_loss == 0.0] = 100.0
    return out


def _drawdown_from_high(df: pd.DataFrame, lookback: int) -> Optional[float]:
    """고점 대비 현재 종가 하락률(눌림 깊이, 음수).

    직전 lookback 봉(마지막 봉 포함)의 고가 최대값 대비 현재 종가.
    return (close - hi) / hi  (예: -0.30 = 고점대비 -30%). hi<=0 → None.
    """
    if len(df) < 2:
        return None
    seg = df.iloc[-min(lookback, len(df)):]
    hi = float(seg["high"].max())
    if hi <= 0:
        return None
    return (float(df["close"].iloc[-1]) - hi) / hi


def _runup_from_low(df: pd.DataFrame, lookback: int) -> Optional[float]:
    """저점 대비 현재 종가 상승률(과열 정도, 양수).

    직전 lookback 봉(마지막 봉 포함)의 저가 최소값 대비 현재 종가.
    return (close - lo) / lo. lo<=0 → None.
    """
    if len(df) < 2:
        return None
    seg = df.iloc[-min(lookback, len(df)):]
    lo = float(seg["low"].min())
    if lo <= 0:
        return None
    return (float(df["close"].iloc[-1]) - lo) / lo


def _is_bullish(bar) -> bool:
    return float(bar["close"]) > float(bar["open"])


def _is_long_bullish(bar, body_pct: float) -> bool:
    """장대양봉: 양봉이고 (종가-시가)/시가 >= body_pct."""
    o = float(bar["open"])
    c = float(bar["close"])
    if o <= 0 or c <= o:
        return False
    return (c - o) / o >= body_pct


def _is_hammer(bar, lower_wick_ratio: float = 2.0, upper_wick_max: float = 0.01) -> bool:
    """아래꼬리 장대양봉(개미털기/망치형) 근사.

    - 양봉(또는 거의 보합 이상)
    - 아래꼬리 길이 >= 몸통 * lower_wick_ratio
    - 위꼬리 <= 종가 * upper_wick_max (카탈로그 §2 "위꼬리 ≤종가 1%")
    """
    o = float(bar["open"])
    h = float(bar["high"])
    l = float(bar["low"])
    c = float(bar["close"])
    if c < o:
        return False
    body = abs(c - o)
    lower_wick = min(o, c) - l
    upper_wick = h - max(o, c)
    rng = h - l
    if rng <= 0:
        return False
    # 몸통이 0에 가까우면(도지) 몸통 대신 range 기준으로 아래꼬리 우세 판정
    body_ref = body if body > rng * 0.05 else rng * 0.05
    long_lower = lower_wick >= body_ref * lower_wick_ratio
    small_upper = upper_wick <= max(c, 1e-9) * upper_wick_max
    return long_lower and small_upper


def _bottom_reversal_bar(bar, body_pct: float = 0.03) -> bool:
    """바닥 반전 봉: 장대양봉 OR 아래꼬리 장대양봉(망치형)."""
    return _is_long_bullish(bar, body_pct) or _is_hammer(bar)


def _vol_spike(df: pd.DataFrame, lookback: int = 20, mult: float = 1.5) -> bool:
    """마지막 봉 거래량 >= 직전 lookback 평균 * mult."""
    if len(df) < lookback + 1:
        return False
    last_vol = float(df["volume"].iloc[-1])
    avg = float(df["volume"].iloc[-(lookback + 1):-1].mean())
    return avg > 0 and last_vol >= avg * mult


def _fin_ok(ctx: Dict[str, Any]) -> bool:
    """재무 하드필터·디노 재무점수 게이트.

    ctx["dino_fin"] 가 dict 면:
      - dict["hard_pass"] is False → 좀비기업/관리 근사 → 탈락
      - dict["fin_score"] (0~5) >= ctx 주입 min_fin_score 면 통과 (run 스크립트가 컷오프 주입)
    ctx["dino_fin"] 가 None(미주입/단위테스트) → 재무축 중립(통과).
    """
    fin = ctx.get("dino_fin")
    if fin is None:
        return True  # 재무 미주입 → 가격·기술축만으로 평가(단위테스트/근사 운용)
    if fin.get("hard_pass") is False:
        return False
    min_score = fin.get("min_fin_score")
    if min_score is None:
        return True
    return float(fin.get("fin_score", 0.0)) >= float(min_score)


# ---------------------------------------------------------------------------
# Variant A — 책 원안 충실 (디노 4축 + 눌림 + OBV + RSI + 바닥반전봉)
# ---------------------------------------------------------------------------

@dataclass
class rule_dino_test_pullback(Rule):
    """디노테스트 충실판 — 눌린 우량 급등주 바닥반전 진입.

    진입(모두 충족):
      1. 재무 게이트: _fin_ok(ctx) (좀비기업 근사 제외 + 디노 재무점수 컷오프; 미주입 시 통과)
      2. 가격축 — 눌림: 고점(high_lookback 내) 대비 종가가 −pullback_max ~ −pullback_min 구간
         (예: −20% ~ −40%). 카탈로그 §1 가점 구간.
      3. 가격축 — 과열 아님: 저점(low_lookback 내) 대비 상승률 <= overheat_max
         (과열(저점대비 +300%↑)은 감점 → 제외).
      4. 기술축 — OBV 우상향(수급 양호)
      5. 기술축 — RSI(rsi_n) <= rsi_max (침체 구간; 반등 직전/초입)
      6. 봉패턴 — 바닥 반전 봉(장대양봉 또는 아래꼬리 장대양봉)
    청산: tp +10% / sl −7% / MA5 이탈 trail (run 스크립트 variant A).
    """
    name: str = "dino_test_pullback"
    high_lookback: int = 120
    low_lookback: int = 250
    pullback_min: float = 0.20    # 고점대비 최소 −20%
    pullback_max: float = 0.40    # 고점대비 최대 −40% (그 이상 깊은 하락은 추세붕괴 회피)
    overheat_max: float = 3.00    # 저점대비 +300% 이상이면 과열 제외
    obv_lookback: int = 60        # 매집(상승) 구간 포괄 — 눌림 중 OBV 미이탈 판정용
    rsi_n: int = 14
    rsi_max: float = 40.0
    body_pct: float = 0.03        # 장대양봉 몸통 기준 +3%

    def evaluate(self, df: pd.DataFrame, ctx: Dict[str, Any]) -> RuleResult:
        if len(df) < max(self.high_lookback, self.obv_lookback, self.rsi_n) + 2:
            return RuleResult(triggered=False)

        # 1. 재무 게이트
        if not _fin_ok(ctx):
            return RuleResult(triggered=False)

        # 2. 눌림 깊이 (고점대비 −20~−40%)
        dd = _drawdown_from_high(df, self.high_lookback)
        if dd is None:
            return RuleResult(triggered=False)
        in_pullback = (-self.pullback_max) <= dd <= (-self.pullback_min)
        if not in_pullback:
            return RuleResult(triggered=False)

        # 3. 과열 아님 (저점대비 상승률 <= overheat_max)
        runup = _runup_from_low(df, self.low_lookback)
        if runup is not None and runup > self.overheat_max:
            return RuleResult(triggered=False)

        # 4. OBV 우상향
        if not obv_rising(df["close"].astype(float), df["volume"].astype(float), self.obv_lookback):
            return RuleResult(triggered=False)

        # 5. RSI 침체
        r = rsi(df["close"].astype(float), self.rsi_n)
        last_rsi = r.iloc[-1]
        if pd.isna(last_rsi) or float(last_rsi) > self.rsi_max:
            return RuleResult(triggered=False)

        # 6. 바닥 반전 봉
        last = df.iloc[-1]
        if not _bottom_reversal_bar(last, self.body_pct):
            return RuleResult(triggered=False)

        return RuleResult(
            triggered=True, side="buy", confidence=74.0,
            reasons=[
                f"dino_test_pullback dd={dd:.2%} runup={(runup if runup is not None else float('nan')):.2%} "
                f"rsi={float(last_rsi):.1f}<= {self.rsi_max:.0f} obv_up bottom_rev"
            ],
            metadata={"drawdown": dd, "rsi": float(last_rsi)},
        )


# ---------------------------------------------------------------------------
# Variant B — 회전율 단순화 (눌림 + RSI 반등 + 장대양봉)
# ---------------------------------------------------------------------------

@dataclass
class rule_pullback_rebound(Rule):
    """회전율 단순판 — 눌림(−20~−40%) + RSI 저점 반등 + 장대양봉.

    진입:
      1. 가격축 — 눌림: 고점 대비 −pullback_max ~ −pullback_min
      2. 기술축 — RSI 반등: RSI[-1] <= rsi_rebound_ceiling AND RSI[-1] > RSI[-2] (저점 상향전환)
      3. 봉패턴 — 장대양봉(몸통 +body_pct↑) + 거래량 증가
    청산: tp +10% / sl −5% (타이트, 회전 중심; run 스크립트 variant B, trail 없음).
    OBV·재무 게이트 없음(회전 단순화).
    """
    name: str = "pullback_rebound"
    high_lookback: int = 120
    pullback_min: float = 0.20
    pullback_max: float = 0.40
    rsi_n: int = 14
    rsi_rebound_ceiling: float = 45.0
    body_pct: float = 0.03
    vol_lookback: int = 20
    vol_mult: float = 1.3

    def evaluate(self, df: pd.DataFrame, ctx: Dict[str, Any]) -> RuleResult:
        if len(df) < max(self.high_lookback, self.rsi_n, self.vol_lookback) + 2:
            return RuleResult(triggered=False)

        # 1. 눌림
        dd = _drawdown_from_high(df, self.high_lookback)
        if dd is None:
            return RuleResult(triggered=False)
        if not ((-self.pullback_max) <= dd <= (-self.pullback_min)):
            return RuleResult(triggered=False)

        # 2. RSI 저점 반등 (침체권 + 상향전환)
        r = rsi(df["close"].astype(float), self.rsi_n)
        last_rsi = r.iloc[-1]
        prev_rsi = r.iloc[-2]
        if pd.isna(last_rsi) or pd.isna(prev_rsi):
            return RuleResult(triggered=False)
        rebounding = float(last_rsi) <= self.rsi_rebound_ceiling and float(last_rsi) > float(prev_rsi)
        if not rebounding:
            return RuleResult(triggered=False)

        # 3. 장대양봉 + 거래량 증가
        last = df.iloc[-1]
        if not _is_long_bullish(last, self.body_pct):
            return RuleResult(triggered=False)
        if not _vol_spike(df, self.vol_lookback, self.vol_mult):
            return RuleResult(triggered=False)

        return RuleResult(
            triggered=True, side="buy", confidence=66.0,
            reasons=[
                f"pullback_rebound dd={dd:.2%} rsi={float(prev_rsi):.1f}->{float(last_rsi):.1f} "
                f"long_bull vol_up"
            ],
            metadata={"drawdown": dd, "rsi": float(last_rsi)},
        )


# 책 전체 일봉 규칙
ALL_RULES = [
    rule_dino_test_pullback,   # variant A — 디노테스트 충실
    rule_pullback_rebound,     # variant B — 회전율 단순
]
