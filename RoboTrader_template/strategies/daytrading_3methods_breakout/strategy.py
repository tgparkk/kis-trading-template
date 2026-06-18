"""
DayTrading 3Methods Breakout Strategy — 유지윤 『데이트레이딩 3대 타법』 돌파 타법 실전판
==========================================================================

유지윤 『하루 만에 수익 내는 데이트레이딩 3대 타법』 돌파 타법(전고점 거래량 동반
돌파) variant B — 백테스트(2021~2026, top_volume:50)에서 책의 베스트 룰
(706T / +5.90% / Sharpe 0.17 / hit 46.7%). Sharpe가 약해 탐색·관찰용.

백테스트 검증판을 실전 파이프라인(BaseStrategy / on_tick)으로 코드화한 전략.

진입 신호는 백테스트와 1:1 일치를 보장하기 위해
``strategies/books/daytrading_3methods/rules.py`` 의 룰을 직접 재사용한다:
  - ``rule_breakout_prev_high`` : 전고점 돌파 + 거래량 동반 폭증 양봉

진입 (rule=breakout_prev_high):
  1. 종가 >= 직전 15봉 전고점 (현재봉 제외, 전고점 돌파)  ← high_window=15 (config 배선)
  2. 당일 거래량 >= 직전 15봉 평균 × 2.0 (거래량 동반 폭증)
  3. 양봉 (close > open)

청산 (variant B 빠른 익절):
  - 손절: -10%
  - 익절: +10%
  - 최대 보유: 10거래일 (주말/공휴일 제외 — korean_holidays)
  - trailing 없음 (돌파 타법은 고정 손익절)

매수는 일봉(daily) 기준, 매도는 보유 종목의 일봉 재조회로 판정한다.
``holding_period = "swing"`` 이므로 EOD 일괄청산을 건너뛴다.
"""

from typing import Any, Dict, List, Optional, Tuple

import pandas as pd

from config.market_hours import MarketHours
from utils.korean_time import now_kst
from utils.korean_holidays import count_trading_days_between
from ..base import BaseStrategy, OrderInfo, Signal, SignalType

# 백테스트 룰을 직접 재사용 → 진입 신호 1:1 일치 보장
from strategies.books.daytrading_3methods.rules import rule_breakout_prev_high


class DayTrading3MethodsBreakoutStrategy(BaseStrategy):
    """3대 타법 돌파 — 전고점 거래량 동반 돌파 양봉 진입 (스윙)."""

    name: str = "DayTrading3MethodsBreakoutStrategy"
    version: str = "1.0.0"
    description: str = "3대 타법 돌파 — 전고점 거래량 동반 돌파 (sl10/tp10/max10, trailing 없음)"
    author: str = "Template"
    holding_period: str = "swing"
    exit_timeframe: str = "daily"   # 일봉 청산 — 분봉 ma_break/trailing whipsaw(매수 직후 매도) 방지
    # 추세추종 진입 — 거래량 상위 fallback 풀과 정합 (기본 True 유지)
    accepts_volume_fallback: bool = True

    # ========================================================================
    # 라이프사이클
    # ========================================================================

    def get_min_data_length(self) -> int:
        """진입 룰(rules.py)이 요구하는 최소 일봉 수."""
        params = self.config.get("parameters", {})
        return int(params.get("min_daily_bars", 25))

    def on_init(self, broker, data_provider, executor) -> bool:
        self._broker = broker
        self._data_provider = data_provider
        self._executor = executor

        params = self.config.get("parameters", {})
        self._min_daily_bars = int(params.get("min_daily_bars", 25))
        self._high_window = int(params.get("high_window", 15))

        risk = self.config.get("risk_management", {})
        self._take_profit_pct = float(risk.get("take_profit_pct", 0.10))
        self._stop_loss_pct = float(risk.get("stop_loss_pct", 0.10))
        self._max_hold_days = int(risk.get("max_hold_days", 10))
        self._trail_ma = risk.get("trail_ma", None)
        self._trail_ma = int(self._trail_ma) if self._trail_ma is not None else None
        self._max_positions = int(risk.get("max_positions", 5))
        self._max_daily_trades = int(risk.get("max_daily_trades", 5))
        self._max_per_stock_amount = float(risk.get("max_per_stock_amount", 3_000_000))
        # 진입 지정가 밴드 (돌파형): 기준가(직전 확정 종가) 위로 추격 한도만 둔다.
        # 갭업/상한가 종목을 스테일 종가로 체결하던 허수 진입 차단(2026-06-15).
        self._entry_band_up_pct = float(risk.get("entry_band_up_pct", 0.03))
        _band_down = risk.get("entry_band_down_pct", None)
        self._entry_band_down_pct = float(_band_down) if _band_down is not None else None

        # 프레임워크 max_holding_days 표준 키 (parameters 우선, fallback risk.max_hold_days)
        self.max_holding_days = int(
            params.get("max_holding_days", risk.get("max_hold_days", 10))
        )

        self._paper_trading = self.config.get("paper_trading", True)

        # 상태
        self.positions: Dict[str, Dict[str, Any]] = {}
        self.daily_trades = 0

        self._is_initialized = True
        self.logger.info(
            f"{self.name} v{self.version} 초기화 완료 "
            f"(전고점 돌파, high_window={self._high_window}, "
            f"sl={self._stop_loss_pct:.0%}/tp={self._take_profit_pct:.0%}/"
            f"trail_ma={self._trail_ma}/max_hold={self._max_hold_days}거래일)"
        )
        if self._paper_trading:
            self.logger.info("⚠️ Paper Trading 모드 활성화")
        return True

    def on_market_open(self) -> None:
        self.daily_trades = 0
        if self.positions:
            self.logger.info(
                f"장 시작 — 보유 종목 {len(self.positions)}개: {list(self.positions.keys())}"
            )
        else:
            self.logger.info("장 시작 — 보유 종목 없음")

    def generate_signal(
        self,
        stock_code: str,
        data: pd.DataFrame,
        timeframe: str = "daily",
    ) -> Optional[Signal]:
        if data is None or len(data) < self.get_min_data_length():
            return None

        # 보유 종목 → 매도(청산) 판단 우선
        if stock_code in self.positions:
            return self._check_sell(stock_code, data)

        if self.daily_trades >= self._max_daily_trades:
            return None
        if len(self.positions) >= self._max_positions:
            return None

        # 진입은 확정 일봉 기준 (백테스트와 동일). 매도 경로(intraday)에서는 신규 진입 안 함.
        if timeframe != "daily":
            return None

        return self._check_buy(stock_code, data)

    def on_order_filled(self, order: OrderInfo) -> None:
        self.daily_trades += 1
        if order.is_buy:
            self.positions[order.stock_code] = {
                "quantity": order.quantity,
                "entry_price": order.price,
                "entry_time": order.filled_at,
            }
            self.logger.info(
                f"📥 매수 체결: {order.stock_code} "
                f"@ {order.price:,.0f} x {order.quantity}주"
            )
        elif order.stock_code in self.positions:
            pos = self.positions.pop(order.stock_code)
            entry = pos["entry_price"]
            pnl_pct = (order.price - entry) / entry * 100
            prefix = "[PAPER] " if self._paper_trading else ""
            self.logger.info(
                f"📤 {prefix}매도 체결: {order.stock_code} "
                f"@ {order.price:,.0f} (수익률 {pnl_pct:+.1f}%)"
            )

    def on_market_close(self) -> None:
        self.logger.info(
            f"장 마감 — 거래 {self.daily_trades}건, 보유 {len(self.positions)}종목"
        )

    # ========================================================================
    # 순수 판단 함수 — 백테스트와 1:1 일치 검증 가능
    # ========================================================================

    @staticmethod
    def evaluate_entry(
        df: pd.DataFrame,
        min_daily_bars: int = 25,
        high_window: int = 15,
    ) -> Tuple[bool, List[str], Dict[str, Any]]:
        """진입 조건 평가 — 백테스트 rule_breakout_prev_high를 그대로 호출.

        Args:
            df: 일봉 OHLCV DataFrame (마지막 행 = 평가 시점 t, no-lookahead)
            min_daily_bars: 최소 일봉 수 가드
            high_window: 전고점 돌파창 봉 수 (기본 15 — config 배선값)

        Returns:
            (triggered, reasons, metadata)
        """
        if df is None or len(df) < min_daily_bars:
            return False, [], {}
        rule = rule_breakout_prev_high(high_window=high_window)
        res = rule.evaluate(df, {})
        if not res.triggered:
            return False, [], {}
        return True, list(res.reasons), dict(res.metadata)

    @staticmethod
    def evaluate_sell_conditions(
        df: pd.DataFrame,
        entry_price: float,
        hold_days: int,
        take_profit_pct: float = 0.10,
        stop_loss_pct: float = 0.10,
        max_hold_days: int = 10,
        trail_ma: Optional[int] = None,
    ) -> Tuple[bool, List[str], str]:
        """청산 조건 평가 — 백테스트 청산 우선순위를 1:1 복제.

        평가 우선순위:
          1. stop_loss   : ret <= -stop_loss_pct  (-10%)
          2. take_profit : ret >= take_profit_pct  (+10%)
          3. max_hold    : hold_days >= max_hold_days  (거래일 기준)
          4. trail_ma    : ret > 0 AND close < SMA(trail_ma)  (수익 중에만, 기본 미사용)

        Args:
            df: 일봉 OHLCV DataFrame (마지막 행 = 평가 시점). SMA 계산에 사용.
            entry_price: 진입가
            hold_days: 보유 거래일 수 (주말/공휴일 제외)
            나머지: breakout_prev_high variant B 파라미터 (trailing 기본 없음)

        Returns:
            (should_sell, reasons, exit_reason)  — exit_reason은 단일 사유 코드.
        """
        close = df["close"].astype(float)
        cur_close = float(close.iloc[-1])
        ret = (cur_close - entry_price) / entry_price

        # 1) 손절 (-10%)
        if ret <= -stop_loss_pct:
            return True, [f"손절 도달 ({ret * 100:+.1f}%)"], "stop_loss"
        # 2) 익절 (+10%)
        if ret >= take_profit_pct:
            return True, [f"익절 도달 ({ret * 100:+.1f}%)"], "take_profit"
        # 3) 최대 보유 거래일
        if hold_days >= max_hold_days:
            return True, [f"최대 보유일 초과 ({hold_days}거래일)"], "max_hold"
        # 4) MA trailing (수익 중에만 — variant B 기본 미사용)
        if trail_ma is not None and ret > 0:
            ma_series = close.rolling(window=trail_ma).mean()
            ma_trail = float(ma_series.iloc[-1]) if not pd.isna(ma_series.iloc[-1]) else None
            if ma_trail is not None and cur_close < ma_trail:
                return (
                    True,
                    [f"MA{trail_ma} trailing 이탈 (종가 {cur_close:.0f} < "
                     f"MA{trail_ma} {ma_trail:.0f})"],
                    "trail_ma",
                )

        return False, [], ""

    # ========================================================================
    # 내부 헬퍼
    # ========================================================================

    def _check_buy(self, stock_code: str, data: pd.DataFrame) -> Optional[Signal]:
        if not MarketHours.is_market_open("KRX"):
            return None

        triggered, reasons, rule_meta = self.evaluate_entry(
            data, min_daily_bars=self._min_daily_bars, high_window=self._high_window
        )
        if not triggered:
            return None

        current_price = float(data["close"].astype(float).iloc[-1])

        target = current_price * (1 + self._take_profit_pct)
        stop = current_price * (1 - self._stop_loss_pct)
        entry_min, entry_max = self._entry_band(
            current_price, down_pct=self._entry_band_down_pct, up_pct=self._entry_band_up_pct)
        recommended_qty = max(1, int(self._max_per_stock_amount // current_price))

        metadata = {
            "prior_high": rule_meta.get("prior_high"),
            "vol_ratio": rule_meta.get("vol_ratio"),
            "close": current_price,
            "recommended_qty": recommended_qty,
        }
        if self._paper_trading:
            metadata["paper_only"] = True
            self.logger.info(
                f"🧾 [PAPER] 매수 시그널: {stock_code} @ {current_price:,.0f} "
                f"(추천 {recommended_qty}주) | " + " | ".join(reasons)
            )

        return Signal(
            signal_type=SignalType.BUY,
            stock_code=stock_code,
            confidence=68.0,  # 백테스트 rule confidence와 동일
            target_price=target,
            stop_loss=stop,
            entry_min_price=entry_min,
            entry_max_price=entry_max,
            reasons=reasons,
            metadata=metadata,
        )

    def _check_sell(self, stock_code: str, data: pd.DataFrame) -> Optional[Signal]:
        pos = self.positions[stock_code]
        entry_price = pos["entry_price"]
        entry_time = pos.get("entry_time")
        # 보유 거래일 수 (주말/공휴일 제외). 진입일=0일차 → 경과 거래일 = 구간-1.
        if entry_time:
            hold_days = max(0, count_trading_days_between(entry_time, now_kst()) - 1)
        else:
            hold_days = 0

        should_sell, reasons, exit_reason = self.evaluate_sell_conditions(
            df=data,
            entry_price=entry_price,
            hold_days=hold_days,
            take_profit_pct=self._take_profit_pct,
            stop_loss_pct=self._stop_loss_pct,
            max_hold_days=self._max_hold_days,
            trail_ma=self._trail_ma,
        )
        if not should_sell:
            return None

        current_price = float(data["close"].astype(float).iloc[-1])
        pnl_pct = (current_price - entry_price) / entry_price * 100
        metadata = {
            "entry_price": entry_price,
            "pnl_pct": pnl_pct,
            "hold_days": hold_days,
            "exit_reason": exit_reason,
        }
        if self._paper_trading:
            metadata["paper_only"] = True
            self.logger.info(
                f"🧾 [PAPER] 매도 시그널: {stock_code} @ {current_price:,.0f} "
                f"({exit_reason}) | " + " | ".join(reasons)
            )

        return Signal(
            signal_type=SignalType.SELL,
            stock_code=stock_code,
            confidence=min(95.0, 60.0 + len(reasons) * 15),
            reasons=reasons,
            metadata=metadata,
        )
