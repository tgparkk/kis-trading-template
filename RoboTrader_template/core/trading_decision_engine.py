"""
매매 판단 엔진 - 템플릿

Strategy 시스템과 연동되어 매매 판단을 수행합니다.
- Strategy가 설정되면: strategy.generate_signal()을 통해 매매 판단
- Strategy가 없으면: 기본 동작 (매수 안함, 손절/익절만 동작)

손절/익절 체크는 PositionMonitor가 담당 (trading_stock별 설정 사용)
"""
from typing import Tuple, Optional, TYPE_CHECKING
import pandas as pd
from utils.logger import setup_logger
from config.constants import DEFAULT_STOP_LOSS_RATE, DEFAULT_TARGET_PROFIT_RATE

if TYPE_CHECKING:
    from strategies.base import BaseStrategy
    from core.fund_manager import FundManager


class TradingDecisionEngine:
    """
    매매 판단 엔진 (템플릿)

    구현 필요: analyze_buy_decision(), analyze_sell_decision()
    기본 제공: 가상/실제 매매 실행
    손절/익절: PositionMonitor에서 일원화하여 처리
    """

    # 기본 설정
    DEFAULT_STOP_LOSS = DEFAULT_STOP_LOSS_RATE      # 손절: -10%
    DEFAULT_TAKE_PROFIT = DEFAULT_TARGET_PROFIT_RATE   # 익절: +15%
    DEFAULT_MAX_AMOUNT = 500000  # 최대 매수: 50만원

    def __init__(self, db_manager=None, telegram_integration=None,
                 trading_manager=None, broker=None,
                 intraday_manager=None, config=None):
        self.logger = setup_logger(__name__)
        self.db_manager = db_manager
        self.telegram = telegram_integration
        self.trading_manager = trading_manager
        self.broker = broker
        self.intraday_manager = intraday_manager
        self.config = config
        self.is_virtual_mode = getattr(config, 'paper_trading', True) if config else True

        from core.virtual_trading_manager import VirtualTradingManager
        self.virtual_trading = VirtualTradingManager(
            db_manager=db_manager, broker=broker,
            paper_trading=self.is_virtual_mode
        )

        # Strategy 연결 (나중에 set_strategy로 설정)
        self.strategy: Optional['BaseStrategy'] = None

        # FundManager 연결 (나중에 set_fund_manager로 설정)
        self.fund_manager: Optional['FundManager'] = None

        self.logger.info("매매 판단 엔진 초기화")

    def set_strategy(self, strategy: 'BaseStrategy') -> None:
        """전략 설정"""
        self.strategy = strategy
        self.logger.info(f"전략 연결됨: {strategy.name if strategy else 'None'}")

    def set_fund_manager(self, fund_manager: 'FundManager') -> None:
        """자금 관리자 설정"""
        self.fund_manager = fund_manager
        self.logger.info("FundManager 연결됨")

    def _safe_float(self, v) -> float:
        if pd.isna(v) or v is None: return 0.0
        try: return float(str(v).replace(',', ''))
        except (ValueError, TypeError): return 0.0

    def _get_max_buy_amount(self, stock_code: str = "") -> float:
        """
        종목별 최대 매수 가능 금액 계산

        FundManager가 설정되어 있으면 FundManager를 통해 계산 (자금 예약 반영)
        없으면 broker에서 직접 조회 (fallback)
        """
        # FundManager 우선 사용
        if self.fund_manager:
            try:
                max_amount = self.fund_manager.get_max_buy_amount(stock_code)
                if max_amount > 0:
                    return max_amount
            except Exception as e:
                self.logger.debug(f"FundManager 최대 매수금액 조회 실패: {e}")

        # Fallback: broker 직접 조회
        try:
            if self.broker:
                info = self.broker.get_account_balance()
                if info:
                    # KISBroker returns dict, KISAPIManager returns AccountInfo
                    available = (info.get('available_cash', 0) if isinstance(info, dict)
                                 else getattr(info, 'available_amount', 0))
                    if available:
                        return min(5000000, float(available) * 0.1)
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

            # 현재가 조회 (일봉 종가 대신 장중 실시간 가격 사용)
            current_price = None
            # 1순위: intraday_manager 캐시 (빠름)
            if self.intraday_manager and hasattr(self.intraday_manager, 'get_cached_current_price'):
                try:
                    price_info = self.intraday_manager.get_cached_current_price(code)
                    if price_info and price_info.get('current_price', 0) > 0:
                        current_price = price_info['current_price']
                except Exception:
                    pass
            # 2순위: broker API (정확)
            if current_price is None and self.broker:
                try:
                    price_obj = self.broker.get_current_price(code)
                    if price_obj and hasattr(price_obj, 'current_price') and price_obj.current_price > 0:
                        current_price = float(price_obj.current_price)
                except Exception:
                    pass
            # 3순위: 일봉 종가 fallback
            if current_price is None:
                current_price = float(daily_data['close'].iloc[-1])

            from utils.price_utils import round_to_tick
            price = round_to_tick(current_price)
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

        손절/익절은 PositionMonitor._analyze_sell_for_stock()에서 일원화 처리.
        여기서는 Strategy 매도 신호만 체크.
        """
        try:
            if not trading_stock.position or trading_stock.position.avg_price <= 0:
                return False, "포지션없음"

            # Strategy 매도 신호 체크
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
                                  buy_reason: str, buy_price: float = None,
                                  quantity: int = None,
                                  target_profit_rate: float = None,
                                  stop_loss_rate: float = None) -> None:
        """가상 매수

        Args:
            trading_stock: 거래 대상 주식
            combined_data: 차트 데이터 (None 가능 — buy_price 미전달 시 fallback 조회)
            buy_reason: 매수 사유
            buy_price: 매수 가격 (None이면 아래 우선순위로 조회)
                       1순위: intraday_manager 캐시
                       2순위: broker API
                       3순위: combined_data 종가 (combined_data가 있을 때만)
            quantity: 매수 수량 (None이면 VirtualTradingManager.get_max_quantity() 재계산)
            target_profit_rate: 익절률 (None이면 DEFAULT_TARGET_PROFIT_RATE 사용)
            stop_loss_rate: 손절률 (None이면 DEFAULT_STOP_LOSS_RATE 사용)
        """
        try:
            code = trading_stock.stock_code

            # buy_price 결정: 전달값 우선, 없으면 순차 fallback
            if buy_price is None:
                # 1순위: intraday_manager 캐시
                if self.intraday_manager and hasattr(self.intraday_manager, 'get_cached_current_price'):
                    try:
                        price_info = self.intraday_manager.get_cached_current_price(code)
                        if price_info and price_info.get('current_price', 0) > 0:
                            buy_price = float(price_info['current_price'])
                    except Exception:
                        pass
                # 2순위: broker API
                if buy_price is None and self.broker:
                    try:
                        price_obj = self.broker.get_current_price(code)
                        if price_obj and hasattr(price_obj, 'current_price') and price_obj.current_price > 0:
                            buy_price = float(price_obj.current_price)
                    except Exception:
                        pass
                # 3순위: combined_data 종가 (None이 아닐 때만)
                if buy_price is None and combined_data is not None:
                    try:
                        v = self._safe_float(combined_data['close'].iloc[-1])
                        if v > 0:
                            buy_price = v
                    except Exception:
                        pass

            if not buy_price or buy_price <= 0:
                self.logger.warning(f"가상매수 취소: {code} 매수 가격 조회 실패")
                return

            # 익절/손절률: 전달값 우선, 없으면 기본값 사용
            if target_profit_rate is None:
                target_profit_rate = self.DEFAULT_TAKE_PROFIT
            if stop_loss_rate is None:
                stop_loss_rate = self.DEFAULT_STOP_LOSS

            # 수량 결정: 전달값 우선, 없으면 VirtualTradingManager 재계산
            if quantity is not None and quantity > 0:
                qty = quantity
            else:
                qty = self.virtual_trading.get_max_quantity(buy_price)
            if qty <= 0: return

            strategy_name = self.strategy.name if self.strategy else "사용자전략"
            rid = self.virtual_trading.execute_virtual_buy(
                stock_code=trading_stock.stock_code, stock_name=trading_stock.stock_name,
                price=buy_price, quantity=qty, strategy=strategy_name, reason=buy_reason,
                target_profit_rate=target_profit_rate, stop_loss_rate=stop_loss_rate)
            if rid:
                trading_stock.set_virtual_buy_info(rid, buy_price, qty)
                trading_stock.set_position(qty, buy_price)
                trading_stock.target_profit_rate = target_profit_rate
                trading_stock.stop_loss_rate = stop_loss_rate
                self.logger.info(
                    f"가상매수: {trading_stock.stock_code} {qty}주 @{buy_price:,.0f} "
                    f"(익절:{target_profit_rate*100:.1f}% 손절:{stop_loss_rate*100:.1f}%)"
                )
        except Exception as e:
            self.logger.error(f"가상매수오류: {e}")

    async def execute_real_sell(self, trading_stock, sell_reason: str) -> bool:
        """실제 매도"""
        try:
            if not trading_stock.position or trading_stock.position.quantity <= 0:
                return False
            stock_code = trading_stock.stock_code
            # 매도 후보 상태로 전이 (execute_sell_order는 SELL_CANDIDATE 상태 필요)
            move_ok = self.trading_manager.move_to_sell_candidate(
                stock_code=stock_code, reason=sell_reason)
            if not move_ok:
                self.logger.warning(f"매도 후보 전환 실패: {stock_code}")
                return False
            ok = await self.trading_manager.execute_sell_order(
                stock_code=stock_code,
                quantity=trading_stock.position.quantity,
                price=0, reason=sell_reason, market=True)
            if ok:
                self.logger.info(f"매도: {stock_code} - {sell_reason}")
            else:
                # 매도 주문 실패 시 POSITIONED로 복원
                self._restore_to_positioned(stock_code, "매도 주문 실패")
            return ok
        except Exception as e:
            self.logger.error(f"매도오류: {e}")
            # 예외 발생 시에도 POSITIONED로 복원 시도
            try:
                self._restore_to_positioned(trading_stock.stock_code, f"매도 예외: {e}")
            except Exception:
                pass
            return False

    def _restore_to_positioned(self, stock_code: str, reason: str) -> None:
        """매도 실패 시 POSITIONED 상태로 복원"""
        try:
            if self.trading_manager:
                from core.models import StockState
                trading_stock = self.trading_manager.get_trading_stock(stock_code)
                if trading_stock and trading_stock.state in [StockState.SELL_CANDIDATE, StockState.SELL_PENDING]:
                    self.trading_manager._change_stock_state(
                        stock_code, StockState.POSITIONED, f"복원: {reason}"
                    )
                    trading_stock.is_selling = False
                    self.logger.info(f"{stock_code} POSITIONED로 복원 완료: {reason}")
        except Exception as e:
            self.logger.warning(f"{stock_code} POSITIONED 복원 실패: {e}")

    async def execute_virtual_sell(self, trading_stock, sell_price: Optional[float],
                                   sell_reason: str) -> bool:
        """가상 매도

        Args:
            trading_stock: 거래 대상 주식
            sell_price: 매도 가격 (None/0 가능 — 아래 우선순위로 조회)
                        1순위: 전달된 sell_price
                        2순위: intraday_manager 캐시
                        3순위: broker API
                        4순위: trading_stock.position.avg_price (매수가로 매도, 최후수단)
            sell_reason: 매도 사유

        Returns:
            bool: 매도 성공 여부
        """
        try:
            code = trading_stock.stock_code

            # sell_price 결정: 전달값 우선, 없으면 순차 fallback
            if not sell_price or sell_price <= 0:
                sell_price = None  # 명확히 None으로 초기화 후 fallback 진행
                # 2순위: intraday_manager 캐시
                if self.intraday_manager and hasattr(self.intraday_manager, 'get_cached_current_price'):
                    try:
                        info = self.intraday_manager.get_cached_current_price(code)
                        if info and info.get('current_price', 0) > 0:
                            sell_price = float(info['current_price'])
                    except Exception:
                        pass
                # 3순위: broker API
                if sell_price is None and self.broker:
                    try:
                        price_obj = self.broker.get_current_price(code)
                        if price_obj and hasattr(price_obj, 'current_price') and price_obj.current_price > 0:
                            sell_price = float(price_obj.current_price)
                    except Exception:
                        pass
                # 4순위: 매수 평균가 (최후수단)
                if sell_price is None:
                    avg = getattr(getattr(trading_stock, 'position', None), 'avg_price', None)
                    if avg and avg > 0:
                        sell_price = float(avg)
                        self.logger.warning(
                            f"가상매도: {code} 현재가 조회 실패 → 매수 평균가로 매도 ({sell_price:,.0f}원)"
                        )

            if not sell_price or sell_price <= 0:
                self.logger.error(f"가상매도 취소: {code} 매도 가격 조회 완전 실패")
                return False

            rid = getattr(trading_stock, '_virtual_buy_record_id', None)
            bp = getattr(trading_stock, '_virtual_buy_price', None)
            qty = getattr(trading_stock, '_virtual_quantity', None)

            if not rid and self.db_manager:
                pos = self.db_manager.get_virtual_open_positions()
                sp = pos[pos['stock_code'] == code]
                if not sp.empty:
                    r = sp.iloc[0]
                    rid = int(r['id']) if r.get('id') is not None else None
                    bp = float(r['buy_price']) if r.get('buy_price') is not None else None
                    qty = int(r['quantity']) if r.get('quantity') is not None else None

            # Defensive type conversions for arithmetic safety
            sell_price = float(sell_price)
            if bp is not None:
                bp = float(bp)
            if qty is not None:
                qty = int(qty)
            if rid is not None:
                rid = int(rid)

            if rid:
                strategy_name = self.strategy.name if self.strategy else "사용자전략"
                ok = self.virtual_trading.execute_virtual_sell(
                    stock_code=code, stock_name=trading_stock.stock_name,
                    price=sell_price, quantity=qty, strategy=strategy_name,
                    reason=sell_reason, buy_record_id=rid)
                if ok:
                    pnl = (float(sell_price) - float(bp)) * int(qty) if bp and qty else 0
                    self.logger.info(f"가상매도: {code} (손익: {pnl:+,.0f}원)")
                    trading_stock.clear_virtual_buy_info()
                    trading_stock.clear_position()
                    # H5 fix: 가상매도 후 종목 상태를 COMPLETED로 변경하여 고아 상태 방지
                    try:
                        if self.trading_manager:
                            from core.models import StockState
                            self.trading_manager._change_stock_state(
                                code, StockState.COMPLETED, "가상 매도 완료"
                            )
                    except Exception as state_err:
                        self.logger.warning(f"가상매도 상태 변경 실패: {code} - {state_err}")
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
