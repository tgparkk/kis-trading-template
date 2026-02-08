"""
종목 거래 상태 통합 관리 모듈

이 모듈은 Facade 패턴을 적용하여 여러 하위 모듈을 통합합니다.
기존 인터페이스(public 메서드, 클래스명)는 완전히 유지됩니다.

하위 모듈:
- trading/stock_state_manager.py: 종목 상태 관리
- trading/order_execution.py: 매수/매도 주문 실행
- trading/order_completion_handler.py: 주문 체결 확인
- trading/position_monitor.py: 포지션 모니터링
"""
from typing import Dict, List, Optional, Any

from .models import TradingStock, StockState
from .intraday_stock_manager import IntradayStockManager
from .data_collector import RealTimeDataCollector
from .order_manager import OrderManager
from .trading import (
    StockStateManager,
    OrderExecution,
    OrderCompletionHandler,
    PositionMonitor,
)
from utils.logger import setup_logger


class TradingStockManager:
    """
    종목 거래 상태 통합 관리자 (Facade)

    주요 기능:
    1. 종목별 거래 상태 통합 관리
    2. 상태 변화에 따른 자동 처리
    3. 매수/매도 후보 관리
    4. 포지션 및 주문 상태 동기화
    5. 리스크 관리 및 모니터링

    내부적으로 다음 모듈에 기능을 위임:
    - StockStateManager: 종목 상태 관리
    - OrderExecution: 매수/매도 주문 실행
    - OrderCompletionHandler: 주문 체결 확인
    - PositionMonitor: 포지션 모니터링
    """

    def __init__(self, intraday_manager: IntradayStockManager,
                 data_collector: RealTimeDataCollector,
                 order_manager: OrderManager,
                 telegram_integration=None):
        """
        초기화

        Args:
            intraday_manager: 장중 종목 관리자
            data_collector: 실시간 데이터 수집기
            order_manager: 주문 관리자
            telegram_integration: 텔레그램 알림 (선택)
        """
        self.intraday_manager = intraday_manager
        self.data_collector = data_collector
        self.order_manager = order_manager
        self.telegram = telegram_integration
        self.logger = setup_logger(__name__)

        # 하위 모듈 초기화
        self._state_manager = StockStateManager()
        self._order_execution = OrderExecution(
            self._state_manager,
            intraday_manager,
            data_collector,
            order_manager
        )
        self._completion_handler = OrderCompletionHandler(
            self._state_manager,
            order_manager
        )
        self._position_monitor = PositionMonitor(
            self._state_manager,
            self._completion_handler,
            intraday_manager,
            data_collector
        )

        # decision_engine은 나중에 설정됨 (순환 참조 방지)
        self.decision_engine = None

        # 전략은 나중에 set_strategy로 설정됨
        self._strategy = None

        self.logger.info("종목 거래 상태 통합 관리자 초기화 완료")

        # 주문 관리자에 역참조 등록 (정정 시 주문ID 동기화용)
        try:
            if hasattr(self.order_manager, 'set_trading_manager'):
                self.order_manager.set_trading_manager(self)
        except Exception as e:
            self.logger.debug(f"주문 관리자 역참조 등록 실패: {e}")

    # =========================================================================
    # 프로퍼티: 하위 호환성을 위한 직접 접근
    # =========================================================================

    @property
    def trading_stocks(self) -> Dict[str, TradingStock]:
        """종목 상태 딕셔너리 (하위 호환성)"""
        return self._state_manager.trading_stocks

    @property
    def stocks_by_state(self) -> Dict[StockState, Dict[str, TradingStock]]:
        """상태별 종목 딕셔너리 (하위 호환성)"""
        return self._state_manager.stocks_by_state

    @property
    def _lock(self):
        """Lock 객체 (하위 호환성)"""
        return self._state_manager.lock

    @property
    def is_monitoring(self) -> bool:
        """모니터링 상태"""
        return self._position_monitor.is_monitoring

    @is_monitoring.setter
    def is_monitoring(self, value: bool):
        """모니터링 상태 설정"""
        self._position_monitor.is_monitoring = value

    @property
    def monitor_interval(self) -> int:
        """모니터링 간격"""
        return self._position_monitor.monitor_interval

    @monitor_interval.setter
    def monitor_interval(self, value: int):
        """모니터링 간격 설정"""
        self._position_monitor.monitor_interval = value

    @property
    def enable_re_trading(self) -> bool:
        """재거래 활성화 여부"""
        return self._order_execution.enable_re_trading

    @enable_re_trading.setter
    def enable_re_trading(self, value: bool):
        """재거래 활성화 설정"""
        self._order_execution.enable_re_trading = value
        self._completion_handler.enable_re_trading = value

    # =========================================================================
    # decision_engine 설정
    # =========================================================================

    def set_decision_engine(self, decision_engine):
        """매매 판단 엔진 설정 (순환 참조 방지를 위해 별도 메서드)"""
        self.decision_engine = decision_engine
        self._position_monitor.set_decision_engine(decision_engine)
        self.logger.debug("TradingStockManager에 decision_engine 연결 완료")

    def set_strategy(self, strategy):
        """전략 연결 (on_order_filled 콜백 + 매도 시그널 전달용)"""
        self._strategy = strategy
        self._completion_handler.set_strategy(strategy)
        self._position_monitor.set_strategy(strategy)
        self.logger.debug(f"TradingStockManager에 전략 연결: {strategy.name if strategy else 'None'}")

    # =========================================================================
    # 종목 선정 및 주문 실행 (OrderExecution에 위임)
    # =========================================================================

    async def add_selected_stock(self, stock_code: str, stock_name: str,
                                 selection_reason: str = "", prev_close: float = 0.0) -> bool:
        """
        조건검색으로 선정된 종목 추가 (비동기)

        Args:
            stock_code: 종목코드
            stock_name: 종목명
            selection_reason: 선정 사유
            prev_close: 전날 종가 (일봉 기준)

        Returns:
            bool: 추가 성공 여부
        """
        return await self._order_execution.add_selected_stock(
            stock_code, stock_name, selection_reason, prev_close
        )

    async def execute_buy_order(self, stock_code: str, quantity: int,
                                price: float, reason: str = "") -> bool:
        """
        매수 주문 실행

        Args:
            stock_code: 종목코드
            quantity: 주문 수량
            price: 주문 가격
            reason: 매수 사유

        Returns:
            bool: 주문 성공 여부
        """
        return await self._order_execution.execute_buy_order(
            stock_code, quantity, price, reason
        )

    def move_to_sell_candidate(self, stock_code: str, reason: str = "") -> bool:
        """
        포지션 종목을 매도 후보로 변경

        Args:
            stock_code: 종목코드
            reason: 변경 사유

        Returns:
            bool: 변경 성공 여부
        """
        return self._order_execution.move_to_sell_candidate(stock_code, reason)

    async def execute_sell_order(self, stock_code: str, quantity: int,
                                 price: float, reason: str = "", market: bool = False) -> bool:
        """
        매도 주문 실행

        Args:
            stock_code: 종목코드
            quantity: 주문 수량
            price: 주문 가격
            reason: 매도 사유
            market: 시장가 주문 여부

        Returns:
            bool: 주문 성공 여부
        """
        return await self._order_execution.execute_sell_order(
            stock_code, quantity, price, reason, market
        )

    def remove_stock(self, stock_code: str, reason: str = "") -> bool:
        """
        종목 제거

        Args:
            stock_code: 종목코드
            reason: 제거 사유

        Returns:
            bool: 제거 성공 여부
        """
        return self._order_execution.remove_stock(stock_code, reason)

    async def handle_order_timeout(self, order) -> None:
        """
        OrderManager에서 타임아웃/취소된 주문 처리

        Args:
            order: 타임아웃된 주문 객체 (Order)
        """
        await self._order_execution.handle_order_timeout(order)

    def set_re_trading_config(self, enable: bool):
        """
        재거래 설정 변경

        Args:
            enable: 재거래 활성화 여부 (COMPLETED 상태에서 직접 매수 판단)
        """
        self._order_execution.set_re_trading_config(enable)
        self._completion_handler.enable_re_trading = enable

        status = "활성화" if enable else "비활성화"
        self.logger.info(f"재거래 설정 변경: {status} (즉시 재거래 방식)")

    def get_re_trading_config(self) -> Dict[str, Any]:
        """재거래 설정 조회"""
        return self._order_execution.get_re_trading_config()

    # =========================================================================
    # 모니터링 (PositionMonitor에 위임)
    # =========================================================================

    async def check_positions_once(self):
        """보유종목 1회 체크 (메인루프용)"""
        await self._position_monitor.check_positions_once()

    async def start_monitoring(self):
        """종목 상태 모니터링 시작"""
        await self._position_monitor.start_monitoring()

    def stop_monitoring(self):
        """모니터링 중단"""
        self._position_monitor.stop_monitoring()

    # =========================================================================
    # 주문 체결 확인 (OrderCompletionHandler에 위임)
    # =========================================================================

    async def on_order_filled(self, order):
        """주문 체결 시 즉시 호출되는 콜백 메서드"""
        await self._completion_handler.on_order_filled(order)

    # =========================================================================
    # 종목 상태 조회 (StockStateManager에 위임)
    # =========================================================================

    def get_stocks_by_state(self, state: StockState) -> List[TradingStock]:
        """특정 상태의 종목들 조회"""
        return self._state_manager.get_stocks_by_state(state)

    def get_trading_stock(self, stock_code: str) -> Optional[TradingStock]:
        """종목 정보 조회"""
        return self._state_manager.get_trading_stock(stock_code)

    def update_current_order(self, stock_code: str, new_order_id: str) -> None:
        """정정 등으로 새 주문이 생성되었을 때 현재 주문ID를 최신값으로 동기화"""
        self._state_manager.update_current_order(stock_code, new_order_id)

    def get_portfolio_summary(self) -> Dict[str, Any]:
        """포트폴리오 전체 현황"""
        return self._state_manager.get_portfolio_summary()

    # =========================================================================
    # 내부 메서드 (하위 호환성을 위해 유지)
    # =========================================================================

    def _register_stock(self, trading_stock: TradingStock):
        """종목 등록 (하위 호환성)"""
        self._state_manager.register_stock(trading_stock)

    def _unregister_stock(self, stock_code: str):
        """종목 등록 해제 (하위 호환성)"""
        self._state_manager.unregister_stock(stock_code)

    def _change_stock_state(self, stock_code: str, new_state: StockState, reason: str = ""):
        """종목 상태 변경 (하위 호환성)"""
        self._state_manager.change_stock_state(stock_code, new_state, reason)
