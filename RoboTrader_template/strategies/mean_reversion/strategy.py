"""
Mean Reversion Strategy — MA20 이탈 평균회귀
=============================================

매수 조건:
  - 현재가가 MA20 대비 -10% 이상 이탈
  - (선택) RSI가 과매도 구간

매도 조건 (1개 이상 충족 시):
  - MA 복귀: 현재가가 MA20의 90% 수준까지 회복
  - 익절: +12% 도달
  - 손절: -7% 도달
"""

from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd

from ..base import BaseStrategy, OrderInfo, Signal, SignalType
from utils.indicators import calculate_rsi


class MeanReversionStrategy(BaseStrategy):
    """MA20 이탈 평균회귀 전략"""

    name: str = "MeanReversionStrategy"
    version: str = "1.0.0"
    description: str = "MA20 대비 과도한 이탈 시 매수, 평균 복귀 시 매도"
    author: str = "Template"
    holding_period: str = "swing"

    def get_min_data_length(self) -> int:
        """MA20 + RSI14 + 여유 2 = 22"""
        params = self.config.get("parameters", {})
        ma_period = params.get("ma_period", 20)
        rsi_period = params.get("rsi_period", 14)
        return max(ma_period, rsi_period) + 2

    def on_init(self, broker, data_provider, executor) -> bool:
        self._broker = broker
        self._data_provider = data_provider
        self._executor = executor

        params = self.config.get("parameters", {})
        self._ma_period = params.get("ma_period", 20)
        self._entry_deviation_pct = params.get("entry_deviation_pct", -10.0)
        self._exit_recovery_ratio = params.get("exit_recovery_ratio", 0.9)
        self._use_rsi_filter = params.get("use_rsi_filter", True)
        self._rsi_period = params.get("rsi_period", 14)
        self._rsi_oversold = params.get("rsi_oversold", 30)

        risk = self.config.get("risk_management", {})
        self._stop_loss_pct = risk.get("stop_loss_pct", 0.07)
        self._take_profit_pct = risk.get("take_profit_pct", 0.12)
        self._max_daily_trades = risk.get("max_daily_trades", 5)
        # C4: 프레임워크 max_holding_days 표준 키
        self.max_holding_days = params.get("max_holding_days", 7)

        self.positions: Dict[str, Dict[str, Any]] = {}
        self.daily_trades = 0

        self._is_initialized = True
        self.logger.info(
            f"{self.name} v{self.version} 초기화 완료 "
            f"(MA{self._ma_period}, 이탈 {self._entry_deviation_pct}%)"
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
        min_len = max(self._ma_period, self._rsi_period) + 2
        if data is None or len(data) < min_len:
            return None

        if self.daily_trades >= self._max_daily_trades:
            return None

        close = data["close"]
        current_price = float(close.iloc[-1])
        ma = close.rolling(self._ma_period).mean()
        ma_value = float(ma.iloc[-1])

        if pd.isna(ma_value) or ma_value == 0:
            return None

        deviation_pct = (current_price - ma_value) / ma_value * 100

        # 보유 종목 → 매도
        if stock_code in self.positions:
            return self._check_sell(stock_code, current_price, ma_value, deviation_pct)

        # 미보유 → 매수
        return self._check_buy(stock_code, current_price, ma_value, deviation_pct, data)

    def on_order_filled(self, order: OrderInfo) -> None:
        self.daily_trades += 1
        if order.is_buy:
            self.positions[order.stock_code] = {
                "entry_price": order.price,
                "entry_time": order.filled_at,
            }
        elif order.stock_code in self.positions:
            del self.positions[order.stock_code]

    def on_market_close(self) -> None:
        self.logger.info(f"장 마감 — 거래 {self.daily_trades}건, 보유 {len(self.positions)}종목")

    # ========================================================================
    # 내부 헬퍼
    # ========================================================================

    def _check_buy(
        self,
        stock_code: str,
        current_price: float,
        ma_value: float,
        deviation_pct: float,
        data: pd.DataFrame,
    ) -> Optional[Signal]:
        # MA 대비 충분히 이탈했는지
        if deviation_pct > self._entry_deviation_pct:
            return None

        reasons = [f"MA{self._ma_period} 대비 {deviation_pct:.1f}% 이탈"]

        # RSI 필터
        if self._use_rsi_filter:
            rsi = calculate_rsi(data["close"], self._rsi_period)
            rsi_val = float(rsi.iloc[-1])
            if pd.isna(rsi_val) or rsi_val > self._rsi_oversold:
                return None
            reasons.append(f"RSI({self._rsi_period}) = {rsi_val:.1f} (과매도)")

        target = current_price * (1 + self._take_profit_pct)
        stop = current_price * (1 - self._stop_loss_pct)

        return Signal(
            signal_type=SignalType.BUY,
            stock_code=stock_code,
            confidence=min(90.0, 50.0 + abs(deviation_pct) * 2),
            target_price=target,
            stop_loss=stop,
            reasons=reasons,
            metadata={
                "ma_value": ma_value,
                "deviation_pct": deviation_pct,
            },
        )

    def _check_sell(
        self,
        stock_code: str,
        current_price: float,
        ma_value: float,
        deviation_pct: float,
    ) -> Optional[Signal]:
        pos = self.positions[stock_code]
        entry_price = pos["entry_price"]
        pnl_pct = (current_price - entry_price) / entry_price

        reasons: List[str] = []

        # MA 복귀
        if deviation_pct >= self._entry_deviation_pct * (1 - self._exit_recovery_ratio):
            reasons.append(f"MA{self._ma_period} 복귀 (이탈 {deviation_pct:.1f}%)")

        # 익절
        if pnl_pct >= self._take_profit_pct:
            reasons.append(f"익절 도달 ({pnl_pct * 100:+.1f}%)")

        # 손절
        if pnl_pct <= -self._stop_loss_pct:
            reasons.append(f"손절 도달 ({pnl_pct * 100:+.1f}%)")

        if not reasons:
            return None

        return Signal(
            signal_type=SignalType.SELL,
            stock_code=stock_code,
            confidence=min(90.0, 50.0 + len(reasons) * 20),
            reasons=reasons,
        )

    # RSI 계산은 utils.indicators.calculate_rsi 사용
