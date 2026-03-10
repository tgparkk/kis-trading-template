"""
Sample Strategy — 이동평균 크로스 + RSI
=======================================

간단하지만 실제 동작하는 예제 전략입니다.

매수 조건 (2개 이상 충족 시):
  1. 5일 이동평균이 20일 이동평균을 골든크로스
  2. RSI(14)가 과매도(30) 구간에서 탈출
  3. 거래량이 20일 평균의 1.5배 이상

매도 조건 (1개 이상 충족 시):
  1. 5일 이동평균이 20일 이동평균을 데드크로스
  2. RSI(14)가 과매수(70) 구간 진입
  3. 익절(+10%) 또는 손절(-5%) 도달
"""

from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd

from ..base import BaseStrategy, OrderInfo, Signal, SignalType


class SampleStrategy(BaseStrategy):
    """이동평균 크로스 + RSI 복합 전략"""

    name: str = "SampleStrategy"
    version: str = "1.0.0"
    description: str = "이동평균 골든/데드크로스 + RSI 기반 매매 전략"
    author: str = "Template"

    # ========================================================================
    # 라이프사이클
    # ========================================================================

    def on_init(self, broker, data_provider, executor) -> bool:
        self._broker = broker
        self._data_provider = data_provider
        self._executor = executor

        # 전략 파라미터 (config.yaml에서 로드)
        params = self.config.get("parameters", {})
        self._ma_short = params.get("ma_short_period", 5)
        self._ma_long = params.get("ma_long_period", 20)
        self._rsi_period = params.get("rsi_period", 14)
        self._rsi_oversold = params.get("rsi_oversold", 30)
        self._rsi_overbought = params.get("rsi_overbought", 70)
        self._volume_multiplier = params.get("volume_multiplier", 1.5)
        self._min_buy_signals = params.get("min_buy_signals", 2)

        # 리스크 파라미터
        risk = self.config.get("risk_management", {})
        self._stop_loss_pct = risk.get("stop_loss_pct", 0.05)
        self._take_profit_pct = risk.get("take_profit_pct", 0.10)
        self._max_position_size = risk.get("max_position_size", 0.1)
        self._max_daily_trades = risk.get("max_daily_trades", 5)

        # 상태 변수
        self.positions: Dict[str, Dict[str, Any]] = {}
        self.daily_trades = 0
        self.daily_profit = 0.0

        self._is_initialized = True
        self.logger.info(
            f"{self.name} v{self.version} 초기화 완료 "
            f"(MA {self._ma_short}/{self._ma_long}, RSI {self._rsi_period})"
        )
        return True

    def on_market_open(self) -> None:
        self.daily_trades = 0
        self.daily_profit = 0.0

        # 보유 종목이 있으면 로깅
        if self.positions:
            self.logger.info(
                f"장 시작 — 보유 종목 {len(self.positions)}개: "
                f"{list(self.positions.keys())}"
            )
        else:
            self.logger.info("장 시작 — 보유 종목 없음")

    def generate_signal(
        self,
        stock_code: str,
        data: pd.DataFrame,
        timeframe: str = 'daily',
    ) -> Optional[Signal]:
        # 최소 데이터 길이 확인
        min_len = max(self._ma_long, self._rsi_period) + 2
        if data is None or len(data) < min_len:
            return None

        # 일일 거래 한도 확인
        if self.daily_trades >= self._max_daily_trades:
            return None

        # 지표 계산
        close = data["close"]
        sma_short = close.rolling(self._ma_short).mean()
        sma_long = close.rolling(self._ma_long).mean()
        rsi = self._calculate_rsi(close, self._rsi_period)
        avg_volume = data["volume"].rolling(self._ma_long).mean()

        current_price = float(close.iloc[-1])

        # ── 보유 종목이면 매도 판단 우선 ──
        if stock_code in self.positions:
            sell, reasons = self._check_sell(
                stock_code, current_price, sma_short, sma_long, rsi
            )
            if sell:
                return Signal(
                    signal_type=SignalType.SELL,
                    stock_code=stock_code,
                    confidence=min(90.0, 50.0 + len(reasons) * 20),
                    reasons=reasons,
                    metadata={"position": self.positions[stock_code]},
                )
            self.logger.debug(
                f"[신호없음] {stock_code}: 매도조건 미달 "
                f"(RSI={float(rsi.iloc[-1]):.1f}, "
                f"MA{self._ma_short}={float(sma_short.iloc[-1]):.0f}"
                f"{'>' if sma_short.iloc[-1] > sma_long.iloc[-1] else '<'}"
                f"MA{self._ma_long}={float(sma_long.iloc[-1]):.0f})"
            )
            return None

        # ── 미보유 종목이면 매수 판단 ──
        buy, reasons = self._check_buy(
            sma_short, sma_long, rsi, data["volume"], avg_volume
        )
        if buy:
            target = current_price * (1 + self._take_profit_pct)
            stop = current_price * (1 - self._stop_loss_pct)
            return Signal(
                signal_type=SignalType.BUY,
                stock_code=stock_code,
                confidence=min(95.0, 50.0 + len(reasons) * 15),
                target_price=target,
                stop_loss=stop,
                reasons=reasons,
                metadata={
                    "sma_short": float(sma_short.iloc[-1]),
                    "sma_long": float(sma_long.iloc[-1]),
                    "rsi": float(rsi.iloc[-1]),
                },
            )

        # 지표 계산까지 했지만 매수 조건 미달
        self.logger.debug(
            f"[신호없음] {stock_code}: 매수조건 미달 "
            f"(RSI={float(rsi.iloc[-1]):.1f}, "
            f"MA{self._ma_short}={float(sma_short.iloc[-1]):.0f}"
            f"{'>' if sma_short.iloc[-1] > sma_long.iloc[-1] else '<'}"
            f"MA{self._ma_long}={float(sma_long.iloc[-1]):.0f})"
        )
        return None

    def on_order_filled(self, order: OrderInfo) -> None:
        self.daily_trades += 1

        if order.is_buy:
            self.positions[order.stock_code] = {
                "quantity": order.quantity,
                "entry_price": order.price,
                "entry_time": order.filled_at,
            }
            self.logger.info(
                f"매수 체결: {order.stock_code} "
                f"{order.quantity}주 @ {order.price:,.0f}원"
            )
        else:
            if order.stock_code in self.positions:
                entry = self.positions[order.stock_code]["entry_price"]
                pnl_pct = (order.price - entry) / entry * 100
                self.daily_profit += (order.price - entry) * order.quantity
                self.logger.info(
                    f"매도 체결: {order.stock_code} "
                    f"{order.quantity}주 @ {order.price:,.0f}원 "
                    f"(수익률 {pnl_pct:+.2f}%)"
                )
                del self.positions[order.stock_code]
            else:
                self.logger.info(
                    f"매도 체결: {order.stock_code} "
                    f"{order.quantity}주 @ {order.price:,.0f}원"
                )

    def on_market_close(self) -> None:
        self.logger.info(
            f"장 마감 — 일일 거래 {self.daily_trades}건, "
            f"일일 수익 {self.daily_profit:+,.0f}원, "
            f"잔여 포지션 {len(self.positions)}개"
        )

    # ========================================================================
    # 내부 헬퍼
    # ========================================================================

    def _check_buy(
        self,
        sma_short: pd.Series,
        sma_long: pd.Series,
        rsi: pd.Series,
        volume: pd.Series,
        avg_volume: pd.Series,
    ) -> Tuple[bool, List[str]]:
        reasons: List[str] = []

        # 1) 골든크로스
        if (
            sma_short.iloc[-1] > sma_long.iloc[-1]
            and sma_short.iloc[-2] <= sma_long.iloc[-2]
        ):
            reasons.append(
                f"{self._ma_short}일선이 {self._ma_long}일선 골든크로스"
            )

        # 2) RSI 과매도 탈출
        if rsi.iloc[-2] < self._rsi_oversold and rsi.iloc[-1] >= self._rsi_oversold:
            reasons.append(
                f"RSI({self._rsi_period}) 과매도 탈출 ({rsi.iloc[-1]:.1f})"
            )

        # 3) 거래량 급증
        if (
            pd.notna(avg_volume.iloc[-1])
            and avg_volume.iloc[-1] > 0
            and volume.iloc[-1] > avg_volume.iloc[-1] * self._volume_multiplier
        ):
            ratio = volume.iloc[-1] / avg_volume.iloc[-1]
            reasons.append(f"거래량 {ratio:.1f}배 급증")

        # 진단 로그
        gc = "O" if any("골든크로스" in r for r in reasons) else "X"
        rs = "O" if any("과매도 탈출" in r for r in reasons) else "X"
        vl = "O" if any("거래량" in r for r in reasons) else "X"
        hit = len(reasons)
        status = "매수!" if hit >= self._min_buy_signals else "미달"
        self.logger.debug(
            f"[매수조건] 골든크로스:{gc} RSI탈출:{rs} 거래량:{vl}"
            f" → 충족 {hit}/{self._min_buy_signals} ({status})"
        )

        return hit >= self._min_buy_signals, reasons

    def _check_sell(
        self,
        stock_code: str,
        current_price: float,
        sma_short: pd.Series,
        sma_long: pd.Series,
        rsi: pd.Series,
    ) -> Tuple[bool, List[str]]:
        reasons: List[str] = []
        pos = self.positions.get(stock_code, {})
        entry_price = pos.get("entry_price", 0)

        # 1) 데드크로스
        if (
            sma_short.iloc[-1] < sma_long.iloc[-1]
            and sma_short.iloc[-2] >= sma_long.iloc[-2]
        ):
            reasons.append(
                f"{self._ma_short}일선이 {self._ma_long}일선 데드크로스"
            )

        # 2) RSI 과매수
        if rsi.iloc[-1] > self._rsi_overbought:
            reasons.append(
                f"RSI({self._rsi_period}) 과매수 ({rsi.iloc[-1]:.1f})"
            )

        # 3) 익절 / 손절
        if entry_price > 0:
            pnl_pct = (current_price - entry_price) / entry_price
            if pnl_pct >= self._take_profit_pct:
                reasons.append(f"익절 도달 ({pnl_pct * 100:+.1f}%)")
            elif pnl_pct <= -self._stop_loss_pct:
                reasons.append(f"손절 도달 ({pnl_pct * 100:+.1f}%)")

        return len(reasons) >= 1, reasons

    @staticmethod
    def _calculate_rsi(series: pd.Series, period: int = 14) -> pd.Series:
        """Wilder RSI 계산"""
        delta = series.diff()
        gain = delta.clip(lower=0)
        loss = -delta.clip(upper=0)

        avg_gain = gain.ewm(alpha=1 / period, min_periods=period).mean()
        avg_loss = loss.ewm(alpha=1 / period, min_periods=period).mean()

        rs = avg_gain / avg_loss.replace(0, float("nan"))
        return 100 - (100 / (1 + rs))
