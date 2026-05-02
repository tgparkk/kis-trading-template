"""퀀트 페르소나 — 팩터 z-score 정규화 + 포트폴리오 5~10종목.

알고리즘 요약:
  - Universe: corp_events 필터 후 z-score 정규화 팩터 상위 factor_top_n
  - Scorer: Universe._score_cache에서 정규화 점수 조회 (재계산 없음)
  - Regime: global_risk_mode != risk_off_avoid 이면 risk_on
  - SignalGen: 정규화 score > tech_score_threshold AND 모멘텀 raw > 0 이면 BUY
  - Sizer: max_weight_per_stock 비율, 평균 주가 7만원 가정
  - ExitRule: 보유 60일 초과 청산
  - Rebalancer: daily/weekly/biweekly/monthly 파라미터 따름
  - HoldingCap: holding_max_days 초과 강제 청산
"""
from __future__ import annotations

import math
from datetime import date
from typing import Dict, Optional, Tuple

from RoboTrader_template.multiverse.composable.paramset import ParamSet
from RoboTrader_template.multiverse.composable.strategy import ComposableStrategy
from RoboTrader_template.multiverse.engine.pit_engine import PITContext

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


class _QuantUniverse:
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
            self._score_cache[cache_key] = self._compute_scores(ctx, filtered, paramset)

        scores = self._score_cache[cache_key]
        ranked = sorted(scores, key=lambda s: scores[s], reverse=True)
        return ranked[: paramset.factor_top_n]

    def _compute_scores(
        self, ctx: PITContext, symbols: list[str], paramset: ParamSet
    ) -> Dict[str, float]:
        """팩터 4개를 z-score 정규화 후 가중합으로 종목별 점수 계산."""
        v_raw: list[float] = []
        q_raw: list[float] = []
        g_raw: list[float] = []
        m_raw: list[float] = []

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
                # value: 1/PBR (PBR = close/bps)
                if bps > 0:
                    pbr = last_close / bps
                    v = 1.0 / pbr if pbr > 0 else math.nan
                else:
                    v = math.nan
            else:
                m = math.nan
                v = math.nan
                last_close = 0.0

            # quality: ROE
            q = roe / 100.0 if roe else math.nan

            # growth: mean(net_income_growth, sales_growth) / 100
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


class _QuantScorer:
    def __init__(self, universe: _QuantUniverse) -> None:
        self._universe = universe

    def score(self, ctx: PITContext, symbol: str, paramset: ParamSet) -> float:
        """Universe 캐시에서 정규화 점수 조회. 캐시 미스 시 0.0."""
        cache_key = (ctx.as_of_date, paramset.config_hash())
        scores = self._universe._score_cache.get(cache_key, {})
        return scores.get(symbol, 0.0)


class _QuantRegime:
    def is_risk_on(self, ctx: PITContext, paramset: ParamSet) -> bool:
        return paramset.global_risk_mode != "risk_off_avoid"


class _QuantSignalGen:
    def __init__(self, universe: _QuantUniverse) -> None:
        self._universe = universe

    def generate(self, ctx: PITContext, symbol: str, paramset: ParamSet) -> str:
        """정규화 score > threshold AND 모멘텀 raw > 0 이면 BUY."""
        cache_key = (ctx.as_of_date, paramset.config_hash())
        scores = self._universe._score_cache.get(cache_key, {})
        norm_score = scores.get(symbol, 0.0)

        if norm_score <= paramset.tech_score_threshold:
            return "HOLD"

        # 모멘텀 방향 확인: 보유 데이터 내 첫 종가 대비 최근 종가 (하락장 진입 회피)
        # lookback_days=20으로 단기만 읽어 DB 데이터 부족 시에도 동작
        df = ctx.read_daily(symbol=symbol, lookback_days=20)
        if df is None or df.empty or len(df) < 2:
            return "HOLD"
        try:
            mom_raw = float(df["close"].iloc[-1] / df["close"].iloc[0] - 1)
        except Exception:
            return "HOLD"

        if mom_raw <= 0:
            return "HOLD"

        return "BUY"


class _QuantSizer:
    def size(self, capital: float, score: float, paramset: ParamSet) -> int:
        target_value = capital * paramset.max_weight_per_stock
        qty = int(target_value / 70_000)  # 평균 주가 7만원 가정
        return max(qty, 1)


class _QuantExitRule:
    def should_exit(
        self, ctx: PITContext, position: dict, paramset: ParamSet
    ) -> tuple[bool, str]:
        held_days = position.get("held_days", 0)
        if held_days > 60:
            return True, "long_hold"
        return False, ""


class _QuantRebalancer:
    def should_rebalance(self, current_date: date, paramset: ParamSet) -> bool:
        freq = paramset.rebalance_frequency
        if freq == "monthly":
            return current_date.day <= 7
        if freq == "weekly":
            return current_date.weekday() == 0  # 월요일
        if freq == "biweekly":
            return current_date.weekday() == 0 and (
                current_date.isocalendar()[1] % 2 == 0
            )
        return True  # daily


class _QuantHoldingCap:
    def should_force_exit_by_age(
        self, position: dict, current_date: date, paramset: ParamSet
    ) -> bool:
        cap = paramset.holding_max_days
        if cap is None:
            return False
        return position.get("held_days", 0) >= cap


def build_quant_strategy(
    paramset: ParamSet, candidate_symbols: list[str]
) -> ComposableStrategy:
    """퀀트 페르소나 ComposableStrategy 팩토리."""
    universe = _QuantUniverse(candidate_symbols)
    scorer = _QuantScorer(universe)
    signal_gen = _QuantSignalGen(universe)
    return ComposableStrategy(
        paramset=paramset,
        universe=universe,
        scorer=scorer,
        regime=_QuantRegime(),
        signal_gen=signal_gen,
        sizer=_QuantSizer(),
        exit_rule=_QuantExitRule(),
        rebalancer=_QuantRebalancer(),
        holding_cap=_QuantHoldingCap(),
    )
