"""
매매 판단 엔진 - 템플릿

Strategy 시스템과 연동되어 매매 판단을 수행합니다.
- Strategy가 설정되면: strategy.generate_signal()을 통해 매매 판단
- Strategy가 없으면: 기본 동작 (매수 안함, 손절/익절만 동작)

손절/익절 체크는 PositionMonitor가 담당 (trading_stock별 설정 사용)
"""
import time
from typing import Tuple, Optional, TYPE_CHECKING
import pandas as pd
from utils.logger import setup_logger
from config.constants import (
    DEFAULT_STOP_LOSS_RATE, DEFAULT_TARGET_PROFIT_RATE,
    MARKET_DIRECTION_FILTER_ENABLED, KOSPI_DECLINE_THRESHOLD, KOSDAQ_DECLINE_THRESHOLD,
    COMMISSION_RATE, SECURITIES_TAX_RATE, CANDIDATE_MIN_DAILY_DATA
)

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

        # 시장 방향성 필터 캐시 (60초)
        self._market_direction_cache: Optional[Tuple[bool, str]] = None
        self._market_direction_cache_time: float = 0.0
        self._MARKET_DIRECTION_CACHE_TTL = 60  # 초

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
    # 시장 방향성 필터 (폭락장 매수 차단)
    # =========================================================================
    def check_market_direction(self) -> Tuple[bool, str]:
        """
        시장 방향성 확인 - KOSPI/KOSDAQ 급락 시 매수 차단

        Returns:
            Tuple[is_crashing, reason]:
                is_crashing=True이면 매수 차단, reason은 차단 사유
                is_crashing=False이면 매수 허용
        """
        if not MARKET_DIRECTION_FILTER_ENABLED:
            return False, ""

        # 캐시 확인 (60초 이내면 캐시 결과 반환)
        now = time.monotonic()
        if (self._market_direction_cache is not None
                and (now - self._market_direction_cache_time) < self._MARKET_DIRECTION_CACHE_TTL):
            return self._market_direction_cache

        # API 호출
        try:
            from api.kis_market_api import get_index_data

            # KOSPI 지수 조회
            kospi_data = get_index_data("0001")
            if kospi_data:
                try:
                    kospi_change = float(kospi_data.get('bstp_nmix_prdy_ctrt', '0'))
                    if kospi_change <= KOSPI_DECLINE_THRESHOLD:
                        result = (True, f"KOSPI {kospi_change:+.2f}% (임계값: {KOSPI_DECLINE_THRESHOLD}%)")
                        self._market_direction_cache = result
                        self._market_direction_cache_time = now
                        self.logger.info(
                            f"[시장방향성필터] 매수 차단: {result[1]}"
                        )
                        return result
                except (ValueError, TypeError):
                    pass

            # KOSDAQ 지수 조회
            kosdaq_data = get_index_data("1001")
            if kosdaq_data:
                try:
                    kosdaq_change = float(kosdaq_data.get('bstp_nmix_prdy_ctrt', '0'))
                    if kosdaq_change <= KOSDAQ_DECLINE_THRESHOLD:
                        result = (True, f"KOSDAQ {kosdaq_change:+.2f}% (임계값: {KOSDAQ_DECLINE_THRESHOLD}%)")
                        self._market_direction_cache = result
                        self._market_direction_cache_time = now
                        self.logger.info(
                            f"[시장방향성필터] 매수 차단: {result[1]}"
                        )
                        return result
                except (ValueError, TypeError):
                    pass

            # 시장 정상 → 매수 허용
            result = (False, "")
            self._market_direction_cache = result
            self._market_direction_cache_time = now
            return result

        except Exception as e:
            # API 실패 시 fail-safe: 매수 허용
            self.logger.warning(f"[시장방향성필터] API 조회 실패 (매수 허용): {e}")
            result = (False, "")
            self._market_direction_cache = result
            self._market_direction_cache_time = now
            return result

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

            # 시장 방향성 필터: 폭락장 매수 차단
            is_crashing, crash_reason = self.check_market_direction()
            if is_crashing:
                return False, f"{code} 시장급락 매수차단 ({crash_reason})", empty

            if daily_data is None or len(daily_data) < CANDIDATE_MIN_DAILY_DATA:
                return False, f"{code} 데이터부족", empty

            should_buy = False
            buy_reason = ""
            signal = None

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
                    if price_obj is not None and isinstance(price_obj, (int, float)) and price_obj > 0:
                        current_price = float(price_obj)
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

            buy_info = {'buy_price': price, 'quantity': qty, 'max_buy_amount': max_amt}
            if signal:
                buy_info['signal'] = signal
            return True, buy_reason, buy_info

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
                                  stop_loss_rate: float = None,
                                  signal=None) -> None:
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
            target_profit_rate: 익절률 (None이면 아래 우선순위로 결정)
            stop_loss_rate: 손절률 (None이면 아래 우선순위로 결정)
            signal: 전략 Signal 객체 (target_price/stop_loss 포함 시 활용)

        익절/손절률 우선순위 (높을수록 먼저 적용):
            1순위: 호출자가 명시적으로 전달한 target_profit_rate / stop_loss_rate
            2순위: Signal.target_price / Signal.stop_loss (절대가 → 매수가 대비 비율 변환)
            3순위: 전략 config.yaml의 risk_management.take_profit_ratio / stop_loss_ratio
            4순위: 시스템 기본값 — trading_config.json risk_management 우선,
                   없으면 constants.py DEFAULT_TARGET_PROFIT_RATE / DEFAULT_STOP_LOSS_RATE
        결정된 값은 trading_stock.target_profit_rate / stop_loss_rate에 기록되어
        PositionMonitor._analyze_sell_for_stock()에서 손익절 판단에 사용됨.
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
                        if price_obj is not None and isinstance(price_obj, (int, float)) and price_obj > 0:
                            buy_price = float(price_obj)
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

            # ----------------------------------------------------------------
            # 익절/손절률 결정 — 4단계 우선순위
            # ----------------------------------------------------------------
            # [1순위] 호출자 명시 값은 파라미터로 이미 수신됨 (target_profit_rate, stop_loss_rate)

            # [2순위] Signal의 target_price / stop_loss (절대가 → 비율 변환)
            if target_profit_rate is None and signal and signal.target_price and buy_price > 0:
                target_profit_rate = (signal.target_price - buy_price) / buy_price
            if stop_loss_rate is None and signal and signal.stop_loss and buy_price > 0:
                stop_loss_rate = (buy_price - signal.stop_loss) / buy_price

            # [3순위] 전략 config.yaml의 risk_management 섹션
            if (target_profit_rate is None or stop_loss_rate is None) and self.strategy:
                try:
                    cfg = getattr(self.strategy, 'config', None)
                    if isinstance(cfg, dict):
                        rm = cfg.get('risk_management', {})
                        if target_profit_rate is None and rm.get('take_profit_ratio'):
                            target_profit_rate = float(rm['take_profit_ratio'])
                        if stop_loss_rate is None and rm.get('stop_loss_ratio'):
                            stop_loss_rate = float(rm['stop_loss_ratio'])
                except Exception:
                    pass  # 전략 config 조회 실패 시 4순위로 fallback

            # [4순위] 시스템 기본값: trading_config.json risk_management 우선,
            #         없으면 constants.py DEFAULT_* (클래스 상수 DEFAULT_TAKE_PROFIT / DEFAULT_STOP_LOSS)
            if target_profit_rate is None:
                config_tp = getattr(
                    getattr(self.config, 'risk_management', None),
                    'take_profit_ratio', None
                )
                target_profit_rate = float(config_tp) if config_tp else self.DEFAULT_TAKE_PROFIT
            if stop_loss_rate is None:
                config_sl = getattr(
                    getattr(self.config, 'risk_management', None),
                    'stop_loss_ratio', None
                )
                stop_loss_rate = float(config_sl) if config_sl else self.DEFAULT_STOP_LOSS

            # 수량 결정: 전달값 우선, 없으면 VirtualTradingManager 재계산
            if quantity is not None and quantity > 0:
                qty = quantity
            else:
                qty = self.virtual_trading.get_max_quantity(buy_price)
            if qty <= 0: return

            strategy_name = self.strategy.name if self.strategy else "unknown"
            # trading_stock에 소유 전략 기록 (DB용 이름 + 메모리용 인스턴스)
            trading_stock.owner_strategy_name = strategy_name
            trading_stock.owner_strategy = self.strategy
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
        """매도 실패 시 POSITIONED 상태로 복원

        주의: is_selling 플래그는 여기서 해제하지 않습니다.
        - execute_sell_order 실패 시: execute_sell_order 내부에서 이미 해제
        - move_to_sell_candidate 실패 시: 호출측(position_monitor)에서 해제
        """
        try:
            if self.trading_manager:
                from core.models import StockState
                trading_stock = self.trading_manager.get_trading_stock(stock_code)
                if trading_stock and trading_stock.state in [StockState.SELL_CANDIDATE, StockState.SELL_PENDING]:
                    self.trading_manager._change_stock_state(
                        stock_code, StockState.POSITIONED, f"복원: {reason}"
                    )
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
                        4순위: 모두 실패 시 매도 보류 (다음 사이클 재시도)
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
                        if price_obj is not None and isinstance(price_obj, (int, float)) and price_obj > 0:
                            sell_price = float(price_obj)
                    except Exception:
                        pass
                # 4순위: 현재가 조회 모두 실패 → 매도 보류 (다음 사이클에서 재시도)
                if sell_price is None:
                    self.logger.error(
                        f"[{code}] 현재가 조회 모두 실패 - 매도 보류 (다음 사이클 재시도)"
                    )
                    return False  # 매수가로 매도하면 손익 0%로 왜곡되므로 거부

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
                # 전략 이름: trading_stock에 이미 기록된 값 우선, 없으면 현재 전략
                strategy_name = trading_stock.strategy_name or (
                    self.strategy.name if self.strategy else "unknown"
                )
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
                    # fund_manager 업데이트 (매도 후 자금 반환) — 단일 책임 지점
                    if self.fund_manager and bp and qty:
                        try:
                            invested = float(bp) * int(qty)
                            sell_amount = float(sell_price) * int(qty)
                            buy_commission = invested * COMMISSION_RATE
                            sell_commission = sell_amount * COMMISSION_RATE
                            sell_tax = sell_amount * SECURITIES_TAX_RATE
                            pnl_with_fees = sell_amount - invested - buy_commission - sell_commission - sell_tax
                            self.fund_manager.release_investment(invested, stock_code=code)
                            if pnl_with_fees != 0:
                                self.fund_manager.adjust_pnl(pnl_with_fees)
                            self.fund_manager.remove_position(code)
                            self.fund_manager.set_sell_cooldown(code, sell_reason)
                        except Exception as fm_e:
                            self.logger.error(f"{code} 매도 후 자금관리 업데이트 실패: {fm_e}")
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
