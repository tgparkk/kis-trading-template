"""spike_precursor 페르소나 — 장초 급등 선행 시그널 (D-1 일봉 5 피처 룰 매칭).

알고리즘 요약:
  - Universe: corp_events 필터만 (z-score 정규화 없음 — 종목별 독립 평가)
  - Scorer: signal_gen에서 매칭된 피처 개수 (정수 0~5)
  - Regime: risk_on=True 고정 (regime 무관)
  - SignalGen: 핵심 로직
      ctx.read_daily(symbol, lookback_days=30) → compute_all_features()
      5개 피처 임계값 매칭 → 매칭수 >= spike_match_min 이면 BUY
  - Sizer: 1/N 균등 (max_weight_per_stock 사용)
  - ExitRule: held_days >= 1 → True (D+1 종가 청산)
  - Rebalancer: daily (매일 신호 점검)
  - HoldingCap: held_days >= 1 강제 청산
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


class _SpikeUniverse:
    """corp_events 필터만 적용 — z-score 정규화 없음 (종목별 독립 평가)."""

    def __init__(self, candidate_symbols: list[str]) -> None:
        self.candidates = candidate_symbols

    def select(self, ctx: PITContext, paramset: ParamSet) -> list[str]:
        from RoboTrader_template.multiverse.data import corp_events

        return corp_events.filter_universe(self.candidates, ctx.as_of_date)


class _SpikeScorer:
    """매칭된 피처 개수를 점수로 반환 (0~5 정수).

    signal_gen 이후에 호출되므로 캐시 없이 단순 재계산.
    """

    def score(self, ctx: PITContext, symbol: str, paramset: ParamSet) -> float:
        df = ctx.read_daily(symbol=symbol, lookback_days=30)
        if df is None or df.empty:
            return 0.0
        features = compute_all_features(df)
        return float(_count_matches(features, paramset))


class _SpikeRegime:
    """항상 risk_on=True — spike는 regime 필터 없음."""

    def is_risk_on(self, ctx: PITContext, paramset: ParamSet) -> bool:
        return True


class _SpikeSignalGen:
    """핵심 로직: D-1 일봉 피처 5개 임계값 매칭 → BUY/HOLD."""

    def generate(self, ctx: PITContext, symbol: str, paramset: ParamSet) -> str:
        df = ctx.read_daily(symbol=symbol, lookback_days=30)
        if df is None or df.empty:
            return "HOLD"

        features = compute_all_features(df)

        # 5개 피처 중 어느 하나라도 None이 많으면 매칭수 부족 → HOLD 가능
        match_count = _count_matches(features, paramset)
        if match_count >= paramset.spike_match_min:
            return "BUY"
        return "HOLD"


def _count_matches(
    features: dict[str, Optional[float]], paramset: ParamSet
) -> int:
    """5개 피처 임계값 조건을 확인하고 충족한 개수 반환.

    None 값은 해당 피처 불충족(0점)으로 처리.
    """
    count = 0

    # F1: vol_zscore_20 >= spike_vol_z_thresh
    v1 = features.get("vol_zscore_20")
    if v1 is not None and v1 >= paramset.spike_vol_z_thresh:
        count += 1

    # F2: spike_ma20_dist_min <= ma20_dist <= spike_ma20_dist_max
    v2 = features.get("ma20_dist")
    if (
        v2 is not None
        and paramset.spike_ma20_dist_min <= v2 <= paramset.spike_ma20_dist_max
    ):
        count += 1

    # F3: atr_ratio <= spike_atr_max (변동성 압축)
    v3 = features.get("atr_ratio")
    if v3 is not None and v3 <= paramset.spike_atr_max:
        count += 1

    # F4: box_squeeze <= spike_box_max (박스권 압축)
    v4 = features.get("box_squeeze")
    if v4 is not None and v4 <= paramset.spike_box_max:
        count += 1

    # F5: vol_trend >= spike_vol_trend_min (거래량 가속)
    v5 = features.get("vol_trend")
    if v5 is not None and v5 >= paramset.spike_vol_trend_min:
        count += 1

    return count


class _SpikeSizer:
    """1/N 균등 사이징 (max_weight_per_stock 비율, 평균 주가 5만원 가정)."""

    def size(self, capital: float, score: float, paramset: ParamSet) -> int:
        target_value = capital * paramset.max_weight_per_stock
        qty = int(target_value / 50_000)  # 평균 주가 5만원 가정
        return max(qty, 1)


class _SpikeExitRule:
    """held_days >= 1 이면 D+1 종가 청산."""

    def should_exit(
        self, ctx: PITContext, position: dict, paramset: ParamSet
    ) -> tuple[bool, str]:
        held_days = position.get("held_days", 0)
        if held_days >= 1:
            return True, "intraday_d+1"
        return False, ""


class _SpikeRebalancer:
    """매일 신호 점검 (daily)."""

    def should_rebalance(self, current_date: date, paramset: ParamSet) -> bool:
        return True


class _SpikeHoldingCap:
    """held_days >= 1 강제 청산 (holding_max_days 파라미터 무시하고 1일 고정)."""

    def should_force_exit_by_age(
        self, position: dict, current_date: date, paramset: ParamSet
    ) -> bool:
        return position.get("held_days", 0) >= 1


def build_spike_precursor_strategy(
    paramset: ParamSet, candidate_symbols: list[str]
) -> ComposableStrategy:
    """spike_precursor 페르소나 ComposableStrategy 팩토리."""
    return ComposableStrategy(
        paramset=paramset,
        universe=_SpikeUniverse(candidate_symbols),
        scorer=_SpikeScorer(),
        regime=_SpikeRegime(),
        signal_gen=_SpikeSignalGen(),
        sizer=_SpikeSizer(),
        exit_rule=_SpikeExitRule(),
        rebalancer=_SpikeRebalancer(),
        holding_cap=_SpikeHoldingCap(),
    )
