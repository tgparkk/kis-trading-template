"""Deep MR Dev20 Strategy — MA20 -20% 폭락 평균회귀 (페이퍼 관찰 전용).

발굴 파이프라인 배치3 졸업 (gate_deep_mr_dev20.md, 3배치 22변형 중 유일 품질 전관문 통과).
진입: 백테스트 룰 단일소스(scripts.discovery.rules.MeanReversionMA20Rule, -20%/RSI<30) 재사용.
청산: sl -7% → tp +12% → MA20×0.9 회복 → 최대보유 7거래일
      (백테스트 MAReversionExitAdapter 와 동일 우선순위).
exit_timeframe="daily" — 일봉 청산 전략의 분봉 오작동(Elder whipsaw, 2026-06-09) 방지.
holding_period="swing" → EOD 일괄청산 건너뜀. paper_trading=True.
"""
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd

from config.market_hours import MarketHours
from utils.korean_time import now_kst
from utils.korean_holidays import count_trading_days_between
from ..base import BaseStrategy, OrderInfo, Signal, SignalType
from scripts.discovery.rules import MeanReversionMA20Rule


class DeepMrDev20Strategy(BaseStrategy):
    name: str = "DeepMrDev20Strategy"
    version: str = "1.0.0"
    description: str = "MA20 -20% 폭락 평균회귀 — sl7/tp12/MA회복0.9/max7거래일 (paper)"
    author: str = "Template"
    holding_period: str = "swing"
    exit_timeframe: str = "daily"          # 일봉 청산 — 분봉 whipsaw 방지
    accepts_volume_fallback: bool = False  # 희소조건 전략 — 후보 없으면 미진입이 정합

    def get_min_data_length(self) -> int:
        params = self.config.get("parameters", {})
        return int(params.get("min_daily_bars", 35))

    def on_init(self, broker, data_provider, executor) -> bool:
        self._broker = broker
        self._data_provider = data_provider
        self._executor = executor

        params = self.config.get("parameters", {})
        self._min_daily_bars = int(params.get("min_daily_bars", 35))
        self._ma_period = int(params.get("ma_period", 20))
        self._entry_deviation_pct = float(params.get("entry_deviation_pct", -20.0))
        self._rsi_period = int(params.get("rsi_period", 14))
        self._rsi_oversold = float(params.get("rsi_oversold", 30))

        risk = self.config.get("risk_management", {})
        self._stop_loss_pct = float(risk.get("stop_loss_pct", 0.07))
        self._take_profit_pct = float(risk.get("take_profit_pct", 0.12))
        self._max_hold_days = int(risk.get("max_hold_days", 7))
        self._recovery_ratio = float(risk.get("recovery_ratio", 0.9))
        self._max_positions = int(risk.get("max_positions", 5))
        self._max_daily_trades = int(risk.get("max_daily_trades", 5))
        self._max_per_stock_amount = float(risk.get("max_per_stock_amount", 2_000_000))

        self.max_holding_days = int(
            params.get("max_holding_days", risk.get("max_hold_days", 7))
        )
        self._paper_trading = self.config.get("paper_trading", True)

        self.positions: Dict[str, Dict[str, Any]] = {}
        self.daily_trades = 0
        self._is_initialized = True
        self.logger.info(
            f"{self.name} v{self.version} 초기화 완료 "
            f"(MA{self._ma_period} {self._entry_deviation_pct:.0f}% 폭락 매수, "
            f"sl={self._stop_loss_pct:.0%}/tp={self._take_profit_pct:.0%}/"
            f"회복 MA×{self._recovery_ratio}/max_hold={self._max_hold_days}거래일)"
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
        if timeframe != "daily":
            # 매도분기보다 먼저 — position_monitor는 보유종목 매도판단에 무조건
            # timeframe='intraday'로 분봉을 전달하므로, 가드가 뒤에 있으면 분봉
            # MA20(≈현재가)×0.9 회복이 항상 참 → 매수 즉시 청산 (2026-06-12 라이브).
            return None
        if stock_code in self.positions:
            return self._check_sell(stock_code, data)
        if self.daily_trades >= self._max_daily_trades:
            return None
        if len(self.positions) >= self._max_positions:
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

    # --- 순수 판단 함수 (백테스트 단일소스 정합) ---
    @staticmethod
    def evaluate_entry(df: pd.DataFrame, min_daily_bars: int = 35,
                       ma_period: int = 20, entry_deviation_pct: float = -20.0,
                       rsi_period: int = 14, rsi_oversold: float = 30.0,
                       ) -> Tuple[bool, List[str]]:
        """깊은 폭락 진입 — MeanReversionMA20Rule 단일 소스 재사용 (DRY)."""
        if df is None or len(df) < min_daily_bars:
            return False, []
        rule = MeanReversionMA20Rule(
            ma_period=ma_period, entry_deviation_pct=entry_deviation_pct,
            rsi_period=rsi_period, rsi_oversold=rsi_oversold)
        sig = rule.generate_signal("_", df, "daily")
        if sig is None:
            return False, []
        return True, list(sig.reasons or [f"MA{ma_period} {entry_deviation_pct:.0f}% 이탈+RSI<{rsi_oversold:.0f}"])

    @staticmethod
    def evaluate_sell_conditions(df: pd.DataFrame, entry_price: float, hold_days: int,
                                 stop_loss_pct: float = 0.07, take_profit_pct: float = 0.12,
                                 max_hold_days: int = 7, ma_period: int = 20,
                                 recovery_ratio: float = 0.9,
                                 ) -> Tuple[bool, List[str], str]:
        """청산 우선순위(백테스트 MAReversionExitAdapter 정합):
        stop_loss → take_profit → ma_recovery(종가≥MA20×ratio) → max_hold."""
        close = df["close"].astype(float)
        cur_close = float(close.iloc[-1])
        ret = (cur_close - entry_price) / entry_price
        if ret <= -stop_loss_pct:
            return True, [f"손절 ({ret*100:+.1f}%)"], "stop_loss"
        if ret >= take_profit_pct:
            return True, [f"익절 ({ret*100:+.1f}%)"], "take_profit"
        if len(close) >= ma_period:
            ma_val = float(close.iloc[-ma_period:].mean())
            if cur_close >= ma_val * recovery_ratio:
                return True, [f"MA{ma_period}×{recovery_ratio} 회복 "
                              f"(종가 {cur_close:.0f} ≥ {ma_val * recovery_ratio:.0f})"], "ma_recovery"
        if hold_days >= max_hold_days:
            return True, [f"최대 보유일 초과 ({hold_days}거래일)"], "max_hold"
        return False, [], ""

    # --- 내부 헬퍼 ---
    def _check_buy(self, stock_code: str, data: pd.DataFrame) -> Optional[Signal]:
        if not MarketHours.is_market_open("KRX"):
            return None
        triggered, reasons = self.evaluate_entry(
            data, min_daily_bars=self._min_daily_bars,
            ma_period=self._ma_period, entry_deviation_pct=self._entry_deviation_pct,
            rsi_period=self._rsi_period, rsi_oversold=self._rsi_oversold)
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
            max_hold_days=self._max_hold_days, ma_period=self._ma_period,
            recovery_ratio=self._recovery_ratio)
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
