"""스윙 페르소나 — 볼린저밴드 + RSI 회귀 전략 + z-score Universe 정렬.

알고리즘 요약:
  - Universe: corp_events 필터 후 5일 모멘텀 z-score 정규화 상위 10종목
  - Scorer: Universe._score_cache에서 정규화 점수 조회 (재계산 없음)
  - Regime: global_risk_mode != risk_off_avoid 이면 risk_on
  - SignalGen: Universe 상위 통과 + BB 하단 이탈 후 회복 + RSI < 40 이면 BUY
  - Sizer: 동일 비중 (equal weight)
  - ExitRule: RSI > exit_rsi_overbought OR 손절 hard_stop_pct 초과
  - Rebalancer: 매주 월요일
  - HoldingCap: holding_max_days 초과 강제 청산
"""
from __future__ import annotations

import math
from datetime import date
from typing import Dict, Tuple

import pandas as pd

from RoboTrader_template.multiverse.composable.paramset import ParamSet
from RoboTrader_template.multiverse.composable.strategy import ComposableStrategy
from RoboTrader_template.multiverse.engine.pit_engine import PITContext

_UNIVERSE_TOP_N = 10
_BB_PERIOD = 20
_BB_STD = 2.0
_RSI_PERIOD = 14

# 캐시 키: (as_of_date, config_hash) → {symbol: normalized_score}
_ScoreCache = Dict[Tuple, Dict[str, float]]


def _z_normalize(values: list[float]) -> list[float]:
    """Universe-wide z-score 정규화. std=0이면 0 반환."""
    finite = [v for v in values if not math.isnan(v)]
    if not finite:
        return [0.0] * len(values)
    mean = sum(finite) / len(finite)
    variance = sum((v - mean) ** 2 for v in finite) / len(finite)
    std = math.sqrt(variance)
    if std == 0:
        return [0.0] * len(values)
    return [(v - mean) / std if not math.isnan(v) else 0.0 for v in values]


def _calc_rsi(closes: pd.Series, period: int = 14) -> float:
    """단순 RSI 계산 — 마지막 값 반환."""
    if len(closes) < period + 1:
        return 50.0
    delta = closes.diff().dropna()
    gain = delta.clip(lower=0).rolling(period).mean()
    loss = (-delta.clip(upper=0)).rolling(period).mean()
    rs = gain / loss.replace(0, 1e-9)
    rsi = 100 - (100 / (1 + rs))
    last = rsi.iloc[-1]
    return float(last) if pd.notna(last) else 50.0


class _SwingUniverse:
    def __init__(self, candidate_symbols: list[str]) -> None:
        self.candidates = candidate_symbols
        # (as_of_date, config_hash) → {symbol: normalized_score}
        self._score_cache: _ScoreCache = {}

    def select(self, ctx: PITContext, paramset: ParamSet) -> list[str]:
        from RoboTrader_template.multiverse.data import corp_events

        filtered = corp_events.filter_universe(self.candidates, ctx.as_of_date)
        if not filtered:
            return []

        cache_key = (ctx.as_of_date, paramset.config_hash())
        if cache_key not in self._score_cache:
            self._score_cache[cache_key] = self._compute_scores(ctx, filtered)

        scores = self._score_cache[cache_key]
        ranked = sorted(scores, key=lambda s: scores[s], reverse=True)
        return ranked[:_UNIVERSE_TOP_N]

    def _compute_scores(
        self, ctx: PITContext, symbols: list[str]
    ) -> Dict[str, float]:
        """5일 모멘텀 raw → z-score 정규화."""
        mom_raw: list[float] = []

        for sym in symbols:
            df = ctx.read_daily(symbol=sym, lookback_days=10)
            if df is not None and not df.empty and len(df) >= 5:
                try:
                    m = float(df["close"].iloc[-1] / df["close"].iloc[-5] - 1)
                except Exception:
                    m = math.nan
            else:
                m = math.nan
            mom_raw.append(m)

        mom_z = _z_normalize(mom_raw)

        scores: Dict[str, float] = {}
        for i, sym in enumerate(symbols):
            scores[sym] = mom_z[i]
        return scores


class _SwingScorer:
    def __init__(self, universe: _SwingUniverse) -> None:
        self._universe = universe

    def score(self, ctx: PITContext, symbol: str, paramset: ParamSet) -> float:
        """Universe 캐시에서 정규화 점수 조회. 캐시 미스 시 0.0."""
        cache_key = (ctx.as_of_date, paramset.config_hash())
        scores = self._universe._score_cache.get(cache_key, {})
        return scores.get(symbol, 0.0)


class _SwingRegime:
    def is_risk_on(self, ctx: PITContext, paramset: ParamSet) -> bool:
        # positive_only 설정이면 엄격 모드 — 데모에선 항상 True 반환(실데이터 없음)
        return paramset.global_risk_mode != "risk_off_avoid"


class _SwingSignalGen:
    def __init__(self, universe: _SwingUniverse) -> None:
        self._universe = universe

    def generate(self, ctx: PITContext, symbol: str, paramset: ParamSet) -> str:
        """Universe 상위 통과 + BB 하단 이탈 후 회복 + RSI < 40 이면 BUY."""
        # Universe 상위 통과 가드
        cache_key = (ctx.as_of_date, paramset.config_hash())
        scores = self._universe._score_cache.get(cache_key, {})
        if symbol not in scores:
            return "HOLD"

        df = ctx.read_daily(symbol=symbol, lookback_days=_BB_PERIOD + 5)
        if df is None or df.empty or len(df) < _BB_PERIOD:
            return "HOLD"

        closes = df["close"].astype(float)
        bb_mid = closes.rolling(_BB_PERIOD).mean()
        bb_std = closes.rolling(_BB_PERIOD).std()
        bb_lower = bb_mid - _BB_STD * bb_std

        last_close = closes.iloc[-1]
        prev_close = closes.iloc[-2] if len(closes) >= 2 else last_close
        last_lower = float(bb_lower.iloc[-1]) if pd.notna(bb_lower.iloc[-1]) else 0.0
        prev_lower = float(bb_lower.iloc[-2]) if len(bb_lower) >= 2 and pd.notna(bb_lower.iloc[-2]) else 0.0

        # BB 하단 이탈 후 회복: 전일 close <= prev_lower, 당일 close > last_lower
        bb_bounce = (prev_close <= prev_lower) and (last_close > last_lower)

        rsi = _calc_rsi(closes, _RSI_PERIOD)
        if bb_bounce and rsi < 40:
            return "BUY"
        return "HOLD"


class _SwingSizer:
    def size(self, capital: float, score: float, paramset: ParamSet) -> int:
        """동일 비중 — max_positions 분의 1 할당."""
        n = max(paramset.max_positions, 1)
        target_value = capital / n
        qty = int(target_value / 50_000)  # 평균 주가 5만원 가정
        return max(qty, 1)


class _SwingExitRule:
    def should_exit(
        self, ctx: PITContext, position: dict, paramset: ParamSet
    ) -> tuple[bool, str]:
        """RSI 과열 또는 손절선 초과."""
        df = ctx.read_daily(symbol=position.get("symbol", ""), lookback_days=20)
        if df is not None and not df.empty:
            rsi = _calc_rsi(df["close"].astype(float), _RSI_PERIOD)
            if rsi > paramset.exit_rsi_overbought:
                return True, "rsi_overbought"

        entry_price = position.get("entry_price", 0.0)
        current_price = position.get("current_price", entry_price)
        if entry_price > 0:
            ret = (current_price - entry_price) / entry_price
            if ret < paramset.hard_stop_pct:
                return True, "hard_stop"

        return False, ""


class _SwingRebalancer:
    def should_rebalance(self, current_date: date, paramset: ParamSet) -> bool:
        return current_date.weekday() == 0  # 매주 월요일


class _SwingHoldingCap:
    def should_force_exit_by_age(
        self, position: dict, current_date: date, paramset: ParamSet
    ) -> bool:
        cap = paramset.holding_max_days
        if cap is None:
            return False
        return position.get("held_days", 0) >= cap


def build_swing_strategy(
    paramset: ParamSet, candidate_symbols: list[str]
) -> ComposableStrategy:
    """스윙 페르소나 ComposableStrategy 팩토리."""
    universe = _SwingUniverse(candidate_symbols)
    scorer = _SwingScorer(universe)
    signal_gen = _SwingSignalGen(universe)
    return ComposableStrategy(
        paramset=paramset,
        universe=universe,
        scorer=scorer,
        regime=_SwingRegime(),
        signal_gen=signal_gen,
        sizer=_SwingSizer(),
        exit_rule=_SwingExitRule(),
        rebalancer=_SwingRebalancer(),
        holding_cap=_SwingHoldingCap(),
    )
