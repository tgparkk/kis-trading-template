"""
주문 관리 및 미체결 처리 모듈

이 파일은 하위 호환성을 위한 Facade 패턴으로 구현되었습니다.
실제 구현은 core/orders/ 서브모듈에 분리되어 있습니다.

모듈 구조:
- orders/order_base.py: 기본 클래스 및 유틸리티 (OrderManagerBase)
- orders/order_executor.py: 주문 실행 로직 (OrderExecutorMixin)
- orders/order_monitor.py: 미체결 모니터링 로직 (OrderMonitorMixin)
- orders/order_timeout.py: 타임아웃 처리 로직 (OrderTimeoutMixin)
- orders/order_db_handler.py: DB 저장 처리 로직 (OrderDBHandlerMixin)
"""
from typing import TYPE_CHECKING

from .orders.order_base import OrderManagerBase
from .orders.order_executor import OrderExecutorMixin
from .orders.order_monitor import OrderMonitorMixin
from .orders.order_timeout import OrderTimeoutMixin
from .orders.order_db_handler import OrderDBHandlerMixin

if TYPE_CHECKING:
    from .models import TradingConfig
    from framework import KISBroker


class OrderManager(
    OrderManagerBase,
    OrderExecutorMixin,
    OrderMonitorMixin,
    OrderTimeoutMixin,
    OrderDBHandlerMixin
):
    """
    주문 관리자 (Facade 클래스)

    모든 주문 관련 기능을 통합하여 제공합니다.
    기존 인터페이스와 완전히 호환됩니다.

    주요 기능:
    - 매수/매도 주문 실행 (place_buy_order, place_sell_order)
    - 주문 취소 (cancel_order)
    - 미체결 주문 모니터링 (start_monitoring, stop_monitoring)
    - 주문 상태 조회 (get_pending_orders, get_completed_orders, get_order_summary)

    사용 예:
        >>> from core.order_manager import OrderManager
        >>> order_mgr = OrderManager(config, api_manager, telegram, db_manager)
        >>> order_id = await order_mgr.place_buy_order("005930", 10, 70000)
        >>> await order_mgr.start_monitoring()
    """

    def __init__(self, config: 'TradingConfig', broker: 'KISBroker',
                 telegram_integration=None, db_manager=None) -> None:
        """
        주문 관리자 초기화

        Args:
            config: 트레이딩 설정 객체
            broker: KISBroker 인스턴스
            telegram_integration: 텔레그램 알림 통합 (선택)
            db_manager: 데이터베이스 매니저 (선택)
        """
        # 부모 클래스 초기화 (OrderManagerBase)
        super().__init__(config, broker, telegram_integration, db_manager)

    # ==================== Public API (기존 인터페이스 유지) ====================
    # 모든 메서드는 Mixin 클래스에서 상속받습니다.
    #
    # OrderExecutorMixin:
    #   - place_buy_order(stock_code, quantity, price, timeout_seconds, target_profit_rate, stop_loss_rate)
    #   - place_sell_order(stock_code, quantity, price, timeout_seconds, market, force)
    #   - cancel_order(order_id)
    #
    # OrderMonitorMixin:
    #   - start_monitoring()
    #   - _monitor_pending_orders()
    #   - _check_order_status(order_id)
    #   - _check_false_positive_filled_orders(current_time)
    #   - _restore_false_positive_order(order, current_time)
    #
    # OrderTimeoutMixin:
    #   - _handle_timeout(order_id)
    #   - _handle_4candle_timeout(order_id)
    #
    # OrderDBHandlerMixin:
    #   - _save_real_trade_to_db(order, filled_price)
    #
    # OrderManagerBase:
    #   - set_trading_manager(trading_manager)
    #   - get_pending_orders()
    #   - get_completed_orders()
    #   - get_order_summary()
    #   - stop_monitoring()
    #   - _get_current_3min_candle_time()
    #   - _has_4_candles_passed(order_candle_time)
    #   - _move_to_completed(order_id)


# 하위 호환성을 위한 re-export
__all__ = ['OrderManager']
