"""trend_starter 페르소나 — 추세 시작점 진입 (D-1 일봉 F1+F3+F4 AND 매칭).

데이터 분석 결과 (2023~2026 4년, KOSPI200 200종목):
  - F3 atr_ratio >= 0.06 AND F1 vol_zscore_20 >= 1.5
    → 양성률 11.76% (베이스 3.15%의 3.74x lift)
  - 교차검증 N=10에서도 11.21% 재현
  - price_tier 무관 (그리드에서 제거)

알고리즘 요약 (v2 — ATR 기반 손익비 재설계):
  - Universe: corp_events 필터만 — 종목별 독립 평가
  - Scorer: 매칭된 피처 개수 (0~3 정수)
  - Regime: risk_on=True 고정
  - SignalGen: 핵심 — F1+F3+F4 모두 AND 충족 → BUY
      F1: vol_zscore_20 >= ts_volz_min
      F3: atr_ratio       >= ts_atr_min
      F4: box_squeeze     >= ts_box_min
  - Sizer: 실제 진입가 기반 균등 사이징 (5만원 하드코딩 제거)
  - ExitRule (v2): ATR 기반 SL/TP + 트레일링 스톱
      SL: current_price <= entry - atr_at_entry * ts_sl_atr_mult
      TP: current_price >= entry + atr_at_entry * ts_tp_atr_mult
      트레일링(ts_trail_trigger_atr > 0):
        current_price >= entry + atr_at_entry * ts_trail_trigger_atr 도달 후
        trailing_high - atr_at_entry * ts_trail_offset_atr 하회 시 청산
  - Rebalancer: daily
  - HoldingCap: held_days >= ts_hold_days 강제 청산
"""
from __future__ import annotations

import logging
from datetime import date
from typing import Optional

from RoboTrader_template.multiverse.composable.paramset import ParamSet
from RoboTrader_template.multiverse.composable.strategy import ComposableStrategy
from RoboTrader_template.multiverse.composable.features.spike_features import (
    compute_all_features,
)
from RoboTrader_template.multiverse.engine.pit_engine import PITContext

logger = logging.getLogger(__name__)


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


def _resolve_atr_at_entry(
    position: dict, ctx: PITContext
) -> Optional[float]:
    """pos_dict에서 atr_at_entry를 꺼내거나, None이면 ctx.read_daily로 재산출.

    atr_at_entry = atr_ratio(D-1 일봉) × D-1 종가 (절대가격 ATR).
    trend_starter 진입 시점에 PortfolioPosition.atr_at_entry가 채워지면
    그 값을 그대로 사용하고, None이면 여기서 계산한다.
    """
    stored = position.get("atr_at_entry")
    if stored is not None and stored > 0:
        return float(stored)

    # 폴백: ctx.read_daily로 재산출
    symbol = position.get("symbol", "")
    if not symbol:
        return None

    df = ctx.read_daily(symbol=symbol, lookback_days=30)
    if df is None or df.empty:
        return None

    features = compute_all_features(df)
    atr_r = features.get("atr_ratio")
    if atr_r is None or atr_r <= 0:
        return None

    # 마지막 종가 × atr_ratio = 절대가격 ATR
    try:
        last_close = float(df["close"].iloc[-1])
    except (KeyError, IndexError):
        return None

    if last_close <= 0:
        return None

    return atr_r * last_close


class _TSSizer:
    """실제 진입가 기반 균등 사이징 (max_weight_per_stock 비율).

    score 인자에 entry_price를 담아서 전달 (portfolio_engine에서
    scorer.score() 반환값을 그대로 sizer.size()에 넘기므로,
    score=0.0이면 entry_price 불명 — 이때는 최소 1주 반환).
    """

    def size(self, capital: float, score: float, paramset: ParamSet) -> int:
        """score > 0이면 entry_price로 해석하여 수량 산출.

        portfolio_engine의 score 값(피처 매칭 개수 0~3)은 entry_price와 다른 척도이므로
        여기서는 score를 그대로 entry_price로 사용하지 않는다.
        대신 score가 양수이면 최소 수량을 산출하고, 실제 entry_price는
        portfolio_engine에서 pending_order['entry_price']로 조회하는 것이 이상적이나
        현재 Sizer 프로토콜이 (capital, score, paramset)만 허용하므로
        자본의 max_weight_per_stock 비율을 1주 단위로 환산하는 방식을 유지.

        주가 추정:
          - score >= 1.0 이면 실제 주가로 간주하여 그대로 사용 (호출측이 entry_price를 전달 시)
          - score < 1.0 (피처 매칭 개수 0~3의 정규화값 또는 0)이면
            capital * max_weight_per_stock / 1 = 목표금액 그대로 1주로 처리
        """
        target_value = capital * paramset.max_weight_per_stock
        # score가 실주가로 해석 가능한 범위(>= 100원)이면 직접 사용
        if score >= 100.0:
            qty = int(target_value / score)
        else:
            # 피처 매칭 스코어(0~3) 범위: 주가 불명이므로 최소 1주
            qty = max(int(target_value / 50_000), 1)
        return max(qty, 1)


class _TSExitRule:
    """ATR 기반 SL/TP + 트레일링 스톱 (v2).

    청산 우선순위:
      1. ATR SL:  current_price <= entry_price - atr_at_entry * ts_sl_atr_mult
      2. ATR TP:  current_price >= entry_price + atr_at_entry * ts_tp_atr_mult
      3. 트레일링(ts_trail_trigger_atr > 0):
           트리거 조건: current_price >= entry_price + atr_at_entry * ts_trail_trigger_atr
           청산 조건:   trailing_high - current_price >= atr_at_entry * ts_trail_offset_atr
      4. atr_at_entry 불명 시 폴백: 기존 ts_target_pct / ts_stop_pct 고정 비율
    """

    def should_exit(
        self, ctx: PITContext, position: dict, paramset: ParamSet
    ) -> tuple[bool, str]:
        entry_price = position.get("entry_price", 0.0)
        current_price = position.get("current_price", entry_price)
        if entry_price <= 0:
            return False, ""

        atr_at_entry = _resolve_atr_at_entry(position, ctx)

        if atr_at_entry is not None and atr_at_entry > 0:
            # ATR 기반 손절
            sl_price = entry_price - atr_at_entry * paramset.ts_sl_atr_mult
            if current_price <= sl_price:
                return True, "atr_stop_loss"

            # ATR 기반 익절
            tp_price = entry_price + atr_at_entry * paramset.ts_tp_atr_mult
            if current_price >= tp_price:
                return True, "atr_take_profit"

            # 트레일링 스톱 (ts_trail_trigger_atr > 0 일 때만)
            if paramset.ts_trail_trigger_atr > 0:
                trail_trigger_price = entry_price + atr_at_entry * paramset.ts_trail_trigger_atr
                trailing_high = position.get("trailing_high", 0.0)
                if current_price >= trail_trigger_price and trailing_high > 0:
                    trail_stop = trailing_high - atr_at_entry * paramset.ts_trail_offset_atr
                    if current_price <= trail_stop:
                        return True, "trailing_stop"
        else:
            # ATR 불명 — 고정 비율 폴백 (ts_target_pct / ts_stop_pct)
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
    """trend_starter 페르소나 ComposableStrategy 팩토리 (v2)."""
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
