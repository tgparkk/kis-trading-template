"""강창권 『주식투자 단기 트레이딩의 정석』 — 분봉(1분봉) 매매 규칙.

카탈로그 A등급 중 분봉 전략만 코드화. 일봉 묶음은 별도.
각 함수/클래스는 Rule 인스턴스. evaluate(df, ctx)에서 t 시점 평가 — t+1 데이터 접근 금지.

입력 df는 분봉 OHLCV 시계열이며, BookBacktester가 종목별 **다일(multi-day) 연속** 분봉의
df.iloc[:i+1] 윈도우를 그대로 전달한다. 따라서:
  - 480분선/240분선 등 장기 분봉 이평선은 df["close"].rolling(N) 으로 자연스럽게
    멀티데이 연결되어 계산된다 (trailing 이므로 no-lookahead 유지).
  - "당일 등락률"·시간 필터는 df["datetime"] 에서 당일/직전일 구간을 분리해 계산한다.

datetime 컬럼: pandas Timestamp (timezone-naive, KST). 장 09:00~15:30, ~390봉/일.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import time as dtime
from typing import Any, Dict, Optional

import pandas as pd

from strategies.books._base_book_strategy import Rule, RuleResult


# ---------------------------------------------------------------------------
# 공통 헬퍼
# ---------------------------------------------------------------------------

def _ensure_dt(df: pd.DataFrame) -> Optional[pd.Series]:
    """df["datetime"] 을 Timestamp Series로 반환. 없으면 None."""
    if "datetime" not in df.columns:
        return None
    dt = df["datetime"]
    if not pd.api.types.is_datetime64_any_dtype(dt):
        dt = pd.to_datetime(dt, errors="coerce")
    return dt


def _today_mask(dt: pd.Series) -> pd.Series:
    """윈도우 마지막 봉과 같은 날짜인 봉들의 boolean mask."""
    last_date = dt.iloc[-1].date()
    return dt.dt.date == last_date


def _day_return(df: pd.DataFrame, dt: pd.Series) -> Optional[float]:
    """당일 등락률.

    직전 거래일 종가가 윈도우에 있으면 (last_close - prev_close)/prev_close.
    없으면 (last_close - today_open)/today_open 로 근사.
    """
    today = _today_mask(dt)
    if today.sum() == 0:
        return None
    last_close = float(df["close"].iloc[-1])
    if (~today).any():
        prev_close = float(df["close"][~today].iloc[-1])
    else:
        prev_close = float(df["open"][today].iloc[0])
    if prev_close <= 0:
        return None
    return (last_close - prev_close) / prev_close


def _day_high_return(df: pd.DataFrame, dt: pd.Series) -> Optional[float]:
    """당일 장중 최대 등락률 = (당일 고가 - 기준종가)/기준종가.

    '당일 +15%↑ 급등주' 필터용. 급등 후 480분선까지 눌려도 당일 고가가 +15%↑ 였으면
    급등주로 인정 (catalog A-01 의도). 기준종가는 직전 거래일 종가, 없으면 당일 시초가.
    """
    today = _today_mask(dt)
    if today.sum() == 0:
        return None
    today_high = float(df["high"][today.values].max())
    if (~today).any():
        ref_close = float(df["close"][~today].iloc[-1])
    else:
        ref_close = float(df["open"][today.values].iloc[0])
    if ref_close <= 0:
        return None
    return (today_high - ref_close) / ref_close


def _in_time_window(dt: pd.Series, start: dtime, end: dtime) -> bool:
    """윈도우 마지막 봉의 시각이 [start, end] (포함) 안인지."""
    t = dt.iloc[-1].time()
    return start <= t <= end


def _today_slice(df: pd.DataFrame, dt: pd.Series) -> pd.DataFrame:
    """당일 봉만 슬라이스."""
    return df[_today_mask(dt).values]


# ---------------------------------------------------------------------------
# A-01. CK480 기법 ★시그니처★
# ---------------------------------------------------------------------------

@dataclass
class rule_ck480(Rule):
    """당일 +15%↑ 급등주, 1분봉 480분선 지지 10~20분 횡보 후 재상승 양봉 진입.

    진입:
      1. 당일 등락률 >= surge_pct (default +15%)
      2. 시간 필터: lunch_start(12:00) ~ lunch_end(14:30). 14:30 이후 진입 금지.
      3. 480분선(멀티데이 연결) 위/근처에서 직전 support_bars 봉이 480선 부근 횡보(지지)
      4. 마지막 봉이 양봉이며 480선 위에서 재상승
      5. 역배열(480선 아래) 첫 반등 추격 금지 — last_close >= ma480 요구.

    익절/손절은 BookBacktester sl/tp(CK480 권장 tp 0.02 / sl 0.02)로 처리.
    """
    name: str = "ck480"
    ma_window: int = 480
    surge_pct: float = 0.15
    support_bars: int = 15
    support_tol: float = 0.01      # 480선 ±1% 이내 = 지지 횡보
    lunch_start: dtime = dtime(12, 0)
    lunch_end: dtime = dtime(14, 30)

    def evaluate(self, df: pd.DataFrame, ctx: Dict[str, Any]) -> RuleResult:
        if len(df) < self.ma_window + self.support_bars + 1:
            return RuleResult(triggered=False)
        dt = _ensure_dt(df)
        if dt is None or dt.isna().any():
            return RuleResult(triggered=False)

        # 2. 시간 필터 (점심~14:30)
        if not _in_time_window(dt, self.lunch_start, self.lunch_end):
            return RuleResult(triggered=False)

        # 1. 당일 +15% 급등 필터 (당일 장중 고가 기준)
        day_ret = _day_high_return(df, dt)
        if day_ret is None or day_ret < self.surge_pct:
            return RuleResult(triggered=False)

        # 3. 480분선 (멀티데이 연결, trailing)
        ma480 = df["close"].rolling(self.ma_window).mean()
        last_ma = ma480.iloc[-1]
        if pd.isna(last_ma) or last_ma <= 0:
            return RuleResult(triggered=False)
        last_ma = float(last_ma)

        last_close = float(df["close"].iloc[-1])
        last_open = float(df["open"].iloc[-1])
        last_low = float(df["low"].iloc[-1])

        # 5. 역배열 추격 금지: 종가가 480선 위
        if last_close < last_ma:
            return RuleResult(triggered=False)

        # 3. 직전 support_bars 봉이 480선 부근에서 지지(횡보) — 저가가 480선 ±tol 안에 머묾
        support_seg = df.iloc[-(self.support_bars + 1):-1]
        seg_low = float(support_seg["low"].min())
        seg_high = float(support_seg["high"].max())
        # 지지 확인: 구간 저가가 480선 아래로 크게 깨지지 않음 + 구간이 480선 부근(±tol)
        held = (seg_low >= last_ma * (1.0 - self.support_tol))
        near = (abs(seg_low - last_ma) / last_ma <= self.support_tol) or \
               (seg_low <= last_ma * (1.0 + self.support_tol) <= seg_high)
        touched = (last_low <= last_ma * (1.0 + self.support_tol))

        # 4. 재상승 양봉
        bullish = last_close > last_open

        if held and (near or touched) and bullish:
            return RuleResult(
                triggered=True, side="buy", confidence=74.0,
                reasons=[
                    f"ck480 day_ret={day_ret:.2%} ma480={last_ma:.2f} "
                    f"close={last_close:.2f} seg_low={seg_low:.2f}"
                ],
                metadata={"ma480": last_ma, "day_ret": day_ret, "seg_low": seg_low},
            )
        return RuleResult(triggered=False)


# ---------------------------------------------------------------------------
# A-09. 1분봉 5·10분선 눌림목
# ---------------------------------------------------------------------------

@dataclass
class rule_ma_5_10_pullback(Rule):
    """장중 급등 후 2~3봉 눌림 → 5분/10분선 지지 재상승 양봉 진입.

    진입:
      1. 당일 추세 상승 (직전 prior_bars 동안 +run_pct 이상 상승한 적)
      2. 마지막 2~3봉 눌림 후 마지막 봉 저가가 5분선 또는 10분선 부근 터치
      3. 마지막 봉 양봉 (재상승)
    청산은 sl/tp + max_hold (5·10분선 이탈 근사).
    """
    name: str = "ma_5_10_pullback"
    short_ma: int = 5
    long_ma: int = 10
    touch_tol: float = 0.005
    run_lookback: int = 20
    run_pct: float = 0.02
    pullback_bars: int = 3

    def evaluate(self, df: pd.DataFrame, ctx: Dict[str, Any]) -> RuleResult:
        if len(df) < max(self.long_ma, self.run_lookback) + self.pullback_bars + 1:
            return RuleResult(triggered=False)

        ma5 = df["close"].rolling(self.short_ma).mean().iloc[-1]
        ma10 = df["close"].rolling(self.long_ma).mean().iloc[-1]
        if pd.isna(ma5) or pd.isna(ma10):
            return RuleResult(triggered=False)
        ma5 = float(ma5)
        ma10 = float(ma10)

        last_close = float(df["close"].iloc[-1])
        last_open = float(df["open"].iloc[-1])
        last_low = float(df["low"].iloc[-1])

        # 1. 직전 상승 추세 (run)
        run_seg = df["close"].iloc[-(self.run_lookback + 1):-1]
        run = (last_close - float(run_seg.min())) / max(float(run_seg.min()), 1e-9)
        trending = run >= self.run_pct

        # 2. 눌림 후 5/10분선 터치
        touch5 = abs(last_low - ma5) / max(ma5, 1e-9) <= self.touch_tol
        touch10 = abs(last_low - ma10) / max(ma10, 1e-9) <= self.touch_tol

        # 3. 양봉 재상승 + 종가가 이평선 위
        bullish = last_close > last_open
        above = last_close >= min(ma5, ma10)

        if trending and (touch5 or touch10) and bullish and above:
            return RuleResult(
                triggered=True, side="buy", confidence=66.0,
                reasons=[f"ma5_10 ma5={ma5:.2f} ma10={ma10:.2f} low={last_low:.2f} run={run:.2%}"],
                metadata={"ma5": ma5, "ma10": ma10},
            )
        return RuleResult(triggered=False)


# ---------------------------------------------------------------------------
# A-10. 1분봉 20분선 눌림목
# ---------------------------------------------------------------------------

@dataclass
class rule_ma20_pullback(Rule):
    """20분선 위 눌림 후 지지 양봉 진입. 20분선 하향이탈 즉시 청산(근사: sl/tp).

    진입:
      1. 종가가 20분선 위 (정배열 상태)
      2. 마지막 봉 저가가 20분선 부근(±tol) 터치 (눌림 지지)
      3. 마지막 봉 양봉 재상승
    """
    name: str = "ma20_pullback"
    ma_window: int = 20
    touch_tol: float = 0.005

    def evaluate(self, df: pd.DataFrame, ctx: Dict[str, Any]) -> RuleResult:
        if len(df) < self.ma_window + 2:
            return RuleResult(triggered=False)
        ma20 = df["close"].rolling(self.ma_window).mean().iloc[-1]
        if pd.isna(ma20):
            return RuleResult(triggered=False)
        ma20 = float(ma20)

        last_close = float(df["close"].iloc[-1])
        last_open = float(df["open"].iloc[-1])
        last_low = float(df["low"].iloc[-1])
        prev_close = float(df["close"].iloc[-2])

        above = last_close >= ma20 and prev_close >= ma20 * (1.0 - self.touch_tol)
        touch = abs(last_low - ma20) / max(ma20, 1e-9) <= self.touch_tol
        bullish = last_close > last_open

        if above and touch and bullish:
            return RuleResult(
                triggered=True, side="buy", confidence=64.0,
                reasons=[f"ma20_pull ma20={ma20:.2f} low={last_low:.2f} close={last_close:.2f}"],
                metadata={"ma20": ma20},
            )
        return RuleResult(triggered=False)


# ---------------------------------------------------------------------------
# A-13. 1분봉 240·480분선 지지/저항 필터
# ---------------------------------------------------------------------------

@dataclass
class rule_ma_240_480_support(Rule):
    """480분선 지지 + 거래량 회복 반등 양봉 매수. 480선 이하면 매수 금지.

    진입:
      1. 종가가 480분선 위 (저항 통과 = 매수 허용)
      2. 마지막 봉 저가가 240분선 또는 480분선 부근 터치 (지지 반등)
      3. 거래량 회복 (마지막 봉 거래량 >= 직전 vol_lookback 평균 * vol_recover)
      4. 마지막 봉 양봉
    """
    name: str = "ma_240_480_support"
    ma_mid: int = 240
    ma_long: int = 480
    touch_tol: float = 0.008
    vol_lookback: int = 20
    vol_recover: float = 1.2

    def evaluate(self, df: pd.DataFrame, ctx: Dict[str, Any]) -> RuleResult:
        if len(df) < self.ma_long + self.vol_lookback + 1:
            return RuleResult(triggered=False)
        ma240 = df["close"].rolling(self.ma_mid).mean().iloc[-1]
        ma480 = df["close"].rolling(self.ma_long).mean().iloc[-1]
        if pd.isna(ma240) or pd.isna(ma480):
            return RuleResult(triggered=False)
        ma240 = float(ma240)
        ma480 = float(ma480)

        last_close = float(df["close"].iloc[-1])
        last_open = float(df["open"].iloc[-1])
        last_low = float(df["low"].iloc[-1])
        last_vol = float(df["volume"].iloc[-1])
        avg_vol = float(df["volume"].iloc[-(self.vol_lookback + 1):-1].mean())

        # 1. 480선 위 (매수 금지 필터 통과)
        above_480 = last_close >= ma480
        # 2. 240 또는 480선 지지 터치
        touch240 = abs(last_low - ma240) / max(ma240, 1e-9) <= self.touch_tol
        touch480 = abs(last_low - ma480) / max(ma480, 1e-9) <= self.touch_tol
        # 3. 거래량 회복
        vol_ok = last_vol >= avg_vol * self.vol_recover
        # 4. 양봉
        bullish = last_close > last_open

        if above_480 and (touch240 or touch480) and vol_ok and bullish:
            return RuleResult(
                triggered=True, side="buy", confidence=68.0,
                reasons=[
                    f"ma240_480 ma240={ma240:.2f} ma480={ma480:.2f} "
                    f"low={last_low:.2f} vol={last_vol:.0f}/{avg_vol:.0f}"
                ],
                metadata={"ma240": ma240, "ma480": ma480},
            )
        return RuleResult(triggered=False)


# ---------------------------------------------------------------------------
# A-04. 전일 고가 돌파 + 거래량 (VI 데이터 없어 생략/근사)
# ---------------------------------------------------------------------------

@dataclass
class rule_prev_high_break(Rule):
    """1분봉으로 전일 고가 상향 돌파 + 거래량 급증 시 진입.

    전일 고가: 윈도우 내 직전 거래일 봉들의 high 최대값.
    진입:
      1. 윈도우에 전일(직전 거래일) 봉이 존재
      2. 직전 봉 종가 <= 전일 고가 < 마지막 봉 종가 (돌파 순간)
      3. 거래량 급증 (마지막 봉 vol >= 직전 vol_lookback 평균 * vol_spike)
      4. 마지막 봉 양봉
    VI는 데이터 없어 생략(거래량 급증으로 강한 돌파 근사).
    """
    name: str = "prev_high_break"
    vol_lookback: int = 20
    vol_spike: float = 2.0

    def evaluate(self, df: pd.DataFrame, ctx: Dict[str, Any]) -> RuleResult:
        if len(df) < self.vol_lookback + 2:
            return RuleResult(triggered=False)
        dt = _ensure_dt(df)
        if dt is None or dt.isna().any():
            return RuleResult(triggered=False)

        today = _today_mask(dt)
        if (~today).sum() == 0:
            return RuleResult(triggered=False)  # 전일 봉 없음

        # 직전 거래일 = today 직전의 날짜
        prev_dates = dt[~today].dt.date
        prev_day = prev_dates.iloc[-1]
        prev_mask = (dt.dt.date == prev_day).values
        prev_high = float(df["high"][prev_mask].max())

        last_close = float(df["close"].iloc[-1])
        last_open = float(df["open"].iloc[-1])
        prev_close = float(df["close"].iloc[-2])
        last_vol = float(df["volume"].iloc[-1])
        avg_vol = float(df["volume"].iloc[-(self.vol_lookback + 1):-1].mean())

        breakout = prev_close <= prev_high < last_close
        vol_ok = last_vol >= avg_vol * self.vol_spike
        bullish = last_close > last_open

        if breakout and vol_ok and bullish:
            return RuleResult(
                triggered=True, side="buy", confidence=67.0,
                reasons=[
                    f"prev_high_break prev_high={prev_high:.2f} close={last_close:.2f} "
                    f"vol={last_vol:.0f}/{avg_vol:.0f}"
                ],
                metadata={"prev_high": prev_high},
            )
        return RuleResult(triggered=False)


# ---------------------------------------------------------------------------
# A-11. 시초가 음봉 2개 후 양봉
# ---------------------------------------------------------------------------

@dataclass
class rule_open_two_red_then_green(Rule):
    """시초가 후 음봉 2개 → 3번째 거래량 급증 + 강한 양봉 시 매수.

    당일 봉 기준:
      1. 당일 첫 봉 이후 진행. 당일 봉 수 >= 3 (시초가 직후 구간)
      2. 당일 직전 2봉(마지막 봉 제외)이 모두 음봉
      3. 마지막 봉이 강한 양봉 (몸통 >= body_pct) + 거래량 급증
    개장 직후 한정(early_bars 이내)으로 '시초가' 의미 유지.
    """
    name: str = "open_two_red_then_green"
    body_pct: float = 0.003
    vol_lookback: int = 10
    vol_spike: float = 1.5
    early_bars: int = 30   # 개장 후 30봉(09:00~09:30) 이내만

    def evaluate(self, df: pd.DataFrame, ctx: Dict[str, Any]) -> RuleResult:
        if len(df) < self.vol_lookback + 4:
            return RuleResult(triggered=False)
        dt = _ensure_dt(df)
        if dt is None or dt.isna().any():
            return RuleResult(triggered=False)

        today = _today_slice(df, dt)
        n_today = len(today)
        if n_today < 3 or n_today > self.early_bars:
            return RuleResult(triggered=False)

        last = today.iloc[-1]
        red1 = today.iloc[-2]
        red2 = today.iloc[-3]

        is_red = lambda b: float(b["close"]) < float(b["open"])
        two_red = is_red(red1) and is_red(red2)

        last_open = float(last["open"])
        last_close = float(last["close"])
        body = (last_close - last_open) / max(last_open, 1e-9)
        strong_green = body >= self.body_pct

        last_vol = float(last["volume"])
        avg_vol = float(df["volume"].iloc[-(self.vol_lookback + 1):-1].mean())
        vol_ok = last_vol >= avg_vol * self.vol_spike

        if two_red and strong_green and vol_ok:
            return RuleResult(
                triggered=True, side="buy", confidence=63.0,
                reasons=[
                    f"two_red_green body={body:.2%} vol={last_vol:.0f}/{avg_vol:.0f} "
                    f"n_today={n_today}"
                ],
            )
        return RuleResult(triggered=False)


# 책 전체 분봉 규칙
# 스킵: A-05 (이틀 연속 20분선 반복 패턴) — 전일 패턴 매칭 복잡도로 v1 제외.
ALL_RULES = [
    rule_ck480,
    rule_ma_5_10_pullback,
    rule_ma20_pullback,
    rule_ma_240_480_support,
    rule_prev_high_break,
    rule_open_two_red_then_green,
]
