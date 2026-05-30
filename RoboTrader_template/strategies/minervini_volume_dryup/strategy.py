"""
Minervini Volume Dry-up Strategy (Variant B) 페이퍼판
=====================================================

백테스트 검증판을 실전 파이프라인(BaseStrategy / on_tick)으로 코드화한 전략.

진입 신호는 백테스트와 1:1 일치를 보장하기 위해
``strategies/books/minervini_vcp/rules.py`` 의 ``rule_volume_dryup`` 을
직접 재사용한다 (Elder 전략과 동일 패턴).

진입 (rule=volume_dryup):
  - 최근 10봉 평균 거래량 <= 직전 30봉 평균의 70%  (거래량 dry-up)
  - confidence = 58 (룰 반환값)

청산 (Variant B):
  - 우선순위: 손절(-8%) → 익절(+12%) → 최대 보유(20거래일)
  - **trail 없음, trend_flip 없음** (Variant A와의 차이)

매수는 일봉(daily) 기준, 매도는 보유 종목의 일봉 재조회로 판정한다.
``holding_period = "swing"`` 이므로 EOD 일괄청산을 건너뛴다.

설계상 의도된 처리(Elder와 동일 정책):
  - hold_days는 달력일이 아니라 **거래일** 경과수(``_trading_days_elapsed``)로
    계산해 백테스트 bar-count와 정합시킨다.
  - 체결 슬리피지·세금·수수료는 프레임워크(core/fund_manager · OrderExecutor)의
    책임이며 전략은 순수 신호만 생성한다.

⚠️ 경고: 백테스트 Sharpe **variant B 0.64 vs variant A 0.03** — variant 선택에
극도로 민감하며 BULL(강세장) 편향 리스크가 크다. 단일 국면(강세장)에서 측정된
우위일 수 있으므로 반드시 페이퍼 검증(paper_trading=True)을 거친 뒤 운용한다.
"""

from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd

from config.market_hours import MarketHours
from utils.korean_time import now_kst
from utils.korean_holidays import count_trading_days_between
from ..base import BaseStrategy, OrderInfo, Signal, SignalType

# 백테스트 룰을 직접 재사용 → 진입 신호 1:1 일치 보장
from strategies.books.minervini_vcp.rules import rule_volume_dryup


class MinerviniVolumeDryupStrategy(BaseStrategy):
    """Minervini Volume Dry-up (Variant B) — 거래량 수축 진입, sl/tp/max_hold 청산 (스윙).

    ⚠️ 백테스트 Sharpe variant B 0.64 vs variant A 0.03 — variant 의존성·BULL 편향
    리스크. 페이퍼(paper_trading=True) 검증 필수.
    """

    name: str = "MinerviniVolumeDryupStrategy"
    version: str = "1.0.0"
    description: str = "Minervini volume_dryup B — 거래량 dry-up 진입 (sl8/tp12/max_hold20거래일)"
    author: str = "Template"
    holding_period: str = "swing"
    # 거래량 수축 진입 — 거래량 상위 fallback 풀과 정합 (기본 True 유지)
    accepts_volume_fallback: bool = True

    # ========================================================================
    # 라이프사이클
    # ========================================================================

    def get_min_data_length(self) -> int:
        """진입 룰(rule_volume_dryup)이 요구하는 최소 일봉 수 (recent10 + base30 = 40)."""
        params = self.config.get("parameters", {})
        return int(params.get("min_daily_bars", 40))

    def on_init(self, broker, data_provider, executor) -> bool:
        self._broker = broker
        self._data_provider = data_provider
        self._executor = executor

        params = self.config.get("parameters", {})
        self._min_daily_bars = int(params.get("min_daily_bars", 40))

        risk = self.config.get("risk_management", {})
        self._take_profit_pct = float(risk.get("take_profit_pct", 0.12))
        self._stop_loss_pct = float(risk.get("stop_loss_pct", 0.08))
        self._max_hold_days = int(risk.get("max_hold_days", 20))
        self._max_positions = int(risk.get("max_positions", 5))
        self._max_daily_trades = int(risk.get("max_daily_trades", 5))
        self._max_per_stock_amount = float(risk.get("max_per_stock_amount", 3_000_000))

        # 프레임워크 max_holding_days 표준 키 (parameters 우선, fallback risk.max_hold_days)
        self.max_holding_days = int(
            params.get("max_holding_days", risk.get("max_hold_days", 20))
        )

        # 진입 룰 인스턴스 (백테스트와 동일 파라미터)
        self._entry_rule = rule_volume_dryup()

        self._paper_trading = self.config.get("paper_trading", True)

        # 상태
        self.positions: Dict[str, Dict[str, Any]] = {}
        self.daily_trades = 0

        self._is_initialized = True
        self.logger.info(
            f"{self.name} v{self.version} 초기화 완료 "
            f"(volume_dryup, sl={self._stop_loss_pct:.0%}/tp={self._take_profit_pct:.0%}/"
            f"max_hold={self.max_holding_days}거래일)"
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
        min_daily_bars: int = 40,
    ) -> Tuple[bool, List[str], Dict[str, Any]]:
        """진입 조건 평가 — 백테스트 rule_volume_dryup을 그대로 호출.

        Args:
            df: 일봉 OHLCV DataFrame (마지막 행 = 평가 시점 t, no-lookahead)
            min_daily_bars: 최소 일봉 수 가드 (recent10 + base30 = 40)

        Returns:
            (triggered, reasons, metadata)
        """
        if df is None or len(df) < min_daily_bars:
            return False, [], {}
        rule = rule_volume_dryup()
        res = rule.evaluate(df, {})
        if not res.triggered:
            return False, [], {}
        return True, list(res.reasons), dict(res.metadata)

    @staticmethod
    def evaluate_sell_conditions(
        df: pd.DataFrame,
        entry_price: float,
        hold_days: int,
        take_profit_pct: float = 0.12,
        stop_loss_pct: float = 0.08,
        max_hold_days: int = 20,
    ) -> Tuple[bool, List[str], str]:
        """청산 조건 평가 (Variant B) — sl → tp → max_hold 우선순위.

        Variant A와 달리 **trail_ema / trend_flip 없음**.

        평가 우선순위:
          1. stop_loss   : ret <= -stop_loss_pct
          2. take_profit : ret >= take_profit_pct
          3. max_hold    : hold_days >= max_hold_days  (거래일 기준)

        Args:
            df: 일봉 OHLCV DataFrame (마지막 행 = 평가 시점). 현재가 산출에 사용.
            entry_price: 진입가
            hold_days: 보유 거래일 수
            나머지: Variant B 파라미터

        Returns:
            (should_sell, reasons, exit_reason)  — exit_reason은 단일 사유 코드.
        """
        close = df["close"].astype(float)
        cur_close = float(close.iloc[-1])
        ret = (cur_close - entry_price) / entry_price

        # 1) 손절
        if ret <= -stop_loss_pct:
            return True, [f"손절 도달 ({ret * 100:+.1f}%)"], "stop_loss"
        # 2) 익절
        if ret >= take_profit_pct:
            return True, [f"익절 도달 ({ret * 100:+.1f}%)"], "take_profit"
        # 3) 최대 보유일 (거래일)
        if hold_days >= max_hold_days:
            return True, [f"최대 보유일 초과 ({hold_days}거래일)"], "max_hold"

        return False, [], ""

    # ========================================================================
    # 내부 헬퍼
    # ========================================================================

    @staticmethod
    def _trading_days_elapsed(entry_time: Optional[datetime]) -> int:
        """진입 시점 이후 경과한 **거래일** 수 (주말·공휴일 제외).

        백테스트는 보유일을 일봉 bar 단위로 센다(= 거래일 카운트). 달력일을 쓰면
        20거래일 ≈ 28달력일로 max_hold가 조기 발동해 백테스트와 어긋난다.
        ``utils.korean_holidays.count_trading_days_between`` 으로 진입 다음 거래일부터
        현재까지의 거래일 수를 계산한다. (Elder 전략과 동일 헬퍼.)

        의미: 같은 날 진입·평가하면 0거래일. 다음 거래일이면 1, 이후 누적.
        """
        if entry_time is None:
            return 0
        now = now_kst()
        start = entry_time + timedelta(days=1)
        if start.date() > now.date():
            return 0
        return count_trading_days_between(
            datetime(start.year, start.month, start.day),
            datetime(now.year, now.month, now.day),
        )

    def _check_buy(self, stock_code: str, data: pd.DataFrame) -> Optional[Signal]:
        if not MarketHours.is_market_open("KRX"):
            return None

        triggered, reasons, rule_meta = self.evaluate_entry(
            data, min_daily_bars=self._min_daily_bars
        )
        if not triggered:
            return None

        current_price = float(data["close"].astype(float).iloc[-1])

        target = current_price * (1 + self._take_profit_pct)
        stop = current_price * (1 - self._stop_loss_pct)
        recommended_qty = max(1, int(self._max_per_stock_amount // current_price))

        metadata = {
            "close": current_price,
            "recommended_qty": recommended_qty,
        }
        metadata.update(rule_meta)
        if self._paper_trading:
            metadata["paper_only"] = True
            self.logger.info(
                f"🧾 [PAPER] 매수 시그널: {stock_code} @ {current_price:,.0f} "
                f"(추천 {recommended_qty}주) | " + " | ".join(reasons)
            )

        return Signal(
            signal_type=SignalType.BUY,
            stock_code=stock_code,
            confidence=58.0,  # 백테스트 rule_volume_dryup confidence와 동일
            target_price=target,
            stop_loss=stop,
            reasons=reasons,
            metadata=metadata,
        )

    def _check_sell(self, stock_code: str, data: pd.DataFrame) -> Optional[Signal]:
        pos = self.positions[stock_code]
        entry_price = pos["entry_price"]
        entry_time = pos.get("entry_time")
        # 보유일은 달력일이 아니라 거래일 경과수로 평가 (백테스트 bar-count 정합)
        hold_days = self._trading_days_elapsed(entry_time)

        should_sell, reasons, exit_reason = self.evaluate_sell_conditions(
            df=data,
            entry_price=entry_price,
            hold_days=hold_days,
            take_profit_pct=self._take_profit_pct,
            stop_loss_pct=self._stop_loss_pct,
            max_hold_days=self._max_hold_days,
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
