"""
Volume Breakout Strategy — 거래량 폭증 돌파
============================================

매수 조건:
  - 당일 거래량이 20일 평균의 10배 이상
  - 양봉 (종가 > 시가)
  - 봉 크기가 최소 기준 이상

매도 조건 (1개 이상 충족 시):
  - 익절: +10% 도달
  - 손절: -5% 도달
  - 보유기간: 5일 초과
  - 거래량 감소: 전일 대비 50% 이하로 급감
"""

from datetime import datetime
from typing import Any, Dict, List, Optional

import pandas as pd

from ..base import BaseStrategy, OrderInfo, Signal, SignalType


class VolumeBreakoutStrategy(BaseStrategy):
    """거래량 폭증 + 양봉 돌파 전략"""

    name: str = "VolumeBreakoutStrategy"
    version: str = "1.0.0"
    description: str = "거래량 10배 폭증 + 양봉 발생 시 돌파 매매"
    author: str = "Template"

    def on_init(self, broker, data_provider, executor) -> bool:
        self._broker = broker
        self._data_provider = data_provider
        self._executor = executor

        params = self.config.get("parameters", {})
        self._volume_avg_period = params.get("volume_avg_period", 20)
        self._volume_multiplier = params.get("volume_multiplier", 10.0)
        self._require_bullish = params.get("require_bullish_candle", True)
        self._min_candle_body_pct = params.get("min_candle_body_pct", 1.0)
        self._max_holding_days = params.get("max_holding_days", 5)

        risk = self.config.get("risk_management", {})
        self._stop_loss_pct = risk.get("stop_loss_pct", 0.05)
        self._take_profit_pct = risk.get("take_profit_pct", 0.10)
        self._max_daily_trades = risk.get("max_daily_trades", 3)

        self.positions: Dict[str, Dict[str, Any]] = {}
        self.daily_trades = 0

        self._is_initialized = True
        self.logger.info(
            f"{self.name} v{self.version} 초기화 완료 "
            f"(거래량 {self._volume_multiplier}배, "
            f"TP {self._take_profit_pct*100:.0f}%/SL {self._stop_loss_pct*100:.0f}%)"
        )
        return True

    def on_market_open(self) -> None:
        self.daily_trades = 0

    def generate_signal(
        self,
        stock_code: str,
        data: pd.DataFrame,
        timeframe: str = 'daily',
    ) -> Optional[Signal]:
        if data is None or len(data) < self._volume_avg_period + 2:
            return None

        if self.daily_trades >= self._max_daily_trades:
            return None

        current_price = float(data["close"].iloc[-1])

        # 보유 종목 → 매도
        if stock_code in self.positions:
            return self._check_sell(stock_code, current_price, data)

        # 미보유 → 매수
        return self._check_buy(stock_code, current_price, data)

    def on_order_filled(self, order: OrderInfo) -> None:
        self.daily_trades += 1
        if order.is_buy:
            self.positions[order.stock_code] = {
                "entry_price": order.price,
                "entry_time": order.filled_at,
                "holding_days": 0,
            }
        elif order.stock_code in self.positions:
            del self.positions[order.stock_code]

    def on_market_close(self) -> None:
        for code in self.positions:
            self.positions[code]["holding_days"] = self.positions[code].get("holding_days", 0) + 1
        self.logger.info(f"장 마감 — 거래 {self.daily_trades}건, 보유 {len(self.positions)}종목")

    # ========================================================================
    # 내부 헬퍼
    # ========================================================================

    def _check_buy(
        self, stock_code: str, current_price: float, data: pd.DataFrame
    ) -> Optional[Signal]:
        volume = data["volume"]
        avg_volume = volume.rolling(self._volume_avg_period).mean()

        cur_vol = float(volume.iloc[-1])
        avg_vol = float(avg_volume.iloc[-1])

        if pd.isna(avg_vol) or avg_vol <= 0:
            return None

        vol_ratio = cur_vol / avg_vol
        if vol_ratio < self._volume_multiplier:
            return None

        reasons = [f"거래량 {vol_ratio:.1f}배 폭증 (평균 {avg_vol:,.0f} → {cur_vol:,.0f})"]

        # 양봉 체크
        open_price = float(data["open"].iloc[-1])
        if self._require_bullish and current_price <= open_price:
            return None

        body_pct = (current_price - open_price) / open_price * 100
        if body_pct < self._min_candle_body_pct:
            return None

        reasons.append(f"양봉 +{body_pct:.1f}%")

        target = current_price * (1 + self._take_profit_pct)
        stop = current_price * (1 - self._stop_loss_pct)

        return Signal(
            signal_type=SignalType.BUY,
            stock_code=stock_code,
            confidence=min(95.0, 50.0 + vol_ratio * 2),
            target_price=target,
            stop_loss=stop,
            reasons=reasons,
            metadata={
                "volume_ratio": vol_ratio,
                "candle_body_pct": body_pct,
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

        if pnl_pct >= self._take_profit_pct:
            reasons.append(f"익절 도달 ({pnl_pct * 100:+.1f}%)")

        if pnl_pct <= -self._stop_loss_pct:
            reasons.append(f"손절 도달 ({pnl_pct * 100:+.1f}%)")

        if holding_days >= self._max_holding_days:
            reasons.append(f"보유기간 {holding_days}일 초과")

        # 거래량 급감 (전일 대비 50% 이하)
        volume = data["volume"]
        if len(volume) >= 2 and volume.iloc[-2] > 0:
            vol_change = volume.iloc[-1] / volume.iloc[-2]
            if vol_change < 0.5:
                reasons.append(f"거래량 급감 ({vol_change:.0%})")

        if not reasons:
            return None

        return Signal(
            signal_type=SignalType.SELL,
            stock_code=stock_code,
            confidence=min(90.0, 50.0 + len(reasons) * 20),
            reasons=reasons,
        )
