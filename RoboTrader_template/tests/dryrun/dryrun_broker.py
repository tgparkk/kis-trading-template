"""
DryRunBroker - KISBroker와 동일 인터페이스의 시뮬레이션 브로커

실제 API 호출 없이 가상 체결/잔고/보유종목을 메모리에서 관리합니다.
테스트 전용 — 실전 코드에 영향 없음.
"""
import random
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional

from framework.broker import BaseBroker, Position, AccountInfo


@dataclass
class DryRunConfig:
    """DryRun 브로커 설정"""
    initial_cash: float = 10_000_000  # 초기 자금 (1천만원)
    # 시뮬레이션 옵션
    enable_random_delay: bool = False  # 주문 체결 시 랜덤 지연
    delay_range_ms: tuple = (50, 500)  # 지연 범위 (ms)
    enable_partial_fill: bool = False  # 부분 체결 허용
    partial_fill_ratio: float = 0.6   # 부분 체결 비율
    enable_rejection: bool = False     # 주문 거부 발생
    rejection_rate: float = 0.1       # 거부 확률
    # 가격 슬리피지
    slippage_bps: int = 0             # 슬리피지 (basis points)


@dataclass
class SimulatedOrder:
    """시뮬레이션 주문"""
    order_id: str
    stock_code: str
    side: str  # "buy" | "sell"
    price: float
    quantity: int
    filled_quantity: int = 0
    filled_price: float = 0.0
    status: str = "pending"  # pending, filled, partial, cancelled, rejected
    timestamp: datetime = field(default_factory=datetime.now)
    message: str = ""


class DryRunBroker(BaseBroker):
    """
    KISBroker 호환 시뮬레이션 브로커.

    - 주문 시 가상 체결 (시장가→현재가, 지정가→지정가)
    - 잔고/보유종목 메모리 관리
    - 랜덤 지연/부분체결/거부 옵션
    """

    def __init__(self, config: Optional[DryRunConfig] = None):
        self.config = config or DryRunConfig()
        self._connected = False

        # 자금
        self._initial_cash = self.config.initial_cash
        self._available_cash = self.config.initial_cash
        self._invested_amount = 0.0

        # 보유종목: stock_code -> Position
        self._positions: Dict[str, Position] = {}

        # 가격 데이터 주입: stock_code -> price
        self._current_prices: Dict[str, float] = {}

        # 주문 이력
        self._orders: List[SimulatedOrder] = []
        self._order_map: Dict[str, SimulatedOrder] = {}

        # 체결 내역 (리포트용)
        self._trades: List[Dict[str, Any]] = []

    # ==== BaseBroker 인터페이스 ====

    async def connect(self) -> bool:
        self._connected = True
        return True

    async def disconnect(self) -> None:
        self._connected = False

    def get_account_balance(self) -> dict:
        total = self._available_cash + self._invested_amount
        return {
            'total_balance': total,
            'available_cash': self._available_cash,
            'invested_amount': self._invested_amount,
            'total_profit_loss': self._calc_total_pnl(),
            'total_profit_loss_rate': self._calc_total_pnl_rate(),
        }

    def get_holdings(self) -> List[dict]:
        result = []
        for code, pos in self._positions.items():
            cp = self._current_prices.get(code, pos.current_price)
            pos.update_price(cp)
            result.append({
                'stock_code': pos.stock_code,
                'stock_name': pos.stock_name,
                'quantity': pos.quantity,
                'avg_price': pos.avg_price,
                'current_price': pos.current_price,
                'eval_amount': pos.current_price * pos.quantity,
                'profit_loss': pos.profit_loss,
                'profit_loss_rate': pos.profit_loss_rate,
            })
        return result

    def get_available_cash(self) -> float:
        return self._available_cash

    # ==== 가격 주입 ====

    def set_price(self, stock_code: str, price: float) -> None:
        """시뮬레이션용 가격 설정"""
        self._current_prices[stock_code] = price
        if stock_code in self._positions:
            self._positions[stock_code].update_price(price)

    def set_prices(self, prices: Dict[str, float]) -> None:
        """여러 종목 가격 일괄 설정"""
        for code, price in prices.items():
            self.set_price(code, price)

    def get_current_price(self, stock_code: str) -> Optional[float]:
        return self._current_prices.get(stock_code)

    def get_current_prices(self, stock_codes: List[str]) -> Dict[str, float]:
        return {c: p for c, p in self._current_prices.items() if c in stock_codes}

    # ==== 주문 ====

    def place_buy_order(
        self,
        stock_code: str,
        quantity: int,
        price: int,
        order_type: str = "00",
    ) -> Dict[str, Any]:
        """매수 주문 (가상 체결)"""
        return self._simulate_order("buy", stock_code, quantity, float(price), order_type)

    def place_sell_order(
        self,
        stock_code: str,
        quantity: int,
        price: int,
        order_type: str = "00",
    ) -> Dict[str, Any]:
        """매도 주문 (가상 체결)"""
        return self._simulate_order("sell", stock_code, quantity, float(price), order_type)

    def cancel_order(
        self,
        order_id: str,
        stock_code: str = "",
        order_type: str = "00",
    ) -> Dict[str, Any]:
        """주문 취소"""
        order = self._order_map.get(order_id)
        if not order:
            return {"success": False, "message": "주문 없음"}
        if order.status not in ("pending", "partial"):
            return {"success": False, "message": f"취소 불가 상태: {order.status}"}

        # 미체결분 환불 (create_pending_order에서 전액 차감했으므로 미체결분 복원)
        unfilled = order.quantity - order.filled_quantity
        if order.side == "buy" and unfilled > 0:
            refund = unfilled * order.price
            self._available_cash += refund

        order.status = "cancelled"
        order.message = "취소됨"
        return {"success": True, "order_id": order_id, "message": "취소 완료"}

    def get_order_status(self, order_id: str) -> Optional[Dict[str, Any]]:
        """주문 상태 조회"""
        order = self._order_map.get(order_id)
        if not order:
            return None
        return {
            'order_id': order.order_id,
            'stock_code': order.stock_code,
            'side': order.side,
            'status': order.status,
            'quantity': order.quantity,
            'filled_quantity': order.filled_quantity,
            'filled_price': order.filled_price,
            'price': order.price,
            'message': order.message,
        }

    # ==== 미체결 조회 ====

    def get_pending_orders(self) -> List[Dict[str, Any]]:
        return [
            self.get_order_status(o.order_id)
            for o in self._orders
            if o.status in ("pending", "partial")
        ]

    def get_unfilled_orders(self) -> List[Dict[str, Any]]:
        """미체결 주문 조회 (KISBroker 호환)"""
        return self.get_pending_orders()

    # ==== 체결 내역 ====

    def get_trades(self) -> List[Dict[str, Any]]:
        """전체 체결 내역"""
        return list(self._trades)

    # ==== 내부 로직 ====

    def _simulate_order(
        self, side: str, stock_code: str, quantity: int, price: float, order_type: str
    ) -> Dict[str, Any]:
        """주문 시뮬레이션 핵심 로직"""
        order_id = f"DRY-{side.upper()}-{uuid.uuid4().hex[:8]}"

        # 거부 체크
        if self.config.enable_rejection and random.random() < self.config.rejection_rate:
            order = SimulatedOrder(
                order_id=order_id, stock_code=stock_code, side=side,
                price=price, quantity=quantity, status="rejected",
                message="주문 거부 (시뮬레이션)"
            )
            self._orders.append(order)
            self._order_map[order_id] = order
            return {"success": False, "order_id": order_id, "message": "주문 거부", "data": None}

        # 체결가 결정
        if order_type == "01":  # 시장가
            fill_price = self._current_prices.get(stock_code, price)
        else:  # 지정가
            fill_price = price

        # 슬리피지 적용
        if self.config.slippage_bps > 0:
            slip = fill_price * self.config.slippage_bps / 10000
            fill_price = fill_price + slip if side == "buy" else fill_price - slip

        # 부분 체결
        fill_qty = quantity
        status = "filled"
        if self.config.enable_partial_fill and random.random() < 0.5:
            fill_qty = max(1, int(quantity * self.config.partial_fill_ratio))
            status = "partial"

        # 자금 체크 (매수)
        if side == "buy":
            required = fill_qty * fill_price
            if required > self._available_cash:
                order = SimulatedOrder(
                    order_id=order_id, stock_code=stock_code, side=side,
                    price=price, quantity=quantity, status="rejected",
                    message="잔고 부족"
                )
                self._orders.append(order)
                self._order_map[order_id] = order
                return {"success": False, "order_id": order_id, "message": "잔고 부족", "data": None}

        # 보유 체크 (매도)
        if side == "sell":
            pos = self._positions.get(stock_code)
            if not pos or pos.quantity < fill_qty:
                order = SimulatedOrder(
                    order_id=order_id, stock_code=stock_code, side=side,
                    price=price, quantity=quantity, status="rejected",
                    message="보유 수량 부족"
                )
                self._orders.append(order)
                self._order_map[order_id] = order
                return {"success": False, "order_id": order_id, "message": "보유 수량 부족", "data": None}

        # 랜덤 지연
        if self.config.enable_random_delay:
            lo, hi = self.config.delay_range_ms
            time.sleep(random.randint(lo, hi) / 1000)

        # 체결 처리
        order = SimulatedOrder(
            order_id=order_id, stock_code=stock_code, side=side,
            price=price, quantity=quantity,
            filled_quantity=fill_qty, filled_price=fill_price,
            status=status,
            message=f"{'부분 ' if status == 'partial' else ''}체결 완료"
        )
        self._orders.append(order)
        self._order_map[order_id] = order

        # 잔고 반영
        if side == "buy":
            cost = fill_qty * fill_price
            self._available_cash -= cost
            self._invested_amount += cost
            self._update_position_buy(stock_code, fill_qty, fill_price)
        else:
            proceeds = fill_qty * fill_price
            pos = self._positions[stock_code]
            cost_basis = fill_qty * pos.avg_price
            self._invested_amount -= cost_basis
            self._available_cash += proceeds
            self._update_position_sell(stock_code, fill_qty)

        # 체결 기록
        self._trades.append({
            'order_id': order_id,
            'stock_code': stock_code,
            'side': side,
            'quantity': fill_qty,
            'price': fill_price,
            'amount': fill_qty * fill_price,
            'timestamp': datetime.now(),
        })

        return {
            "success": True,
            "order_id": order_id,
            "message": order.message,
            "data": {
                "ODNO": order_id,
                "filled_quantity": fill_qty,
                "filled_price": fill_price,
            },
        }

    def _update_position_buy(self, stock_code: str, qty: int, price: float) -> None:
        """매수 체결 → 포지션 업데이트"""
        if stock_code in self._positions:
            pos = self._positions[stock_code]
            total_cost = pos.avg_price * pos.quantity + price * qty
            total_qty = pos.quantity + qty
            pos.avg_price = total_cost / total_qty
            pos.quantity = total_qty
        else:
            self._positions[stock_code] = Position(
                stock_code=stock_code,
                stock_name=stock_code,
                quantity=qty,
                avg_price=price,
                current_price=price,
            )

    def _update_position_sell(self, stock_code: str, qty: int) -> None:
        """매도 체결 → 포지션 업데이트"""
        if stock_code not in self._positions:
            return
        pos = self._positions[stock_code]
        pos.quantity -= qty
        if pos.quantity <= 0:
            del self._positions[stock_code]

    def _calc_total_pnl(self) -> float:
        total = 0.0
        for pos in self._positions.values():
            cp = self._current_prices.get(pos.stock_code, pos.current_price)
            total += (cp - pos.avg_price) * pos.quantity
        return total

    def _calc_total_pnl_rate(self) -> float:
        if self._invested_amount <= 0:
            return 0.0
        return self._calc_total_pnl() / self._invested_amount

    # ==== 수동 체결 제어 (테스트용) ====

    def force_fill_order(self, order_id: str, fill_qty: Optional[int] = None,
                         fill_price: Optional[float] = None) -> bool:
        """수동으로 주문 체결 처리 (부분체결 테스트용)

        Note: create_pending_order가 매수 시 이미 총액을 예약(차감)했으므로
        여기서는 예약분→투자분 전환만 수행합니다.
        """
        order = self._order_map.get(order_id)
        if not order or order.status not in ("pending", "partial"):
            return False

        remaining = order.quantity - order.filled_quantity
        qty = min(fill_qty or remaining, remaining)
        price = fill_price or order.price

        if order.side == "buy":
            cost = qty * price
            # create_pending_order에서 이미 available에서 차감됨 → invested로 이동만
            self._invested_amount += cost
            self._update_position_buy(order.stock_code, qty, price)
        else:
            pos = self._positions.get(order.stock_code)
            if not pos or pos.quantity < qty:
                return False
            proceeds = qty * price
            cost_basis = qty * pos.avg_price
            self._invested_amount -= cost_basis
            self._available_cash += proceeds
            self._update_position_sell(order.stock_code, qty)

        order.filled_quantity += qty
        order.filled_price = price
        if order.filled_quantity >= order.quantity:
            order.status = "filled"
        else:
            order.status = "partial"

        self._trades.append({
            'order_id': order_id,
            'stock_code': order.stock_code,
            'side': order.side,
            'quantity': qty,
            'price': price,
            'amount': qty * price,
            'timestamp': datetime.now(),
        })
        return True

    def create_pending_order(self, side: str, stock_code: str,
                             quantity: int, price: float) -> str:
        """체결되지 않는 대기 주문 생성 (수동 체결 테스트용)"""
        order_id = f"DRY-{side.upper()}-{uuid.uuid4().hex[:8]}"
        order = SimulatedOrder(
            order_id=order_id, stock_code=stock_code, side=side,
            price=price, quantity=quantity, status="pending",
        )
        self._orders.append(order)
        self._order_map[order_id] = order

        if side == "buy":
            cost = quantity * price
            self._available_cash -= cost  # 예약

        return order_id

    # ==== 리셋 ====

    def reset(self) -> None:
        """전체 상태 초기화"""
        self._available_cash = self._initial_cash
        self._invested_amount = 0.0
        self._positions.clear()
        self._current_prices.clear()
        self._orders.clear()
        self._order_map.clear()
        self._trades.clear()
