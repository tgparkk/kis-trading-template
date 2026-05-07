"""trend_starter 페르소나 — 추세 시작점 진입 (D-1 일봉 F1+F3+F4 AND 매칭).

데이터 분석 결과 (2023~2026 4년, KOSPI200 200종목):
  - F3 atr_ratio >= 0.06 AND F1 vol_zscore_20 >= 1.5
    → 양성률 11.76% (베이스 3.15%의 3.74x lift)
  - 교차검증 N=10에서도 11.21% 재현
  - price_tier 무관 (그리드에서 제거)

알고리즘 요약:
  - Universe: corp_events 필터만 — 종목별 독립 평가
  - Scorer: 매칭된 피처 개수 (0~3 정수)
  - Regime: risk_on=True 고정
  - SignalGen: 핵심 — F1+F3+F4 모두 AND 충족 → BUY
      F1: vol_zscore_20 >= ts_volz_min
      F3: atr_ratio       >= ts_atr_min
      F4: box_squeeze     >= ts_box_min
  - Sizer: 1/N 균등 (max_weight_per_stock 사용)
  - ExitRule: 익절(>= ts_target_pct) OR 손절(<= ts_stop_pct) → True
  - Rebalancer: daily
  - HoldingCap: held_days >= ts_hold_days 강제 청산
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


class _TSUniverse:
    """corp_events 필터만 적용 — 종목별 독립 평가 (z-score 정규화 없음)."""

    def __init__(self, candidate_symbols: list[str]) -> None:
        self.candidates = candidate_symbols

    def select(self, ctx: PITContext, paramset: ParamSet) -> list[str]:
        from RoboTrader_template.multiverse.data import corp_events

        return corp_events.filter_universe(self.candidates, ctx.as_of_date)


class _TSScorer:
    """매칭된 피처 개수를 점수로 반환 (0~3 정수)."""

    def score(self, ctx: PITContext, symbol: str, paramset: ParamSet) -> float:
        df = ctx.read_daily(symbol=symbol, lookback_days=30)
        if df is None or df.empty:
            return 0.0
        features = compute_all_features(df)
        return float(_count_ts_matches(features, paramset))


class _TSRegime:
    """항상 risk_on=True — regime 필터 없음."""

    def is_risk_on(self, ctx: PITContext, paramset: ParamSet) -> bool:
        return True


class _TSSignalGen:
    """핵심 로직: D-1 일봉 F1+F3+F4 AND 충족 → BUY/HOLD.

    AND 조건 (3개 모두 만족):
      F1: vol_zscore_20 >= ts_volz_min
      F3: atr_ratio       >= ts_atr_min
      F4: box_squeeze     >= ts_box_min
    """

    def generate(self, ctx: PITContext, symbol: str, paramset: ParamSet) -> str:
        df = ctx.read_daily(symbol=symbol, lookback_days=30)
        if df is None or df.empty:
            return "HOLD"

        features = compute_all_features(df)
        if _count_ts_matches(features, paramset) >= 3:
            return "BUY"
        return "HOLD"


def _count_ts_matches(
    features: dict[str, Optional[float]], paramset: ParamSet
) -> int:
    """F1+F3+F4 AND 충족 개수 반환 (0~3).

    None 값은 해당 피처 불충족(0점)으로 처리.
    BUY 결정은 호출측에서 == 3 비교.
    """
    count = 0

    # F1: vol_zscore_20 >= ts_volz_min
    v1 = features.get("vol_zscore_20")
    if v1 is not None and v1 >= paramset.ts_volz_min:
        count += 1

    # F3: atr_ratio >= ts_atr_min
    v3 = features.get("atr_ratio")
    if v3 is not None and v3 >= paramset.ts_atr_min:
        count += 1

    # F4: box_squeeze >= ts_box_min
    v4 = features.get("box_squeeze")
    if v4 is not None and v4 >= paramset.ts_box_min:
        count += 1

    return count


class _TSSizer:
    """1/N 균등 사이징 (max_weight_per_stock 비율, 평균 주가 5만원 가정)."""

    def size(self, capital: float, score: float, paramset: ParamSet) -> int:
        target_value = capital * paramset.max_weight_per_stock
        qty = int(target_value / 50_000)
        return max(qty, 1)


class _TSExitRule:
    """익절(>= ts_target_pct) OR 손절(<= ts_stop_pct) → SELL."""

    def should_exit(
        self, ctx: PITContext, position: dict, paramset: ParamSet
    ) -> tuple[bool, str]:
        entry_price = position.get("entry_price", 0.0)
        current_price = position.get("current_price", entry_price)
        if entry_price <= 0:
            return False, ""
        ret = (current_price - entry_price) / entry_price
        if ret >= paramset.ts_target_pct:
            return True, "take_profit"
        if ret <= paramset.ts_stop_pct:
            return True, "stop_loss"
        return False, ""


class _TSRebalancer:
    """매일 신호 점검 (daily)."""

    def should_rebalance(self, current_date: date, paramset: ParamSet) -> bool:
        return True


class _TSHoldingCap:
    """held_days >= ts_hold_days 강제 청산."""

    def should_force_exit_by_age(
        self, position: dict, current_date: date, paramset: ParamSet
    ) -> bool:
        return position.get("held_days", 0) >= paramset.ts_hold_days


def build_trend_starter_strategy(
    paramset: ParamSet, candidate_symbols: list[str]
) -> ComposableStrategy:
    """trend_starter 페르소나 ComposableStrategy 팩토리."""
    return ComposableStrategy(
        paramset=paramset,
        universe=_TSUniverse(candidate_symbols),
        scorer=_TSScorer(),
        regime=_TSRegime(),
        signal_gen=_TSSignalGen(),
        sizer=_TSSizer(),
        exit_rule=_TSExitRule(),
        rebalancer=_TSRebalancer(),
        holding_cap=_TSHoldingCap(),
    )
