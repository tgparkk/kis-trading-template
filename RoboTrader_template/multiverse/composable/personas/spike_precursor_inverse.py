"""spike_precursor_inverse 페르소나 — 반전 가설: 조용한 종목이 깨어나기 직전.

반전 가설:
  원본 그리드(고거래량·고점 진입)는 100셀 전손 → 시그널 방향이 정반대일 가능성.
  진짜 선행 시그널은 거래량 침체 + MA20 아래 + 좁은 박스권 → 깨어나기 직전.

원본(spike_precursor)과의 비교방향 차이:
  F1 vol_zscore_20: 원본은 >= thresh, 반전은 <= thresh (거래량 침체)
  F2 ma20_dist: 원본과 같은 범위 비교, 반전 그리드는 음수 범위 사용
  F3 atr_ratio: 원본과 동일 방향(<=), 반전 그리드는 더 낮은 임계값
  F4 box_squeeze: 원본과 동일 방향(<=), 반전 그리드는 더 좁은 임계값
  F5 vol_trend: 원본은 >= thresh, 반전은 <= thresh (거래량 감소)
"""
from __future__ import annotations

from datetime import date
from typing import Optional

from RoboTrader_template.multiverse.composable.paramset import ParamSet
from RoboTrader_template.multiverse.composable.strategy import ComposableStrategy
from RoboTrader_template.multiverse.composable.features.spike_features import (
    compute_all_features,
)
from RoboTrader_template.multiverse.engine.pit_engine import PITContext


class _SpikeInverseUniverse:
    """corp_events 필터만 적용 — 반전 가설도 종목별 독립 평가."""

    def __init__(self, candidate_symbols: list[str]) -> None:
        self.candidates = candidate_symbols

    def select(self, ctx: PITContext, paramset: ParamSet) -> list[str]:
        from RoboTrader_template.multiverse.data import corp_events

        return corp_events.filter_universe(self.candidates, ctx.as_of_date)


class _SpikeInverseScorer:
    """반전 조건 매칭 피처 개수를 점수로 반환 (0~5 정수)."""

    def score(self, ctx: PITContext, symbol: str, paramset: ParamSet) -> float:
        df = ctx.read_daily(symbol=symbol, lookback_days=30)
        if df is None or df.empty:
            return 0.0
        features = compute_all_features(df)
        return float(_count_inverse_matches(features, paramset))


class _SpikeInverseRegime:
    """항상 risk_on=True — regime 필터 없음."""

    def is_risk_on(self, ctx: PITContext, paramset: ParamSet) -> bool:
        return True


class _SpikeInverseSignalGen:
    """반전 로직: 거래량 침체 + MA20 아래 + 좁은 박스권 → BUY/HOLD.

    비교방향:
      F1: vol_zscore_20 <= spike_vol_z_thresh  (원본은 >=)
      F2: spike_ma20_dist_min <= ma20_dist <= spike_ma20_dist_max (범위 동일, 음수 영역)
      F3: atr_ratio <= spike_atr_max            (원본과 동일, 더 낮은 임계값)
      F4: box_squeeze <= spike_box_max           (원본과 동일, 더 좁은 임계값)
      F5: vol_trend <= spike_vol_trend_min       (원본은 >=)
    """

    def generate(self, ctx: PITContext, symbol: str, paramset: ParamSet) -> str:
        df = ctx.read_daily(symbol=symbol, lookback_days=30)
        if df is None or df.empty:
            return "HOLD"

        features = compute_all_features(df)
        match_count = _count_inverse_matches(features, paramset)
        if match_count >= paramset.spike_match_min:
            return "BUY"
        return "HOLD"


def _count_inverse_matches(
    features: dict[str, Optional[float]], paramset: ParamSet
) -> int:
    """반전 5개 피처 임계값 조건 확인, 충족 개수 반환.

    None 값은 해당 피처 불충족(0점)으로 처리.
    """
    count = 0

    # F1: vol_zscore_20 <= spike_vol_z_thresh (침체/평소 수준 — 원본과 반대)
    v1 = features.get("vol_zscore_20")
    if v1 is not None and v1 <= paramset.spike_vol_z_thresh:
        count += 1

    # F2: spike_ma20_dist_min <= ma20_dist <= spike_ma20_dist_max (음수 범위)
    v2 = features.get("ma20_dist")
    if (
        v2 is not None
        and paramset.spike_ma20_dist_min <= v2 <= paramset.spike_ma20_dist_max
    ):
        count += 1

    # F3: atr_ratio <= spike_atr_max (매우 낮은 변동성 — 방향 동일, 임계값 낮음)
    v3 = features.get("atr_ratio")
    if v3 is not None and v3 <= paramset.spike_atr_max:
        count += 1

    # F4: box_squeeze <= spike_box_max (매우 좁은 박스 — 방향 동일, 임계값 낮음)
    v4 = features.get("box_squeeze")
    if v4 is not None and v4 <= paramset.spike_box_max:
        count += 1

    # F5: vol_trend <= spike_vol_trend_min (거래량 감소 추세 — 원본과 반대)
    v5 = features.get("vol_trend")
    if v5 is not None and v5 <= paramset.spike_vol_trend_min:
        count += 1

    return count


class _SpikeInverseSizer:
    """1/N 균등 사이징 (max_weight_per_stock 비율, 평균 주가 5만원 가정)."""

    def size(self, capital: float, score: float, paramset: ParamSet) -> int:
        target_value = capital * paramset.max_weight_per_stock
        qty = int(target_value / 50_000)
        return max(qty, 1)


class _SpikeInverseExitRule:
    """held_days >= 1 이면 D+1 종가 청산 (원본과 동일)."""

    def should_exit(
        self, ctx: PITContext, position: dict, paramset: ParamSet
    ) -> tuple[bool, str]:
        held_days = position.get("held_days", 0)
        if held_days >= 1:
            return True, "intraday_d+1"
        return False, ""


class _SpikeInverseRebalancer:
    """매일 신호 점검 (daily)."""

    def should_rebalance(self, current_date: date, paramset: ParamSet) -> bool:
        return True


class _SpikeInverseHoldingCap:
    """held_days >= 1 강제 청산 (1일 보유 고정)."""

    def should_force_exit_by_age(
        self, position: dict, current_date: date, paramset: ParamSet
    ) -> bool:
        return position.get("held_days", 0) >= 1


def build_spike_precursor_inverse_strategy(
    paramset: ParamSet, candidate_symbols: list[str]
) -> ComposableStrategy:
    """spike_precursor_inverse 페르소나 ComposableStrategy 팩토리."""
    return ComposableStrategy(
        paramset=paramset,
        universe=_SpikeInverseUniverse(candidate_symbols),
        scorer=_SpikeInverseScorer(),
        regime=_SpikeInverseRegime(),
        signal_gen=_SpikeInverseSignalGen(),
        sizer=_SpikeInverseSizer(),
        exit_rule=_SpikeInverseExitRule(),
        rebalancer=_SpikeInverseRebalancer(),
        holding_cap=_SpikeInverseHoldingCap(),
    )
