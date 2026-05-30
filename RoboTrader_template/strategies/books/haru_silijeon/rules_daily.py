"""강창권 『주식투자 단기 트레이딩의 정석』 — 일봉(daily) 매매 규칙.

카탈로그 A등급 중 **일봉 전략 7종**을 코드화. 분봉 묶음(rules.py)과 별개 파일.
각 함수/클래스는 Rule 인스턴스. evaluate(df, ctx)에서 t 시점(df 마지막 행) 평가 — t+1 데이터 접근 금지.

입력 df는 일봉 OHLCV 시계열이며, run_haru_silijeon_daily.py 가 종목별 daily_prices 의
df.iloc[:i+1] 윈도우를 그대로 전달한다. 따라서 5/10/20/60/240/480일 이동평균은
df["close"].rolling(N) 으로 trailing 계산되어 no-lookahead 가 유지된다.

datetime 컬럼: pandas Timestamp (일 단위). 컬럼: datetime, open, high, low, close, volume.

──────────────────────────────────────────────────────────────────────────
책 정량화 기준 (카탈로그 §3 / §4 근거, 불명확한 항목은 합리적 기본값 + 주석):

- "급등" 정의: 최근 surge_lookback(기본 30)일 내 저점 대비 +surge_pct(기본 +25%) 이상 상승.
  카탈로그 §4 "20일선 눌림목: 5~30일 내 +20~50% 추정" → 보수적으로 +25%/30일.
- "조정/눌림" 폭: 급등 고점 대비 일정 하락(조정) 후 이평선 부근까지 회귀.
- "이평선 부근 터치": 저가가 이평선 ±touch_tol(기본 ±2%) 안.
- "살짝 이탈 허용": 종가가 이평선 × (1 - below_tol) 이상이면 지지 유효(기본 -2%).
- "도지 캔들": |close-open| <= (high-low) × doji_body_ratio (기본 0.1) + range>0.
- "거래량 감소": 최근 vol_window 평균이 그 직전 동기간 평균 대비 vol_drop_ratio(기본 0.8) 이하.
- "거래량 300%↑": 마지막 봉 거래량 >= 직전 vol_lookback 평균 × vol_spike(기본 3.0 = +300%p? →
  책 '평균 대비 300% 이상' = 3배 → vol_spike=3.0).
- "신고가": 종가가 직전 전체 윈도우(역사적) 고가를 상향 돌파. 52주(252일)는 hist_window 로 근사 가능.
──────────────────────────────────────────────────────────────────────────
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Optional

import pandas as pd

from strategies.books._base_book_strategy import Rule, RuleResult


# ---------------------------------------------------------------------------
# 공통 헬퍼
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


# ---------------------------------------------------------------------------
# A-07. 일봉 20일선 눌림목 공략 ★유일 익절 명시 (+10%)★
# ---------------------------------------------------------------------------

@dataclass
class rule_daily_ma20_pullback(Rule):
    """급등 후 20일선까지 조정 → 20일선 지지 양봉 매수. (익절 +10% 는 run 스크립트 tp로 처리)

    진입:
      1. 직전 surge_lookback(30)일 내 +surge_pct(+25%) 급등 이력
      2. 종가가 20일선 위 (지지 유효: close >= ma20 × (1 - below_tol))
      3. 마지막 봉 저가가 20일선 부근 터치 (±touch_tol)
      4. 마지막 봉 양봉 (지지 반등)
    청산: 20일선 이탈(run 스크립트 trail_ma=20) + tp +10% (A-07 variant).
    """
    name: str = "daily_ma20_pullback"
    ma_window: int = 20
    surge_lookback: int = 30
    surge_pct: float = 0.25
    touch_tol: float = 0.02
    below_tol: float = 0.02

    def evaluate(self, df: pd.DataFrame, ctx: Dict[str, Any]) -> RuleResult:
        if len(df) < max(self.ma_window, self.surge_lookback) + 2:
            return RuleResult(triggered=False)
        ma20 = _ma(df, self.ma_window)
        if ma20 is None:
            return RuleResult(triggered=False)

        last = df.iloc[-1]
        last_close = float(last["close"])
        last_low = float(last["low"])

        surged = _recent_surge(df, self.surge_lookback, self.surge_pct)
        above = last_close >= ma20 * (1.0 - self.below_tol)
        touched = _touch_ma(last_low, ma20, self.touch_tol)
        bullish = _is_bullish(last)

        if surged and above and touched and bullish:
            return RuleResult(
                triggered=True, side="buy", confidence=72.0,
                reasons=[f"daily_ma20_pull ma20={ma20:.2f} low={last_low:.2f} close={last_close:.2f}"],
                metadata={"ma20": ma20},
            )
        return RuleResult(triggered=False)


# ---------------------------------------------------------------------------
# A-08. 일봉 5·10일선 따라가기
# ---------------------------------------------------------------------------

@dataclass
class rule_daily_ma5_10_follow(Rule):
    """급등주 5일선 지지 보유, 흔들리면 10일선 지지 확인 후 재매수.

    진입:
      1. 직전 급등 이력 (surge)
      2. 정배열: 5일선 >= 10일선 (단기 우상향)
      3. 마지막 봉 저가가 5일선 또는 10일선 부근 터치 (±touch_tol)
      4. 종가가 10일선 위 (지지 유효) + 양봉
    청산: 5·10일선 이탈(run 스크립트 trail_ma=10).
    """
    name: str = "daily_ma5_10_follow"
    short_ma: int = 5
    long_ma: int = 10
    surge_lookback: int = 30
    surge_pct: float = 0.25
    touch_tol: float = 0.02
    below_tol: float = 0.02

    def evaluate(self, df: pd.DataFrame, ctx: Dict[str, Any]) -> RuleResult:
        if len(df) < max(self.long_ma, self.surge_lookback) + 2:
            return RuleResult(triggered=False)
        ma5 = _ma(df, self.short_ma)
        ma10 = _ma(df, self.long_ma)
        if ma5 is None or ma10 is None:
            return RuleResult(triggered=False)

        last = df.iloc[-1]
        last_close = float(last["close"])
        last_low = float(last["low"])

        surged = _recent_surge(df, self.surge_lookback, self.surge_pct)
        aligned = ma5 >= ma10
        touched = _touch_ma(last_low, ma5, self.touch_tol) or _touch_ma(last_low, ma10, self.touch_tol)
        above = last_close >= ma10 * (1.0 - self.below_tol)
        bullish = _is_bullish(last)

        if surged and aligned and touched and above and bullish:
            return RuleResult(
                triggered=True, side="buy", confidence=68.0,
                reasons=[f"daily_ma5_10 ma5={ma5:.2f} ma10={ma10:.2f} low={last_low:.2f}"],
                metadata={"ma5": ma5, "ma10": ma10},
            )
        return RuleResult(triggered=False)


# ---------------------------------------------------------------------------
# A-12. 일봉 60일선 반등 + 도지 캔들
# ---------------------------------------------------------------------------

@dataclass
class rule_daily_ma60_doji_rebound(Rule):
    """5→10→20일선 순차 이탈 후 60일선 근처 거래량 감소 + 도지 → 반등 양봉 진입.

    진입(마지막 봉 = 반등 양봉. 직전 봉 = 도지):
      1. 직전 깊은 조정: 5일선 < 10일선 < 20일선 (역배열 = 순차 이탈) 이력
      2. 종가/저가가 60일선 부근 (±touch_tol)
      3. 직전 봉이 도지 캔들 (|c-o| <= range × doji_body_ratio)
      4. 도지 부근 거래량 감소 (최근 vol_window 평균 <= 직전 동기간 평균 × vol_drop_ratio)
      5. 마지막 봉 양봉 (반등) + 종가 60일선 위
    청산: 60일선 이탈(run 스크립트 trail_ma=60).
    """
    name: str = "daily_ma60_doji_rebound"
    ma_window: int = 60
    touch_tol: float = 0.03
    doji_body_ratio: float = 0.1
    vol_window: int = 5
    vol_drop_ratio: float = 0.8
    below_tol: float = 0.02

    def evaluate(self, df: pd.DataFrame, ctx: Dict[str, Any]) -> RuleResult:
        if len(df) < self.ma_window + self.vol_window * 2 + 2:
            return RuleResult(triggered=False)
        ma60 = _ma(df, self.ma_window)
        if ma60 is None:
            return RuleResult(triggered=False)

        last = df.iloc[-1]
        doji_bar = df.iloc[-2]
        last_close = float(last["close"])
        last_low = float(last["low"])

        # 1. 역배열 (순차 이탈로 깊게 조정) — 도지 바 시점(df[:-1])의 단기 이평으로 판정.
        #    마지막 반등 양봉이 ma5 를 끌어올려 역배열을 자기상쇄하는 것을 방지(책 의도: '직전' 하락 정렬).
        prior = df.iloc[:-1]
        ma5 = _ma(prior, 5)
        ma10 = _ma(prior, 10)
        ma20 = _ma(prior, 20)
        if None in (ma5, ma10, ma20):
            return RuleResult(triggered=False)
        bearish_stack = ma5 < ma10 < ma20
        # 2. 60일선 부근
        near60 = _touch_ma(last_low, ma60, self.touch_tol) or _touch_ma(last_close, ma60, self.touch_tol)
        # 3. 직전 봉 도지
        d_open = float(doji_bar["open"])
        d_close = float(doji_bar["close"])
        d_range = float(doji_bar["high"]) - float(doji_bar["low"])
        is_doji = d_range > 0 and abs(d_close - d_open) <= d_range * self.doji_body_ratio
        # 4. 거래량 감소 (최근 vol_window 평균 vs 그 직전 동기간 평균)
        recent_vol = float(df["volume"].iloc[-self.vol_window:].mean())
        prior_vol = float(df["volume"].iloc[-(self.vol_window * 2):-self.vol_window].mean())
        vol_dried = prior_vol > 0 and recent_vol <= prior_vol * self.vol_drop_ratio
        # 5. 반등 양봉 + 60일선 위
        bullish = _is_bullish(last)
        above = last_close >= ma60 * (1.0 - self.below_tol)

        if bearish_stack and near60 and is_doji and vol_dried and bullish and above:
            return RuleResult(
                triggered=True, side="buy", confidence=66.0,
                reasons=[
                    f"daily_ma60_doji ma60={ma60:.2f} close={last_close:.2f} "
                    f"doji_body={abs(d_close - d_open):.2f}/{d_range:.2f} "
                    f"vol={recent_vol:.0f}/{prior_vol:.0f}"
                ],
                metadata={"ma60": ma60},
            )
        return RuleResult(triggered=False)


# ---------------------------------------------------------------------------
# A-14. 일봉 240·480일선 추세 필터 / 손절 (상위 필터)
# ---------------------------------------------------------------------------

@dataclass
class rule_daily_trend_filter_240_480(Rule):
    """480일선 위에서만 진입 허용하는 상위 추세 필터(단독 진입 신호로도 사용 가능).

    진입(추세 정상 + 장기선 지지 반등):
      1. 종가가 480일선 위 (480선 이탈=추세 붕괴 → 위에 있어야 매수 허용)
      2. 종가가 240일선 위 (정배열 추세 유효)
      3. 마지막 봉 저가가 240일선 또는 480일선 부근 터치 (장기선 지지 반등)
      4. 마지막 봉 양봉
    이 룰은 '상위 필터'로 설계되었으나, 다른 룰과 all_AND 조합 또는 단독 long-trend
    진입으로 활용 가능. 청산: 240/480일선 이탈(run 스크립트 trail_ma=240).
    """
    name: str = "daily_trend_filter_240_480"
    ma_mid: int = 240
    ma_long: int = 480
    touch_tol: float = 0.03

    def evaluate(self, df: pd.DataFrame, ctx: Dict[str, Any]) -> RuleResult:
        if len(df) < self.ma_long + 2:
            return RuleResult(triggered=False)
        ma240 = _ma(df, self.ma_mid)
        ma480 = _ma(df, self.ma_long)
        if ma240 is None or ma480 is None:
            return RuleResult(triggered=False)

        last = df.iloc[-1]
        last_close = float(last["close"])
        last_low = float(last["low"])

        above_480 = last_close >= ma480
        above_240 = last_close >= ma240
        touched = _touch_ma(last_low, ma240, self.touch_tol) or _touch_ma(last_low, ma480, self.touch_tol)
        bullish = _is_bullish(last)

        if above_480 and above_240 and touched and bullish:
            return RuleResult(
                triggered=True, side="buy", confidence=64.0,
                reasons=[f"daily_trend_240_480 ma240={ma240:.2f} ma480={ma480:.2f} close={last_close:.2f}"],
                metadata={"ma240": ma240, "ma480": ma480},
            )
        return RuleResult(triggered=False)


# ---------------------------------------------------------------------------
# A-02. 직장인 스윙 (급등 후 기간조정 → 20/60일선 반등)
# ---------------------------------------------------------------------------

@dataclass
class rule_daily_swing_pullback(Rule):
    """상한가/대량 급등 → 3일+ 기간조정 + 거래량 감소 → 20 또는 60일선 지지 반등 진입.

    진입:
      1. 직전 surge_lookback(30)일 내 +surge_pct(+25%) 급등 이력
      2. 기간 조정: 직전 고점 이후 min_consol_days(3)봉 이상 횡보/하락 (고점이 충분히 과거)
      3. 조정 중 거래량 감소 (최근 vol_window 평균 <= 직전 동기간 평균 × vol_drop_ratio)
      4. 마지막 봉 저가가 20일선 또는 60일선 부근 터치 (얕은/깊은 조정)
      5. 마지막 봉 양봉 + 종가 해당 이평선 위
    청산: 20일선 이탈(run 스크립트 trail_ma=20).
    """
    name: str = "daily_swing_pullback"
    surge_lookback: int = 30
    surge_pct: float = 0.25
    min_consol_days: int = 3
    touch_tol: float = 0.025
    vol_window: int = 5
    vol_drop_ratio: float = 0.85
    below_tol: float = 0.02

    def evaluate(self, df: pd.DataFrame, ctx: Dict[str, Any]) -> RuleResult:
        if len(df) < max(60, self.surge_lookback) + self.vol_window * 2 + 2:
            return RuleResult(triggered=False)
        ma20 = _ma(df, 20)
        ma60 = _ma(df, 60)
        if ma20 is None or ma60 is None:
            return RuleResult(triggered=False)

        last = df.iloc[-1]
        last_close = float(last["close"])
        last_low = float(last["low"])

        # 1. 급등 이력
        surged = _recent_surge(df, self.surge_lookback, self.surge_pct)
        # 2. 기간 조정: 직전 surge_lookback 구간 고점이 최소 min_consol_days 봉 전
        seg = df.iloc[-(self.surge_lookback + 1):-1].reset_index(drop=True)
        high_pos = int(seg["high"].idxmax())
        days_since_high = (len(seg) - 1) - high_pos
        consolidating = days_since_high >= self.min_consol_days
        # 3. 거래량 감소
        recent_vol = float(df["volume"].iloc[-self.vol_window:].mean())
        prior_vol = float(df["volume"].iloc[-(self.vol_window * 2):-self.vol_window].mean())
        vol_dried = prior_vol > 0 and recent_vol <= prior_vol * self.vol_drop_ratio
        # 4. 20 또는 60일선 지지 터치
        touch20 = _touch_ma(last_low, ma20, self.touch_tol)
        touch60 = _touch_ma(last_low, ma60, self.touch_tol)
        support_ma = ma20 if touch20 else (ma60 if touch60 else None)
        # 5. 양봉 + 해당 이평선 위
        bullish = _is_bullish(last)
        above = support_ma is not None and last_close >= support_ma * (1.0 - self.below_tol)

        if surged and consolidating and vol_dried and (touch20 or touch60) and bullish and above:
            which = "ma20" if touch20 else "ma60"
            return RuleResult(
                triggered=True, side="buy", confidence=70.0,
                reasons=[
                    f"daily_swing {which} ma20={ma20:.2f} ma60={ma60:.2f} "
                    f"consol_days={days_since_high} vol={recent_vol:.0f}/{prior_vol:.0f}"
                ],
                metadata={"ma20": ma20, "ma60": ma60},
            )
        return RuleResult(triggered=False)


# ---------------------------------------------------------------------------
# A-03. 신고가 돌파 (역사적 신고가 우선)
# ---------------------------------------------------------------------------

@dataclass
class rule_daily_new_high_breakout(Rule):
    """역사적(또는 hist_window 근사) 신고가 종가 돌파 + 20일선 위 → 진입.

    진입:
      1. 종가가 직전 윈도우(마지막 봉 제외) 전체 고가를 상향 돌파 (= 신고가, 무주공산)
      2. 직전 봉 종가는 직전 고가 이하 (돌파 '순간')
      3. 종가가 20일선 위 (추세 유효)
      4. 마지막 봉 양봉
    hist_window=None 이면 윈도우 전체(역사적), 정수면 그 일수(예: 252=52주) 신고가.
    청산: 20일선 이탈(run 스크립트 trail_ma=20).
    """
    name: str = "daily_new_high_breakout"
    hist_window: Optional[int] = None  # None=역사적 전체, 252=52주 근사
    ma_window: int = 20

    def evaluate(self, df: pd.DataFrame, ctx: Dict[str, Any]) -> RuleResult:
        if len(df) < self.ma_window + 5:
            return RuleResult(triggered=False)
        ma20 = _ma(df, self.ma_window)
        if ma20 is None:
            return RuleResult(triggered=False)

        if self.hist_window is None:
            prior = df["high"].iloc[:-1]
        else:
            if len(df) < self.hist_window + 2:
                return RuleResult(triggered=False)
            prior = df["high"].iloc[-(self.hist_window + 1):-1]
        prior_high = float(prior.max())

        last = df.iloc[-1]
        last_close = float(last["close"])
        prev_close = float(df["close"].iloc[-2])

        breakout = prev_close <= prior_high < last_close
        above_ma = last_close >= ma20
        bullish = _is_bullish(last)

        if breakout and above_ma and bullish:
            return RuleResult(
                triggered=True, side="buy", confidence=70.0,
                reasons=[f"daily_new_high prior_high={prior_high:.2f} close={last_close:.2f} ma20={ma20:.2f}"],
                metadata={"prior_high": prior_high, "ma20": ma20},
            )
        return RuleResult(triggered=False)


# ---------------------------------------------------------------------------
# A-06. 거래량 300%↑ + 장기 이평(240/480일선) 종가 돌파 베팅
# ---------------------------------------------------------------------------

@dataclass
class rule_daily_vol300_longma_break(Rule):
    """직전 평균 대비 +300%(=3배) 거래량 급증 + 240/480일선 종가 돌파 당일 진입.

    진입:
      1. 마지막 봉 거래량 >= 직전 vol_lookback(20) 평균 × vol_spike(3.0)
      2. 240일선 또는 480일선 종가 돌파: 직전 봉 종가 <= 장기선 < 마지막 봉 종가
      3. 마지막 봉 양봉
    청산: 장기선 재이탈(run 스크립트 trail_ma=240).
    """
    name: str = "daily_vol300_longma_break"
    ma_mid: int = 240
    ma_long: int = 480
    vol_lookback: int = 20
    vol_spike: float = 3.0

    def evaluate(self, df: pd.DataFrame, ctx: Dict[str, Any]) -> RuleResult:
        if len(df) < self.ma_mid + self.vol_lookback + 2:
            return RuleResult(triggered=False)
        ma240 = _ma(df, self.ma_mid)
        ma480 = _ma(df, self.ma_long) if len(df) >= self.ma_long else None

        last = df.iloc[-1]
        last_close = float(last["close"])
        prev_close = float(df["close"].iloc[-2])
        last_vol = float(last["volume"])
        avg_vol = float(df["volume"].iloc[-(self.vol_lookback + 1):-1].mean())

        vol_ok = avg_vol > 0 and last_vol >= avg_vol * self.vol_spike

        def _crossed(ma: Optional[float]) -> bool:
            return ma is not None and prev_close <= ma < last_close

        broke = _crossed(ma240) or _crossed(ma480)
        bullish = _is_bullish(last)

        if vol_ok and broke and bullish:
            which = "ma240" if _crossed(ma240) else "ma480"
            broken_ma = ma240 if _crossed(ma240) else ma480
            return RuleResult(
                triggered=True, side="buy", confidence=67.0,
                reasons=[
                    f"daily_vol300_longma {which}={broken_ma:.2f} close={last_close:.2f} "
                    f"vol={last_vol:.0f}/{avg_vol:.0f}"
                ],
                metadata={"ma240": ma240, "ma480": ma480, "broken": which},
            )
        return RuleResult(triggered=False)


# 책 전체 일봉 규칙 (A등급 일봉 7종)
ALL_DAILY_RULES = [
    rule_daily_ma20_pullback,        # A-07 ★+10% 익절 명시
    rule_daily_ma5_10_follow,        # A-08
    rule_daily_ma60_doji_rebound,    # A-12
    rule_daily_trend_filter_240_480, # A-14 (상위 필터 겸 진입)
    rule_daily_swing_pullback,       # A-02
    rule_daily_new_high_breakout,    # A-03
    rule_daily_vol300_longma_break,  # A-06
]
