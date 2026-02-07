"""
매매 판단 엔진 - 템플릿

Strategy 시스템과 연동되어 매매 판단을 수행합니다.
- Strategy가 설정되면: strategy.generate_signal()을 통해 매매 판단
- Strategy가 없으면: 기본 동작 (매수 안함, 손절/익절만 동작)

기본 제공: 손절(-10%)/익절(+15%) 체크
"""
from typing import Tuple, Optional, TYPE_CHECKING
import pandas as pd
from utils.logger import setup_logger
from config.constants import DEFAULT_STOP_LOSS_RATE, DEFAULT_TARGET_PROFIT_RATE

if TYPE_CHECKING:
    from strategies.base import BaseStrategy


class TradingDecisionEngine:
    """
    매매 판단 엔진 (템플릿)

    구현 필요: analyze_buy_decision(), analyze_sell_decision()
    기본 제공: 손절/익절 체크, 가상/실제 매매 실행
    """

    # 기본 설정
    DEFAULT_STOP_LOSS = DEFAULT_STOP_LOSS_RATE      # 손절: -10%
    DEFAULT_TAKE_PROFIT = DEFAULT_TARGET_PROFIT_RATE   # 익절: +15%
    DEFAULT_MAX_AMOUNT = 500000  # 최대 매수: 50만원

    def __init__(self, db_manager=None, telegram_integration=None,
                 trading_manager=None, api_manager=None,
                 intraday_manager=None, config=None):
        self.logger = setup_logger(__name__)
        self.db_manager = db_manager
        self.telegram = telegram_integration
        self.trading_manager = trading_manager
        self.api_manager = api_manager
        self.intraday_manager = intraday_manager
        self.config = config
        self.is_virtual_mode = getattr(config, 'paper_trading', True) if config else True

        from core.virtual_trading_manager import VirtualTradingManager
        self.virtual_trading = VirtualTradingManager(
            db_manager=db_manager, api_manager=api_manager,
            paper_trading=self.is_virtual_mode
        )

        # Strategy 연결 (나중에 set_strategy로 설정)
        self.strategy: Optional['BaseStrategy'] = None

        self.logger.info("매매 판단 엔진 초기화")

    def set_strategy(self, strategy: 'BaseStrategy'):
        """전략 설정"""
        self.strategy = strategy
        self.logger.info(f"전략 연결됨: {strategy.name if strategy else 'None'}")

    def _safe_float(self, v) -> float:
        if pd.isna(v) or v is None: return 0.0
        try: return float(str(v).replace(',', ''))
        except (ValueError, TypeError): return 0.0

    def _get_max_buy_amount(self, stock_code: str = "") -> float:
        try:
            if self.api_manager:
                info = self.api_manager.get_account_balance()
                if info and hasattr(info, 'available_amount'):
                    return min(5000000, float(info.available_amount) * 0.1)
        except Exception as e:
            self.logger.debug(f"최대 매수금액 조회 실패: {e}")
        return self.DEFAULT_MAX_AMOUNT

    # =========================================================================
    # 매수 판단
    # =========================================================================
    async def analyze_buy_decision(self, trading_stock, daily_data) -> Tuple[bool, str, dict]:
        """
        매수 판단 분석

        Returns: Tuple[매수여부, 사유, {buy_price, quantity, max_buy_amount}]

        Strategy가 설정된 경우: strategy.generate_signal()을 통해 매수 판단
        Strategy가 없는 경우: 매수하지 않음 (False 반환)
        """
        try:
            code = trading_stock.stock_code
            empty = {'buy_price': 0, 'quantity': 0, 'max_buy_amount': 0}

            if daily_data is None or len(daily_data) < 20:
                return False, f"{code} 데이터부족", empty

            should_buy = False
            buy_reason = ""

            # Strategy가 설정된 경우 신호 생성
            if self.strategy:
                try:
                    from strategies.base import SignalType
                    signal = self.strategy.generate_signal(code, daily_data)

                    if signal and signal.signal_type in [SignalType.BUY, SignalType.STRONG_BUY]:
                        should_buy = True
                        buy_reason = ", ".join(signal.reasons) if signal.reasons else f"{self.strategy.name} 매수신호"
                        self.logger.info(f"{code} 전략 매수신호: {buy_reason} (신뢰도: {signal.confidence}%)")
                except Exception as e:
                    self.logger.warning(f"{code} 전략 신호 생성 오류: {e}")

            if not should_buy:
                return False, f"{code} 조건미충족", empty

            price = float(daily_data['close'].iloc[-1])
            max_amt = self._get_max_buy_amount(code)
            qty = int(max_amt / price) if price > 0 else 0

            if qty <= 0:
                return False, f"{code} 수량부족", empty

            return True, buy_reason, {'buy_price': price, 'quantity': qty, 'max_buy_amount': max_amt}

        except Exception as e:
            self.logger.error(f"매수판단 오류: {e}")
            return False, str(e), {'buy_price': 0, 'quantity': 0, 'max_buy_amount': 0}

    # =========================================================================
    # 매도 판단
    # =========================================================================
    async def analyze_sell_decision(self, trading_stock, combined_data=None) -> Tuple[bool, str]:
        """
        매도 판단 분석

        Returns: Tuple[매도여부, 사유]

        우선순위:
        1. 손절/익절 체크 (항상 우선)
        2. Strategy 매도 신호 (설정된 경우)
        """
        try:
            if not trading_stock.position or trading_stock.position.avg_price <= 0:
                return False, "포지션없음"

            # 현재가 조회
            price = None
            if self.intraday_manager:
                info = self.intraday_manager.get_cached_current_price(trading_stock.stock_code)
                if info: price = info['current_price']
            if not price: return False, "현재가없음"

            # 1. 기본 손절/익절 체크 (항상 우선)
            signal, reason = self._check_stop_profit(trading_stock, price)
            if signal: return True, reason

            # 2. Strategy 매도 신호 체크
            if self.strategy and combined_data is not None:
                try:
                    from strategies.base import SignalType
                    signal_result = self.strategy.generate_signal(trading_stock.stock_code, combined_data)

                    if signal_result and signal_result.signal_type in [SignalType.SELL, SignalType.STRONG_SELL]:
                        sell_reason = ", ".join(signal_result.reasons) if signal_result.reasons else f"{self.strategy.name} 매도신호"
                        self.logger.info(f"{trading_stock.stock_code} 전략 매도신호: {sell_reason}")
                        return True, sell_reason
                except Exception as e:
                    self.logger.warning(f"{trading_stock.stock_code} 전략 매도신호 생성 오류: {e}")

            return False, ""

        except Exception as e:
            self.logger.error(f"매도판단 오류: {e}")
            return False, str(e)

    # =========================================================================
    # 손절/익절 (기본 제공)
    # =========================================================================
    def _check_stop_profit(self, trading_stock, cur_price: float) -> Tuple[bool, str]:
        """손절/익절 체크 (기본: -10%/+15%, 종목별 설정 우선)"""
        try:
            buy_price = self._safe_float(trading_stock.position.avg_price)
            if buy_price <= 0: return False, ""

            pnl = (cur_price - buy_price) / buy_price
            target = getattr(trading_stock, 'target_profit_rate', self.DEFAULT_TAKE_PROFIT)
            stop = getattr(trading_stock, 'stop_loss_rate', self.DEFAULT_STOP_LOSS)

            if pnl >= target:
                return True, f"익절 {pnl*100:.1f}%"
            if pnl <= -stop:
                return True, f"손절 {pnl*100:.1f}%"
            return False, ""
        except Exception as e:
            self.logger.debug(f"손절/익절 체크 실패: {e}")
            return False, ""

    # =========================================================================
    # 매매 실행
    # =========================================================================
    async def execute_real_buy(self, trading_stock, buy_reason: str,
                               buy_price: float, quantity: int, candle_time=None) -> bool:
        """실제 매수"""
        try:
            if quantity <= 0 or buy_price <= 0: return False
            from core.trading_stock_manager import TradingStockManager
            if isinstance(self.trading_manager, TradingStockManager):
                ok = await self.trading_manager.execute_buy_order(
                    stock_code=trading_stock.stock_code,
                    price=buy_price, quantity=quantity, reason=buy_reason)
                if ok: self.logger.info(f"매수: {trading_stock.stock_code} {quantity}주 @{buy_price:,.0f}")
                return ok
            return False
        except Exception as e:
            self.logger.error(f"매수오류: {e}")
            return False

    async def execute_virtual_buy(self, trading_stock, combined_data,
                                  buy_reason: str, buy_price: float = None):
        """가상 매수"""
        try:
            if buy_price is None:
                buy_price = self._safe_float(combined_data['close'].iloc[-1])
            qty = self.virtual_trading.get_max_quantity(buy_price)
            if qty <= 0: return

            rid = self.virtual_trading.execute_virtual_buy(
                stock_code=trading_stock.stock_code, stock_name=trading_stock.stock_name,
                price=buy_price, quantity=qty, strategy="사용자전략", reason=buy_reason)
            if rid:
                trading_stock.set_virtual_buy_info(rid, buy_price, qty)
                trading_stock.set_position(qty, buy_price)
                self.logger.info(f"가상매수: {trading_stock.stock_code} {qty}주 @{buy_price:,.0f}")
        except Exception as e:
            self.logger.error(f"가상매수오류: {e}")

    async def execute_real_sell(self, trading_stock, sell_reason: str) -> bool:
        """실제 매도"""
        try:
            if not trading_stock.position or trading_stock.position.quantity <= 0:
                return False
            ok = await self.trading_manager.execute_sell_order(
                stock_code=trading_stock.stock_code,
                quantity=trading_stock.position.quantity,
                price=0, reason=sell_reason, market=True)
            if ok: self.logger.info(f"매도: {trading_stock.stock_code} - {sell_reason}")
            return ok
        except Exception as e:
            self.logger.error(f"매도오류: {e}")
            return False

    async def execute_virtual_sell(self, trading_stock, sell_price: float, sell_reason: str):
        """가상 매도"""
        try:
            code = trading_stock.stock_code
            if not sell_price and self.intraday_manager:
                info = self.intraday_manager.get_cached_current_price(code)
                if info: sell_price = info['current_price']
            if not sell_price: return False

            rid = getattr(trading_stock, '_virtual_buy_record_id', None)
            bp = getattr(trading_stock, '_virtual_buy_price', None)
            qty = getattr(trading_stock, '_virtual_quantity', None)

            if not rid and self.db_manager:
                pos = self.db_manager.get_virtual_open_positions()
                sp = pos[pos['stock_code'] == code]
                if not sp.empty:
                    r = sp.iloc[0]
                    rid, bp, qty = r['id'], r['buy_price'], r['quantity']

            if rid:
                ok = self.virtual_trading.execute_virtual_sell(
                    stock_code=code, stock_name=trading_stock.stock_name,
                    price=sell_price, quantity=qty, strategy="사용자전략",
                    reason=sell_reason, buy_record_id=rid)
                if ok:
                    pnl = (sell_price - bp) * qty if bp else 0
                    self.logger.info(f"가상매도: {code} (손익: {pnl:+,.0f}원)")
                    trading_stock.clear_virtual_buy_info()
                    trading_stock.clear_position()
                return ok
            return False
        except Exception as e:
            self.logger.error(f"가상매도오류: {e}")
            return False

    def _is_already_holding(self, stock_code: str) -> bool:
        """보유 종목 확인"""
        try:
            if not self.trading_manager: return False
            from core.models import StockState
            for s in self.trading_manager.get_stocks_by_state(StockState.POSITIONED):
                if s.stock_code == stock_code: return True
            return False
        except Exception as e:
            self.logger.debug(f"보유 종목 확인 실패: {e}")
            return False
