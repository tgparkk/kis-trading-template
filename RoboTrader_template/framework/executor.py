"""
Order Executor Module
=====================

Order execution for KIS API:
- Buy orders (market/limit)
- Sell orders (market/limit)
- Order modification
- Order cancellation
- Order status tracking
- Async support for concurrent operations
"""

import asyncio
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from typing import Optional, Dict, List, Any, TYPE_CHECKING
from enum import Enum
from datetime import datetime

from .utils import setup_logger, round_to_tick, now_kst

if TYPE_CHECKING:
    from .broker import KISBroker


# ============================================================================
# Enums and Data Classes
# ============================================================================

class OrderType(Enum):
    """Order type enumeration."""
    MARKET = "market"   # Market order (KIS: 01)
    LIMIT = "limit"     # Limit order (KIS: 00)

    def to_kis_code(self) -> str:
        """Convert to KIS API order division code."""
        return "01" if self == OrderType.MARKET else "00"


class OrderSide(Enum):
    """Order side enumeration."""
    BUY = "buy"
    SELL = "sell"


class OrderStatus(Enum):
    """Order status enumeration."""
    PENDING = "pending"       # Order submitted
    PARTIAL = "partial"       # Partially filled
    FILLED = "filled"         # Fully filled
    CANCELLED = "cancelled"   # Cancelled
    REJECTED = "rejected"     # Rejected by exchange
    EXPIRED = "expired"       # Order expired


@dataclass
class OrderRequest:
    """
    Order request data.

    Attributes:
        stock_code: Stock ticker (6 digits)
        side: Buy or Sell
        quantity: Number of shares
        order_type: MARKET or LIMIT
        price: Order price (optional for market orders)
    """
    stock_code: str
    side: OrderSide
    quantity: int
    order_type: OrderType = OrderType.MARKET
    price: Optional[float] = None

    def __post_init__(self):
        """Validate order request."""
        if self.quantity <= 0:
            raise ValueError(f"Invalid quantity: {self.quantity}")

        if self.order_type == OrderType.LIMIT:
            if self.price is None or self.price <= 0:
                raise ValueError(f"Limit order requires valid price: {self.price}")
            # Round to tick size
            self.price = float(round_to_tick(self.price))


@dataclass
class OrderResult:
    """
    Order execution result.

    Attributes:
        success: Whether order was successful
        order_id: Order identifier (if successful)
        message: Status message or error description
        filled_quantity: Number of shares filled
        filled_price: Average fill price
    """
    success: bool
    order_id: Optional[str] = None
    message: str = ""
    filled_quantity: int = 0
    filled_price: float = 0.0


@dataclass
class Order:
    """
    Order information.

    Attributes:
        order_id: Unique order identifier
        stock_code: Stock ticker (6 digits)
        side: Buy or Sell
        order_type: Market or Limit
        quantity: Order quantity
        price: Order price (0 for market orders)
        status: Current order status
        filled_quantity: Quantity filled so far
        filled_price: Average fill price
        created_at: Order creation time
        updated_at: Last update time
        org_order_no: Original order number (for KIS API)
        order_no: KIS order number
    """
    order_id: str
    stock_code: str
    side: OrderSide
    order_type: OrderType
    quantity: int
    price: float
    status: OrderStatus = OrderStatus.PENDING
    filled_quantity: int = 0
    filled_price: float = 0.0
    created_at: datetime = field(default_factory=now_kst)
    updated_at: datetime = field(default_factory=now_kst)
    org_order_no: str = ""
    order_no: str = ""

    @property
    def is_completed(self) -> bool:
        """Check if order is in a terminal state."""
        return self.status in (
            OrderStatus.FILLED,
            OrderStatus.CANCELLED,
            OrderStatus.REJECTED,
            OrderStatus.EXPIRED
        )

    @property
    def remaining_quantity(self) -> int:
        """Get remaining unfilled quantity."""
        return self.quantity - self.filled_quantity

    @property
    def fill_rate(self) -> float:
        """Get fill rate as percentage."""
        if self.quantity > 0:
            return self.filled_quantity / self.quantity
        return 0.0


# ============================================================================
# Order Executor
# ============================================================================

class OrderExecutor:
    """
    Order execution handler with async support.

    Manages order lifecycle:
    - Submit buy/sell orders
    - Track order status
    - Handle order modifications and cancellations
    - Async operations for non-blocking execution

    Usage:
        executor = OrderExecutor(broker)
        result = await executor.execute(OrderRequest(...))
        await executor.cancel(order_id)
    """

    def __init__(self, broker: 'KISBroker'):
        """
        Initialize order executor.

        Args:
            broker: Broker instance for API calls
        """
        self.broker = broker
        self.logger = setup_logger(__name__)

        # Order tracking
        self._orders: Dict[str, Order] = {}
        self._order_counter = 0

        # Thread pool for blocking API calls
        self._executor = ThreadPoolExecutor(max_workers=4)

    # ========================================================================
    # Public Async Methods
    # ========================================================================

    async def execute(self, order: OrderRequest) -> OrderResult:
        """
        Execute an order asynchronously.

        Args:
            order: OrderRequest with order details

        Returns:
            OrderResult: Execution result with order_id if successful
        """
        try:
            # Validate and prepare price
            price = order.price or 0
            if order.order_type == OrderType.LIMIT:
                if price <= 0:
                    return OrderResult(
                        success=False,
                        message="Limit order requires valid price"
                    )
                price = round_to_tick(price)

            # Generate order ID
            self._order_counter += 1
            order_id = f"ORD{now_kst().strftime('%Y%m%d%H%M%S')}{self._order_counter:04d}"

            # Create internal order object
            internal_order = Order(
                order_id=order_id,
                stock_code=order.stock_code,
                side=order.side,
                order_type=order.order_type,
                quantity=order.quantity,
                price=price
            )

            # Submit to KIS API (blocking call in thread pool)
            loop = asyncio.get_event_loop()
            api_result = await loop.run_in_executor(
                self._executor,
                self._call_kis_order,
                internal_order
            )

            if api_result:
                internal_order.order_no = api_result.get('order_no', '')
                internal_order.org_order_no = api_result.get('org_order_no', '')
                self._orders[order_id] = internal_order

                self.logger.info(
                    f"Order executed: {order_id} {order.side.value} {order.stock_code} "
                    f"{order.quantity}x @{price:,.0f} ({order.order_type.value})"
                )

                return OrderResult(
                    success=True,
                    order_id=order_id,
                    message="Order submitted successfully"
                )
            else:
                return OrderResult(
                    success=False,
                    message="Order submission failed"
                )

        except Exception as e:
            self.logger.error(f"Order execution error: {e}")
            return OrderResult(
                success=False,
                message=str(e)
            )

    async def cancel(self, order_id: str) -> bool:
        """
        Cancel an order asynchronously.

        Args:
            order_id: Order identifier

        Returns:
            bool: True if cancellation successful
        """
        order = self._orders.get(order_id)

        if not order:
            self.logger.error(f"Order not found: {order_id}")
            return False

        if order.is_completed:
            self.logger.warning(f"Cannot cancel completed order: {order_id}")
            return False

        try:
            loop = asyncio.get_event_loop()
            result = await loop.run_in_executor(
                self._executor,
                self._call_kis_cancel,
                order
            )

            if result:
                order.status = OrderStatus.CANCELLED
                order.updated_at = now_kst()
                self.logger.info(f"Order cancelled: {order_id}")
                return True

            return False

        except Exception as e:
            self.logger.error(f"Cancel error: {e}")
            return False

    async def modify(self, order_id: str, new_price: float) -> bool:
        """
        Modify an order's price asynchronously.

        Args:
            order_id: Order identifier
            new_price: New price for the order

        Returns:
            bool: True if modification successful
        """
        order = self._orders.get(order_id)

        if not order:
            self.logger.error(f"Order not found: {order_id}")
            return False

        if order.is_completed:
            self.logger.warning(f"Cannot modify completed order: {order_id}")
            return False

        try:
            # Round to tick size
            adjusted_price = round_to_tick(new_price)

            loop = asyncio.get_event_loop()
            result = await loop.run_in_executor(
                self._executor,
                self._call_kis_modify,
                order,
                adjusted_price,
                order.remaining_quantity
            )

            if result:
                order.price = adjusted_price
                order.updated_at = now_kst()
                self.logger.info(
                    f"Order modified: {order_id} -> price={adjusted_price:,.0f}"
                )
                return True

            return False

        except Exception as e:
            self.logger.error(f"Modify error: {e}")
            return False

    async def get_order_status(self, order_id: str) -> dict:
        """
        Get order status asynchronously.

        Args:
            order_id: Order identifier

        Returns:
            dict: Order status information
        """
        order = self._orders.get(order_id)

        if not order:
            return {'error': 'Order not found'}

        try:
            # Fetch latest status from API
            loop = asyncio.get_event_loop()
            api_status = await loop.run_in_executor(
                self._executor,
                self._call_kis_order_status,
                order
            )

            # Update order with API response
            if api_status:
                filled_qty = api_status.get('filled_quantity', order.filled_quantity)
                filled_price = api_status.get('filled_price', order.filled_price)
                is_cancelled = api_status.get('cancelled', False)

                order.filled_quantity = filled_qty
                order.filled_price = filled_price
                order.updated_at = now_kst()

                # Update status based on fill
                if is_cancelled:
                    order.status = OrderStatus.CANCELLED
                elif filled_qty >= order.quantity:
                    order.status = OrderStatus.FILLED
                elif filled_qty > 0:
                    order.status = OrderStatus.PARTIAL

            return {
                'order_id': order.order_id,
                'stock_code': order.stock_code,
                'side': order.side.value,
                'order_type': order.order_type.value,
                'quantity': order.quantity,
                'price': order.price,
                'status': order.status.value,
                'filled_quantity': order.filled_quantity,
                'filled_price': order.filled_price,
                'remaining_quantity': order.remaining_quantity,
                'created_at': order.created_at.isoformat(),
                'updated_at': order.updated_at.isoformat()
            }

        except Exception as e:
            self.logger.error(f"Get order status error: {e}")
            return {
                'order_id': order.order_id,
                'status': order.status.value,
                'error': str(e)
            }

    async def get_pending_orders(self) -> List[dict]:
        """
        Get all pending (non-completed) orders asynchronously.

        Returns:
            List[dict]: List of pending order information
        """
        try:
            # Optionally refresh from API
            loop = asyncio.get_event_loop()
            api_pending = await loop.run_in_executor(
                self._executor,
                self._call_kis_pending_orders
            )

            # Update local orders with API data
            if api_pending:
                for api_order in api_pending:
                    order_no = api_order.get('order_no', '')
                    for order in self._orders.values():
                        if order.order_no == order_no:
                            order.filled_quantity = api_order.get('filled_qty', 0)
                            remaining = api_order.get('remaining_qty', order.remaining_quantity)
                            if remaining == 0 and order.quantity > 0:
                                order.status = OrderStatus.FILLED
                            elif order.filled_quantity > 0:
                                order.status = OrderStatus.PARTIAL
                            order.updated_at = now_kst()

            # Return pending orders
            pending = [
                {
                    'order_id': order.order_id,
                    'stock_code': order.stock_code,
                    'side': order.side.value,
                    'order_type': order.order_type.value,
                    'quantity': order.quantity,
                    'price': order.price,
                    'status': order.status.value,
                    'filled_quantity': order.filled_quantity,
                    'remaining_quantity': order.remaining_quantity,
                    'created_at': order.created_at.isoformat()
                }
                for order in self._orders.values()
                if not order.is_completed
            ]

            return pending

        except Exception as e:
            self.logger.error(f"Get pending orders error: {e}")
            return []

    # ========================================================================
    # Synchronous Convenience Methods
    # ========================================================================

    def buy(
        self,
        stock_code: str,
        quantity: int,
        price: float = 0,
        order_type: OrderType = OrderType.LIMIT
    ) -> Optional[Order]:
        """
        Submit a buy order (synchronous).

        Args:
            stock_code: Stock ticker
            quantity: Number of shares to buy
            price: Order price (0 for market order)
            order_type: LIMIT or MARKET

        Returns:
            Order: Order object or None if failed
        """
        return self._submit_order(
            stock_code=stock_code,
            side=OrderSide.BUY,
            quantity=quantity,
            price=price,
            order_type=order_type
        )

    def sell(
        self,
        stock_code: str,
        quantity: int,
        price: float = 0,
        order_type: OrderType = OrderType.LIMIT
    ) -> Optional[Order]:
        """
        Submit a sell order (synchronous).

        Args:
            stock_code: Stock ticker
            quantity: Number of shares to sell
            price: Order price (0 for market order)
            order_type: LIMIT or MARKET

        Returns:
            Order: Order object or None if failed
        """
        return self._submit_order(
            stock_code=stock_code,
            side=OrderSide.SELL,
            quantity=quantity,
            price=price,
            order_type=order_type
        )

    def _submit_order(
        self,
        stock_code: str,
        side: OrderSide,
        quantity: int,
        price: float,
        order_type: OrderType
    ) -> Optional[Order]:
        """
        Internal synchronous order submission.

        Args:
            stock_code: Stock ticker
            side: BUY or SELL
            quantity: Number of shares
            price: Order price
            order_type: LIMIT or MARKET

        Returns:
            Order: Submitted order or None if failed
        """
        try:
            # Validate quantity
            if quantity <= 0:
                self.logger.error(f"Invalid quantity: {quantity}")
                return None

            # Validate price for limit orders
            if order_type == OrderType.LIMIT:
                if price <= 0:
                    self.logger.error(f"Invalid price for limit order: {price}")
                    return None
                # Round to tick size
                price = round_to_tick(price)

            # Generate order ID
            self._order_counter += 1
            order_id = f"ORD{now_kst().strftime('%Y%m%d%H%M%S')}{self._order_counter:04d}"

            # Create order object
            order = Order(
                order_id=order_id,
                stock_code=stock_code,
                side=side,
                order_type=order_type,
                quantity=quantity,
                price=price
            )

            # Submit to KIS API
            result = self._call_kis_order(order)

            if result:
                order.order_no = result.get('order_no', '')
                order.org_order_no = result.get('org_order_no', '')
                self._orders[order_id] = order

                self.logger.info(
                    f"Order submitted: {order_id} {side.value} {stock_code} "
                    f"{quantity}x @{price:,.0f} ({order_type.value})"
                )

                return order
            else:
                self.logger.error(f"Order submission failed: {stock_code}")
                return None

        except Exception as e:
            self.logger.error(f"Order error: {e}")
            return None

    # ========================================================================
    # KIS API Calls (Blocking)
    # ========================================================================

    def _call_kis_order(self, order: Order) -> Optional[Dict[str, Any]]:
        """
        Call KIS API for order submission.

        Args:
            order: Order to submit

        Returns:
            Dict: API response or None if failed
        """
        try:
            from api.kis_order_api import get_order_cash

            # Determine order division
            ord_dv = "buy" if order.side == OrderSide.BUY else "sell"

            # Convert order type to KIS code
            ord_dvsn = order.order_type.to_kis_code()

            # Call API
            result = get_order_cash(
                ord_dv=ord_dv,
                itm_no=order.stock_code,
                qty=order.quantity,
                unpr=int(order.price),
                ord_dvsn=ord_dvsn
            )

            if result is not None and not result.empty:
                return {
                    'order_no': result.get('ODNO', [''])[0] if 'ODNO' in result.columns else '',
                    'org_order_no': result.get('KRX_FWDG_ORD_ORGNO', [''])[0] if 'KRX_FWDG_ORD_ORGNO' in result.columns else ''
                }

            return None

        except ImportError:
            self.logger.error("KIS order API not available")
            return None
        except Exception as e:
            self.logger.error(f"KIS API call failed: {e}")
            return None

    def _call_kis_cancel(self, order: Order) -> bool:
        """
        Call KIS API for order cancellation.

        Args:
            order: Order to cancel

        Returns:
            bool: True if successful
        """
        try:
            from api.kis_order_api import get_order_rvsecncl

            result = get_order_rvsecncl(
                ord_orgno=order.org_order_no,
                orgn_odno=order.order_no,
                ord_dvsn=order.order_type.to_kis_code(),
                rvse_cncl_dvsn_cd="02",  # Cancel
                ord_qty=order.remaining_quantity,
                qty_all_ord_yn="Y"
            )

            return result is not None and not result.empty

        except ImportError:
            self.logger.error("KIS order API not available")
            return False
        except Exception as e:
            self.logger.error(f"KIS cancel API call failed: {e}")
            return False

    def _call_kis_modify(
        self,
        order: Order,
        new_price: int,
        new_quantity: int
    ) -> bool:
        """
        Call KIS API for order modification.

        Args:
            order: Order to modify
            new_price: New price
            new_quantity: New quantity

        Returns:
            bool: True if successful
        """
        try:
            from api.kis_order_api import get_order_rvsecncl

            result = get_order_rvsecncl(
                ord_orgno=order.org_order_no,
                orgn_odno=order.order_no,
                ord_dvsn=order.order_type.to_kis_code(),
                rvse_cncl_dvsn_cd="01",  # Modify
                ord_qty=new_quantity,
                ord_unpr=new_price,
                qty_all_ord_yn="N"
            )

            return result is not None and not result.empty

        except ImportError:
            self.logger.error("KIS order API not available")
            return False
        except Exception as e:
            self.logger.error(f"KIS modify API call failed: {e}")
            return False

    def _call_kis_order_status(self, order: Order) -> Optional[Dict[str, Any]]:
        """
        Call KIS API to get order status.

        Args:
            order: Order to check

        Returns:
            Dict: Order status data or None
        """
        try:
            from api.kis_order_api import get_inquire_daily_ccld_lst

            # Get today's orders
            result = get_inquire_daily_ccld_lst(
                dv="01",
                ccld_dvsn="00"  # All orders
            )

            if result is not None and not result.empty:
                # Find matching order by order number
                for _, row in result.iterrows():
                    if str(row.get('ODNO', '')) == order.order_no:
                        filled_qty = int(row.get('TOT_CCLD_QTY', 0) or 0)
                        filled_price = float(row.get('AVG_PRVS', 0) or 0)
                        cancelled = row.get('CNCL_YN', 'N') == 'Y'

                        return {
                            'filled_quantity': filled_qty,
                            'filled_price': filled_price,
                            'cancelled': cancelled
                        }

            return None

        except ImportError:
            self.logger.error("KIS order API not available")
            return None
        except Exception as e:
            self.logger.error(f"KIS order status API call failed: {e}")
            return None

    def _call_kis_pending_orders(self) -> Optional[List[Dict[str, Any]]]:
        """
        Call KIS API to get pending orders.

        Returns:
            List: Pending orders data or None
        """
        try:
            from api.kis_order_api import get_inquire_psbl_rvsecncl_lst

            result = get_inquire_psbl_rvsecncl_lst()

            if result is not None and not result.empty:
                pending = []
                for _, row in result.iterrows():
                    pending.append({
                        'order_no': str(row.get('ODNO', '')),
                        'stock_code': str(row.get('PDNO', '')),
                        'order_qty': int(row.get('ORD_QTY', 0) or 0),
                        'filled_qty': int(row.get('TOT_CCLD_QTY', 0) or 0),
                        'remaining_qty': int(row.get('PSBL_QTY', 0) or 0),
                        'order_price': float(row.get('ORD_UNPR', 0) or 0)
                    })
                return pending

            return None

        except ImportError:
            self.logger.error("KIS order API not available")
            return None
        except Exception as e:
            self.logger.error(f"KIS pending orders API call failed: {e}")
            return None

    # ========================================================================
    # Order Management
    # ========================================================================

    def get_order(self, order_id: str) -> Optional[Order]:
        """
        Get order by ID.

        Args:
            order_id: Order identifier

        Returns:
            Order: Order object or None
        """
        return self._orders.get(order_id)

    def get_orders_for_stock(self, stock_code: str) -> List[Order]:
        """
        Get all orders for a specific stock.

        Args:
            stock_code: Stock ticker

        Returns:
            List[Order]: List of orders
        """
        return [
            order for order in self._orders.values()
            if order.stock_code == stock_code
        ]

    def update_order_status(
        self,
        order_id: str,
        status: OrderStatus,
        filled_quantity: int = None,
        filled_price: float = None
    ) -> None:
        """
        Update order status (called by order monitoring).

        Args:
            order_id: Order identifier
            status: New status
            filled_quantity: Updated filled quantity
            filled_price: Updated average fill price
        """
        order = self._orders.get(order_id)

        if not order:
            return

        order.status = status
        order.updated_at = now_kst()

        if filled_quantity is not None:
            order.filled_quantity = filled_quantity

        if filled_price is not None:
            order.filled_price = filled_price

        self.logger.debug(
            f"Order updated: {order_id} status={status.value} "
            f"filled={filled_quantity}/{order.quantity}"
        )

    def clear_completed_orders(self) -> int:
        """
        Remove completed orders from tracking.

        Returns:
            int: Number of orders cleared
        """
        completed = [
            order_id for order_id, order in self._orders.items()
            if order.is_completed
        ]

        for order_id in completed:
            del self._orders[order_id]

        return len(completed)

    def shutdown(self) -> None:
        """Clean up executor resources."""
        self._executor.shutdown(wait=False)
        self.logger.info("OrderExecutor shutdown complete")

    def __del__(self):
        """Destructor to clean up thread pool."""
        if hasattr(self, '_executor'):
            self._executor.shutdown(wait=False)
