"""발굴 배치1 후보 진입룰 4종 (per-stock, no-lookahead).

설계 원칙 (spec G1): 출처 사양 verbatim, 임의 튜닝 금지. 각 룰의 파라미터는
출처(발표된 사양 또는 레포 템플릿 기본값) 그대로이며, 섭동(G5)은 강건성 확인용.

no-lookahead: generate_signal 은 호출자가 넘긴 window(=df.iloc[:i+1]) 만 본다.
rolling/EWM 전부 trailing. 성능: 지표는 필요한 꼬리 구간만 슬라이스해 계산.
"""
from __future__ import annotations

import datetime as _dt
from functools import lru_cache

import pandas as pd

from strategies.base import Signal, SignalType
from utils.indicators import calculate_rsi
from utils.korean_holidays import is_holiday


# ---------------------------------------------------------------------------
# 거래일 캘린더 헬퍼 (turn_of_month 용) — 주말+공휴일 라이브러리 기반.
# PIT: 거래소 캘린더는 사전 공표 → 미래일 판정이 룩어헤드 아님.
# 한계: 임시휴장(선거 등)은 라이브러리에 없을 수 있어 월경계 판정이 드물게 1일 어긋날
#       수 있음(근사) — CANDIDATES.md 에 한계로 기록.
# ---------------------------------------------------------------------------

@lru_cache(maxsize=None)
def _is_trading_day(d: _dt.date) -> bool:
    if d.weekday() >= 5:
        return False
    return not is_holiday(_dt.datetime(d.year, d.month, d.day))


@lru_cache(maxsize=None)
def _next_trading_day(d: _dt.date) -> _dt.date:
    cur = d + _dt.timedelta(days=1)
    for _ in range(15):
        if _is_trading_day(cur):
            return cur
        cur += _dt.timedelta(days=1)
    return cur


@lru_cache(maxsize=None)
def _is_last_trading_day(d: _dt.date) -> bool:
    """d 가 해당 월의 마지막 거래일인가."""
    return _is_trading_day(d) and _next_trading_day(d).month != d.month


@lru_cache(maxsize=None)
def _trading_ordinal(d: _dt.date) -> int:
    """d 가 해당 월의 몇 번째 거래일인가 (1-based). 비거래일이면 0."""
    if not _is_trading_day(d):
        return 0
    cnt = 0
    cur = _dt.date(d.year, d.month, 1)
    while cur <= d:
        if _is_trading_day(cur):
            cnt += 1
        cur += _dt.timedelta(days=1)
    return cnt


class OversoldRSI2Rule:
    """① 단기 과락 평균회귀 — Connors RSI-2 (발표 사양 verbatim).

    진입: RSI(2) < 10 AND 종가 > SMA200 (장기 상승추세 내 단기 과락만).
    청산: 종가 > SMA5 (CloseAboveMAExitAdapter) + max_hold 가드.
    출처: Connors & Alvarez, Short Term Trading Strategies That Work (2009).
    """
    name = "oversold_rsi2"

    def __init__(self, rsi_period: int = 2, rsi_buy: float = 10.0, sma_long: int = 200):
        self.rsi_period = rsi_period
        self.rsi_buy = rsi_buy
        self.sma_long = sma_long

    def generate_signal(self, stock_code: str, df: pd.DataFrame, timeframe: str = "daily"):
        need = self.sma_long + 2
        if df is None or len(df) < need:
            return None
        close = df["close"].astype(float).iloc[-need:]
        c = float(close.iloc[-1])
        sma = float(close.rolling(self.sma_long, min_periods=self.sma_long).mean().iloc[-1])
        if pd.isna(sma) or c <= sma:
            return None
        rsi = calculate_rsi(close.iloc[-(self.rsi_period + 20):], self.rsi_period)
        r = float(rsi.iloc[-1])
        if pd.isna(r) or r >= self.rsi_buy:
            return None
        return Signal(signal_type=SignalType.BUY, stock_code=stock_code, confidence=60,
                      reasons=[f"RSI({self.rsi_period})={r:.1f}<{self.rsi_buy} & close>SMA{self.sma_long}"])


class StrengthClose1DRule:
    """② 강세마감 익일보유 — a priori 고정 사양.

    진입: 양봉 AND 종가가 당일 레인지 상단(>= low + range_pos×(high-low))
          AND 거래량 >= 직전 vol_lookback봉 평균 × vol_mult.
    청산: max_hold=0 (다음봉 시가 진입 → 그 다음봉 시가 청산 = 1거래일 보유).
    근거: 강세 마감 단기 지속 + 보유기간이 기존 7전략(5~100일)과 비중첩 → 저상관 후보.
    """
    name = "strength_close_1d"

    def __init__(self, range_pos: float = 0.75, vol_lookback: int = 20, vol_mult: float = 1.5):
        self.range_pos = range_pos
        self.vol_lookback = vol_lookback
        self.vol_mult = vol_mult

    def generate_signal(self, stock_code: str, df: pd.DataFrame, timeframe: str = "daily"):
        if df is None or len(df) < self.vol_lookback + 2:
            return None
        last = df.iloc[-1]
        o, h, low, c = (float(last["open"]), float(last["high"]),
                        float(last["low"]), float(last["close"]))
        if c <= o or h <= low:
            return None
        if (c - low) / (h - low) < self.range_pos:
            return None
        prev_vol = df["volume"].astype(float).iloc[-(self.vol_lookback + 1):-1]
        avg = float(prev_vol.mean())
        if avg <= 0 or float(last["volume"]) < avg * self.vol_mult:
            return None
        return Signal(signal_type=SignalType.BUY, stock_code=stock_code, confidence=60,
                      reasons=[f"강세마감 pos={(c - low) / (h - low):.2f} vol×{float(last['volume']) / avg:.1f}"])


class BBReversionRule:
    """③ BB 평균회귀 — strategies/bb_reversion 템플릿 verbatim 재활용.

    진입(전부 충족): close<=BB(20,2σ)하단 AND RSI14<40 AND ADX14<20(횡보) AND
                    거래량>=20일평균×1.2. 판정은 템플릿의 evaluate_buy_conditions 재사용.
    청산: BBReversionExitAdapter (sl3/tp5/BB중심회귀/ADX>30/mh15 — 템플릿 verbatim).
    """
    name = "bb_reversion"

    def __init__(self, bb_period: int = 20, bb_std: float = 2.0,
                 rsi_oversold: float = 40.0, adx_max: float = 20.0,
                 volume_ratio_min: float = 1.2):
        self.bb_period = bb_period
        self.bb_std = bb_std
        self.rsi_oversold = rsi_oversold
        self.adx_max = adx_max
        self.volume_ratio_min = volume_ratio_min

    def generate_signal(self, stock_code: str, df: pd.DataFrame, timeframe: str = "daily"):
        from strategies.bb_reversion.strategy import BBReversionStrategy
        need = max(self.bb_period, 14, 20) + 25  # BB/ADX/RSI 워밍업 + EWM 안정화 여유
        if df is None or len(df) < need:
            return None
        tail = df.iloc[-need:]
        close = tail["close"].astype(float)
        c = float(close.iloc[-1])
        bb = BBReversionStrategy.calculate_bollinger_bands(close, self.bb_period, self.bb_std)
        adx = BBReversionStrategy.calculate_adx(
            tail["high"].astype(float), tail["low"].astype(float), close, 14)
        rsi = calculate_rsi(close, 14)
        vol = tail["volume"].astype(float)
        vol_ma = float(vol.iloc[-20:].mean())  # 템플릿 verbatim: 현재봉 포함 20봉 평균
        volume_ratio = float(vol.iloc[-1]) / vol_ma if vol_ma > 0 else 0.0
        reasons = BBReversionStrategy.evaluate_buy_conditions(
            current_price=c,
            bb_lower=float(bb["lower"].iloc[-1]),
            bb_middle=float(bb["middle"].iloc[-1]),
            rsi_value=float(rsi.iloc[-1]),
            adx_value=float(adx.iloc[-1]) if not pd.isna(adx.iloc[-1]) else 50.0,
            volume_ratio=volume_ratio,
            rsi_oversold=self.rsi_oversold,
            adx_max=self.adx_max,
            volume_ratio_min=self.volume_ratio_min,
        )
        if reasons is None:
            return None
        return Signal(signal_type=SignalType.BUY, stock_code=stock_code,
                      confidence=60, reasons=reasons)


class ThreeDownBounceRule:
    """⑤ N일 연속 하락 반등 (배치2) — 발표 사양 (Connors 'consecutive down closes') verbatim.

    진입: 직전 n_down(3)봉 연속 종가 하락 → 익일 시가 매수.
    청산: 순수 시간청산 — h1(mh=0, 1거래일) / h2(mh=1, 2거래일), 손익절 없음.
    """
    name = "three_down_bounce"

    def __init__(self, n_down: int = 3):
        self.n_down = n_down

    def generate_signal(self, stock_code: str, df: pd.DataFrame, timeframe: str = "daily"):
        if df is None or len(df) < self.n_down + 2:
            return None
        close = df["close"].astype(float).iloc[-(self.n_down + 1):]
        diffs = close.diff().iloc[1:]
        if (diffs < 0).all():
            return Signal(signal_type=SignalType.BUY, stock_code=stock_code, confidence=60,
                          reasons=[f"{self.n_down}일 연속 하락"])
        return None


class NDownVolSurgeRule:
    """⑧ 조건 중첩: N일 연속 하락 AND 당일 거래량 급증 (배치3 confluence).

    진입: 직전 n_down(4)봉 연속 종가 하락 AND 당일 거래량 >= 직전 vol_lookback(20)봉
          평균 × vol_mult(2.0). 독립 조건의 AND — "조건이 겹칠 때만"의 코드화 버전.
    청산: 순수 시간청산 (h2=2거래일).
    """
    name = "ndown_volsurge"

    def __init__(self, n_down: int = 4, vol_mult: float = 2.0, vol_lookback: int = 20):
        self.n_down = n_down
        self.vol_mult = vol_mult
        self.vol_lookback = vol_lookback

    def generate_signal(self, stock_code: str, df: pd.DataFrame, timeframe: str = "daily"):
        need = max(self.n_down + 1, self.vol_lookback + 1) + 1
        if df is None or len(df) < need:
            return None
        close = df["close"].astype(float).iloc[-(self.n_down + 1):]
        if not (close.diff().iloc[1:] < 0).all():
            return None
        prev_vol = df["volume"].astype(float).iloc[-(self.vol_lookback + 1):-1]
        avg = float(prev_vol.mean())
        if avg <= 0 or float(df["volume"].iloc[-1]) < avg * self.vol_mult:
            return None
        return Signal(signal_type=SignalType.BUY, stock_code=stock_code, confidence=60,
                      reasons=[f"{self.n_down}연속하락+거래량×{self.vol_mult}"])


class RSI2PureRule:
    """⑥ 순수 RSI(2) 과락 (배치2) — 추세필터 없는 a priori 변형.

    배치1 oversold_rsi2 의 corr 0.89 가 SMA200 추세필터 때문이라는 가설을 직접 검정:
    진입 RSI(2) < 10 만 (SMA200 조건 제거). 청산: h1/h2 순수 시간청산.
    """
    name = "rsi2_pure"

    def __init__(self, rsi_period: int = 2, rsi_buy: float = 10.0):
        self.rsi_period = rsi_period
        self.rsi_buy = rsi_buy

    def generate_signal(self, stock_code: str, df: pd.DataFrame, timeframe: str = "daily"):
        if df is None or len(df) < self.rsi_period + 22:
            return None
        close = df["close"].astype(float).iloc[-(self.rsi_period + 20):]
        r = float(calculate_rsi(close, self.rsi_period).iloc[-1])
        if pd.isna(r) or r >= self.rsi_buy:
            return None
        return Signal(signal_type=SignalType.BUY, stock_code=stock_code, confidence=60,
                      reasons=[f"RSI({self.rsi_period})={r:.1f}<{self.rsi_buy} (무필터)"])


class TurnOfMonthRule:
    """⑦ 월말월초(turn-of-month) 효과 (배치2) — 발표된 캘린더 이상현상.

    진입: 체결일(신호봉의 다음 거래일)이 TOM 윈도우의 entry_offset 위치일 때.
      offset  0 = 월 1번째 거래일(기본·base) · -1 = 전월 마지막 거래일 ·
      +1/+2/+3 = 월 2/3/4번째 거래일. 섭동(G5)은 윈도우 내 오프셋 이동
      (published TOM 윈도우 = 월말일~월초 3일 → 전부 양수 기대).
    청산: h1/h2 순수 시간청산. 가격 외 정보 원천 → 구조적 저상관 기대.
    """
    name = "turn_of_month"

    def __init__(self, entry_offset: int = 0):
        self.entry_offset = entry_offset

    def generate_signal(self, stock_code: str, df: pd.DataFrame, timeframe: str = "daily"):
        if df is None or len(df) < 2:
            return None
        d = pd.Timestamp(df["datetime"].iloc[-1]).date()
        entry = _next_trading_day(d)
        if self.entry_offset == -1:
            hit = _is_last_trading_day(entry)
        else:
            hit = _trading_ordinal(entry) == self.entry_offset + 1
        if not hit:
            return None
        return Signal(signal_type=SignalType.BUY, stock_code=stock_code, confidence=60,
                      reasons=[f"TOM offset={self.entry_offset} entry={entry}"])


class MeanReversionMA20Rule:
    """④ MA20 이탈 평균회귀 — strategies/mean_reversion 템플릿 verbatim 재활용.

    진입: (close-MA20)/MA20×100 <= entry_deviation_pct(-10) AND RSI14 < 30.
    청산: MAReversionExitAdapter (sl7/tp12/MA20×0.9 회복/mh7 — 템플릿 verbatim).
    """
    name = "mean_reversion_ma20"

    def __init__(self, ma_period: int = 20, entry_deviation_pct: float = -10.0,
                 rsi_period: int = 14, rsi_oversold: float = 30.0,
                 use_rsi_filter: bool = True):
        self.ma_period = ma_period
        self.entry_deviation_pct = entry_deviation_pct
        self.rsi_period = rsi_period
        self.rsi_oversold = rsi_oversold
        self.use_rsi_filter = use_rsi_filter

    def generate_signal(self, stock_code: str, df: pd.DataFrame, timeframe: str = "daily"):
        need = max(self.ma_period, self.rsi_period) + 10
        if df is None or len(df) < need:
            return None
        close = df["close"].astype(float).iloc[-need:]
        c = float(close.iloc[-1])
        ma = float(close.rolling(self.ma_period, min_periods=self.ma_period).mean().iloc[-1])
        if pd.isna(ma) or ma <= 0:
            return None
        deviation_pct = (c - ma) / ma * 100.0
        if deviation_pct > self.entry_deviation_pct:
            return None
        if self.use_rsi_filter:
            r = float(calculate_rsi(close, self.rsi_period).iloc[-1])
            if pd.isna(r) or r >= self.rsi_oversold:
                return None
        return Signal(signal_type=SignalType.BUY, stock_code=stock_code, confidence=60,
                      reasons=[f"MA{self.ma_period} 이탈 {deviation_pct:.1f}%"])
