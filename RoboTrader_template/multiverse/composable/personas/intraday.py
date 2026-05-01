"""단타 페르소나 — 일봉 모멘텀 기반 (호가 없는 일봉 단타).

알고리즘 요약:
  - Universe: corp_events 필터 후 상위 20종목 (변동성 높은 단타 후보)
  - Scorer: 5일 변동성 (일봉 표준편차)
  - Regime: 항상 risk_on (단타는 국면 무관 단기 기회 포착)
  - SignalGen: 전일 양봉(종가>시가) + 거래량 급증(전일 대비 1.5배 이상) 이면 BUY
  - Sizer: 소형 포지션 — max_weight_per_stock * 0.5
  - ExitRule: 다음 날 EOD 청산 (held_days >= 1) 또는 hard_stop_pct 손절
  - Rebalancer: 매일 (daily)
  - HoldingCap: 1일 강제 청산 (holding_max_days=1 강제 적용)
"""
from __future__ import annotations

from datetime import date

import pandas as pd

from RoboTrader_template.multiverse.composable.paramset import ParamSet
from RoboTrader_template.multiverse.composable.strategy import ComposableStrategy
from RoboTrader_template.multiverse.engine.pit_engine import PITContext

_UNIVERSE_TOP_N = 20
_VOL_WINDOW = 5
_VOL_SURGE_RATIO = 1.5
_INTRADAY_HOLD_DAYS = 1  # 단타 최대 보유일 강제


class _IntradayUniverse:
    def __init__(self, candidate_symbols: list[str]) -> None:
        self.candidates = candidate_symbols

    def select(self, ctx: PITContext, paramset: ParamSet) -> list[str]:
        from RoboTrader_template.multiverse.data import corp_events
        filtered = corp_events.filter_universe(self.candidates, ctx.as_of_date)
        return filtered[:_UNIVERSE_TOP_N]


class _IntradayScorer:
    def score(self, ctx: PITContext, symbol: str, paramset: ParamSet) -> float:
        """5일 변동성 (일봉 수익률 표준편차) — 높을수록 단타 기회."""
        df = ctx.read_daily(symbol=symbol, lookback_days=_VOL_WINDOW + 2)
        if df is None or df.empty or len(df) < _VOL_WINDOW:
            return 0.0
        try:
            closes = df["close"].astype(float)
            vol = float(closes.pct_change().dropna().std())
            return max(vol, 0.0)
        except Exception:
            return 0.0


class _IntradayRegime:
    def is_risk_on(self, ctx: PITContext, paramset: ParamSet) -> bool:
        # 단타는 시장 국면과 무관하게 단기 기회 포착 — 항상 True
        return True


class _IntradaySignalGen:
    def generate(self, ctx: PITContext, symbol: str, paramset: ParamSet) -> str:
        """전일 양봉 + 거래량 급증 이면 BUY."""
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

        # 거래량 급증 확인 (최근 _VOL_WINDOW일 평균 대비)
        if len(df) >= _VOL_WINDOW + 1:
            avg_vol = float(
                df["volume"].astype(float).iloc[-(  _VOL_WINDOW + 1):-1].mean()
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
    return ComposableStrategy(
        paramset=paramset,
        universe=_IntradayUniverse(candidate_symbols),
        scorer=_IntradayScorer(),
        regime=_IntradayRegime(),
        signal_gen=_IntradaySignalGen(),
        sizer=_IntradaySizer(),
        exit_rule=_IntradayExitRule(),
        rebalancer=_IntradayRebalancer(),
        holding_cap=_IntradayHoldingCap(),
    )
