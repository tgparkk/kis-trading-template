"""
주문 DB 저장 처리 모듈
- 실전 매매 거래 기록 DB 저장
"""
import inspect
from typing import TYPE_CHECKING

from ..models import OrderType

if TYPE_CHECKING:
    from .order_base import OrderManagerBase


class OrderDBHandlerMixin:
    """주문 DB 저장 관련 메서드들을 모아둔 Mixin 클래스"""

    def _get_strategy_name_for_order(self: 'OrderManagerBase', stock_code: str) -> str:
        """주문 DB 저장 시 순수 전략 이름 조회

        우선순위:
        1. trading_stock.strategy_name (직접 설정된 전략명)
        2. "unknown" + WARNING (다전략 환경에서 strategy_name 미설정 시 오귀속 방지)

        Note: config.strategy.name fallback은 단일 전략 환경에서만 의미가 있어
              다전략 환경에서 잘못된 전략으로 기록될 수 있으므로 제거.
        """
        # 1. TradingStock에 직접 설정된 전략명
        if self.trading_manager and hasattr(self.trading_manager, 'get_trading_stock'):
            try:
                ts = self.trading_manager.get_trading_stock(stock_code)
                # AsyncMock 등에서 coroutine이 반환될 수 있으므로 방어
                if inspect.iscoroutine(ts):
                    ts.close()  # 코루틴 GC 경고 방지
                    ts = None
                if ts and hasattr(ts, 'strategy_name') and ts.strategy_name:
                    return ts.strategy_name
            except Exception:
                pass

        # 2. strategy_name 미설정 — 다전략 환경에서 오귀속 위험
        self.logger.warning(
            f"[{stock_code}] trading_stock.strategy_name 미설정. "
            f"DB 기록을 'unknown'으로 저장. 다전략 환경에서는 strategy_name을 명시적으로 설정하세요."
        )
        return "unknown"

    async def _save_real_trade_to_db(self: 'OrderManagerBase', order, filled_price: float) -> None:
        """
        실전 매매 시 DB에 거래 기록 저장

        Args:
            order: 체결된 Order 객체
            filled_price: 실제 체결가
        """
        try:
            # 가상매매 모드면 이미 저장됨 (place_buy_order/place_sell_order에서 처리)
            if getattr(self.config, "paper_trading", True):
                return

            if not self.db_manager:
                self.logger.warning("DB 매니저가 없어 실전 거래 기록을 저장할 수 없음")
                return

            stock_name = order.stock_name or f'Stock_{order.stock_code}'

            if order.order_type == OrderType.BUY:
                await self._save_real_buy_to_db(order, filled_price, stock_name)
            elif order.order_type == OrderType.SELL:
                await self._save_real_sell_to_db(order, filled_price, stock_name)

        except Exception as e:
            self.logger.error(f"실전 거래 DB 저장 오류: {e}")

    async def _save_real_buy_to_db(self: 'OrderManagerBase', order, filled_price: float, stock_name: str) -> None:
        """실전 매수 기록 DB 저장"""
        strategy_name = self._get_strategy_name_for_order(order.stock_code)
        buy_record_id = self.db_manager.save_real_buy(
            stock_code=order.stock_code,
            stock_name=stock_name,
            price=filled_price,  # 실제 체결가 사용
            quantity=order.quantity,
            strategy=strategy_name,
            reason="실전매매"
        )
        if buy_record_id:
            self.logger.info(f"실전 매수 기록 저장: {order.stock_code} {order.quantity}주 @{filled_price:,.0f}원 (ID: {buy_record_id})")
        else:
            self.logger.error(f"실전 매수 기록 저장 실패: {order.stock_code}")

    async def _save_real_sell_to_db(self: 'OrderManagerBase', order, filled_price: float, stock_name: str) -> None:
        """실전 매도 기록 DB 저장"""
        # 매수 기록 ID 조회
        buy_record_id = None
        if self.trading_manager:
            trading_stock = self.trading_manager.get_trading_stock(order.stock_code)
            if trading_stock and hasattr(trading_stock, '_virtual_buy_record_id'):
                buy_record_id = trading_stock._virtual_buy_record_id

        # buy_record_id가 없으면 DB에서 조회
        if not buy_record_id:
            buy_record_id = self.db_manager.get_last_open_real_buy(order.stock_code)

        # 실전 매도 기록 저장
        strategy_name = self._get_strategy_name_for_order(order.stock_code)
        success = self.db_manager.save_real_sell(
            stock_code=order.stock_code,
            stock_name=stock_name,
            price=filled_price,  # 실제 체결가 사용
            quantity=order.quantity,
            strategy=strategy_name,
            reason="실전매매",
            buy_record_id=buy_record_id
        )
        if success:
            self.logger.info(f"실전 매도 기록 저장: {order.stock_code} {order.quantity}주 @{filled_price:,.0f}원")
        else:
            self.logger.error(f"실전 매도 기록 저장 실패: {order.stock_code}")
