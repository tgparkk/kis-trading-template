"""
Elder EMA Pullback Strategy — Triple Screen (Variant A) 실전판
=============================================================

백테스트 검증판을 실전 파이프라인(BaseStrategy / on_tick)으로 코드화한 전략.

진입 신호는 백테스트와 1:1 일치를 보장하기 위해
``strategies/books/elder_triple_screen/rules.py`` 의 헬퍼를 직접 재사용한다:
  - ``rule_triple_screen_ema_pullback`` : Screen 1(EMA65 상승) + Screen 2(EMA13 눌림 회복)
  - ``ema`` / ``screen1_uptrend`` / ``krx_tick`` : 지표·매수스톱 계산

진입 (Variant A, rule=triple_screen_ema_pullback):
  1. Screen 1 — EMA65 상승 (5바 전 대비 기울기 > 0)
  2. Screen 2 — low[-1] <= EMA13*touch_band(1.02) AND close[-1] > EMA13
  3. Screen 3 — 전일 고가 + 1틱 매수스톱: 실전에선 metadata["buy_stop_price"]로 전달.
     (실전 체결 경로는 시장가/현재가 기준이므로 백테스트의 stop-fill과 차이 — 보고 D 참고)

청산 (Variant A, VARIANT_PARAMS["A"]):
  - 손절: -8%
  - 익절: +30%
  - 최대 보유: 100거래일 (max_holding_days)
  - EMA13 trailing: 수익 중(ret>0) 종가가 EMA13 하향 이탈 시 청산
  - EMA65 추세반전: EMA65[-1] < EMA65[-6] 이면 청산

매수는 일봉(daily) 기준, 매도는 보유 종목의 일봉 재조회로 판정한다.
``holding_period = "swing"`` 이므로 EOD 일괄청산을 건너뛴다.

설계상 의도된 처리(미결 항목 — 백테스트와 의도적으로 정합/위임):
  - 미결 ②(trailing / trend_flip 해상도): trailing·trend_flip 청산은 일봉
    EOD 종가 해상도로만 평가된다. ``holding_period="swing"`` 스윙 전략이므로
    장중 틱 단위 추적이 아니라 확정 일봉 기준 평가가 *의도된 설계*이며,
    백테스트(일봉 bar 단위 평가)와 동일하다. 별도 장중 trailing은 두지 않는다.
  - 미결 ③(슬리피지 / 세금): 체결가 슬리피지·거래세·수수료는 본 전략이 아니라
    프레임워크(core/fund_manager · OrderExecutor)의 책임이다. 전략은 순수 신호만
    생성하고, 체결·비용 반영은 실행 레이어에 *의도적으로 위임*한다.
  - 미결 ④(hold_days 거래일 기준): 보유일 평가는 달력일이 아니라 **거래일**
    경과수(``_trading_days_elapsed``)로 계산해 백테스트 bar-count와 정합시킨다.
"""

from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd

from config.market_hours import MarketHours
from utils.korean_time import now_kst
from utils.korean_holidays import count_trading_days_between
from ..base import BaseStrategy, OrderInfo, Signal, SignalType

# 백테스트 헬퍼를 직접 재사용 → 진입 신호 1:1 일치 보장
from strategies.books.elder_triple_screen.rules import (
    ema,
    krx_tick,
    rule_triple_screen_ema_pullback,
    screen1_uptrend,
)


class ElderEmaPullbackStrategy(BaseStrategy):
    """Elder Triple Screen Variant A — EMA65 추세 + EMA13 눌림 회복 진입 (스윙)."""

    name: str = "ElderEmaPullbackStrategy"
    version: str = "1.0.0"
    description: str = "Elder Triple Screen A — EMA65 상승 + EMA13 눌림 회복 (sl8/tp30/trail/flip)"
    author: str = "Template"
    holding_period: str = "swing"
    # 매도(trailing/trend_flip)는 '확정 일봉' 해상도로 평가 — 분봉 평가 시 EMA13/EMA65가
    # 분봉봉 기준으로 오작동해 진입 직후 청산되는 whipsaw 발생(2026-06-09 192080).
    exit_timeframe: str = "daily"
    # 추세추종 진입 — 거래량 상위 fallback 풀과 정합 (기본 True 유지)
    accepts_volume_fallback: bool = True

    # ========================================================================
    # 라이프사이클
    # ========================================================================

    def get_min_data_length(self) -> int:
        """진입 룰(rules.py)이 요구하는 최소 일봉 수 (len(df) < 70 가드)."""
        params = self.config.get("parameters", {})
        return int(params.get("min_daily_bars", 70))

    def on_init(self, broker, data_provider, executor) -> bool:
        self._broker = broker
        self._data_provider = data_provider
        self._executor = executor

        params = self.config.get("parameters", {})
        self._ema_short = int(params.get("ema_short", 13))
        self._ema_long = int(params.get("ema_long", 65))
        self._touch_band = float(params.get("touch_band", 1.02))
        self._min_daily_bars = int(params.get("min_daily_bars", 70))

        risk = self.config.get("risk_management", {})
        self._take_profit_pct = float(risk.get("take_profit_pct", 0.30))
        self._stop_loss_pct = float(risk.get("stop_loss_pct", 0.08))
        self._max_hold_days = int(risk.get("max_hold_days", 100))
        self._trail_ema = risk.get("trail_ema", 13)
        self._trail_ema = int(self._trail_ema) if self._trail_ema is not None else None
        self._trend_flip_exit = bool(risk.get("trend_flip_exit", True))
        self._max_positions = int(risk.get("max_positions", 5))
        self._max_daily_trades = int(risk.get("max_daily_trades", 5))
        self._max_per_stock_amount = float(risk.get("max_per_stock_amount", 3_000_000))

        # 프레임워크 max_holding_days 표준 키 (parameters 우선, fallback risk.max_hold_days)
        self.max_holding_days = int(
            params.get("max_holding_days", risk.get("max_hold_days", 100))
        )

        # 진입 룰 인스턴스 (백테스트와 동일 touch_band)
        self._entry_rule = rule_triple_screen_ema_pullback(touch_band=self._touch_band)

        # 진입 지정가 밴드 (눌림형): 기준가 위로 추격 금지, 하한은 손절폭까지 허용.
        # 갭업/상한가 종목을 스테일 종가로 체결하던 허수 진입 차단(2026-06-15).
        self._entry_band_up_pct = float(risk.get("entry_band_up_pct", 0.01))
        _band_down = risk.get("entry_band_down_pct", self._stop_loss_pct)
        self._entry_band_down_pct = float(_band_down) if _band_down is not None else None

        self._paper_trading = self.config.get("paper_trading", True)

        # 상태
        self.positions: Dict[str, Dict[str, Any]] = {}
        self.daily_trades = 0

        self._is_initialized = True
        self.logger.info(
            f"{self.name} v{self.version} 초기화 완료 "
            f"(EMA {self._ema_short}/{self._ema_long}, touch_band={self._touch_band}, "
            f"sl={self._stop_loss_pct:.0%}/tp={self._take_profit_pct:.0%}/"
            f"max_hold={self.max_holding_days}일)"
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

        # 진입·청산 모두 '확정 일봉' 기준으로만 평가 (백테스트 정합 + 본 전략 설계의도:
        # "매도는 일봉 재조회, trailing/trend_flip은 일봉 EOD 종가 해상도" — 파일 상단 docstring).
        # 분봉(intraday)으로 들어오면 EMA13/EMA65 청산이 분봉봉 기준으로 오작동해
        # 진입 직후 trend_flip이 오발동(whipsaw)한다(2026-06-09 192080). 장중 실시간
        # 손익절·트레일링·최대보유일은 position_monitor가 현재가 기준으로 독립 처리하므로,
        # 분봉 경로에서는 매도·매수 모두 평가하지 않고 None을 반환한다.
        if timeframe != "daily":
            return None

        # 보유 종목 → 매도(청산) 판단 우선
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
        touch_band: float = 1.02,
        min_daily_bars: int = 70,
    ) -> Tuple[bool, List[str], Dict[str, Any]]:
        """진입 조건 평가 — 백테스트 rule_triple_screen_ema_pullback을 그대로 호출.

        Args:
            df: 일봉 OHLCV DataFrame (마지막 행 = 평가 시점 t, no-lookahead)
            touch_band: Screen 2 눌림 터치 밴드
            min_daily_bars: 최소 일봉 수 가드

        Returns:
            (triggered, reasons, metadata)
        """
        if df is None or len(df) < min_daily_bars:
            return False, [], {}
        rule = rule_triple_screen_ema_pullback(touch_band=touch_band)
        res = rule.evaluate(df, {})
        if not res.triggered:
            return False, [], {}
        return True, list(res.reasons), dict(res.metadata)

    @staticmethod
    def evaluate_sell_conditions(
        df: pd.DataFrame,
        entry_price: float,
        hold_days: int,
        take_profit_pct: float = 0.30,
        stop_loss_pct: float = 0.08,
        max_hold_days: int = 100,
        trail_ema: Optional[int] = 13,
        trend_flip_exit: bool = True,
    ) -> Tuple[bool, List[str], str]:
        """청산 조건 평가 — 백테스트 simulate_one_stock의 청산 분기를 1:1 복제.

        평가 우선순위(백테스트와 동일):
          1. stop_loss   : ret <= -stop_loss_pct
          2. take_profit : ret >= take_profit_pct
          3. max_hold    : hold_days >= max_hold_days
          4. trail_ema   : ret > 0 AND close < EMA(trail_ema)   (수익 중에만)
          5. trend_flip  : EMA65[-1] < EMA65[-6]

        Args:
            df: 일봉 OHLCV DataFrame (마지막 행 = 평가 시점). EMA 계산에 사용.
            entry_price: 진입가
            hold_days: 보유 거래일 수
            나머지: Variant A 파라미터

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
        # 3) 최대 보유일
        if hold_days >= max_hold_days:
            return True, [f"최대 보유일 초과 ({hold_days}일)"], "max_hold"
        # 4) EMA trailing (수익 중에만)
        if trail_ema is not None and ret > 0:
            ema_trail = ema(close, trail_ema)
            if cur_close < float(ema_trail.iloc[-1]):
                return (
                    True,
                    [f"EMA{trail_ema} trailing 이탈 (종가 {cur_close:.0f} < "
                     f"EMA{trail_ema} {float(ema_trail.iloc[-1]):.0f})"],
                    "trail_ema",
                )
        # 5) EMA65 추세반전
        if trend_flip_exit and len(close) >= 6:
            ema65 = ema(close, 65)
            if float(ema65.iloc[-1]) < float(ema65.iloc[-6]):
                return True, ["EMA65 추세반전 청산"], "trend_flip"

        return False, [], ""

    # ========================================================================
    # 내부 헬퍼
    # ========================================================================

    @staticmethod
    def _trading_days_elapsed(entry_time: Optional[datetime]) -> int:
        """진입 시점 이후 경과한 **거래일** 수 (주말·공휴일 제외).

        백테스트는 보유일을 일봉 bar 단위로 센다(= 거래일 카운트). 달력일
        ``(now - entry).days`` 를 쓰면 100거래일 ≈ 140달력일로 max_hold가
        조기 발동해 백테스트와 어긋난다. 이를 막기 위해
        ``utils.korean_holidays.count_trading_days_between`` 으로 진입 다음
        거래일부터 현재까지의 거래일 수를 계산한다.

        의미: 같은 날 진입·평가하면 0거래일. 다음 거래일이면 1, 이후 누적.
        (count_trading_days_between은 양 끝 포함이므로 entry 다음 날부터 센다.)
        """
        if entry_time is None:
            return 0
        from datetime import timedelta

        now = now_kst()
        # tz-aware/naive 혼용 방지: 날짜(date)만으로 거래일 카운트
        start = entry_time + timedelta(days=1)
        if start.date() > now.date():
            return 0
        # count_trading_days_between은 start~end(양끝 포함) 거래일 수.
        # entry 다음 날부터 now까지 세므로 = 진입 후 경과 거래일.
        return count_trading_days_between(
            datetime(start.year, start.month, start.day),
            datetime(now.year, now.month, now.day),
        )

    def _check_buy(self, stock_code: str, data: pd.DataFrame) -> Optional[Signal]:
        if not MarketHours.is_market_open("KRX"):
            return None

        triggered, reasons, rule_meta = self.evaluate_entry(
            data, touch_band=self._touch_band, min_daily_bars=self._min_daily_bars
        )
        if not triggered:
            return None

        current_price = float(data["close"].astype(float).iloc[-1])

        # Screen 3 매수스톱 (백테스트: 전일=현재봉 고가 + 1틱). 실전에선 참고용 메타데이터.
        last_high = float(data["high"].astype(float).iloc[-1])
        buy_stop_price = last_high + krx_tick(last_high)

        target = current_price * (1 + self._take_profit_pct)
        stop = current_price * (1 - self._stop_loss_pct)
        entry_min, entry_max = self._entry_band(
            current_price, down_pct=self._entry_band_down_pct, up_pct=self._entry_band_up_pct)
        recommended_qty = max(1, int(self._max_per_stock_amount // current_price))

        metadata = {
            "ema13": rule_meta.get("ema13"),
            "close": rule_meta.get("close", current_price),
            "buy_stop_price": buy_stop_price,
            "recommended_qty": recommended_qty,
        }
        if self._paper_trading:
            metadata["paper_only"] = True
            self.logger.info(
                f"🧾 [PAPER] 매수 시그널: {stock_code} @ {current_price:,.0f} "
                f"(매수스톱 {buy_stop_price:,.0f}, 추천 {recommended_qty}주) | "
                + " | ".join(reasons)
            )

        return Signal(
            signal_type=SignalType.BUY,
            stock_code=stock_code,
            confidence=60.0,  # 백테스트 rule confidence와 동일
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
        # 미결 ④: 보유일은 달력일이 아니라 거래일 경과수로 평가 (백테스트 bar-count 정합)
        hold_days = self._trading_days_elapsed(entry_time)

        should_sell, reasons, exit_reason = self.evaluate_sell_conditions(
            df=data,
            entry_price=entry_price,
            hold_days=hold_days,
            take_profit_pct=self._take_profit_pct,
            stop_loss_pct=self._stop_loss_pct,
            max_hold_days=self._max_hold_days,
            trail_ema=self._trail_ema,
            trend_flip_exit=self._trend_flip_exit,
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
