"""
Sawkami Strategy — 사와카미 가치투자 전략
=========================================

매수 조건 (5개 모두 충족):
  1. 영업이익 YoY 성장률 30% 이상
  2. 52주 고점 대비 -20% 이상 하락
  3. PBR < 1.5
  4. 거래량이 20일 평균의 1.5배 이상
  5. RSI(14) < 30

매도 조건 (1개 이상 충족 시):
  - 익절: +15%
  - 손절: -15%
  - 최대 보유: 40일
"""

from datetime import datetime
from typing import Any, Dict, List, Optional

import pandas as pd

from config.market_hours import MarketHours
from ..base import BaseStrategy, OrderInfo, Signal, SignalType
from utils.indicators import calculate_rsi
from utils.korean_time import now_kst
from .db_manager import SawkamiDBManager


class SawkamiStrategy(BaseStrategy):
    """사와카미 가치투자 전략"""

    name: str = "SawkamiStrategy"
    version: str = "1.0.0"
    description: str = "영업이익 성장 + 52주 고점 하락 + 저PBR + 거래량 급증 + RSI 과매도"
    author: str = "Template"
    holding_period: str = "swing"

    def get_min_data_length(self) -> int:
        """52주 고가(252일) + 거래량MA20 + RSI14 중 최대 + 여유 2 = 254"""
        params = self.config.get("parameters", {})
        high52w_period = params.get("high52w_period", 252)
        vol_ma_period = params.get("volume_ma_period", 20)
        rsi_period = params.get("rsi_period", 14)
        return max(high52w_period, vol_ma_period, rsi_period) + 2

    def on_init(self, broker, data_provider, executor) -> bool:
        self._broker = broker
        self._data_provider = data_provider
        self._executor = executor

        # 매수 파라미터
        params = self.config.get("parameters", {})
        self._op_growth_min = params.get("op_income_growth_min", 30.0)
        self._high52w_drop_pct = params.get("high52w_drop_pct", -20.0)
        self._pbr_max = params.get("pbr_max", 1.5)
        self._vol_ratio_min = params.get("volume_ratio_min", 1.5)
        self._vol_ma_period = params.get("volume_ma_period", 20)
        self._rsi_period = params.get("rsi_period", 14)
        self._rsi_oversold = params.get("rsi_oversold", 30)
        self._high52w_period = params.get("high52w_period", 252)

        # 매도 / 리스크 파라미터
        risk = self.config.get("risk_management", {})
        self._take_profit_pct = risk.get("take_profit_pct", 0.15)
        self._stop_loss_pct = risk.get("stop_loss_pct", 0.15)
        self._max_hold_days = risk.get("max_hold_days", 40)
        self._max_daily_trades = risk.get("max_daily_trades", 5)
        self._max_positions = risk.get("max_positions", 10)
        self._max_daily_loss_pct = risk.get("max_daily_loss_pct", 5.0)
        self._max_per_stock_amount = risk.get("max_per_stock_amount", 5_000_000)

        # 안전장치
        self._paper_trading = self.config.get("paper_trading", True)

        # DB 매니저
        self._db = SawkamiDBManager()

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
            f"(영업이익성장≥{self._op_growth_min}%, "
            f"52주고점≤{self._high52w_drop_pct}%, "
            f"PBR<{self._pbr_max}, "
            f"거래량≥{self._vol_ratio_min}x, "
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
        # 장 외 시간 체크 — 장중이 아니면 시그널 생성 안 함
        if not MarketHours.is_market_open('KRX'):
            return None

        min_len = max(self._high52w_period, self._vol_ma_period, self._rsi_period) + 2
        if data is None or len(data) < min_len:
            return None

        if self.daily_trades >= self._max_daily_trades:
            return None

        close = data["close"]
        current_price = float(close.iloc[-1])

        # 보유 종목 → 매도 체크 (매도는 손실 제한과 무관하게 허용)
        if stock_code in self.positions:
            return self._check_sell(stock_code, current_price)

        # 일일 손실 제한 초과 시 매수 차단
        if self._daily_loss_limit_hit:
            return None

        # 최대 보유 종목 수 제한
        if len(self.positions) >= self._max_positions:
            return None

        # 미보유 → 매수 체크 (daily timeframe 에서만)
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
            # DB에 매수 기록
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
            # DB에 매도 기록
            sell_reason = "TP" if pnl_pct >= self._take_profit_pct * 100 else \
                          "SL" if pnl_pct <= -self._stop_loss_pct * 100 else "TIMEOUT"
            self._db.close_trade(
                stock_code=order.stock_code,
                sell_date=order.filled_at,
                sell_price=order.price,
                sell_reason=sell_reason,
            )
            # 실현 손실 추적
            if pnl_pct < 0:
                self._daily_realized_loss += pnl_pct
                if abs(self._daily_realized_loss) >= self._max_daily_loss_pct:
                    self._daily_loss_limit_hit = True
                    self.logger.warning(
                        f"🚨 일일 최대 손실 제한 도달! "
                        f"누적 손실 {self._daily_realized_loss:.1f}% "
                        f"(제한: -{self._max_daily_loss_pct}%) — 매수 중단"
                    )
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
        for code, pos in self.positions.items():
            hold_days = (now_kst() - pos["entry_time"]).days
            self.logger.info(
                f"  {code}: 진입가 {pos['entry_price']:,.0f}, "
                f"보유 {hold_days}일"
            )

    # ========================================================================
    # 포지션 복원 (DB)
    # ========================================================================

    def _load_positions_from_db(self) -> None:
        """DB에서 HOLDING 포지션 복원"""
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

    # ========================================================================
    # 후보 스크리닝
    # ========================================================================

    def _run_candidate_screening(self) -> None:
        """장 시작 시 SawkamiCandidateSelector로 매수 후보 스크리닝 후 target_stocks 동적 업데이트"""
        try:
            from strategies.sawkami.screener import SawkamiCandidateSelector
            from core.models import TradingConfig

            # TradingConfig 생성 (broker에서 가져올 수 있으면 가져옴)
            trading_config = getattr(self._broker, 'config', None)
            if trading_config is None:
                trading_config = TradingConfig()

            strategy_params = self.config.get("parameters", {})
            selector = SawkamiCandidateSelector(
                config=trading_config,
                broker=self._broker,
                strategy_params=strategy_params,
            )

            max_candidates = strategy_params.get("max_screening_candidates", 20)

            candidates = selector.select_daily_candidates(max_candidates)

            if candidates:
                new_targets = [c.code for c in candidates]
                # config의 target_stocks 업데이트
                if 'target_stocks' not in self.config:
                    self.config['target_stocks'] = []
                existing = set(self.config['target_stocks'])
                combined = list(existing | set(new_targets))
                self.config['target_stocks'] = combined

                self.logger.info(
                    f"🏯 사와카미 스크리닝 완료: {len(candidates)}종목 선정 → "
                    f"target_stocks {len(combined)}종목"
                )
                for c in candidates:
                    self.logger.info(f"  📌 {c.code}({c.name}) {c.score:.1f}점 — {c.reason}")

                # 재무 캐시도 미리 채움
                for c in candidates:
                    if c.code not in self._fundamental_cache:
                        # selector 캐시에서 가져오기
                        fund = selector._fundamental_cache.get(c.code)
                        if fund:
                            self._fundamental_cache[c.code] = {
                                "op_income_growth": fund.op_income_growth,
                                "bps": fund.bps,
                            }
            else:
                self.logger.info("🏯 사와카미 스크리닝: 조건 충족 종목 없음")

        except Exception as e:
            self.logger.error(f"🏯 사와카미 스크리닝 실패: {e}", exc_info=True)

    # ========================================================================
    # 내부 헬퍼
    # ========================================================================

    def _load_fundamental_data(self) -> None:
        """재무 데이터 로드 (영업이익 성장률, BPS → PBR 계산용)"""
        target_stocks = self.get_target_stocks()
        if not target_stocks:
            return

        try:
            from api.kis_financial_api import get_financial_ratio
        except ImportError:
            self.logger.warning("kis_financial_api 임포트 실패 — 재무 데이터 사용 불가")
            return

        for code in target_stocks:
            if code in self._fundamental_cache:
                continue
            try:
                ratios = get_financial_ratio(code)
                if ratios:
                    latest = ratios[0]
                    self._fundamental_cache[code] = {
                        "op_income_growth": latest.operating_income_growth,
                        "bps": latest.bps,
                    }
                    self.logger.debug(
                        f"📊 재무 로드: {code} "
                        f"영업이익성장={latest.operating_income_growth:.1f}%, "
                        f"BPS={latest.bps:,.0f}"
                    )
            except Exception as e:
                self.logger.warning(f"재무 데이터 조회 실패 {code}: {e}")

    def _check_buy(
        self,
        stock_code: str,
        current_price: float,
        data: pd.DataFrame,
    ) -> Optional[Signal]:
        reasons: List[str] = []

        # 1) 영업이익 YoY 성장률 ≥ 30%
        fund = self._fundamental_cache.get(stock_code)
        if not fund:
            return None
        op_growth = fund.get("op_income_growth", 0.0)
        if op_growth < self._op_growth_min:
            return None
        reasons.append(f"영업이익 YoY {op_growth:+.1f}%")

        # 2) 52주 고점 대비 -20% 이상 하락
        high_52w = float(data["high"].iloc[-self._high52w_period:].max())
        if high_52w == 0:
            return None
        drop_pct = (current_price - high_52w) / high_52w * 100
        if drop_pct > self._high52w_drop_pct:
            return None
        reasons.append(f"52주 고점 대비 {drop_pct:.1f}%")

        # 3) PBR < 1.5  (현재가 / BPS)
        bps = fund.get("bps", 0.0)
        if bps <= 0:
            return None
        pbr = current_price / bps
        if pbr >= self._pbr_max:
            return None
        reasons.append(f"PBR {pbr:.2f}")

        # 4) 거래량 ≥ 20일 평균의 1.5배
        volume = data["volume"]
        vol_ma = float(volume.iloc[-self._vol_ma_period:].mean())
        if vol_ma == 0:
            return None
        current_vol = float(volume.iloc[-1])
        vol_ratio = current_vol / vol_ma
        if vol_ratio < self._vol_ratio_min:
            return None
        reasons.append(f"거래량 {vol_ratio:.1f}x (20일 평균 대비)")

        # 5) RSI(14) < 30
        rsi = calculate_rsi(data["close"], self._rsi_period)
        rsi_val = float(rsi.iloc[-1])
        if pd.isna(rsi_val) or rsi_val >= self._rsi_oversold:
            return None
        reasons.append(f"RSI({self._rsi_period}) = {rsi_val:.1f}")

        # 모든 조건 충족 — 매수 시그널
        target = current_price * (1 + self._take_profit_pct)
        stop = current_price * (1 - self._stop_loss_pct)

        # 종목당 최대 투자금액 → 추천 수량 계산
        recommended_qty = max(1, int(self._max_per_stock_amount // current_price))

        if self._paper_trading:
            self.logger.info(
                f"🧾 [PAPER] 매수 시그널: {stock_code} @ {current_price:,.0f} "
                f"(추천 {recommended_qty}주, 상한 {self._max_per_stock_amount:,.0f}원) | "
                + " | ".join(reasons)
            )

        metadata = {
            "op_income_growth": op_growth,
            "high_52w": high_52w,
            "drop_pct": drop_pct,
            "pbr": pbr,
            "vol_ratio": vol_ratio,
            "rsi": rsi_val,
            "recommended_qty": recommended_qty,
            "max_amount": self._max_per_stock_amount,
        }
        if self._paper_trading:
            metadata["paper_only"] = True

        return Signal(
            signal_type=SignalType.BUY,
            stock_code=stock_code,
            confidence=min(95.0, 60.0 + abs(drop_pct)),
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
        pnl_pct = (current_price - entry_price) / entry_price
        hold_days = (now_kst() - pos["entry_time"]).days

        reasons: List[str] = []

        # 익절
        if pnl_pct >= self._take_profit_pct:
            reasons.append(f"익절 도달 ({pnl_pct * 100:+.1f}%)")

        # 손절
        if pnl_pct <= -self._stop_loss_pct:
            reasons.append(f"손절 도달 ({pnl_pct * 100:+.1f}%)")

        # 최대 보유일 초과
        if hold_days >= self._max_hold_days:
            reasons.append(f"최대 보유일 초과 ({hold_days}일)")

        if not reasons:
            return None

        if self._paper_trading:
            self.logger.info(
                f"🧾 [PAPER] 매도 시그널: {stock_code} @ {current_price:,.0f} | "
                + " | ".join(reasons)
            )

        metadata = {
            "entry_price": entry_price,
            "pnl_pct": pnl_pct * 100,
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

    # RSI 계산은 utils.indicators.calculate_rsi 사용
