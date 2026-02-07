"""
주문 Mock 모듈
실제 주문 API 호출 없이 로그만 기록합니다.
"""
from utils.logger import setup_logger


class MockOrderManager:
    """주문을 실행하지 않고 로그만 기록하는 Mock"""

    def __init__(self):
        self.logger = setup_logger("dryrun.mock_order")
        self.buy_orders = []
        self.sell_orders = []

    async def place_buy_order(self, stock_code: str, quantity: int, price: float, **kwargs):
        """매수 주문 시뮬레이션"""
        order_id = f"DRY-BUY-{stock_code}-{len(self.buy_orders) + 1}"
        order_info = {
            'order_id': order_id,
            'stock_code': stock_code,
            'quantity': quantity,
            'price': price,
            'total': quantity * price,
        }
        self.buy_orders.append(order_info)
        self.logger.info(f"[DRY] 매수: {stock_code} {quantity}주 @{price:,.0f}원 "
                        f"(합계: {quantity * price:,.0f}원)")
        return order_id

    async def place_sell_order(self, stock_code: str, quantity: int, price: float, **kwargs):
        """매도 주문 시뮬레이션"""
        order_id = f"DRY-SELL-{stock_code}-{len(self.sell_orders) + 1}"
        order_info = {
            'order_id': order_id,
            'stock_code': stock_code,
            'quantity': quantity,
            'price': price,
        }
        self.sell_orders.append(order_info)
        self.logger.info(f"[DRY] 매도: {stock_code} {quantity}주 @{price:,.0f}원")
        return order_id

    def get_summary(self):
        """주문 요약"""
        total_buy = sum(o['total'] for o in self.buy_orders)
        return {
            'buy_count': len(self.buy_orders),
            'sell_count': len(self.sell_orders),
            'total_buy_amount': total_buy,
            'buy_orders': self.buy_orders,
            'sell_orders': self.sell_orders,
        }
