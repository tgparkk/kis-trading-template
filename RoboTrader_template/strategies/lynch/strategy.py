"""
Lynch Strategy — 피터 린치 PEG 기반 가치+성장 전략
====================================================

매수 조건 (모두 충족):
  1. PEG ≤ 0.3  (PER / 영업이익성장률%)
  2. 영업이익 YoY ≥ 70%
  3. 부채비율 ≤ 200%
  4. ROE ≥ 5%
  5. RSI(14) < 35
  6. PER > 0, 영업이익 > 0 (적자 제외)

매도 조건 (1개 이상):
  - 익절: +50%
  - 손절: -15%
  - 최대 보유: 120거래일
"""

from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd

from config.market_hours import MarketHours
from ..base import BaseStrategy, OrderInfo, Signal, SignalType
from utils.indicators import calculate_rsi
from utils.korean_time import now_kst
from .db_manager import LynchDBManager


class LynchStrategy(BaseStrategy):
    """피터 린치 PEG 기반 가치+성장 전략"""

    name: str = "LynchStrategy"
    version: str = "1.0.0"
    description: str = "PEG ≤ 0.3 + 영업이익성장 70%↑ + 부채비율 200%↓ + ROE 5%↑ + RSI < 35"
    author: str = "Template"
    holding_period: str = "swing"

    def get_min_data_length(self) -> int:
        """RSI14 + 여유 2 = 16 (재무 기반 전략, 일봉은 RSI만 사용)"""
        params = self.config.get("parameters", {})
        rsi_period = params.get("rsi_period", 14)
        return rsi_period + 2

    def on_init(self, broker, data_provider, executor) -> bool:
        self._broker = broker
        self._data_provider = data_provider
        self._executor = executor

        # 매수 파라미터
        params = self.config.get("parameters", {})
        self._peg_max = params.get("peg_max", 0.3)
        self._op_growth_min = params.get("op_income_growth_min", 70.0)
        self._debt_ratio_max = params.get("debt_ratio_max", 200.0)
        self._roe_min = params.get("roe_min", 5.0)
        self._rsi_period = params.get("rsi_period", 14)
        self._rsi_oversold = params.get("rsi_oversold", 35)

        # 매도 / 리스크 파라미터
        risk = self.config.get("risk_management", {})
        self._take_profit_pct = risk.get("take_profit_pct", 0.50)
        self._stop_loss_pct = risk.get("stop_loss_pct", 0.15)
        self._max_hold_days = risk.get("max_hold_days", 120)
        self._max_daily_trades = risk.get("max_daily_trades", 5)
        self._max_positions = risk.get("max_positions", 5)
        self._max_daily_loss_pct = risk.get("max_daily_loss_pct", 5.0)
        self._max_per_stock_amount = risk.get("max_per_stock_amount", 3_000_000)
        # C4: 프레임워크 max_holding_days 표준 키 (parameters 우선, fallback risk.max_hold_days)
        self.max_holding_days = params.get("max_holding_days", risk.get("max_hold_days", 120))

        # 안전장치
        self._paper_trading = self.config.get("paper_trading", True)

        # DB 매니저
        self._db = LynchDBManager()

        # 상태
        self.positions: Dict[str, Dict[str, Any]] = {}
        self.daily_trades = 0
        self._daily_realized_loss: float = 0.0
        self._daily_loss_limit_hit: bool = False
        self._fundamental_cache: Dict[str, Dict[str, Any]] = {}

        # DB에서 보유 포지션 복원
        self._load_positions_from_db()

        self._is_initialized = True
        self.logger.info(
            f"{self.name} v{self.version} 초기화 완료 "
            f"(PEG≤{self._peg_max}, "
            f"영업이익성장≥{self._op_growth_min}%, "
            f"부채비율≤{self._debt_ratio_max}%, "
            f"ROE≥{self._roe_min}%, "
            f"RSI<{self._rsi_oversold})"
        )
        if self._paper_trading:
            self.logger.info("⚠️ Paper Trading 모드 활성화")
        return True

    def on_market_open(self) -> None:
        self.daily_trades = 0
        self._daily_realized_loss = 0.0
        self._daily_loss_limit_hit = False
        self._run_candidate_screening()
        self._load_fundamental_data()

    def generate_signal(
        self,
        stock_code: str,
        data: pd.DataFrame,
        timeframe: str = "daily",
    ) -> Optional[Signal]:
        if not MarketHours.is_market_open('KRX'):
            return None

        min_len = self._rsi_period + 2
        if data is None or len(data) < min_len:
            return None

        if self.daily_trades >= self._max_daily_trades:
            return None

        close = data["close"]
        current_price = float(close.iloc[-1])

        # 보유 종목 → 매도 체크
        if stock_code in self.positions:
            return self._check_sell(stock_code, current_price)

        if self._daily_loss_limit_hit:
            return None

        if len(self.positions) >= self._max_positions:
            return None

        if timeframe == "daily":
            return self._check_buy(stock_code, current_price, data)

        return None

    def on_order_filled(self, order: OrderInfo) -> None:
        self.daily_trades += 1
        if order.is_buy:
            self.positions[order.stock_code] = {
                "entry_price": order.price,
                "entry_time": order.filled_at,
            }
            self._db.open_trade(
                stock_code=order.stock_code,
                stock_name=getattr(order, 'stock_name', order.stock_code),
                buy_date=order.filled_at,
                buy_price=order.price,
                buy_quantity=order.quantity,
                buy_reason=", ".join(getattr(order, 'reasons', [])),
            )
            self.logger.info(
                f"📥 매수 체결: {order.stock_code} "
                f"@ {order.price:,.0f} x {order.quantity}주"
            )
        elif order.stock_code in self.positions:
            pos = self.positions.pop(order.stock_code)
            pnl_pct = (order.price - pos["entry_price"]) / pos["entry_price"] * 100
            sell_reason = "TP" if pnl_pct >= self._take_profit_pct * 100 else \
                          "SL" if pnl_pct <= -self._stop_loss_pct * 100 else "TIMEOUT"
            self._db.close_trade(
                stock_code=order.stock_code,
                sell_date=order.filled_at,
                sell_price=order.price,
                sell_reason=sell_reason,
            )
            if pnl_pct < 0:
                self._daily_realized_loss += pnl_pct
                if abs(self._daily_realized_loss) >= self._max_daily_loss_pct:
                    self._daily_loss_limit_hit = True
            prefix = "[PAPER] " if self._paper_trading else ""
            self.logger.info(
                f"📤 {prefix}매도 체결: {order.stock_code} "
                f"@ {order.price:,.0f} (수익률 {pnl_pct:+.1f}%)"
            )

    def on_market_close(self) -> None:
        self.logger.info(
            f"장 마감 — 거래 {self.daily_trades}건, "
            f"보유 {len(self.positions)}종목"
        )

    # ========================================================================
    # 순수 판단 함수 — 시뮬레이션에서도 동일하게 호출 가능
    # ========================================================================

    @staticmethod
    def evaluate_buy_conditions(
        current_price: float,
        rsi_value: float,
        fundamentals: Dict[str, Any],
        peg_max: float = 0.3,
        op_growth_min: float = 70.0,
        debt_ratio_max: float = 200.0,
        roe_min: float = 5.0,
        rsi_oversold: float = 35.0,
    ) -> Tuple[bool, List[str]]:
        """
        매수 조건 평가 — 순수 함수 (외부 의존성 없음).

        Args:
            current_price: 현재가
            rsi_value: RSI(14) 값
            fundamentals: dict with keys:
                per, op_income_growth, debt_ratio, roe
            peg_max, op_growth_min, debt_ratio_max, roe_min, rsi_oversold: 파라미터

        Returns:
            (should_buy, reasons)
        """
        reasons: List[str] = []

        per = fundamentals.get("per", 0.0)
        op_growth = fundamentals.get("op_income_growth", 0.0)
        debt_ratio = fundamentals.get("debt_ratio", 999.0)
        roe = fundamentals.get("roe", 0.0)

        # 적자 제외
        if per <= 0 or op_growth <= 0:
            return False, ["PER≤0 또는 영업이익≤0 (적자)"]

        # PEG
        peg = per / op_growth
        if peg > peg_max:
            return False, [f"PEG {peg:.3f} > {peg_max}"]
        reasons.append(f"PEG {peg:.3f}")

        # 영업이익 성장률
        if op_growth < op_growth_min:
            return False, [f"영업이익성장 {op_growth:.1f}% < {op_growth_min}%"]
        reasons.append(f"영업이익 YoY {op_growth:+.1f}%")

        # 부채비율
        if debt_ratio > debt_ratio_max:
            return False, [f"부채비율 {debt_ratio:.1f}% > {debt_ratio_max}%"]
        reasons.append(f"부채비율 {debt_ratio:.1f}%")

        # ROE
        if roe < roe_min:
            return False, [f"ROE {roe:.1f}% < {roe_min}%"]
        reasons.append(f"ROE {roe:.1f}%")

        # RSI
        if pd.isna(rsi_value) or rsi_value >= rsi_oversold:
            return False, [f"RSI {rsi_value:.1f} ≥ {rsi_oversold}"]
        reasons.append(f"RSI {rsi_value:.1f}")

        return True, reasons

    @staticmethod
    def evaluate_sell_conditions(
        current_price: float,
        entry_price: float,
        hold_days: int,
        take_profit_pct: float = 0.50,
        stop_loss_pct: float = 0.15,
        max_hold_days: int = 120,
    ) -> Tuple[bool, List[str]]:
        """
        매도 조건 평가 — 순수 함수 (외부 의존성 없음).

        Returns:
            (should_sell, reasons)
        """
        pnl_pct = (current_price - entry_price) / entry_price
        reasons: List[str] = []

        if pnl_pct >= take_profit_pct:
            reasons.append(f"익절 도달 ({pnl_pct * 100:+.1f}%)")
        if pnl_pct <= -stop_loss_pct:
            reasons.append(f"손절 도달 ({pnl_pct * 100:+.1f}%)")
        if hold_days >= max_hold_days:
            reasons.append(f"최대 보유일 초과 ({hold_days}일)")

        return bool(reasons), reasons

    # ========================================================================
    # 내부 헬퍼
    # ========================================================================

    def _load_positions_from_db(self) -> None:
        try:
            holdings = self._db.get_holding_positions()
            for h in holdings:
                self.positions[h["stock_code"]] = {
                    "entry_price": float(h["buy_price"]),
                    "entry_time": h["buy_date"],
                }
            if self.positions:
                self.logger.info(f"DB에서 포지션 복원: {len(self.positions)}종목")
        except Exception as e:
            self.logger.error(f"DB 포지션 복원 실패: {e}")

    def _run_candidate_screening(self) -> None:
        try:
            from strategies.lynch.screener import LynchCandidateSelector
            from core.models import TradingConfig

            trading_config = getattr(self._broker, 'config', None)
            if trading_config is None:
                trading_config = TradingConfig()

            strategy_params = self.config.get("parameters", {})
            selector = LynchCandidateSelector(
                config=trading_config,
                broker=self._broker,
                strategy_params=strategy_params,
            )

            max_candidates = strategy_params.get("max_screening_candidates", 20)
            candidates = selector.select_daily_candidates(max_candidates)

            if candidates:
                new_targets = [c.code for c in candidates]
                if 'target_stocks' not in self.config:
                    self.config['target_stocks'] = []
                existing = set(self.config['target_stocks'])
                combined = list(existing | set(new_targets))
                self.config['target_stocks'] = combined

                self.logger.info(
                    f"📊 Lynch 스크리닝 완료: {len(candidates)}종목 선정 → "
                    f"target_stocks {len(combined)}종목"
                )
        except Exception as e:
            self.logger.error(f"📊 Lynch 스크리닝 실패: {e}", exc_info=True)

    def _load_fundamental_data(self) -> None:
        target_stocks = self.get_target_stocks()
        if not target_stocks:
            return
        try:
            from api.kis_financial_api import get_financial_ratio
        except ImportError:
            self.logger.warning("kis_financial_api 임포트 실패")
            return

        for code in target_stocks:
            if code in self._fundamental_cache:
                continue
            try:
                ratios = get_financial_ratio(code)
                if ratios:
                    latest = ratios[0]
                    self._fundamental_cache[code] = {
                        "per": latest.per,
                        "op_income_growth": latest.operating_income_growth,
                        "debt_ratio": latest.debt_ratio,
                        "roe": latest.roe,
                    }
            except Exception as e:
                self.logger.warning(f"재무 데이터 조회 실패 {code}: {e}")

    def _check_buy(
        self,
        stock_code: str,
        current_price: float,
        data: pd.DataFrame,
    ) -> Optional[Signal]:
        fund = self._fundamental_cache.get(stock_code)
        if not fund:
            return None

        # RSI 계산
        rsi = calculate_rsi(data["close"], self._rsi_period)
        rsi_val = float(rsi.iloc[-1])

        should_buy, reasons = self.evaluate_buy_conditions(
            current_price=current_price,
            rsi_value=rsi_val,
            fundamentals=fund,
            peg_max=self._peg_max,
            op_growth_min=self._op_growth_min,
            debt_ratio_max=self._debt_ratio_max,
            roe_min=self._roe_min,
            rsi_oversold=self._rsi_oversold,
        )

        if not should_buy:
            return None

        target = current_price * (1 + self._take_profit_pct)
        stop = current_price * (1 - self._stop_loss_pct)
        recommended_qty = max(1, int(self._max_per_stock_amount // current_price))

        if self._paper_trading:
            self.logger.info(
                f"🧾 [PAPER] 매수 시그널: {stock_code} @ {current_price:,.0f} "
                f"(추천 {recommended_qty}주) | " + " | ".join(reasons)
            )

        metadata = {
            "per": fund.get("per"),
            "peg": fund.get("per", 0) / fund.get("op_income_growth", 1),
            "op_income_growth": fund.get("op_income_growth"),
            "debt_ratio": fund.get("debt_ratio"),
            "roe": fund.get("roe"),
            "rsi": rsi_val,
            "recommended_qty": recommended_qty,
        }
        if self._paper_trading:
            metadata["paper_only"] = True

        return Signal(
            signal_type=SignalType.BUY,
            stock_code=stock_code,
            confidence=min(95.0, 70.0 + len(reasons) * 5),
            target_price=target,
            stop_loss=stop,
            reasons=reasons,
            metadata=metadata,
        )

    def _check_sell(
        self,
        stock_code: str,
        current_price: float,
    ) -> Optional[Signal]:
        pos = self.positions[stock_code]
        entry_price = pos["entry_price"]
        hold_days = (now_kst() - pos["entry_time"]).days

        should_sell, reasons = self.evaluate_sell_conditions(
            current_price=current_price,
            entry_price=entry_price,
            hold_days=hold_days,
            take_profit_pct=self._take_profit_pct,
            stop_loss_pct=self._stop_loss_pct,
            max_hold_days=self._max_hold_days,
        )

        if not should_sell:
            return None

        if self._paper_trading:
            self.logger.info(
                f"🧾 [PAPER] 매도 시그널: {stock_code} @ {current_price:,.0f} | "
                + " | ".join(reasons)
            )

        pnl_pct = (current_price - entry_price) / entry_price * 100
        metadata = {
            "entry_price": entry_price,
            "pnl_pct": pnl_pct,
            "hold_days": hold_days,
        }
        if self._paper_trading:
            metadata["paper_only"] = True

        return Signal(
            signal_type=SignalType.SELL,
            stock_code=stock_code,
            confidence=min(95.0, 60.0 + len(reasons) * 15),
            reasons=reasons,
            metadata=metadata,
        )
