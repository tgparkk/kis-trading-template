"""
주문 관리 기본 클래스 및 유틸리티
"""
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, TYPE_CHECKING
from concurrent.futures import ThreadPoolExecutor

from ..models import Order, OrderType, OrderStatus, TradingConfig
from utils.logger import setup_logger
from utils.korean_time import now_kst

if TYPE_CHECKING:
    from framework import KISBroker

MAX_COMPLETED_ORDERS = 200


class OrderManagerBase:
    """주문 관리자 기본 클래스 - 공통 속성 및 유틸리티 메서드"""

    def __init__(self, config: TradingConfig, broker: 'KISBroker',
                 telegram_integration=None, db_manager=None) -> None:
        self.config = config
        self.broker = broker
        self.telegram = telegram_integration
        self.db_manager = db_manager
        self.logger = setup_logger(__name__)
        self.trading_manager = None  # TradingStockManager (선택 연결)

        # 주문 저장소
        self.pending_orders: Dict[str, Order] = {}  # order_id: Order
        self.order_timeouts: Dict[str, datetime] = {}  # order_id: timeout_time
        self.completed_orders: List[Order] = []  # 완료된 주문 기록

        # 중복 주문 방지
        self._active_buy_stocks: Dict[str, str] = {}  # stock_code -> order_id (매수 진행 중인 종목)
        self._active_sell_stocks: Dict[str, str] = {}  # stock_code -> order_id (매도 진행 중인 종목)

        # FundManager 연동
        self.fund_manager = None  # 외부에서 set_fund_manager()로 설정

        # 모니터링 상태
        self.is_monitoring = False
        self.executor = ThreadPoolExecutor(max_workers=2)

    def set_trading_manager(self, trading_manager: Any) -> None:
        """TradingStockManager 참조를 등록 (가격 정정 시 주문ID 동기화용)"""
        self.trading_manager = trading_manager

    def set_fund_manager(self, fund_manager: Any) -> None:
        """FundManager 참조를 등록 (자금 예약/확정/취소 연동용)"""
        self.fund_manager = fund_manager
        self.logger.info("OrderManager에 FundManager 연결됨")

    def has_active_buy_order(self, stock_code: str) -> bool:
        """해당 종목에 진행 중인 매수 주문이 있는지 확인"""
        return stock_code in self._active_buy_stocks

    def has_active_sell_order(self, stock_code: str) -> bool:
        """해당 종목에 진행 중인 매도 주문이 있는지 확인"""
        return stock_code in self._active_sell_stocks

    def _register_active_order(self, stock_code: str, order_id: str, order_type: str) -> None:
        """진행 중인 주문 등록 (중복 방지용)"""
        from ..models import OrderType
        if order_type == OrderType.BUY:
            self._active_buy_stocks[stock_code] = order_id
        else:
            self._active_sell_stocks[stock_code] = order_id

    def _unregister_active_order(self, stock_code: str, order_type: str) -> None:
        """진행 중인 주문 해제"""
        from ..models import OrderType
        if order_type == OrderType.BUY:
            self._active_buy_stocks.pop(stock_code, None)
        else:
            self._active_sell_stocks.pop(stock_code, None)

    def _get_current_3min_candle_time(self) -> datetime:
        """현재 시간을 기준으로 3분봉 시간 계산 (3분 단위로 반올림) - 동적 시간 적용"""
        try:
            from config.market_hours import MarketHours

            current_time = now_kst()

            # 동적 시장 시간 가져오기
            market_hours = MarketHours.get_market_hours('KRX', current_time)
            market_open_time = market_hours['market_open']
            market_close_time = market_hours['market_close']

            # 시장 시작 시간부터의 경과 분 계산
            market_open = current_time.replace(
                hour=market_open_time.hour,
                minute=market_open_time.minute,
                second=0,
                microsecond=0
            )
            elapsed_minutes = int((current_time - market_open).total_seconds() / 60)

            # 3분 단위로 반올림 (예: 0-2분 -> 3분, 3-5분 -> 6분)
            candle_minute = ((elapsed_minutes // 3) + 1) * 3

            # 실제 3분봉 시간 생성 (해당 구간의 끝 시간)
            candle_time = market_open + timedelta(minutes=candle_minute)

            # 장마감 시간 초과 시 장마감 시간으로 제한
            market_close = current_time.replace(
                hour=market_close_time.hour,
                minute=market_close_time.minute,
                second=0,
                microsecond=0
            )
            if candle_time > market_close:
                candle_time = market_close

            return candle_time

        except Exception as e:
            self.logger.error(f"3분봉 시간 계산 오류: {e}")
            return now_kst()

    def _has_4_candles_passed(self, order_candle_time: datetime) -> bool:
        """주문 시점부터 3분봉 4개가 지났는지 확인"""
        try:
            if order_candle_time is None:
                return False

            # 3분봉 4개 = 12분 후 (실제 시각 기준 비교: 장마감 15:30 클램프에 걸려 무한 대기되는 문제 방지)
            now_time = now_kst()
            four_candles_later = order_candle_time + timedelta(minutes=12)

            return now_time >= four_candles_later

        except Exception as e:
            self.logger.error(f"4분봉 경과 확인 오류: {e}")
            return False

    def _move_to_completed(self, order_id: str) -> None:
        """완료된 주문으로 이동 (오탐지 방지 로깅 추가)"""
        if order_id in self.pending_orders:
            order = self.pending_orders.pop(order_id)
            self.completed_orders.append(order)

            # 오탐지 추적을 위한 상세 로깅
            elapsed_time = (now_kst() - order.timestamp).total_seconds()
            self.logger.info(f"주문 완료 처리: {order_id} ({order.stock_code}) "
                           f"- 상태: {order.status.value}, 경과시간: {elapsed_time:.0f}초")

            # 타임아웃 정보도 제거
            if order_id in self.order_timeouts:
                del self.order_timeouts[order_id]
                self.logger.debug(f"타임아웃 정보 제거: {order_id}")
            else:
                self.logger.warning(f"타임아웃 정보 없음: {order_id}")

            # 중복 주문 방지 맵에서 해제
            self._unregister_active_order(order.stock_code, order.order_type)

            # FundManager 연동: 취소/타임아웃 시 예약 해제
            from ..models import OrderStatus
            if order.status in (OrderStatus.CANCELLED, OrderStatus.TIMEOUT, OrderStatus.FAILED):
                if self.fund_manager:
                    try:
                        self.fund_manager.cancel_order(order_id)
                        self.logger.info(f"FundManager 예약 해제: {order_id}")
                    except Exception as e:
                        self.logger.warning(f"FundManager 예약 해제 실패: {order_id} - {e}")

            # 메모리 관리: completed_orders가 MAX_COMPLETED_ORDERS를 초과하면 오래된 것 제거
            if len(self.completed_orders) > MAX_COMPLETED_ORDERS:
                removed = len(self.completed_orders) - MAX_COMPLETED_ORDERS
                self.completed_orders = self.completed_orders[-MAX_COMPLETED_ORDERS:]
                self.logger.debug(f"completed_orders 정리: {removed}건 제거, 현재 {len(self.completed_orders)}건 유지")
        else:
            self.logger.error(f"완료 처리할 주문이 없음: {order_id}")

    def get_pending_orders(self) -> List[Order]:
        """미체결 주문 목록 반환"""
        return list(self.pending_orders.values())

    def get_completed_orders(self) -> List[Order]:
        """완료된 주문 목록 반환"""
        return self.completed_orders.copy()

    def get_order_summary(self) -> dict:
        """주문 요약 정보"""
        return {
            'pending_count': len(self.pending_orders),
            'completed_count': len(self.completed_orders),
            'pending_orders': [
                {
                    'order_id': order.order_id,
                    'stock_code': order.stock_code,
                    'type': order.order_type.value,
                    'price': order.price,
                    'quantity': order.quantity,
                    'status': order.status.value,
                    'filled': order.filled_quantity
                }
                for order in self.pending_orders.values()
            ]
        }

    def stop_monitoring(self) -> None:
        """모니터링 중단"""
        self.is_monitoring = False
        self.logger.info("주문 모니터링 중단")

    def cleanup(self) -> None:
        """리소스 정리"""
        if hasattr(self, 'executor'):
            self.executor.shutdown(wait=False)

    def __del__(self) -> None:
        """소멸자"""
        self.cleanup()
