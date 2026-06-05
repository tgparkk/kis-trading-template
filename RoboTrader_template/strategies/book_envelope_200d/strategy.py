"""
Book Envelope 200d High Strategy — 『트레이딩 전략서』(Book 19) 일봉 돌파 실전판
==========================================================================

200일 종가신고가 + Envelope(10,10) 상단 돌파 매수후보 전략. 백테스트 정본(quant 일봉)
재측정 + OOS 홀드아웃(train 2021~2024.6 Sharpe 1.20 / test 2024.7~2026.5 Sharpe 1.82)에서
cross-period 강건이 확인된 유일 신규 엣지 → 6번째 페이퍼 전략으로 추가(관찰용).

진입 신호는 백테스트와 1:1 일치를 위해 ``strategies/books/trading_strategy_book/rules.py``
의 ``rule_envelope_200d_high`` 를 직접 재사용한다(조건식 A~I, 책 원문 verbatim 기본값).

★진입 평가는 200일 신고가 계산에 200영업일 이상이 필요하다. 라이브 일봉 피드(분석기
140달력일≈95봉, robotrader sparse)로는 부족하므로, **진입 평가용 일봉은 QuantDailyReader
(robotrader_quant, 일봉 SSOT)에서 직접 210봉을 조회**한다(스크리너와 동일 소스).
청산(sl/tp/max_hold)은 현재가·보유일만 필요하므로 프레임워크가 전달한 일봉을 사용한다.

청산(고정 손익절, trailing 없음):
  - 손절 -8% / 익절 +10% / 최대 보유 10거래일 (OOS 검증 config)

매수는 일봉(daily) 확정봉 기준, ``holding_period = "swing"`` 이므로 EOD 일괄청산 건너뜀.
"""

from typing import Any, Dict, List, Optional, Tuple

import pandas as pd

from config.market_hours import MarketHours
from utils.korean_time import now_kst
from utils.korean_holidays import count_trading_days_between
from ..base import BaseStrategy, OrderInfo, Signal, SignalType

# 백테스트 룰을 직접 재사용 → 진입 신호 1:1 일치 보장
from strategies.books.trading_strategy_book.rules import rule_envelope_200d_high

# 진입 평가에 필요한 최소 봉 수 (rule: max(high_window=200, env, value)+2 = 202)
_MIN_ENTRY_BARS = 202


class BookEnvelope200dStrategy(BaseStrategy):
    """200일 신고가 + Envelope 상단 돌파 매수 (스윙). 진입평가=quant 일봉."""

    name: str = "BookEnvelope200dStrategy"
    version: str = "1.0.0"
    description: str = "Book19 envelope_200d_high — 200일 신고가+Envelope 돌파 (sl8/tp10/max10, OOS 강건)"
    author: str = "Template"
    holding_period: str = "swing"
    accepts_volume_fallback: bool = True

    # ========================================================================
    # 라이프사이클
    # ========================================================================

    def get_min_data_length(self) -> int:
        params = self.config.get("parameters", {})
        return int(params.get("min_daily_bars", _MIN_ENTRY_BARS))

    def on_init(self, broker, data_provider, executor) -> bool:
        self._broker = broker
        self._data_provider = data_provider
        self._executor = executor

        params = self.config.get("parameters", {})
        self._min_daily_bars = int(params.get("min_daily_bars", _MIN_ENTRY_BARS))
        self._entry_lookback = int(params.get("entry_lookback_bars", 210))

        risk = self.config.get("risk_management", {})
        self._take_profit_pct = float(risk.get("take_profit_pct", 0.10))
        self._stop_loss_pct = float(risk.get("stop_loss_pct", 0.08))
        self._max_hold_days = int(risk.get("max_hold_days", 10))
        self._max_positions = int(risk.get("max_positions", 5))
        self._max_daily_trades = int(risk.get("max_daily_trades", 5))
        self._max_per_stock_amount = float(risk.get("max_per_stock_amount", 3_000_000))

        self.max_holding_days = int(
            params.get("max_holding_days", risk.get("max_hold_days", 10))
        )

        self._paper_trading = self.config.get("paper_trading", True)

        # 진입 평가용 quant 일봉 리더 (200봉 요구 → robotrader 피드 부족분 보강)
        self._quant = None
        # (code, KST date) -> 평가용 일봉 캐시 (하루 1회 DB 조회)
        self._entry_df_cache: Dict[Tuple[str, Any], Optional[pd.DataFrame]] = {}

        # 상태
        self.positions: Dict[str, Dict[str, Any]] = {}
        self.daily_trades = 0

        self._is_initialized = True
        self.logger.info(
            f"{self.name} v{self.version} 초기화 완료 "
            f"(200일신고가+Envelope, 진입평가=quant {self._entry_lookback}봉, "
            f"sl={self._stop_loss_pct:.0%}/tp={self._take_profit_pct:.0%}/"
            f"max_hold={self._max_hold_days}거래일, trailing 없음)"
        )
        if self._paper_trading:
            self.logger.info("⚠️ Paper Trading 모드 활성화")
        return True

    def on_market_open(self) -> None:
        self.daily_trades = 0
        self._entry_df_cache.clear()
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
        # 보유 종목 → 매도(청산) 판단 우선 (현재가·보유일만 필요 → 전달된 일봉 사용)
        if stock_code in self.positions:
            return self._check_sell(stock_code, data)

        if self.daily_trades >= self._max_daily_trades:
            return None
        if len(self.positions) >= self._max_positions:
            return None

        # 진입은 확정 일봉 기준. 매도 경로(intraday)에서는 신규 진입 안 함.
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
                f"📥 매수 체결: {order.stock_code} @ {order.price:,.0f} x {order.quantity}주"
            )
        elif order.stock_code in self.positions:
            pos = self.positions.pop(order.stock_code)
            entry = pos["entry_price"]
            pnl_pct = (order.price - entry) / entry * 100
            prefix = "[PAPER] " if self._paper_trading else ""
            self.logger.info(
                f"📤 {prefix}매도 체결: {order.stock_code} @ {order.price:,.0f} "
                f"(수익률 {pnl_pct:+.1f}%)"
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
        min_daily_bars: int = _MIN_ENTRY_BARS,
    ) -> Tuple[bool, List[str], Dict[str, Any]]:
        """진입 조건 평가 — 백테스트 rule_envelope_200d_high(책 verbatim 기본값) 그대로 호출.

        df 는 일봉 OHLCV(마지막 행 = 평가 시점 t, no-lookahead). 조건E(이등분선)은
        'datetime' 컬럼이 필요하므로 없으면 'date' 로 보강(일봉=1일1봉이라 동치).
        """
        if df is None or len(df) < min_daily_bars:
            return False, [], {}
        if "datetime" not in df.columns and "date" in df.columns:
            df = df.assign(datetime=df["date"])
        res = rule_envelope_200d_high().evaluate(df, {})
        if not res.triggered:
            return False, [], {}
        return True, list(res.reasons), dict(res.metadata)

    @staticmethod
    def evaluate_sell_conditions(
        df: pd.DataFrame,
        entry_price: float,
        hold_days: int,
        take_profit_pct: float = 0.10,
        stop_loss_pct: float = 0.08,
        max_hold_days: int = 10,
    ) -> Tuple[bool, List[str], str]:
        """청산 조건 평가 — 백테스트 우선순위 1:1 복제 (trailing 없음).

        우선순위: 1) stop_loss(ret<=-sl) 2) take_profit(ret>=tp) 3) max_hold(hold>=mh).
        """
        close = df["close"].astype(float)
        cur_close = float(close.iloc[-1])
        ret = (cur_close - entry_price) / entry_price

        if ret <= -stop_loss_pct:
            return True, [f"손절 도달 ({ret * 100:+.1f}%)"], "stop_loss"
        if ret >= take_profit_pct:
            return True, [f"익절 도달 ({ret * 100:+.1f}%)"], "take_profit"
        if hold_days >= max_hold_days:
            return True, [f"최대 보유일 초과 ({hold_days}거래일)"], "max_hold"
        return False, [], ""

    # ========================================================================
    # 내부 헬퍼
    # ========================================================================

    def _quant_reader(self):
        if self._quant is None:
            from db.quant_daily_reader import QuantDailyReader
            self._quant = QuantDailyReader()
        return self._quant

    def _fetch_entry_history(self, stock_code: str) -> Optional[pd.DataFrame]:
        """진입 평가용 일봉(quant SSOT, ~210봉, 확정봉). 하루 1회 캐시.

        quant 는 EOD 적재라 장중엔 마지막 봉=직전 영업일(확정). 혹 당일 봉이 들어와도
        KST 오늘 봉은 제거해 no-lookahead 유지(백테스트=확정봉 평가와 정합).
        """
        today = now_kst().date()
        key = (stock_code, today)
        if key in self._entry_df_cache:
            return self._entry_df_cache[key]
        df: Optional[pd.DataFrame] = None
        try:
            df = self._quant_reader().get_daily_prices(
                stock_code, end_date=today, days=self._entry_lookback)
        except Exception as e:
            self.logger.warning(f"{stock_code} quant 일봉 조회 실패: {e}")
            df = None
        if df is not None and not df.empty:
            df = df.copy()
            df["datetime"] = df["date"]
            # 당일 미확정 봉 제거 (KST 오늘)
            mask_today = pd.to_datetime(df["date"]).dt.date == today
            if mask_today.any():
                df = df[~mask_today]
            df = df.reset_index(drop=True)
        self._entry_df_cache[key] = df
        return df

    def _check_buy(self, stock_code: str, data: pd.DataFrame) -> Optional[Signal]:
        if not MarketHours.is_market_open("KRX"):
            return None

        df = self._fetch_entry_history(stock_code)
        if df is None or len(df) < self._min_daily_bars:
            return None

        triggered, reasons, rule_meta = self.evaluate_entry(
            df, min_daily_bars=self._min_daily_bars)
        if not triggered:
            return None

        ref_close = float(df["close"].astype(float).iloc[-1])
        target = ref_close * (1 + self._take_profit_pct)
        stop = ref_close * (1 - self._stop_loss_pct)
        recommended_qty = max(1, int(self._max_per_stock_amount // ref_close))

        metadata = {
            "prior_high": rule_meta.get("prior_high"),
            "env_upper": rule_meta.get("env_upper"),
            "ref_close": ref_close,
            "recommended_qty": recommended_qty,
        }
        if self._paper_trading:
            metadata["paper_only"] = True
            self.logger.info(
                f"🧾 [PAPER] 매수 시그널: {stock_code} @ {ref_close:,.0f} "
                f"(추천 {recommended_qty}주) | " + " | ".join(reasons)
            )

        return Signal(
            signal_type=SignalType.BUY,
            stock_code=stock_code,
            confidence=70.0,
            target_price=target,
            stop_loss=stop,
            reasons=reasons,
            metadata=metadata,
        )

    def _check_sell(self, stock_code: str, data: pd.DataFrame) -> Optional[Signal]:
        if data is None or len(data) == 0:
            return None
        pos = self.positions[stock_code]
        entry_price = pos["entry_price"]
        entry_time = pos.get("entry_time")
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
