"""RS Leader Strategy — 횡보장 RS 리더 (페이퍼 관찰 전용).

진입: 절대상승추세(scripts.rs_leader.rule.RSLeaderRule 단일 소스 재사용) — 횡단면 RS
랭킹은 EOD 스크리너가 담당하고, 이 전략은 선정 풀에서 per-stock 추세 재확인 후 매수.
청산: MA20 하향이탈(무조건, 검증 4-bis 정합) / sl -8% / max_hold 30거래일.
holding_period="swing" → EOD 일괄청산 건너뜀. paper_trading=True.
"""
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd

from config.market_hours import MarketHours
from utils.korean_time import now_kst
from utils.korean_holidays import count_trading_days_between
from ..base import BaseStrategy, OrderInfo, Signal, SignalType
from scripts.rs_leader.rule import RSLeaderRule


class RSLeaderStrategy(BaseStrategy):
    name: str = "RSLeaderStrategy"
    version: str = "1.0.0"
    description: str = "횡보장 RS 리더 — 절대상승추세+횡단면RS (sl8/trail_ma20/max30, paper)"
    author: str = "Template"
    holding_period: str = "swing"
    accepts_volume_fallback: bool = True

    def get_min_data_length(self) -> int:
        params = self.config.get("parameters", {})
        return int(params.get("min_daily_bars", 130))

    def on_init(self, broker, data_provider, executor) -> bool:
        self._broker = broker
        self._data_provider = data_provider
        self._executor = executor

        params = self.config.get("parameters", {})
        self._min_daily_bars = int(params.get("min_daily_bars", 130))
        self._ma_short = int(params.get("ma_short", 20))
        self._ma_long = int(params.get("ma_long", 60))
        self._abs_lb = int(params.get("abs_lb", 60))

        risk = self.config.get("risk_management", {})
        self._take_profit_pct = float(risk.get("take_profit_pct", 0.15))
        self._stop_loss_pct = float(risk.get("stop_loss_pct", 0.08))
        self._max_hold_days = int(risk.get("max_hold_days", 30))
        self._trail_ma = risk.get("trail_ma", 20)
        self._trail_ma = int(self._trail_ma) if self._trail_ma is not None else None
        self._max_positions = int(risk.get("max_positions", 10))
        self._max_daily_trades = int(risk.get("max_daily_trades", 5))
        self._max_per_stock_amount = float(risk.get("max_per_stock_amount", 3_000_000))

        self.max_holding_days = int(
            params.get("max_holding_days", risk.get("max_hold_days", 30))
        )
        self._paper_trading = self.config.get("paper_trading", True)

        self.positions: Dict[str, Dict[str, Any]] = {}
        self.daily_trades = 0
        self._is_initialized = True
        self.logger.info(
            f"{self.name} v{self.version} 초기화 완료 "
            f"(RS리더, sl={self._stop_loss_pct:.0%}/trail_ma={self._trail_ma}/"
            f"max_hold={self._max_hold_days}거래일)"
        )
        if self._paper_trading:
            self.logger.info("⚠️ Paper Trading 모드 활성화")
        return True

    def on_market_open(self) -> None:
        self.daily_trades = 0
        if self.positions:
            self.logger.info(f"장 시작 — 보유 {len(self.positions)}개: {list(self.positions.keys())}")
        else:
            self.logger.info("장 시작 — 보유 종목 없음")

    def generate_signal(self, stock_code: str, data: pd.DataFrame,
                        timeframe: str = "daily") -> Optional[Signal]:
        if data is None or len(data) < self.get_min_data_length():
            return None
        if stock_code in self.positions:
            return self._check_sell(stock_code, data)
        if self.daily_trades >= self._max_daily_trades:
            return None
        if len(self.positions) >= self._max_positions:
            return None
        if timeframe != "daily":
            return None
        return self._check_buy(stock_code, data)

    def on_order_filled(self, order: OrderInfo) -> None:
        self.daily_trades += 1
        if order.is_buy:
            self.positions[order.stock_code] = {
                "quantity": order.quantity, "entry_price": order.price,
                "entry_time": order.filled_at,
            }
            self.logger.info(f"📥 매수 체결: {order.stock_code} @ {order.price:,.0f} x {order.quantity}주")
        elif order.stock_code in self.positions:
            pos = self.positions.pop(order.stock_code)
            pnl_pct = (order.price - pos["entry_price"]) / pos["entry_price"] * 100
            prefix = "[PAPER] " if self._paper_trading else ""
            self.logger.info(f"📤 {prefix}매도 체결: {order.stock_code} @ {order.price:,.0f} ({pnl_pct:+.1f}%)")

    def on_market_close(self) -> None:
        self.logger.info(f"장 마감 — 거래 {self.daily_trades}건, 보유 {len(self.positions)}종목")

    # --- 순수 판단 함수 ---
    @staticmethod
    def evaluate_entry(df: pd.DataFrame, min_daily_bars: int = 130,
                       ma_short: int = 20, ma_long: int = 60, abs_lb: int = 60
                       ) -> Tuple[bool, List[str]]:
        """절대상승추세 진입 — RSLeaderRule 단일 소스 재사용."""
        if df is None or len(df) < min_daily_bars:
            return False, []
        rule = RSLeaderRule(ma_short=ma_short, ma_long=ma_long, abs_lb=abs_lb)
        sig = rule.generate_signal("_", df, "daily")
        if sig is None:
            return False, []
        return True, ["절대상승추세(종가>MA60·MA20>MA60·60일수익>0)"]

    @staticmethod
    def evaluate_sell_conditions(df: pd.DataFrame, entry_price: float, hold_days: int,
                                 stop_loss_pct: float = 0.08, take_profit_pct: float = 0.15,
                                 max_hold_days: int = 30, trail_ma: Optional[int] = 20
                                 ) -> Tuple[bool, List[str], str]:
        """청산 우선순위(검증 4-bis MA20TrailExitAdapter 정합):
        stop_loss → take_profit → ma_break(무조건) → max_hold."""
        close = df["close"].astype(float)
        cur_close = float(close.iloc[-1])
        ret = (cur_close - entry_price) / entry_price
        if ret <= -stop_loss_pct:
            return True, [f"손절 ({ret*100:+.1f}%)"], "stop_loss"
        if ret >= take_profit_pct:
            return True, [f"익절 ({ret*100:+.1f}%)"], "take_profit"
        if trail_ma is not None and len(close) >= trail_ma:
            ma_val = float(close.iloc[-trail_ma:].mean())
            if cur_close < ma_val:
                return True, [f"MA{trail_ma} 이탈 (종가 {cur_close:.0f} < MA {ma_val:.0f})"], "ma_break"
        if hold_days >= max_hold_days:
            return True, [f"최대 보유일 초과 ({hold_days}거래일)"], "max_hold"
        return False, [], ""

    # --- 내부 헬퍼 ---
    def _check_buy(self, stock_code: str, data: pd.DataFrame) -> Optional[Signal]:
        if not MarketHours.is_market_open("KRX"):
            return None
        triggered, reasons = self.evaluate_entry(
            data, min_daily_bars=self._min_daily_bars,
            ma_short=self._ma_short, ma_long=self._ma_long, abs_lb=self._abs_lb)
        if not triggered:
            return None
        current_price = float(data["close"].astype(float).iloc[-1])
        target = current_price * (1 + self._take_profit_pct)
        stop = current_price * (1 - self._stop_loss_pct)
        recommended_qty = max(1, int(self._max_per_stock_amount // current_price))
        metadata = {"close": current_price, "recommended_qty": recommended_qty}
        if self._paper_trading:
            metadata["paper_only"] = True
            self.logger.info(
                f"🧾 [PAPER] 매수 시그널: {stock_code} @ {current_price:,.0f} "
                f"(추천 {recommended_qty}주) | " + " | ".join(reasons))
        return Signal(signal_type=SignalType.BUY, stock_code=stock_code, confidence=60.0,
                      target_price=target, stop_loss=stop, reasons=reasons, metadata=metadata)

    def _check_sell(self, stock_code: str, data: pd.DataFrame) -> Optional[Signal]:
        pos = self.positions[stock_code]
        entry_price = pos["entry_price"]
        entry_time = pos.get("entry_time")
        hold_days = max(0, count_trading_days_between(entry_time, now_kst()) - 1) if entry_time else 0
        should_sell, reasons, exit_reason = self.evaluate_sell_conditions(
            df=data, entry_price=entry_price, hold_days=hold_days,
            stop_loss_pct=self._stop_loss_pct, take_profit_pct=self._take_profit_pct,
            max_hold_days=self._max_hold_days, trail_ma=self._trail_ma)
        if not should_sell:
            return None
        current_price = float(data["close"].astype(float).iloc[-1])
        pnl_pct = (current_price - entry_price) / entry_price * 100
        metadata = {"entry_price": entry_price, "pnl_pct": pnl_pct,
                    "hold_days": hold_days, "exit_reason": exit_reason}
        if self._paper_trading:
            metadata["paper_only"] = True
            self.logger.info(
                f"🧾 [PAPER] 매도 시그널: {stock_code} @ {current_price:,.0f} "
                f"({exit_reason}) | " + " | ".join(reasons))
        return Signal(signal_type=SignalType.SELL, stock_code=stock_code,
                      confidence=min(95.0, 60.0 + len(reasons) * 15),
                      reasons=reasons, metadata=metadata)
