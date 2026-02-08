"""
포지션 모니터링 모듈

보유 종목 현재가 업데이트 및 손익절 모니터링
"""
import asyncio
from typing import TYPE_CHECKING, Optional

from ..models import TradingStock, StockState
from utils.logger import setup_logger
from utils.korean_time import now_kst, is_market_open

if TYPE_CHECKING:
    from .stock_state_manager import StockStateManager
    from .order_completion_handler import OrderCompletionHandler
    from ..intraday_stock_manager import IntradayStockManager
    from ..data_collector import RealTimeDataCollector


class PositionMonitor:
    """
    포지션 모니터링 관리자

    주요 기능:
    1. 종목 상태 모니터링 루프
    2. 포지션 현재가 업데이트
    3. 손익절 조건 체크
    4. 매도 실행
    """

    def __init__(self, state_manager: 'StockStateManager',
                 completion_handler: 'OrderCompletionHandler',
                 intraday_manager: 'IntradayStockManager',
                 data_collector: 'RealTimeDataCollector'):
        """
        초기화

        Args:
            state_manager: 종목 상태 관리자
            completion_handler: 주문 체결 처리자
            intraday_manager: 장중 종목 관리자
            data_collector: 실시간 데이터 수집기
        """
        self.state_manager = state_manager
        self.completion_handler = completion_handler
        self.intraday_manager = intraday_manager
        self.data_collector = data_collector
        self.logger = setup_logger(__name__)

        # 모니터링 설정
        self.is_monitoring = False
        self.monitor_interval = 3  # 3초마다 상태 체크 (체결 확인 빠르게)

        # decision_engine은 나중에 설정됨 (순환 참조 방지)
        self.decision_engine = None

        # 로깅 플래그
        self._sell_check_logged = False

    def set_decision_engine(self, decision_engine):
        """매매 판단 엔진 설정 (순환 참조 방지를 위해 별도 메서드)"""
        self.decision_engine = decision_engine
        self.logger.debug("PositionMonitor에 decision_engine 연결 완료")

    async def start_monitoring(self):
        """종목 상태 모니터링 시작"""
        self.is_monitoring = True
        self.logger.info("종목 상태 모니터링 시작")

        while self.is_monitoring:
            try:
                if not is_market_open():
                    await asyncio.sleep(60)  # 장 마감 시 1분 대기
                    continue

                await self._monitor_stock_states()
                await asyncio.sleep(self.monitor_interval)

            except Exception as e:
                self.logger.error(f"종목 상태 모니터링 오류: {e}")
                await asyncio.sleep(10)

    async def _monitor_stock_states(self):
        """종목 상태 모니터링"""
        try:
            self.logger.debug("종목 상태 모니터링 실행")

            # 주문 완료 확인
            await self.completion_handler.check_order_completions()

            # 포지션 현재가 업데이트
            await self._update_position_prices()

            # 보유 종목 매도 판단 (손익절 체크)
            await self._check_positioned_stocks_for_sell()

        except Exception as e:
            self.logger.error(f"종목 상태 모니터링 중 오류: {e}")

    async def _update_position_prices(self):
        """포지션 현재가 업데이트"""
        try:
            positioned_stocks = list(
                self.state_manager.stocks_by_state[StockState.POSITIONED].values()
            )

            for trading_stock in positioned_stocks:
                if trading_stock.position:
                    # 현재가 조회
                    price_data = self.data_collector.get_stock(trading_stock.stock_code)
                    if price_data and price_data.last_price > 0:
                        trading_stock.position.update_current_price(price_data.last_price)

        except Exception as e:
            self.logger.error(f"포지션 현재가 업데이트 오류: {e}")

    async def _check_positioned_stocks_for_sell(self):
        """보유 종목 매도 판단 (손익절 체크)"""
        try:
            positioned_stocks = list(
                self.state_manager.stocks_by_state[StockState.POSITIONED].values()
            )

            if not positioned_stocks:
                return

            # 최초 1회만 로깅 (너무 많은 로그 방지)
            if not self._sell_check_logged:
                self.logger.info(
                    f"보유 종목 손익절 체크 시작: {len(positioned_stocks)}개 종목"
                )
                self._sell_check_logged = True

            for trading_stock in positioned_stocks:
                if not trading_stock.position:
                    continue

                # decision_engine이 설정되어 있어야 매도 판단 가능
                if not self.decision_engine:
                    continue

                try:
                    await self._analyze_sell_for_stock(trading_stock)
                except Exception as e:
                    self.logger.error(f"{trading_stock.stock_code} 매도 판단 오류: {e}")

        except Exception as e:
            self.logger.error(f"보유 종목 매도 판단 오류: {e}")

    async def _analyze_sell_for_stock(self, trading_stock: TradingStock):
        """개별 종목 매도 판단"""
        try:
            stock_code = trading_stock.stock_code

            # 현재가 조회 - 손익절 정확성을 위해 API 직접 호출 우선
            current_price = await self._get_current_price(stock_code)

            # 현재가 조회 실패 시 종료
            if current_price is None or current_price <= 0:
                self.logger.debug(f"{stock_code} 현재가 조회 실패 - 손익절 체크 스킵")
                return

            # 간단한 손익절 체크
            if trading_stock.position:
                buy_price = trading_stock.position.avg_price
                profit_rate = (current_price - buy_price) / buy_price

                # 09:00~09:05 사이에는 손절 체크 안 함 (익절만)
                current_time = now_kst()
                is_before_rebalancing = (
                    current_time.hour == 9 and
                    current_time.minute < 5
                )

                # 목표 익절률 체크
                if hasattr(trading_stock, 'target_profit_rate') and trading_stock.target_profit_rate:
                    if profit_rate >= trading_stock.target_profit_rate:
                        reason = (
                            f"목표 익절 도달 ({profit_rate:.2%} >= "
                            f"{trading_stock.target_profit_rate:.2%})"
                        )
                        self.logger.info(f"{stock_code} 익절 신호: {reason}")
                        await self._execute_sell(trading_stock, current_price, reason)
                        return

                # 손절률 체크 (리밸런싱 전에는 스킵)
                if not is_before_rebalancing:
                    if hasattr(trading_stock, 'stop_loss_rate') and trading_stock.stop_loss_rate:
                        if profit_rate <= -trading_stock.stop_loss_rate:
                            reason = (
                                f"손절 실행 ({profit_rate:.2%} <= "
                                f"-{trading_stock.stop_loss_rate:.2%})"
                            )
                            self.logger.info(f"{stock_code} 손절 신호: {reason}")
                            await self._execute_sell(trading_stock, current_price, reason)
                            return

        except Exception as e:
            self.logger.error(f"{trading_stock.stock_code} 매도 분석 오류: {e}")

    async def _get_current_price(self, stock_code: str) -> Optional[float]:
        """
        현재가 조회 (여러 소스에서 시도)

        Args:
            stock_code: 종목 코드

        Returns:
            현재가 또는 None
        """
        current_price = None

        # 1. API 직접 호출 (최신 가격, 손익절 판단에 가장 정확)
        try:
            current_price_info = self.intraday_manager.get_current_price_for_sell(stock_code)
            if current_price_info:
                current_price = current_price_info.get('current_price')
        except Exception as api_err:
            self.logger.warning(f"{stock_code} 현재가 API 조회 실패: {api_err}")

        # 2. 캐시된 현재가 폴백 (API 실패 시)
        if current_price is None:
            current_price_info = self.intraday_manager.get_cached_current_price(stock_code)
            if current_price_info:
                current_price = current_price_info.get('current_price')
                self.logger.debug(f"{stock_code} 캐시된 현재가 사용: {current_price:,.0f}원")

        # 3. data_collector fallback (최종 수단)
        if current_price is None:
            price_data = self.data_collector.get_stock(stock_code)
            if price_data and price_data.last_price > 0:
                current_price = price_data.last_price
                self.logger.debug(
                    f"{stock_code} data_collector 현재가 사용: {current_price:,.0f}원"
                )

        return current_price

    async def _execute_sell(self, trading_stock: TradingStock,
                           sell_price: float, reason: str):
        """매도 실행"""
        try:
            stock_code = trading_stock.stock_code

            # decision_engine을 통해 매도 실행
            if self.decision_engine:
                # 가상매매 모드 확인 (TradingConfig 객체 사용)
                from config.settings import load_trading_config
                config = load_trading_config()
                if config.paper_trading:
                    # 가상 매도 실행
                    success = await self.decision_engine.execute_virtual_sell(
                        trading_stock,
                        sell_price,
                        reason
                    )
                    if success:
                        self.logger.info(f"{stock_code} 가상 매도 완료: {reason}")
                else:
                    # 실제 매도 주문
                    success = await self.decision_engine.execute_real_sell(
                        trading_stock,
                        reason
                    )
                    if success:
                        self.logger.info(f"{stock_code} 실제 매도 주문 완료: {reason}")

        except Exception as e:
            self.logger.error(f"{stock_code} 매도 실행 오류: {e}")

    def stop_monitoring(self):
        """모니터링 중단"""
        self.is_monitoring = False
        self.logger.info("종목 상태 모니터링 중단")
