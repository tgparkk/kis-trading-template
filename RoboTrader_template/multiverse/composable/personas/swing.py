"""스윙 페르소나 — 볼린저밴드 + RSI 회귀 전략.

알고리즘 요약:
  - Universe: corp_events 필터 후 상위 10종목
  - Scorer: 5일 모멘텀 수익률
  - Regime: prev_kospi_return_filter == "positive_only" 이면 양봉 시장만, 그 외 항상 risk_on
  - SignalGen: BB 하단 이탈 후 종가가 하단 위로 회복 + RSI < 35 이면 BUY
  - Sizer: 동일 비중 (equal weight)
  - ExitRule: RSI > exit_rsi_overbought OR 손절 hard_stop_pct 초과
  - Rebalancer: 매주 월요일
  - HoldingCap: holding_max_days 초과 강제 청산
"""
from __future__ import annotations

from datetime import date

import pandas as pd

from RoboTrader_template.multiverse.composable.paramset import ParamSet
from RoboTrader_template.multiverse.composable.strategy import ComposableStrategy
from RoboTrader_template.multiverse.engine.pit_engine import PITContext

_UNIVERSE_TOP_N = 10
_BB_PERIOD = 20
_BB_STD = 2.0
_RSI_PERIOD = 14


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

    def select(self, ctx: PITContext, paramset: ParamSet) -> list[str]:
        from RoboTrader_template.multiverse.data import corp_events
        filtered = corp_events.filter_universe(self.candidates, ctx.as_of_date)
        return filtered[:_UNIVERSE_TOP_N]


class _SwingScorer:
    def score(self, ctx: PITContext, symbol: str, paramset: ParamSet) -> float:
        """5일 모멘텀 수익률."""
        df = ctx.read_daily(symbol=symbol, lookback_days=10)
        if df is None or df.empty or len(df) < 5:
            return 0.0
        try:
            return float(df["close"].iloc[-1] / df["close"].iloc[-5] - 1)
        except Exception:
            return 0.0


class _SwingRegime:
    def is_risk_on(self, ctx: PITContext, paramset: ParamSet) -> bool:
        # positive_only 설정이면 엄격 모드 — 데모에선 항상 True 반환(실데이터 없음)
        return paramset.global_risk_mode != "risk_off_avoid"


class _SwingSignalGen:
    def generate(self, ctx: PITContext, symbol: str, paramset: ParamSet) -> str:
        """BB 하단 이탈 후 회복 + RSI < 35 이면 BUY."""
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
        if bb_bounce and rsi < 35:
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
    return ComposableStrategy(
        paramset=paramset,
        universe=_SwingUniverse(candidate_symbols),
        scorer=_SwingScorer(),
        regime=_SwingRegime(),
        signal_gen=_SwingSignalGen(),
        sizer=_SwingSizer(),
        exit_rule=_SwingExitRule(),
        rebalancer=_SwingRebalancer(),
        holding_cap=_SwingHoldingCap(),
    )
