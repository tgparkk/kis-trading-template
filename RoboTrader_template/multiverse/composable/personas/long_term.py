"""중장기 페르소나 — PBR + ROE + 성장률 z-score 정규화.

알고리즘 요약:
  - Universe: corp_events 필터 후 z-score 정규화 팩터 상위 factor_top_n
  - Scorer: Universe._score_cache에서 정규화 점수 조회 (재계산 없음)
  - Regime: global_risk_mode 기반 (risk_off_avoid 이면 회피)
  - SignalGen: pbr < 3 AND roe > 10% 이면 BUY (한국시장 분포 기준 완화)
  - Sizer: score 비례 할당
  - ExitRule: pbr > 5 (가치 악화) OR roe < 0 OR holding_max_days 초과
  - Rebalancer: 매월 첫 주 (monthly)
  - HoldingCap: 분기 보유 가능 (holding_max_days None 시 무제한)
"""
from __future__ import annotations

import math
from datetime import date
from typing import Dict, Tuple

from RoboTrader_template.multiverse.composable.paramset import ParamSet
from RoboTrader_template.multiverse.composable.strategy import ComposableStrategy
from RoboTrader_template.multiverse.engine.pit_engine import PITContext

_PBR_BUY_THRESHOLD = 3.0
_PBR_SELL_THRESHOLD = 5.0
_ROE_BUY_THRESHOLD = 10.0

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


class _LongTermUniverse:
    def __init__(self, candidate_symbols: list[str]) -> None:
        self.candidates = candidate_symbols
        self._score_cache: _ScoreCache = {}

    def select(self, ctx: PITContext, paramset: ParamSet) -> list[str]:
        from RoboTrader_template.multiverse.data import corp_events

        filtered = corp_events.filter_universe(self.candidates, ctx.as_of_date)
        if not filtered:
            return []

        cache_key = (ctx.as_of_date, paramset.config_hash())
        if cache_key not in self._score_cache:
            self._score_cache[cache_key] = self._compute_scores(ctx, filtered, paramset)

        scores = self._score_cache[cache_key]
        ranked = sorted(scores, key=lambda s: scores[s], reverse=True)
        return ranked[: paramset.factor_top_n]

    def _compute_scores(
        self, ctx: PITContext, symbols: list[str], paramset: ParamSet
    ) -> Dict[str, float]:
        """팩터 4개를 z-score 정규화 후 가중합으로 종목별 점수 계산."""
        v_raw: list[float] = []  # value: 1/PBR
        q_raw: list[float] = []  # quality: ROE
        g_raw: list[float] = []  # growth: mean(net_income_growth, sales_growth)
        m_raw: list[float] = []  # momentum: 252일 수익률

        for sym in symbols:
            ratio = ctx.read_financial_ratio(symbol=sym) or {}
            bps = float(ratio.get("bps") or 0)
            roe = float(ratio.get("roe") or 0)
            ng = ratio.get("net_income_growth")
            sg = ratio.get("sales_growth")

            df = ctx.read_daily(symbol=sym, lookback_days=260)
            if df is not None and not df.empty and len(df) >= 200:
                last_close = float(df["close"].iloc[-1])
                first_close = float(df["close"].iloc[0])
                m = max(min(last_close / first_close - 1, 1.0), -1.0)
                if bps > 0:
                    pbr = last_close / bps
                    v = 1.0 / pbr if pbr > 0 else math.nan
                else:
                    v = math.nan
            else:
                m = math.nan
                v = math.nan

            q = roe / 100.0 if roe else math.nan

            growth_vals = []
            if ng is not None:
                try:
                    growth_vals.append(float(ng))
                except (TypeError, ValueError):
                    pass
            if sg is not None:
                try:
                    growth_vals.append(float(sg))
                except (TypeError, ValueError):
                    pass
            g = (sum(growth_vals) / len(growth_vals) / 100.0) if growth_vals else math.nan

            v_raw.append(v)
            q_raw.append(q)
            g_raw.append(g)
            m_raw.append(m)

        v_z = _z_normalize(v_raw)
        q_z = _z_normalize(q_raw)
        g_z = _z_normalize(g_raw)
        m_z = _z_normalize(m_raw)

        scores: Dict[str, float] = {}
        for i, sym in enumerate(symbols):
            scores[sym] = (
                paramset.w_value * v_z[i]
                + paramset.w_quality * q_z[i]
                + paramset.w_momentum * m_z[i]
                + paramset.w_growth * g_z[i]
            )
        return scores


class _LongTermScorer:
    def __init__(self, universe: _LongTermUniverse) -> None:
        self._universe = universe

    def score(self, ctx: PITContext, symbol: str, paramset: ParamSet) -> float:
        """Universe 캐시에서 정규화 점수 조회. 캐시 미스 시 0.0."""
        cache_key = (ctx.as_of_date, paramset.config_hash())
        scores = self._universe._score_cache.get(cache_key, {})
        return scores.get(symbol, 0.0)


class _LongTermRegime:
    def is_risk_on(self, ctx: PITContext, paramset: ParamSet) -> bool:
        return paramset.global_risk_mode != "risk_off_avoid"


class _LongTermSignalGen:
    def generate(self, ctx: PITContext, symbol: str, paramset: ParamSet) -> str:
        """pbr < 3 AND roe > 10% 이면 BUY — 한국시장 기준 가치+수익성 조건."""
        ratio = ctx.read_financial_ratio(symbol=symbol) or {}
        bps = float(ratio.get("bps") or 0)
        roe = float(ratio.get("roe") or 0)

        if bps <= 0:
            return "HOLD"

        df = ctx.read_daily(symbol=symbol, lookback_days=5)
        if df is None or df.empty:
            return "HOLD"
        try:
            last_close = float(df["close"].iloc[-1])
        except Exception:
            return "HOLD"

        pbr = last_close / bps
        if pbr < _PBR_BUY_THRESHOLD and roe > _ROE_BUY_THRESHOLD:
            return "BUY"
        return "HOLD"


class _LongTermSizer:
    def size(self, capital: float, score: float, paramset: ParamSet) -> int:
        """스코어 비례 할당 — score가 낮으면 최소 수량."""
        target_value = capital * paramset.max_weight_per_stock * max(score, 0.1)
        qty = int(target_value / 60_000)  # 평균 주가 6만원 가정
        return max(qty, 1)


class _LongTermExitRule:
    def should_exit(
        self, ctx: PITContext, position: dict, paramset: ParamSet
    ) -> tuple[bool, str]:
        """pbr > 5 (가치 악화) OR roe < 0 (수익성 훼손) OR 손절."""
        symbol = position.get("symbol", "")
        if symbol:
            ratio = ctx.read_financial_ratio(symbol=symbol) or {}
            bps = float(ratio.get("bps") or 0)
            roe = float(ratio.get("roe") or 0)

            if bps > 0:
                df = ctx.read_daily(symbol=symbol, lookback_days=5)
                if df is not None and not df.empty:
                    try:
                        last_close = float(df["close"].iloc[-1])
                        pbr = last_close / bps
                        if pbr > _PBR_SELL_THRESHOLD:
                            return True, "pbr_deterioration"
                    except Exception:
                        pass

            if roe < 0:
                return True, "roe_negative"

        entry_price = position.get("entry_price", 0.0)
        current_price = position.get("current_price", entry_price)
        if entry_price > 0:
            ret = (current_price - entry_price) / entry_price
            if ret < paramset.hard_stop_pct:
                return True, "hard_stop"

        return False, ""


class _LongTermRebalancer:
    def should_rebalance(self, current_date: date, paramset: ParamSet) -> bool:
        """매월 첫 주 (1~7일) 리밸런싱."""
        return current_date.day <= 7


class _LongTermHoldingCap:
    def should_force_exit_by_age(
        self, position: dict, current_date: date, paramset: ParamSet
    ) -> bool:
        cap = paramset.holding_max_days
        if cap is None:
            return False
        return position.get("held_days", 0) >= cap


def build_long_term_strategy(
    paramset: ParamSet, candidate_symbols: list[str]
) -> ComposableStrategy:
    """중장기(가치+수익성) 페르소나 ComposableStrategy 팩토리."""
    universe = _LongTermUniverse(candidate_symbols)
    scorer = _LongTermScorer(universe)
    return ComposableStrategy(
        paramset=paramset,
        universe=universe,
        scorer=scorer,
        regime=_LongTermRegime(),
        signal_gen=_LongTermSignalGen(),
        sizer=_LongTermSizer(),
        exit_rule=_LongTermExitRule(),
        rebalancer=_LongTermRebalancer(),
        holding_cap=_LongTermHoldingCap(),
    )
