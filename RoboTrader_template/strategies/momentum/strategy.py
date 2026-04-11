"""
Momentum Strategy — 5일 연속 상승 모멘텀
========================================

매수 조건:
  - N일 연속 종가 상승 (기본 5일)
  - 누적 상승률이 최소 기준 이상 (기본 3%)

매도 조건 (1개 이상 충족 시):
  - 익절: +10% 도달
  - 손절: -5% 도달
  - 시간: 최대 보유일(10일) 초과
  - 하락 전환: 2일 연속 하락
"""

from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd

from ..base import BaseStrategy, OrderInfo, Signal, SignalType


class MomentumStrategy(BaseStrategy):
    """5일 연속 상승 모멘텀 전략"""

    name: str = "MomentumStrategy"
    version: str = "1.0.0"
    description: str = "N일 연속 상승 모멘텀을 포착하여 추세 추종 매매"
    author: str = "Template"
    holding_period: str = "swing"

    def get_min_data_length(self) -> int:
        """연속상승 N일 + 여유 2"""
        params = self.config.get("parameters", {})
        consecutive_up_days = params.get("consecutive_up_days", 5)
        return consecutive_up_days + 2

    def on_init(self, broker, data_provider, executor) -> bool:
        self._broker = broker
        self._data_provider = data_provider
        self._executor = executor

        params = self.config.get("parameters", {})
        self._consecutive_up_days = params.get("consecutive_up_days", 5)
        self._min_daily_change_pct = params.get("min_daily_change_pct", 0.0)
        self._min_total_change_pct = params.get("min_total_change_pct", 3.0)
        self._max_holding_days = params.get("max_holding_days", 10)

        risk = self.config.get("risk_management", {})
        self._stop_loss_pct = risk.get("stop_loss_pct", 0.05)
        self._take_profit_pct = risk.get("take_profit_pct", 0.10)
        self._max_daily_trades = risk.get("max_daily_trades", 5)

        self.positions: Dict[str, Dict[str, Any]] = {}
        self.daily_trades = 0

        self._is_initialized = True
        self.logger.info(
            f"{self.name} v{self.version} 초기화 완료 "
            f"(연속상승 {self._consecutive_up_days}일, "
            f"TP {self._take_profit_pct*100:.0f}%/SL {self._stop_loss_pct*100:.0f}%)"
        )
        return True

    def on_market_open(self) -> None:
        self.daily_trades = 0
        if self.positions:
            self.logger.info(f"장 시작 — 보유 {len(self.positions)}종목")

    def generate_signal(
        self,
        stock_code: str,
        data: pd.DataFrame,
        timeframe: str = 'daily',
    ) -> Optional[Signal]:
        if data is None or len(data) < self._consecutive_up_days + 2:
            return None

        if self.daily_trades >= self._max_daily_trades:
            return None

        close = data["close"]
        current_price = float(close.iloc[-1])

        # 보유 종목 → 매도 판단
        if stock_code in self.positions:
            return self._check_sell(stock_code, current_price, data)

        # 미보유 → 매수 판단
        return self._check_buy(stock_code, current_price, data)

    def on_order_filled(self, order: OrderInfo) -> None:
        self.daily_trades += 1
        if order.is_buy:
            self.positions[order.stock_code] = {
                "entry_price": order.price,
                "entry_time": order.filled_at,
                "holding_days": 0,
            }
            self.logger.info(
                f"매수 체결: {order.stock_code} {order.quantity}주 @ {order.price:,.0f}원"
            )
        else:
            if order.stock_code in self.positions:
                entry = self.positions[order.stock_code]["entry_price"]
                pnl = (order.price - entry) / entry * 100
                self.logger.info(
                    f"매도 체결: {order.stock_code} {order.quantity}주 @ {order.price:,.0f}원 ({pnl:+.2f}%)"
                )
                del self.positions[order.stock_code]

    def on_market_close(self) -> None:
        # 보유일 증가
        for code in self.positions:
            self.positions[code]["holding_days"] = self.positions[code].get("holding_days", 0) + 1
        self.logger.info(f"장 마감 — 거래 {self.daily_trades}건, 보유 {len(self.positions)}종목")

    # ========================================================================
    # 내부 헬퍼
    # ========================================================================

    def _check_buy(
        self, stock_code: str, current_price: float, data: pd.DataFrame
    ) -> Optional[Signal]:
        close = data["close"]
        n = self._consecutive_up_days

        # N일 연속 상승 확인
        changes = close.pct_change().iloc[-n:]
        if len(changes) < n:
            return None

        if not all(c > self._min_daily_change_pct / 100 for c in changes):
            return None

        # 누적 상승률 확인
        total_change = (close.iloc[-1] / close.iloc[-n - 1] - 1) * 100
        if total_change < self._min_total_change_pct:
            return None

        target = current_price * (1 + self._take_profit_pct)
        stop = current_price * (1 - self._stop_loss_pct)

        return Signal(
            signal_type=SignalType.BUY,
            stock_code=stock_code,
            confidence=min(90.0, 50.0 + total_change * 5),
            target_price=target,
            stop_loss=stop,
            reasons=[
                f"{n}일 연속 상승",
                f"누적 상승률 {total_change:.1f}%",
            ],
            metadata={
                "consecutive_days": n,
                "total_change_pct": total_change,
            },
        )

    def _check_sell(
        self, stock_code: str, current_price: float, data: pd.DataFrame
    ) -> Optional[Signal]:
        pos = self.positions[stock_code]
        entry_price = pos["entry_price"]
        holding_days = pos.get("holding_days", 0)
        pnl_pct = (current_price - entry_price) / entry_price

        reasons: List[str] = []

        # 익절
        if pnl_pct >= self._take_profit_pct:
            reasons.append(f"익절 도달 ({pnl_pct * 100:+.1f}%)")

        # 손절
        if pnl_pct <= -self._stop_loss_pct:
            reasons.append(f"손절 도달 ({pnl_pct * 100:+.1f}%)")

        # 보유기간 초과
        if holding_days >= self._max_holding_days:
            reasons.append(f"보유기간 {holding_days}일 초과")

        # 2일 연속 하락
        close = data["close"]
        if len(close) >= 3:
            if close.iloc[-1] < close.iloc[-2] < close.iloc[-3]:
                reasons.append("2일 연속 하락 전환")

        if not reasons:
            return None

        return Signal(
            signal_type=SignalType.SELL,
            stock_code=stock_code,
            confidence=min(90.0, 50.0 + len(reasons) * 20),
            reasons=reasons,
            metadata={"position": pos, "pnl_pct": pnl_pct * 100},
        )
