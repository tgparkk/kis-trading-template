"""Minervini VCP — Rule 집합.

규칙들:
- rule_trend_template: SEPA Trend Template 8조건
- rule_vcp_breakout: (구) VCP 베이스 전/후반 진폭 비교 + 피벗 돌파 (조잡 proxy)
- rule_vcp_contraction_breakout: (신) 책 핵심 VCP — 2~4회 연속 수축파동 단계축소 +
  contraction별 거래량 감소 + 피벗 돌파 + RVOL
- rule_tight_closes: 3주 변동폭 ≤ 1.5%
- rule_volume_dryup: 거래량 dry-up + tightness

헬퍼:
- compute_rs_percentile_12w: universe 12주 수익률 백분위
- _find_contraction_legs: base 구간 swing high→low 수축 파동 검출 (no-lookahead)
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Tuple

import numpy as np
import pandas as pd

from strategies.books._base_book_strategy import Rule, RuleResult


def compute_rs_percentile_12w(universe_close: pd.DataFrame) -> pd.DataFrame:
    """universe 종목 12주(60거래일) 수익률을 0~99 백분위로 변환.

    Args:
        universe_close: index=date, columns=stock_code, values=close.
    Returns:
        같은 shape의 DataFrame. 각 행은 해당 날짜의 RS 백분위 (0~99).
    """
    if universe_close.shape[1] < 2:
        raise ValueError(
            f"universe_close must have ≥ 2 stocks, got {universe_close.shape[1]}"
        )
    ret_12w = universe_close.pct_change(60)
    rank = ret_12w.rank(axis=1, pct=True, na_option="keep")
    return (rank * 99).round().astype("Int64")


@dataclass
class rule_trend_template(Rule):
    """SEPA Trend Template 8조건. ctx['rs_value'] 필요."""
    name: str = "trend_template"
    rs_threshold: float = 70.0
    high_52w_drawdown_max: float = 0.25
    low_52w_advance_min: float = 0.30

    def evaluate(self, df: pd.DataFrame, ctx: Dict[str, Any]) -> RuleResult:
        if len(df) < 220:
            return RuleResult(triggered=False)
        close = df["close"].astype(float)
        ma50 = close.rolling(50).mean()
        ma150 = close.rolling(150).mean()
        ma200 = close.rolling(200).mean()
        last_close = float(close.iloc[-1])
        last_ma50 = float(ma50.iloc[-1])
        last_ma150 = float(ma150.iloc[-1])
        last_ma200 = float(ma200.iloc[-1])
        ma200_20d_ago = float(ma200.iloc[-21])
        high_52w = float(close.iloc[-252:].max()) if len(close) >= 252 else float(close.max())
        low_52w = float(close.iloc[-252:].min()) if len(close) >= 252 else float(close.min())
        rs_value = ctx.get("rs_value")
        if rs_value is None or pd.isna(rs_value):
            return RuleResult(triggered=False)

        c1 = last_close > last_ma150 and last_close > last_ma200
        c2 = last_ma150 > last_ma200
        c3 = last_ma200 > ma200_20d_ago
        c4 = last_ma50 > last_ma150 > last_ma200
        c5 = last_close > last_ma50
        c6 = (high_52w - last_close) / high_52w <= self.high_52w_drawdown_max if high_52w > 0 else False
        c7 = (last_close - low_52w) / low_52w >= self.low_52w_advance_min if low_52w > 0 else False
        c8 = float(rs_value) >= self.rs_threshold

        if c1 and c2 and c3 and c4 and c5 and c6 and c7 and c8:
            return RuleResult(
                triggered=True, side="buy", confidence=72.0,
                reasons=[f"TT close={last_close:.0f} ma50={last_ma50:.0f} ma200={last_ma200:.0f} rs={rs_value}"],
                metadata={"rs": float(rs_value)},
            )
        return RuleResult(triggered=False)


@dataclass
class rule_vcp_breakout(Rule):
    """VCP 베이스(≥25일) + 진폭 수축 + 거래량 dry-up + 피벗 돌파 + RVOL."""
    name: str = "vcp_breakout"
    base_min_bars: int = 25
    rvol_threshold: float = 1.5
    dryup_ratio_max: float = 0.7  # 베이스 평균 거래량 / 직전 20일 평균 ≤ 0.7
    contraction_ratio_max: float = 0.6  # 후반 진폭 / 전반 진폭 ≤ 0.6

    def evaluate(self, df: pd.DataFrame, ctx: Dict[str, Any]) -> RuleResult:
        if len(df) < self.base_min_bars + 21:
            return RuleResult(triggered=False)

        base = df.iloc[-(self.base_min_bars + 1):-1]
        pre_base = df.iloc[-(self.base_min_bars + 21):-(self.base_min_bars + 1)]
        last = df.iloc[-1]

        pivot = float(base["high"].max())
        last_close = float(last["close"])
        last_vol = float(last["volume"])

        # 1. 피벗 돌파
        if last_close <= pivot:
            return RuleResult(triggered=False)

        # 2. RVOL (최근 봉 거래량 / 베이스 평균 거래량)
        base_avg_vol = float(base["volume"].mean())
        if base_avg_vol <= 0:
            return RuleResult(triggered=False)
        rvol = last_vol / base_avg_vol
        if rvol < self.rvol_threshold:
            return RuleResult(triggered=False)

        # 3. 거래량 dry-up: 베이스 평균 < pre_base 평균 × dryup_ratio_max
        pre_base_avg_vol = float(pre_base["volume"].mean())
        if pre_base_avg_vol <= 0 or base_avg_vol / pre_base_avg_vol > self.dryup_ratio_max:
            return RuleResult(triggered=False)

        # 4. 진폭 수축: 베이스 전반 12봉 진폭 vs 후반 12봉 진폭
        mid = len(base) // 2
        early_range = float((base["high"].iloc[:mid] - base["low"].iloc[:mid]).mean())
        late_range = float((base["high"].iloc[mid:] - base["low"].iloc[mid:]).mean())
        if early_range <= 0 or late_range / early_range > self.contraction_ratio_max:
            return RuleResult(triggered=False)

        return RuleResult(
            triggered=True, side="buy", confidence=75.0,
            reasons=[
                f"vcp_breakout pivot={pivot:.0f} close={last_close:.0f} rvol={rvol:.2f} "
                f"dryup={base_avg_vol/pre_base_avg_vol:.2f} contract={late_range/early_range:.2f}"
            ],
            metadata={"pivot": pivot, "rvol": rvol},
        )


def _find_swing_pivots(
    high: np.ndarray, low: np.ndarray, span: int
) -> Tuple[List[int], List[int]]:
    """span 좌우 윈도우 기준 local high/low 인덱스 목록 (no-lookahead 무관: 입력 배열 내부만).

    피크: high[i] 가 [i-span, i+span] 구간 최대. 트로프: low[i] 가 동 구간 최소.
    경계(span 미만 양끝)는 제외. 동일 극값 평탄구간은 첫 인덱스만 채택.
    """
    n = len(high)
    peaks: List[int] = []
    troughs: List[int] = []
    for i in range(span, n - span):
        win_h = high[i - span : i + span + 1]
        win_l = low[i - span : i + span + 1]
        if high[i] >= win_h.max() and high[i] > high[i - 1]:
            peaks.append(i)
        if low[i] <= win_l.min() and low[i] < low[i - 1]:
            troughs.append(i)
    return peaks, troughs


def _find_contraction_legs(
    high: np.ndarray, low: np.ndarray, volume: np.ndarray, swing_span: int
) -> List[Dict[str, float]]:
    """base 구간에서 peak→다음 trough 로 이어지는 수축 leg 시퀀스 검출.

    각 leg: {peak_idx, trough_idx, peak, trough, depth(낙폭%), avg_vol}.
    peak 다음에 오는 가장 가까운 trough 와 짝지어 leg 구성, 시간순 정렬.
    """
    peaks, troughs = _find_swing_pivots(high, low, swing_span)
    legs: List[Dict[str, float]] = []
    troughs_sorted = sorted(troughs)
    for p in sorted(peaks):
        # p 이후 첫 trough
        nxt = next((t for t in troughs_sorted if t > p), None)
        if nxt is None:
            continue
        peak_v = float(high[p])
        trough_v = float(low[nxt])
        if peak_v <= 0:
            continue
        depth = (peak_v - trough_v) / peak_v
        if depth <= 0:
            continue
        avg_vol = float(volume[p : nxt + 1].mean()) if nxt >= p else float(volume[p])
        legs.append({
            "peak_idx": float(p), "trough_idx": float(nxt),
            "peak": peak_v, "trough": trough_v,
            "depth": depth, "avg_vol": avg_vol,
        })
    # peak_idx 중복(같은 봉이 여러 leg 시작) 제거: 더 앞선 trough 우선 (시퀀스 단조)
    dedup: List[Dict[str, float]] = []
    last_trough = -1.0
    for leg in sorted(legs, key=lambda x: (x["peak_idx"], x["trough_idx"])):
        if leg["peak_idx"] <= last_trough:
            continue  # 직전 leg 안에 포함된 노이즈 peak 스킵
        dedup.append(leg)
        last_trough = leg["trough_idx"]
    return dedup


@dataclass
class rule_vcp_contraction_breakout(Rule):
    """책 핵심 VCP — 연속 수축파동 단계축소 + contraction별 거래량 감소 + 피벗 돌파 + RVOL.

    (기존 rule_vcp_breakout 의 전/후반 진폭 비교 proxy 와 달리) base 구간에서
    이산적 수축 leg(2~4회)를 검출해 각 낙폭이 단계적으로 좁아지는지·거래량이
    leg 마다 감소(dry-up)하는지를 직접 검증한다. no-lookahead: df.iloc[:t+1] 만 사용.
    """
    name: str = "vcp_contraction_breakout"
    base_lookback: int = 60        # 베이스 룩백(거래일). 7주~수개월
    swing_span: int = 2            # swing pivot 좌우 윈도우
    min_contractions: int = 2      # 최소 수축파동 수
    max_contractions: int = 4      # 최대 수축파동 수(초과시 최근 max개 사용)
    contraction_shrink_ratio: float = 0.85  # 각 leg 낙폭 ≤ 직전×ratio (단계축소)
    volume_shrink_ratio: float = 1.0         # 각 leg 평균거래량 ≤ 직전×ratio (dry-up)
    pivot_buffer: float = 0.0      # 종가 > 피벗×(1+buffer)
    rvol_mult: float = 1.5         # 돌파봉 거래량 ≥ base 평균×rvol_mult
    max_last_depth: float = 0.15   # 마지막(가장 타이트) 수축 낙폭 상한

    def evaluate(self, df: pd.DataFrame, ctx: Dict[str, Any]) -> RuleResult:
        if len(df) < self.base_lookback + 1:
            return RuleResult(triggered=False)

        # base = 직전 base_lookback 봉(현재봉 제외), 현재봉 = 돌파 후보
        base = df.iloc[-(self.base_lookback + 1):-1]
        last = df.iloc[-1]
        high = base["high"].astype(float).to_numpy()
        low = base["low"].astype(float).to_numpy()
        volume = base["volume"].astype(float).to_numpy()

        legs = _find_contraction_legs(high, low, volume, self.swing_span)
        if len(legs) < self.min_contractions:
            return RuleResult(triggered=False)

        # 가장 최근 max_contractions 개 leg 사용
        legs = legs[-self.max_contractions:]
        if len(legs) < self.min_contractions:
            return RuleResult(triggered=False)

        # 1. 단계적 낙폭 축소: 각 leg depth ≤ 직전 depth × shrink_ratio
        for prev, cur in zip(legs[:-1], legs[1:]):
            if cur["depth"] > prev["depth"] * self.contraction_shrink_ratio:
                return RuleResult(triggered=False)

        # 2. 마지막 수축이 충분히 타이트
        if legs[-1]["depth"] > self.max_last_depth:
            return RuleResult(triggered=False)

        # 3. contraction 별 거래량 감소(dry-up 시퀀스)
        for prev, cur in zip(legs[:-1], legs[1:]):
            if prev["avg_vol"] <= 0:
                return RuleResult(triggered=False)
            if cur["avg_vol"] > prev["avg_vol"] * self.volume_shrink_ratio:
                return RuleResult(triggered=False)

        # 4. 피벗 = 마지막 수축 leg 의 고점. 종가 돌파.
        pivot = float(legs[-1]["peak"])
        last_close = float(last["close"])
        if last_close <= pivot * (1.0 + self.pivot_buffer):
            return RuleResult(triggered=False)

        # 5. RVOL: 돌파봉 거래량 ≥ base 평균 × rvol_mult
        base_avg_vol = float(volume.mean())
        last_vol = float(last["volume"])
        if base_avg_vol <= 0:
            return RuleResult(triggered=False)
        rvol = last_vol / base_avg_vol
        if rvol < self.rvol_mult:
            return RuleResult(triggered=False)

        depths = [round(l["depth"], 3) for l in legs]
        return RuleResult(
            triggered=True, side="buy", confidence=78.0,
            reasons=[
                f"vcp_contraction n={len(legs)} depths={depths} "
                f"pivot={pivot:.0f} close={last_close:.0f} rvol={rvol:.2f}"
            ],
            metadata={
                "pivot": pivot, "rvol": rvol, "n_contractions": len(legs),
                "last_depth": legs[-1]["depth"],
            },
        )


@dataclass
class rule_tight_closes(Rule):
    """3주(15봉) 종가 변동폭 ≤ 1.5%."""
    name: str = "tight_closes"
    window: int = 15
    range_pct_max: float = 0.015

    def evaluate(self, df: pd.DataFrame, ctx: Dict[str, Any]) -> RuleResult:
        if len(df) < self.window:
            return RuleResult(triggered=False)
        recent_close = df["close"].astype(float).iloc[-self.window:]
        mean_close = recent_close.mean()
        if mean_close <= 0:
            return RuleResult(triggered=False)
        range_pct = (recent_close.max() - recent_close.min()) / mean_close
        if range_pct <= self.range_pct_max:
            return RuleResult(
                triggered=True, side="buy", confidence=60.0,
                reasons=[f"tight_closes range={range_pct:.3%} ≤ {self.range_pct_max:.1%}"],
            )
        return RuleResult(triggered=False)


@dataclass
class rule_volume_dryup(Rule):
    """최근 10봉 평균 거래량 ≤ 직전 30봉 평균의 70%."""
    name: str = "volume_dryup"
    recent_window: int = 10
    base_window: int = 30
    ratio_max: float = 0.7

    def evaluate(self, df: pd.DataFrame, ctx: Dict[str, Any]) -> RuleResult:
        if len(df) < self.recent_window + self.base_window:
            return RuleResult(triggered=False)
        vol = df["volume"].astype(float)
        recent_avg = float(vol.iloc[-self.recent_window:].mean())
        base_avg = float(vol.iloc[-(self.recent_window + self.base_window):-self.recent_window].mean())
        if base_avg <= 0:
            return RuleResult(triggered=False)
        ratio = recent_avg / base_avg
        if ratio <= self.ratio_max:
            return RuleResult(
                triggered=True, side="buy", confidence=58.0,
                reasons=[f"volume_dryup recent/base={ratio:.2f} ≤ {self.ratio_max:.2f}"],
            )
        return RuleResult(triggered=False)


ALL_RULES = [
    rule_trend_template,
    rule_vcp_breakout,
    rule_vcp_contraction_breakout,
    rule_tight_closes,
    rule_volume_dryup,
]
