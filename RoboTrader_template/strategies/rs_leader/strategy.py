"""RS Leader Strategy — 횡보장 RS 리더 (페이퍼 관찰 전용).

진입: 절대상승추세(strategies.rs_leader.rule.RSLeaderRule 단일 소스 재사용) — 횡단면 RS
랭킹은 EOD 스크리너가 담당하고, 이 전략은 선정 풀에서 per-stock 추세 재확인 후 매수.
청산: 전략 고유 청산은 MA20 하향이탈(무조건) / max_hold 30거래일 뿐이다.
sl·tp 는 이 전략이 판정하지 않고 범용 core/trading/position_monitor.py 가
config.yaml risk_management(stop_loss_pct / take_profit_pct) 값으로 라이브
현재가 기준 판정한다(2026-08-25 1810cd2).
holding_period="swing" → EOD 일괄청산 건너뜀. paper_trading=True.
"""
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd

from config.market_hours import MarketHours
from utils.korean_time import now_kst
from utils.korean_holidays import count_trading_days_between
from ..base import BaseStrategy, OrderInfo, Signal, SignalType
from strategies.rs_leader import corp_action_guard as corp_action
from strategies.rs_leader.rule import RSLeaderRule


class RSLeaderStrategy(BaseStrategy):
    name: str = "RSLeaderStrategy"
    version: str = "1.0.0"
    description: str = "횡보장 RS 리더 — 절대상승추세+횡단면RS (sl8/trail_ma20/max30, paper)"
    author: str = "Template"
    holding_period: str = "swing"
    exit_timeframe: str = "daily"   # 일봉 청산 — 분봉 ma_break whipsaw(매수 직후 매도) 방지
    accepts_volume_fallback: bool = True

    def get_min_data_length(self) -> int:
        params = self.config.get("parameters", {})
        return int(params.get("min_daily_bars", 65))

    def on_init(self, broker, data_provider, executor) -> bool:
        self._broker = broker
        self._data_provider = data_provider
        self._executor = executor

        params = self.config.get("parameters", {})
        self._min_daily_bars = int(params.get("min_daily_bars", 65))
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
        # 진입 지정가 밴드 (돌파형): 기준가(직전 확정 종가) 위로 추격 한도만 둔다.
        # 갭업/상한가 종목을 스테일 종가로 체결하던 허수 진입 차단(2026-06-15).
        self._entry_band_up_pct = float(risk.get("entry_band_up_pct", 0.03))
        _band_down = risk.get("entry_band_down_pct", None)
        self._entry_band_down_pct = float(_band_down) if _band_down is not None else None
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
        # 미조정 기업행위 배제 스위치의 «기동 계기» 1줄 (main.py:220 이 프로세스당 1회 호출).
        # 🔑 스캔당 줄(`[rs-corp-action] … scan_date=…`)만으로는 부족하다 —
        #    그 줄은 SCREENER_SNAPSHOT_ENABLED=false 면 통째로 사라져 §6 실패 조건
        #    「줄이 하루라도 없음」이 «무관한 이유»로 발화한다. 기동 줄이 있으면
        #    「스위치가 어느 값이었나」와 「스크리너가 돌았나」를 따로 판정할 수 있다.
        _ca_mode, _ca_invalid = corp_action.resolve_mode()
        if _ca_invalid is not None:
            self.logger.warning(corp_action.invalid_mode_message(_ca_invalid))
        self.logger.info(f"[rs-corp-action] mode={_ca_mode} (startup)")
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
            # timeframe='intraday'로 분봉을 전달한다. ma_break가 무조건(ret 게이트
            # 없음)이라 분봉 MA20≈현재가 부근에서 항상 발동 → 매수 즉시 청산.
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

    # --- 순수 판단 함수 ---
    @staticmethod
    def evaluate_entry(df: pd.DataFrame, min_daily_bars: int = 65,
                       ma_short: int = 20, ma_long: int = 60, abs_lb: int = 60
                       ) -> Tuple[bool, List[str]]:
        """절대상승추세 진입 — RSLeaderRule 단일 소스 재사용."""
        if df is None or len(df) < min_daily_bars:
            return False, []
        rule = RSLeaderRule(ma_short=ma_short, ma_long=ma_long, abs_lb=abs_lb)
        sig = rule.generate_signal("_", df, "daily")
        if sig is None:
            return False, []
        return True, [
            f"절대상승추세(종가>MA{ma_short}·종가>MA{ma_long}·MA{ma_short}>MA{ma_long}·"
            f"{abs_lb}일수익>0)"
        ]

    @staticmethod
    def evaluate_sell_conditions(df: pd.DataFrame, entry_price: float, hold_days: int,
                                 stop_loss_pct: float = 0.08, take_profit_pct: float = 0.15,
                                 max_hold_days: int = 30, trail_ma: Optional[int] = 20
                                 ) -> Tuple[bool, List[str], str]:
        """청산 우선순위 — 라이브 전용 (백테스트는 이 함수를 호출하지 않는다):
        ma_break(무조건) → max_hold. stop_loss·take_profit 은 범용
        position_monitor 위임 — 이 함수에서 판정하지 않는다(시그니처만 유지)."""
        close = df["close"].astype(float)
        cur_close = float(close.iloc[-1])
        # sl/tp 는 core/trading/position_monitor.py 가 라이브 현재가로 판정한다(2026-08-25 2안).
        # 여기서 D-1 종가로 판정하면 갭 체결 시 환영 익절 — docs/prereg_2026-08-25_d1close_tp_phantom.md
        if trail_ma is not None and len(close) >= trail_ma:
            ma_val = float(close.iloc[-trail_ma:].mean())
            if cur_close < ma_val:
                return True, [f"MA{trail_ma} 이탈 (종가 {cur_close:.0f} < MA {ma_val:.0f})"], "ma_break"
        if hold_days >= max_hold_days:
            return True, [f"최대 보유일 초과 ({hold_days}거래일)"], "max_hold"
        return False, [], ""

    # --- 내부 헬퍼 ---
    def _check_buy(self, stock_code: str, data: pd.DataFrame) -> Optional[Signal]:
        # ★ 미조정 기업행위(합병) 의심 배제 — 2차 방어 (2026-09-10 사장님 결정 (b)).
        #   spec: docs/superpowers/specs/2026-09-10-rsleader-corp-action-exclusion-design.md §2 Q3
        #   여기가 필요한 이유: on_tick 매수 루프가 도는 `ctx.get_selected_stocks()` 는
        #   「내 전략 소유」 + 「소유자 미지정」을 돌려주므로 **스크리너를 안 거친 종목이
        #   들어올 수 있다**. 실측 전례 — 09-09·09-10 이틀 연속, 스크리너가 제외한 003350 에
        #   자기 on_tick 이 매수 시그널을 냈다. ⇒ 스크리너만 막으면 구멍이 남는다.
        #
        #   🔴 정직하게 적어 둘 한계 — 여기 오는 프레임은 **82봉**이라 배제 판정도 82봉 안의
        #      사건만 본다. 003350 유형(재개일 97거래일 전)은 **이 가드로도 안 잡힌다**.
        #      「on_tick 도 막았다」를 「전부 막았다」로 읽지 말 것 — 스크리너(130봉)가 1차다.
        #
        #   ⚠️ 매수 전용이다. `_check_sell`(보유 종목 청산)은 다른 함수이고 한 줄도 안 바뀐다.
        #      백테스트가 부르는 순수 함수 `evaluate_entry` 도 마찬가지다(연구 재현 불변).
        mode, invalid = corp_action.resolve_mode()
        if invalid is not None and self._should_log_ontick(stock_code, "corp_action_mode"):
            self.logger.warning(corp_action.invalid_mode_message(invalid))
        if mode != "off":
            hit = corp_action.detect(stock_code, data)
            if hit is not None:
                tail = ("— 진입 제외 (mode=live)" if mode == "live"
                        else f"— 진입 제외 «안 함»(mode={mode})")
                if self._should_log_ontick(stock_code, "corp_action"):
                    self.logger.warning(
                        f"[신호없음] {stock_code}: {corp_action.describe(hit)} {tail}")
                if mode == "live":
                    return None
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
        entry_min, entry_max = self._entry_band(
            current_price, down_pct=self._entry_band_down_pct, up_pct=self._entry_band_up_pct)
        recommended_qty = max(1, int(self._max_per_stock_amount // current_price))
        metadata = {"close": current_price, "recommended_qty": recommended_qty}
        if self._paper_trading:
            metadata["paper_only"] = True
            self.logger.info(
                f"🧾 [PAPER] 매수 시그널: {stock_code} @ {current_price:,.0f} "
                f"(추천 {recommended_qty}주) | " + " | ".join(reasons))
        return Signal(signal_type=SignalType.BUY, stock_code=stock_code, confidence=60.0,
                      target_price=target, stop_loss=stop,
                      entry_min_price=entry_min, entry_max_price=entry_max,
                      reasons=reasons, metadata=metadata)

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
