"""『트레이딩 전략서』 (Book 19) — 일봉 조건식 A~I 매수후보 스크리너.

평가 시점 t = df 마지막 행(0봉). 진입은 드라이버가 t+1 시가(entry_mechanism="market").
t+1 데이터 접근 금지. 모든 지표 trailing(과거~t). 데이터 컬럼: open, high, low, close, volume.

조건식: A and B and C and D and E and F and (not G) and (not H) and I
  A 200일 종가신고가      : close[t] >= max(close[t-199..t])
  B Envelope(10,10) 돌파  : close[t] >= SMA(close,env_period)[t] * (1+env_pct)
  C 양봉                  : open[t] < close[t]
  D 거래량 전일대비 100%+ : volume[t] >= volume[t-1] * vol_ratio  (전일 동시간 일봉 프록시)
  E 종가 > 이등분선       : close[t] > (high[t]+low[t])/2
  F 5일 거래대금 50억+    : mean(close*volume [t-5..t-1]) / 1e6 >= min_value_mil  (금일 제외)
  G 갭상승(제외)          : open[t] >= close[t-1] * (1+gap_excl)
  H 직전급등(제외)        : close[t-1] >= close[t-2] * (1+prior_surge_excl)
  I 당일 시가대비 +3%     : close[t] >= open[t] * (1+intraday_gain)

거래대금(F): 일봉 데이터에 별도 거래대금 컬럼이 없어 close*volume(원) → /1e6(백만) 환산.
필드 기본값 = 책 원문 verbatim. 멀티버스 그리드 스윕 노출용이나 채택판정은 기본값 기준.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict

import numpy as np
import pandas as pd

from strategies.books._base_book_strategy import Rule, RuleResult


def _today_mask(df: pd.DataFrame):
    """t(마지막 행)와 같은 거래일(KST date)의 봉 boolean mask. datetime 필수."""
    if "datetime" not in df.columns:
        return None
    dts = pd.to_datetime(df["datetime"])
    last_date = dts.iloc[-1].date()
    return (dts.dt.date == last_date).values


def _bisector_at(df: pd.DataFrame, mask) -> float:
    """당일 누적 이등분선 = (당일 고가 max + 당일 저가 min) / 2 (t까지)."""
    h = df["high"].astype(float).values[mask]
    l = df["low"].astype(float).values[mask]
    if len(h) == 0:  # 방어: 마스크 봉 없음(NaT 등) → 전체 df 폴백
        h = df["high"].astype(float).values
        l = df["low"].astype(float).values
    return (float(h.max()) + float(l.min())) / 2.0


@dataclass
class rule_envelope_200d_high(Rule):
    name: str = "envelope_200d_high"
    high_window: int = 200       # A: 200일 종가신고가 룩백
    env_period: int = 10         # B: Envelope 이동평균 기간
    env_pct: float = 0.10        # B: Envelope 상단 % (10%)
    vol_ratio: float = 1.0       # D: 전일 거래량 대비 배수(100%)
    value_window: int = 5        # F: 거래대금 평균 기간
    min_value_mil: float = 5000.0  # F: 5일 평균 거래대금 하한(백만원=50억)
    gap_excl: float = 0.07       # G: 갭상승 제외 임계(7%)
    prior_surge_excl: float = 0.10  # H: 직전봉 급등 제외 임계(10%)
    intraday_gain: float = 0.03  # I: 당일 시가대비 종가 상승 하한(3%)

    def evaluate(self, df: pd.DataFrame, ctx: Dict[str, Any]) -> RuleResult:
        need = max(self.high_window, self.env_period, self.value_window) + 2
        if df is None or len(df) < need:
            return RuleResult(triggered=False)

        o = df["open"].astype(float)
        h = df["high"].astype(float)
        l = df["low"].astype(float)
        c = df["close"].astype(float)
        v = df["volume"].astype(float)

        close_t = float(c.iloc[-1])
        open_t = float(o.iloc[-1])
        high_t = float(h.iloc[-1])
        low_t = float(l.iloc[-1])
        vol_t = float(v.iloc[-1])
        vol_prev = float(v.iloc[-2])
        close_prev = float(c.iloc[-2])
        close_prev2 = float(c.iloc[-3])

        # NaN 가드: 더러운 데이터(결측/0)면 평가 불가 → 미트리거.
        # (실파이프라인의 _load_daily_adj 가 close NaN/<=0 행을 이미 드롭하나, 방어적으로 재확인.
        #  NaN 은 비교가 항상 False 라 가드 없으면 A(close_t<window_max=False)를 잘못 통과할 수 있음.)
        scalars = (close_t, open_t, high_t, low_t, vol_t, vol_prev, close_prev, close_prev2)
        if any(pd.isna(x) for x in scalars):
            return RuleResult(triggered=False)

        # A. 200일 종가 신고가 (close_t == 직전 high_window 봉 중 최고종가)
        window_max = float(c.iloc[-self.high_window:].max())
        if close_t < window_max:
            return RuleResult(triggered=False)

        # B. Envelope 상단 돌파
        sma = float(c.iloc[-self.env_period:].mean())
        if not (sma > 0 and close_t >= sma * (1.0 + self.env_pct)):
            return RuleResult(triggered=False)

        # C. 양봉
        if not (open_t < close_t):
            return RuleResult(triggered=False)

        # D. 거래량 전일대비 100% 이상
        if not (vol_t >= vol_prev * self.vol_ratio):
            return RuleResult(triggered=False)

        # E. 종가 > 이등분선
        if not (close_t > (high_t + low_t) / 2.0):
            return RuleResult(triggered=False)

        # F. 5일 평균 거래대금(금일 제외) >= min_value_mil(백만)
        #    slice [-(value_window+1):-1] = 정확히 value_window 봉(t-value_window .. t-1, 금일 제외).
        tv_prev = (c * v).iloc[-(self.value_window + 1):-1]
        if len(tv_prev) < self.value_window:  # 보조 가드: 주 need-가드가 이미 보장(방어용).
            return RuleResult(triggered=False)
        avg_value_mil = float(tv_prev.mean()) / 1e6
        if avg_value_mil < self.min_value_mil:
            return RuleResult(triggered=False)

        # G(제외). 당일 시가 갭상승 >= gap_excl
        if close_prev > 0 and open_t >= close_prev * (1.0 + self.gap_excl):
            return RuleResult(triggered=False)

        # H(제외). 직전봉(어제) 종가가 그제 대비 급등 >= prior_surge_excl
        if close_prev2 > 0 and close_prev >= close_prev2 * (1.0 + self.prior_surge_excl):
            return RuleResult(triggered=False)

        # I. 당일 시가대비 종가 +intraday_gain 이상
        if not (open_t > 0 and close_t >= open_t * (1.0 + self.intraday_gain)):
            return RuleResult(triggered=False)

        return RuleResult(
            triggered=True, side="buy", confidence=70.0,
            reasons=[
                f"envelope_200d_high close={close_t:.0f} >= env_upper={sma * (1 + self.env_pct):.0f} "
                f"200d_high vol>=prev value={avg_value_mil:.0f}M gain={close_t / open_t - 1:.1%}"
            ],
            metadata={"sma": sma, "avg_value_mil": avg_value_mil},
        )


@dataclass
class rule_price_box_tma(Rule):
    """전략1 가격박스(1분봉): TMA(30) 중심선 ± 편차밴드, 하한 지지/중심 상향돌파."""
    name: str = "price_box_tma"
    tma_period: int = 30      # 삼각이동평균 기간
    dev_window: int = 60      # 편차밴드 룩백
    dev_k: float = 2.0        # 편차 std 배수
    tol: float = 0.002        # 지지/돌파 tolerance

    def evaluate(self, df: pd.DataFrame, ctx: Dict[str, Any]) -> RuleResult:
        m = (self.tma_period + 1) // 2  # 15
        need = max(2 * m, self.dev_window) + 2  # +2: tma_prev 1봉 여유 + 슬라이스 경계
        if df is None or len(df) < need:
            return RuleResult(triggered=False)
        mask = _today_mask(df)
        if mask is None:
            return RuleResult(triggered=False)

        c = df["close"].astype(float)
        # TMA(30) ≈ SMA(SMA(close,15),15)
        tma = c.rolling(m).mean().rolling(m).mean()
        tma_t = float(tma.iloc[-1])
        tma_prev = float(tma.iloc[-2])
        close_t = float(c.iloc[-1])
        close_prev = float(c.iloc[-2])
        if any(np.isnan(x) for x in (tma_t, tma_prev, close_t, close_prev)):
            return RuleResult(triggered=False)

        # 편차밴드 (최근 dev_window 봉 |close-TMA| 의 mean+dev_k*std)
        # TMA 워밍업 NaN(앞쪽 2m-2행)은 제외하고 유효값만 사용
        dev = (c - tma).abs().iloc[-self.dev_window:].dropna()
        if len(dev) < 2:
            return RuleResult(triggered=False)
        band = float(dev.mean()) + self.dev_k * float(dev.std())
        if not (band > 0):
            return RuleResult(triggered=False)
        lower = tma_t - band

        support = close_t <= lower * (1.0 + self.tol)
        breakout = (close_prev < tma_prev) and (close_t >= tma_t)
        if not (support or breakout):
            return RuleResult(triggered=False)

        # 이등분선 위
        if close_t < _bisector_at(df, mask):
            return RuleResult(triggered=False)

        return RuleResult(
            triggered=True, side="buy", confidence=70.0,
            reasons=[f"price_box_tma close={close_t:.0f} tma={tma_t:.0f} "
                     f"lower={lower:.0f} {'support' if support else 'breakout'}"],
            metadata={"tma": tma_t, "lower": lower, "band": band},
        )


@dataclass
class rule_bollinger_squeeze(Rule):
    """전략2 볼린저 스퀴즈(5분봉): 밀집(스퀴즈) 구간 이후 밴드 상한 돌파 또는 하한 지지 진입."""
    name: str = "bollinger_squeeze"
    bb_period: int = 20       # BB SMA·std 기간
    bb_k: float = 2.0         # BB 밴드 배수
    sqz_window: int = 100     # 스퀴즈 판별 룩백 (직전봉 bw vs 중앙값)
    tol: float = 0.002        # 하한 지지 tolerance

    def evaluate(self, df: pd.DataFrame, ctx: Dict[str, Any]) -> RuleResult:
        need = self.bb_period + self.sqz_window + 1
        # 데이터 충분 여부 먼저 확인(Task-1 리뷰 교훈: df/len 가드 최우선)
        if df is None or len(df) < need:
            return RuleResult(triggered=False)
        mask = _today_mask(df)
        if mask is None:
            return RuleResult(triggered=False)

        c = df["close"].astype(float)

        # BB 계산: mid=SMA(20), sd=rolling std(20), upper/lower, bandwidth
        mid = c.rolling(self.bb_period).mean()
        sd = c.rolling(self.bb_period).std()
        upper = mid + self.bb_k * sd
        lower = mid - self.bb_k * sd
        bandwidth = (upper - lower) / mid  # mid≈0이면 inf 가능 → isfinite 가드로 처리

        # sd > 0 가드: 평탄 데이터(rolling std=0)이면 upper=lower=mid → 스퓨리어스 돌파 방지
        sd_t = float(sd.iloc[-1])
        if not (np.isfinite(sd_t) and sd_t > 0):
            return RuleResult(triggered=False)

        # 스퀴즈 판별: 직전봉 bw vs 최근 sqz_window 봉(직전봉 제외) 중앙값
        # 직전봉(-2)을 기준으로 측정 → 현재봉 자체의 밴드 확장이 스퀴즈 측정에 영향 주지 않음
        bw_prev = float(bandwidth.iloc[-2])
        bw_med = float(np.nanmedian(bandwidth.iloc[-(self.sqz_window + 1):-1].values))

        # NaN/inf 가드 (mid≈0이면 bandwidth=inf로 스퀴즈 오판 → 미트리거)
        if not (np.isfinite(bw_prev) and np.isfinite(bw_med)):
            return RuleResult(triggered=False)

        # 스퀴즈 조건: 직전봉 밴드폭 <= 최근 중앙값 (밀집 구간)
        if not (bw_prev <= bw_med):
            return RuleResult(triggered=False)

        # 현재봉 종가·상한·하한 추출 후 일괄 NaN/inf 가드
        close_t = float(c.iloc[-1])
        upper_t = float(upper.iloc[-1])
        lower_t = float(lower.iloc[-1])
        if any(not np.isfinite(x) for x in (close_t, upper_t, lower_t)):
            return RuleResult(triggered=False)

        # 진입 조건: 상한 돌파 OR 하한 지지
        breakout = close_t >= upper_t
        support = close_t <= lower_t * (1.0 + self.tol)
        if not (breakout or support):
            return RuleResult(triggered=False)

        # 이등분선 위 필터
        if close_t < _bisector_at(df, mask):
            return RuleResult(triggered=False)

        entry_type = "breakout" if breakout else "support"
        return RuleResult(
            triggered=True, side="buy", confidence=70.0,
            reasons=[f"bollinger_squeeze {entry_type} close={close_t:.0f} "
                     f"upper={upper_t:.0f} lower={lower_t:.0f} "
                     f"bw_prev={bw_prev:.4f} bw_med={bw_med:.4f}"],
            metadata={"upper": upper_t, "lower": lower_t,
                      "bw_prev": bw_prev, "bw_med": bw_med},
        )


@dataclass
class rule_pullback_volume_dry(Rule):
    """전략3 눌림목 4단계(상승·하락·횡보·돌파, 5분봉).

    t = 돌파(매수)봉, t-1 = 횡보(건조)봉. pre-breakout 윈도우(leg_window 봉)에서
    국소 고점 P_high(hi_idx)과 그 이후 되돌림 저점 P_low(dip_idx)을 식별해
    상승→하락(눌림)→횡보(건조)→돌파를 명시 검출. 전부 당일 세션·PIT. range=high-low.
    """
    name: str = "pullback_volume_dry"
    leg_window: int = 12          # ① pre-breakout 국소고점 탐색 룩백
    rise_pct: float = 0.02        # ① 상승 leg 최소 상승폭
    dip_pct: float = 0.01         # ② 되돌림 최소(고점 대비)
    vol_dry_ratio: float = 0.25   # ③ 건조 기준(당일최다 대비)
    vol_block_ratio: float = 0.50  # ④ 과열 차단 상한(당일최다 대비)

    def evaluate(self, df: pd.DataFrame, ctx: Dict[str, Any]) -> RuleResult:
        need = self.leg_window + 3  # leg_window 봉 + t(-1) + t-1(-1) + 경계여유(1)
        if df is None or len(df) < need:
            return RuleResult(triggered=False)
        mask = _today_mask(df)
        if mask is None:
            return RuleResult(triggered=False)

        H = df["high"].astype(float).values
        L = df["low"].astype(float).values
        C = df["close"].astype(float).values
        V = df["volume"].astype(float).values
        n = len(df)

        close_t = float(C[-1])
        vol_t = float(V[-1])
        vol_prev = float(V[-2])
        rng_t = float(H[-1] - L[-1])
        rng_prev = float(H[-2] - L[-2])
        if any(not np.isfinite(x) for x in (close_t, vol_t, vol_prev, rng_t, rng_prev)):
            return RuleResult(triggered=False)

        # pre-breakout 윈도우: 인덱스 [lo .. n-2] (leg_window 봉, t=n-1 제외)
        lo = n - 1 - self.leg_window
        pre_h = H[lo:n - 1]
        pre_l = L[lo:n - 1]
        if len(pre_h) < self.leg_window or not (np.all(np.isfinite(pre_h)) and np.all(np.isfinite(pre_l))):
            return RuleResult(triggered=False)

        # ① 상승: 국소 고점 P_high + 그 직전 저점 대비 rise_pct 상승
        hi_rel = int(np.argmax(pre_h))
        hi_idx = lo + hi_rel
        P_high = float(H[hi_idx])
        if hi_idx > n - 4:  # spec: hi_idx <= t-3 (되돌림+구분된 횡보 ≥2봉 확보)
            return RuleResult(triggered=False)
        rise_low = float(L[lo:hi_idx + 1].min())
        if not (P_high >= rise_low * (1.0 + self.rise_pct)):
            return RuleResult(triggered=False)

        # ② 하락(눌림): 고점 이후 되돌림 저점 P_low
        dip_lows = L[hi_idx + 1:n - 1]
        dip_rel = int(np.argmin(dip_lows))
        dip_idx = hi_idx + 1 + dip_rel
        P_low = float(L[dip_idx])
        if not (P_high > 0 and (P_high - P_low) / P_high >= self.dip_pct):
            return RuleResult(triggered=False)
        bisector = _bisector_at(df, mask)
        if P_low < bisector:  # 지지 유지: 되돌림이 이등분선 위
            return RuleResult(triggered=False)

        # ③ 횡보(건조): 당일 최다거래량(세션, 현재봉 t 제외) 기준
        day_vols = V[mask]
        if len(day_vols) <= 1:  # 세션 첫 봉: 당일 인트라데이 맥락 없음 → 4단계 판단 불가
            return RuleResult(triggered=False)
        day_max_vol = float(day_vols[:-1].max())  # 당일 최다거래량(현재봉 t 제외)
        if day_max_vol <= 0:
            return RuleResult(triggered=False)
        if not (vol_prev <= day_max_vol * self.vol_dry_ratio):  # 거래량 급감
            return RuleResult(triggered=False)
        # 상승 leg range (stage-1 rise_low 와 동일 슬라이스 lo:hi_idx+1)
        leg_rng = (H[lo:hi_idx + 1] - L[lo:hi_idx + 1])
        if not (rng_prev < float(leg_rng.mean())):  # 캔들 축소
            return RuleResult(triggered=False)

        # ④ 돌파: 횡보 박스 상단(되돌림 저점~t-1 고가 최대) 돌파 + 거래량/캔들 확대 + 이등분선 위
        box_high = float(H[dip_idx:n - 1].max())
        if not (close_t > box_high):
            return RuleResult(triggered=False)
        if not (vol_t > vol_prev and vol_t <= day_max_vol * self.vol_block_ratio):
            return RuleResult(triggered=False)
        if not (rng_t > rng_prev):
            return RuleResult(triggered=False)
        if close_t < bisector:
            return RuleResult(triggered=False)

        return RuleResult(
            triggered=True, side="buy", confidence=70.0,
            reasons=[f"pullback_4stage close={close_t:.0f} P_high={P_high:.0f} "
                     f"P_low={P_low:.0f} dip={(P_high - P_low) / P_high:.1%} "
                     f"box_high={box_high:.0f}"],
            metadata={"P_high": P_high, "P_low": P_low, "box_high": box_high,
                      "day_max_vol": day_max_vol},
        )


# 책 전체 규칙 (일봉 A~I + 분봉 실행층 3전략)
ALL_RULES = [
    rule_envelope_200d_high,
    rule_price_box_tma,
    rule_bollinger_squeeze,
    rule_pullback_volume_dry,
]
