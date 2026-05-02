"""단타 페르소나 — 일봉 모멘텀 기반 (호가 없는 일봉 단타).

알고리즘 요약:
  - Universe: corp_events 필터 후 5일 변동성 z-score 정규화 상위 20종목
  - Scorer: Universe._score_cache에서 정규화 점수 조회 (재계산 없음)
  - Regime: 항상 risk_on (단타는 국면 무관 단기 기회 포착)
  - SignalGen: Universe 상위 통과 + 전일 양봉(종가>시가) + 거래량 급증(2.0배 이상) 이면 BUY
  - Sizer: 소형 포지션 — max_weight_per_stock * 0.5
  - ExitRule: 다음 날 EOD 청산 (held_days >= 1) 또는 hard_stop_pct 손절
  - Rebalancer: 매일 (daily)
  - HoldingCap: 1일 강제 청산 (holding_max_days=1 강제 적용)
"""
from __future__ import annotations

import math
from datetime import date
from typing import Dict, Tuple

import pandas as pd

from RoboTrader_template.multiverse.composable.paramset import ParamSet
from RoboTrader_template.multiverse.composable.strategy import ComposableStrategy
from RoboTrader_template.multiverse.engine.pit_engine import PITContext

_UNIVERSE_TOP_N = 20
_VOL_WINDOW = 5
_VOL_SURGE_RATIO = 2.0  # 거래비용 보정: 단타 245bp+슬리피지 50bp → 2.0배로 강화
_INTRADAY_HOLD_DAYS = 1  # 단타 최대 보유일 강제

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


class _IntradayUniverse:
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
        """5일 변동성(일봉 수익률 표준편차) raw → z-score 정규화."""
        vol_raw: list[float] = []

        for sym in symbols:
            df = ctx.read_daily(symbol=sym, lookback_days=_VOL_WINDOW + 2)
            if df is not None and not df.empty and len(df) >= _VOL_WINDOW:
                try:
                    closes = df["close"].astype(float)
                    v = float(closes.pct_change().dropna().std())
                    vol_raw.append(v if not math.isnan(v) else math.nan)
                except Exception:
                    vol_raw.append(math.nan)
            else:
                vol_raw.append(math.nan)

        vol_z = _z_normalize(vol_raw)

        scores: Dict[str, float] = {}
        for i, sym in enumerate(symbols):
            scores[sym] = vol_z[i]
        return scores


class _IntradayScorer:
    def __init__(self, universe: _IntradayUniverse) -> None:
        self._universe = universe

    def score(self, ctx: PITContext, symbol: str, paramset: ParamSet) -> float:
        """Universe 캐시에서 정규화 점수 조회. 캐시 미스 시 0.0."""
        cache_key = (ctx.as_of_date, paramset.config_hash())
        scores = self._universe._score_cache.get(cache_key, {})
        return scores.get(symbol, 0.0)


class _IntradayRegime:
    def is_risk_on(self, ctx: PITContext, paramset: ParamSet) -> bool:
        # 단타는 시장 국면과 무관하게 단기 기회 포착 — 항상 True
        return True


class _IntradaySignalGen:
    def __init__(self, universe: _IntradayUniverse) -> None:
        self._universe = universe

    def generate(self, ctx: PITContext, symbol: str, paramset: ParamSet) -> str:
        """Universe 상위 통과 + 전일 양봉 + 거래량 2.0배 급증 이면 BUY."""
        # Universe 상위 통과 가드
        cache_key = (ctx.as_of_date, paramset.config_hash())
        scores = self._universe._score_cache.get(cache_key, {})
        if symbol not in scores:
            return "HOLD"

        df = ctx.read_daily(symbol=symbol, lookback_days=_VOL_WINDOW + 2)
        if df is None or df.empty or len(df) < 2:
            return "HOLD"

        df = df.sort_values("date").reset_index(drop=True)

        try:
            prev = df.iloc[-1]
            prev_open = float(prev.get("open", 0) or 0)
            prev_close = float(prev.get("close", 0) or 0)
            prev_vol = float(prev.get("volume", 0) or 0)
        except Exception:
            return "HOLD"

        if prev_open <= 0 or prev_close <= 0:
            return "HOLD"

        # 전일 양봉 확인
        is_bullish = prev_close > prev_open

        # 거래량 급증 확인 (최근 _VOL_WINDOW일 평균 대비 2.0배 이상)
        if len(df) >= _VOL_WINDOW + 1:
            avg_vol = float(
                df["volume"].astype(float).iloc[-(_VOL_WINDOW + 1):-1].mean()
            )
            vol_surge = (avg_vol > 0) and (prev_vol >= avg_vol * _VOL_SURGE_RATIO)
        else:
            vol_surge = False

        if is_bullish and vol_surge:
            return "BUY"
        return "HOLD"


class _IntradaySizer:
    def size(self, capital: float, score: float, paramset: ParamSet) -> int:
        """소형 포지션 — max_weight_per_stock * 0.5."""
        target_value = capital * paramset.max_weight_per_stock * 0.5
        qty = int(target_value / 30_000)  # 단타 평균 주가 3만원 가정
        return max(qty, 1)


class _IntradayExitRule:
    def should_exit(
        self, ctx: PITContext, position: dict, paramset: ParamSet
    ) -> tuple[bool, str]:
        """다음 날 EOD 청산 (held_days >= 1) 또는 손절."""
        held_days = position.get("held_days", 0)
        if held_days >= _INTRADAY_HOLD_DAYS:
            return True, "eod_intraday"

        entry_price = position.get("entry_price", 0.0)
        current_price = position.get("current_price", entry_price)
        if entry_price > 0:
            ret = (current_price - entry_price) / entry_price
            if ret < paramset.hard_stop_pct:
                return True, "hard_stop"

        return False, ""


class _IntradayRebalancer:
    def should_rebalance(self, current_date: date, paramset: ParamSet) -> bool:
        return True  # 단타 — 매일 리밸런싱


class _IntradayHoldingCap:
    def should_force_exit_by_age(
        self, position: dict, current_date: date, paramset: ParamSet
    ) -> bool:
        # 단타 고정 1일 상한 강제 (paramset.holding_max_days 무시)
        return position.get("held_days", 0) >= _INTRADAY_HOLD_DAYS


def build_intraday_strategy(
    paramset: ParamSet, candidate_symbols: list[str]
) -> ComposableStrategy:
    """단타(일봉 모멘텀) 페르소나 ComposableStrategy 팩토리."""
    universe = _IntradayUniverse(candidate_symbols)
    scorer = _IntradayScorer(universe)
    signal_gen = _IntradaySignalGen(universe)
    return ComposableStrategy(
        paramset=paramset,
        universe=universe,
        scorer=scorer,
        regime=_IntradayRegime(),
        signal_gen=signal_gen,
        sizer=_IntradaySizer(),
        exit_rule=_IntradayExitRule(),
        rebalancer=_IntradayRebalancer(),
        holding_cap=_IntradayHoldingCap(),
    )
