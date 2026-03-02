"""
주문 DB 저장 처리 모듈
- 실전 매매 거래 기록 DB 저장
"""
from typing import TYPE_CHECKING

from ..models import OrderType

if TYPE_CHECKING:
    from .order_base import OrderManagerBase


class OrderDBHandlerMixin:
    """주문 DB 저장 관련 메서드들을 모아둔 Mixin 클래스"""

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
        buy_record_id = self.db_manager.save_real_buy(
            stock_code=order.stock_code,
            stock_name=stock_name,
            price=filled_price,  # 실제 체결가 사용
            quantity=order.quantity,
            strategy="리밸런싱",
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
        success = self.db_manager.save_real_sell(
            stock_code=order.stock_code,
            stock_name=stock_name,
            price=filled_price,  # 실제 체결가 사용
            quantity=order.quantity,
            strategy="리밸런싱",
            reason="실전매매",
            buy_record_id=buy_record_id
        )
        if success:
            self.logger.info(f"실전 매도 기록 저장: {order.stock_code} {order.quantity}주 @{filled_price:,.0f}원")
        else:
            self.logger.error(f"실전 매도 기록 저장 실패: {order.stock_code}")
