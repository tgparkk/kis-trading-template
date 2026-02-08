"""
Broker Module
=============

KIS (Korea Investment & Securities) API wrapper for:
- Authentication and token management
- Account information and balance
- Position management
- Fund management

This module provides a clean abstraction layer over the existing api/ modules
for use in trading strategies.
"""

import time
import threading
from dataclasses import dataclass, field
from datetime import timedelta
from typing import Optional, Dict, List, Any
from abc import ABC, abstractmethod

import pandas as pd

from .utils import setup_logger, now_kst, round_to_tick


# ============================================================================
# Data Classes
# ============================================================================

@dataclass
class Position:
    """
    Stock position information.

    Attributes:
        stock_code: Stock ticker (6 digits)
        stock_name: Stock name
        quantity: Number of shares held
        avg_price: Average purchase price
        current_price: Current market price
        profit_loss: Profit/Loss amount
        profit_loss_rate: Profit/Loss percentage
    """
    stock_code: str
    stock_name: str
    quantity: int
    avg_price: float
    current_price: float = 0.0
    profit_loss: float = 0.0
    profit_loss_rate: float = 0.0

    def update_price(self, current_price: float) -> None:
        """Update current price and recalculate P&L."""
        self.current_price = current_price
        if self.avg_price > 0 and self.quantity > 0:
            self.profit_loss = (current_price - self.avg_price) * self.quantity
            self.profit_loss_rate = (current_price - self.avg_price) / self.avg_price


@dataclass
class AccountInfo:
    """
    Account information.

    Attributes:
        account_no: Account number
        total_balance: Total asset value
        available_cash: Available cash for trading
        invested_amount: Currently invested amount
        positions: List of held positions
    """
    account_no: str
    total_balance: float
    available_cash: float
    invested_amount: float
    positions: List[Position] = field(default_factory=list)

    @property
    def position_count(self) -> int:
        """Number of positions held."""
        return len(self.positions)

    @property
    def utilization_rate(self) -> float:
        """Investment utilization rate."""
        if self.total_balance > 0:
            return self.invested_amount / self.total_balance
        return 0.0


# ============================================================================
# Abstract Broker
# ============================================================================

class BaseBroker(ABC):
    """
    Abstract base class for broker implementations.

    All broker implementations should inherit from this class
    and implement the required abstract methods.
    """

    @abstractmethod
    async def connect(self) -> bool:
        """
        Connect to the broker API.

        Returns:
            bool: True if connection successful
        """
        pass

    @abstractmethod
    async def disconnect(self) -> None:
        """Disconnect from the broker API."""
        pass

    @abstractmethod
    def get_account_balance(self) -> dict:
        """
        Get account balance information.

        Returns:
            dict: Account balance information
        """
        pass

    @abstractmethod
    def get_holdings(self) -> List[dict]:
        """
        Get list of held positions.

        Returns:
            List[dict]: List of positions
        """
        pass

    @abstractmethod
    def get_available_cash(self) -> float:
        """
        Get available cash for trading.

        Returns:
            float: Available cash amount
        """
        pass


# ============================================================================
# KIS Broker Implementation
# ============================================================================

class KISBroker(BaseBroker):
    """
    Korea Investment & Securities (KIS) API broker implementation.

    This class wraps the existing api/ modules to provide a clean interface
    for trading strategies.

    Usage:
        config = {
            'app_key': 'your_app_key',
            'app_secret': 'your_app_secret',
            'account_no': '12345678-01'
        }
        broker = KISBroker(config)

        if await broker.connect():
            balance = broker.get_account_balance()
            holdings = broker.get_holdings()
            cash = broker.get_available_cash()
    """

    def __init__(self, config: dict = None):
        """
        Initialize KIS broker.

        Args:
            config: Optional configuration dictionary. If not provided,
                    uses settings from config/settings.py
        """
        self.logger = setup_logger(__name__)
        self.config = config or {}

        # API state
        self._connected = False

        # Lazy-loaded API modules
        self._kis_auth = None
        self._kis_account_api = None
        self._kis_market_api = None
        self._api_manager = None

    async def connect(self) -> bool:
        """
        Connect to KIS API (authenticate and initialize).

        Returns:
            bool: True if connection successful
        """
        try:
            self.logger.info("Connecting to KIS API...")

            # Import API modules
            try:
                from api import kis_auth
                from api import kis_account_api
                from api import kis_market_api
                from api.kis_api_manager import KISAPIManager

                self._kis_auth = kis_auth
                self._kis_account_api = kis_account_api
                self._kis_market_api = kis_market_api

            except ImportError as e:
                self.logger.error(f"Failed to import KIS API modules: {e}")
                return False

            # Authenticate
            if not self._kis_auth.auth():
                self.logger.error("KIS API authentication failed")
                return False

            # Initialize API manager for advanced features
            self._api_manager = KISAPIManager()
            if not self._api_manager.initialize():
                self.logger.warning("KIS API Manager initialization failed, using basic mode")
                # Continue without API manager - basic functions will still work

            self._connected = True
            self.logger.info("KIS API connection successful")
            return True

        except Exception as e:
            self.logger.error(f"KIS API connection failed: {e}")
            return False

    async def disconnect(self) -> None:
        """Disconnect from KIS API."""
        try:
            if self._api_manager:
                self._api_manager.shutdown()
                self._api_manager = None

            self._connected = False
            self._kis_auth = None
            self._kis_account_api = None
            self._kis_market_api = None

            self.logger.info("KIS API disconnected")

        except Exception as e:
            self.logger.error(f"Error during disconnect: {e}")

    def get_account_balance(self) -> dict:
        """
        Get account balance information.

        Returns:
            dict: Account balance with keys:
                - total_balance: Total asset value
                - available_cash: Available cash for trading
                - invested_amount: Currently invested amount
                - total_profit_loss: Total P&L
                - total_profit_loss_rate: Total P&L percentage
        """
        if not self._connected:
            self.logger.error("Broker not connected")
            return {}

        try:
            # Use kis_market_api.get_account_balance() for comprehensive info
            balance_info = self._kis_market_api.get_account_balance()

            if balance_info is None:
                self.logger.error("Failed to get account balance")
                return {}

            return {
                'total_balance': balance_info.get('total_value', 0),
                'available_cash': balance_info.get('available_amount', 0),
                'invested_amount': balance_info.get('purchase_amount', 0),
                'total_profit_loss': balance_info.get('total_profit_loss', 0),
                'total_profit_loss_rate': balance_info.get('total_profit_loss_rate', 0),
                'deposit_total': balance_info.get('deposit_total', 0),
                'next_day_amount': balance_info.get('next_day_amount', 0),
                'total_stocks': balance_info.get('total_stocks', 0),
                'inquiry_time': balance_info.get('inquiry_time', '')
            }

        except Exception as e:
            self.logger.error(f"Error getting account balance: {e}")
            return {}

    def get_holdings(self) -> List[dict]:
        """
        Get list of held positions.

        Returns:
            List[dict]: List of positions with keys:
                - stock_code: Stock ticker
                - stock_name: Stock name
                - quantity: Number of shares
                - avg_price: Average purchase price
                - current_price: Current market price
                - eval_amount: Evaluation amount
                - profit_loss: Profit/Loss amount
                - profit_loss_rate: Profit/Loss percentage
        """
        if not self._connected:
            self.logger.error("Broker not connected")
            return []

        try:
            # Use kis_market_api.get_existing_holdings() for position list
            holdings = self._kis_market_api.get_existing_holdings()

            if holdings is None:
                return []

            return holdings

        except Exception as e:
            self.logger.error(f"Error getting holdings: {e}")
            return []

    def get_available_cash(self) -> float:
        """
        Get available cash for trading.

        Returns:
            float: Available cash amount
        """
        if not self._connected:
            self.logger.error("Broker not connected")
            return 0.0

        try:
            balance = self.get_account_balance()
            return float(balance.get('available_cash', 0))

        except Exception as e:
            self.logger.error(f"Error getting available cash: {e}")
            return 0.0

    def get_current_price(self, stock_code: str) -> Optional[float]:
        """
        Get current price of a stock.

        Args:
            stock_code: Stock ticker (6 digits)

        Returns:
            float: Current price or None if failed
        """
        if not self._connected:
            self.logger.error("Broker not connected")
            return None

        try:
            price_data = self._kis_market_api.get_inquire_price(itm_no=stock_code)

            if price_data is None or price_data.empty:
                return None

            return float(price_data.iloc[0].get('stck_prpr', 0))

        except Exception as e:
            self.logger.error(f"Error getting price for {stock_code}: {e}")
            return None

    def get_tradable_amount(self, stock_code: str, price: float) -> Optional[int]:
        """
        Get maximum tradable quantity for a stock at given price.

        Args:
            stock_code: Stock ticker (6 digits)
            price: Order price

        Returns:
            int: Maximum quantity or None if failed
        """
        if not self._connected:
            self.logger.error("Broker not connected")
            return None

        try:
            result = self._kis_account_api.get_inquire_psbl_order(
                pdno=stock_code,
                ord_unpr=int(price)
            )

            if result is None or result.empty:
                return None

            return int(result.iloc[0].get('ord_psbl_qty', 0))

        except Exception as e:
            self.logger.error(f"Error getting tradable amount for {stock_code}: {e}")
            return None

    # ================================================================
    # Market Data Methods (migrated from KISAPIManager)
    # ================================================================

    def get_current_prices(self, stock_codes: List[str]) -> Dict[str, float]:
        """
        Get current prices for multiple stocks.

        Args:
            stock_codes: List of stock tickers

        Returns:
            Dict mapping stock_code -> current price
        """
        if not self._connected:
            self.logger.error("Broker not connected")
            return {}

        from config.constants import PAGING_API_INTERVAL

        prices: Dict[str, float] = {}
        for code in stock_codes:
            p = self.get_current_price(code)
            if p is not None:
                prices[code] = p
            time.sleep(PAGING_API_INTERVAL)
        return prices

    def get_ohlcv_data(
        self,
        stock_code: str,
        period: str = "D",
        days: int = 30,
    ) -> Optional[pd.DataFrame]:
        """
        Get OHLCV data with automatic pagination for large requests.

        Args:
            stock_code: Stock ticker (6 digits)
            period: Period code (D: daily, W: weekly, M: monthly)
            days: Calendar days to look back

        Returns:
            DataFrame with OHLCV data sorted by date, or None
        """
        if not self._connected:
            self.logger.error("Broker not connected")
            return None

        try:
            end_date = now_kst().strftime("%Y%m%d")
            start_date = (now_kst() - timedelta(days=days)).strftime("%Y%m%d")
            estimated_trading_days = int(days * 0.7)

            if estimated_trading_days > 100:
                result = self._kis_market_api.get_inquire_daily_itemchartprice_extended(
                    div_code="J",
                    itm_no=stock_code,
                    inqr_strt_dt=start_date,
                    inqr_end_dt=end_date,
                    period_code=period,
                    max_count=estimated_trading_days + 50,
                )
            else:
                result = self._kis_market_api.get_inquire_daily_itemchartprice(
                    "2", "J", stock_code, start_date, end_date, period
                )

            if result is None or result.empty:
                return None

            df = result.copy()
            df['stck_bsop_date'] = pd.to_datetime(df['stck_bsop_date'])
            df = df.sort_values('stck_bsop_date')
            return df

        except Exception as e:
            self.logger.error(f"Error getting OHLCV for {stock_code}: {e}")
            return None

    def get_index_data(self, index_code: str = "0001") -> Optional[Dict[str, Any]]:
        """
        Get market index data.

        Args:
            index_code: Index code (default "0001" for KOSPI)

        Returns:
            Dict with index data or None
        """
        if not self._connected:
            self.logger.error("Broker not connected")
            return None

        try:
            return self._kis_market_api.get_index_data(index_code)
        except Exception as e:
            self.logger.error(f"Error getting index data {index_code}: {e}")
            return None

    def get_investor_flow_data(self) -> Optional[Dict[str, Any]]:
        """
        Get investor trading flow data.

        Returns:
            Dict with investor flow data or None
        """
        if not self._connected:
            self.logger.error("Broker not connected")
            return None

        try:
            return self._kis_market_api.get_investor_flow_data()
        except Exception as e:
            self.logger.error(f"Error getting investor flow data: {e}")
            return None

    # ================================================================
    # Order Methods (migrated from KISAPIManager)
    # ================================================================

    def place_buy_order(
        self,
        stock_code: str,
        quantity: int,
        price: int,
        order_type: str = "00",
    ) -> Dict[str, Any]:
        """
        Place a buy order.

        Args:
            stock_code: Stock ticker (6 digits)
            quantity: Number of shares
            price: Order price (0 for market order when order_type='01')
            order_type: '00' limit, '01' market

        Returns:
            Dict with keys: success, order_id, message, data
        """
        return self._place_order("buy", stock_code, quantity, price, order_type)

    def place_sell_order(
        self,
        stock_code: str,
        quantity: int,
        price: int,
        order_type: str = "00",
    ) -> Dict[str, Any]:
        """
        Place a sell order.

        Args:
            stock_code: Stock ticker (6 digits)
            quantity: Number of shares
            price: Order price (0 for market order when order_type='01')
            order_type: '00' limit, '01' market

        Returns:
            Dict with keys: success, order_id, message, data
        """
        return self._place_order("sell", stock_code, quantity, price, order_type)

    def _place_order(
        self,
        side: str,
        stock_code: str,
        quantity: int,
        price: int,
        order_type: str,
    ) -> Dict[str, Any]:
        """Internal order placement helper."""
        if not self._connected:
            self.logger.error("Broker not connected")
            return {"success": False, "order_id": "", "message": "Broker not connected", "data": None}

        try:
            from api import kis_order_api

            result = kis_order_api.get_order_cash(
                side, stock_code, quantity, price, "", order_type
            )

            if result is None or result.empty:
                return {"success": False, "order_id": "", "message": "주문 실패 - 응답 없음", "data": None}

            data = result.iloc[0]
            order_id = data.get("ODNO", "")

            if order_id:
                return {
                    "success": True,
                    "order_id": order_id,
                    "message": f"{'매수' if side == 'buy' else '매도'} 주문 성공",
                    "data": data.to_dict(),
                }
            else:
                return {
                    "success": False,
                    "order_id": "",
                    "message": "주문 실패 - 주문번호 없음",
                    "data": data.to_dict(),
                }

        except Exception as e:
            self.logger.error(f"Order error ({side}) {stock_code}: {e}")
            return {"success": False, "order_id": "", "message": f"주문 오류: {e}", "data": None}

    def cancel_order(
        self,
        order_id: str,
        stock_code: str = "",
        order_type: str = "00",
    ) -> Dict[str, Any]:
        """
        Cancel an existing order.

        Args:
            order_id: Original order ID to cancel
            stock_code: Stock ticker (for logging)
            order_type: Order division code

        Returns:
            Dict with keys: success, order_id, message, data
        """
        if not self._connected:
            self.logger.error("Broker not connected")
            return {"success": False, "order_id": order_id, "message": "Broker not connected", "data": None}

        try:
            from api import kis_order_api

            # 1. Get cancellable orders
            pending = kis_order_api.get_inquire_psbl_rvsecncl_lst()
            if pending is None or pending.empty:
                return {
                    "success": False,
                    "order_id": order_id,
                    "message": "취소 가능한 주문 없음",
                    "data": None,
                }

            target = pending[pending["odno"] == order_id]
            if target.empty:
                return {
                    "success": False,
                    "order_id": order_id,
                    "message": f"취소 대상 주문을 찾을 수 없음: {order_id}",
                    "data": None,
                }

            order_data = target.iloc[0]

            # Find org number
            ord_orgno = ""
            for fld in ["krx_fwdg_ord_orgno", "ord_orgno", "ord_gno_brno"]:
                if fld in order_data and order_data[fld]:
                    ord_orgno = order_data[fld]
                    break

            if not ord_orgno:
                return {
                    "success": False,
                    "order_id": order_id,
                    "message": "주문조직번호를 찾을 수 없음",
                    "data": None,
                }

            result = kis_order_api.get_order_rvsecncl(
                ord_orgno, order_id, order_type, "02", 0, 0, "Y"
            )

            if result is None or result.empty:
                return {"success": False, "order_id": order_id, "message": "취소 API 응답 없음", "data": None}

            cancel_data = result.iloc[0]
            rt_cd = cancel_data.get("rt_cd", "")

            if rt_cd == "0":
                return {
                    "success": True,
                    "order_id": order_id,
                    "message": "주문 취소 성공",
                    "data": cancel_data.to_dict(),
                }
            else:
                return {
                    "success": False,
                    "order_id": order_id,
                    "message": f"주문 취소 실패: {cancel_data.get('msg1', '')}",
                    "data": cancel_data.to_dict(),
                }

        except Exception as e:
            self.logger.error(f"Cancel order error {order_id}: {e}")
            return {"success": False, "order_id": order_id, "message": f"취소 오류: {e}", "data": None}

    def get_order_status(self, order_id: str) -> Optional[Dict[str, Any]]:
        """
        Get order status by checking pending orders and daily executions.

        Args:
            order_id: Order ID to check

        Returns:
            Dict with order status info or None
        """
        if not self._connected:
            self.logger.error("Broker not connected")
            return None

        try:
            from api import kis_order_api
            from datetime import datetime

            # Check pending (cancellable) orders
            pending = kis_order_api.get_inquire_psbl_rvsecncl_lst()
            if pending is not None and not pending.empty:
                target = pending[pending["odno"] == order_id]
                if not target.empty:
                    data = target.iloc[0].to_dict()
                    data["status"] = "pending"
                    return data

            # Check daily executions
            today = datetime.today().strftime("%Y%m%d")
            daily = kis_order_api.get_inquire_daily_ccld_lst("01", today, today)
            if daily is not None and not daily.empty:
                target = daily[daily["odno"] == order_id]
                if not target.empty:
                    data = target.iloc[0].to_dict()
                    data["status"] = "filled"
                    return data

            return None

        except Exception as e:
            self.logger.error(f"Error getting order status {order_id}: {e}")
            return None

    # ================================================================
    # Utility Methods (migrated from KISAPIManager)
    # ================================================================

    def health_check(self) -> bool:
        """
        Check API connectivity by fetching Samsung Electronics price.

        Returns:
            bool: True if API is responsive
        """
        if not self._connected:
            return False

        try:
            result = self.get_current_price("005930")
            return result is not None
        except Exception:
            return False

    # ====================================================================
    # Market Data Methods (migrated from KISAPIManager)
    # ====================================================================

    def get_current_prices(self, stock_codes: List[str]) -> Dict[str, float]:
        """
        Get current prices for multiple stocks.

        Args:
            stock_codes: List of stock tickers (6 digits each)

        Returns:
            Dict mapping stock_code -> current_price
        """
        if not self._connected:
            self.logger.error("Broker not connected")
            return {}

        from config.constants import PAGING_API_INTERVAL

        prices: Dict[str, float] = {}
        for code in stock_codes:
            p = self.get_current_price(code)
            if p is not None:
                prices[code] = p
            time.sleep(PAGING_API_INTERVAL)
        return prices

    def get_ohlcv_data(
        self,
        stock_code: str,
        period: str = "D",
        days: int = 30,
    ) -> Optional[pd.DataFrame]:
        """
        Get OHLCV data for a stock (supports continuous query for large ranges).

        Args:
            stock_code: Stock ticker (6 digits)
            period: Period code (D: daily, W: weekly, M: monthly)
            days: Calendar days to look back

        Returns:
            pd.DataFrame with OHLCV data sorted by date, or None
        """
        if not self._connected:
            self.logger.error("Broker not connected")
            return None

        try:
            end_date = now_kst().strftime("%Y%m%d")
            start_date = (now_kst() - timedelta(days=days)).strftime("%Y%m%d")
            estimated_trading_days = int(days * 0.7)

            if estimated_trading_days > 100:
                result = self._kis_market_api.get_inquire_daily_itemchartprice_extended(
                    div_code="J",
                    itm_no=stock_code,
                    inqr_strt_dt=start_date,
                    inqr_end_dt=end_date,
                    period_code=period,
                    max_count=estimated_trading_days + 50,
                )
            else:
                result = self._kis_market_api.get_inquire_daily_itemchartprice(
                    "2", "J", stock_code, start_date, end_date, period
                )

            if result is None or result.empty:
                return None

            df = result.copy()
            df["stck_bsop_date"] = pd.to_datetime(df["stck_bsop_date"])
            df = df.sort_values("stck_bsop_date")
            return df

        except Exception as e:
            self.logger.error(f"Error getting OHLCV for {stock_code}: {e}")
            return None

    def get_index_data(self, index_code: str = "0001") -> Optional[Dict[str, Any]]:
        """
        Get stock market index data.

        Args:
            index_code: Index code (default "0001" = KOSPI)

        Returns:
            Dict with index data or None
        """
        if not self._connected:
            self.logger.error("Broker not connected")
            return None

        try:
            return self._kis_market_api.get_index_data(index_code)
        except Exception as e:
            self.logger.error(f"Error getting index data {index_code}: {e}")
            return None

    def get_investor_flow_data(self) -> Optional[Dict[str, Any]]:
        """
        Get investor-type trading trend data.

        Returns:
            Dict with investor flow data or None
        """
        if not self._connected:
            self.logger.error("Broker not connected")
            return None

        try:
            return self._kis_market_api.get_investor_flow_data()
        except Exception as e:
            self.logger.error(f"Error getting investor flow data: {e}")
            return None

    # ====================================================================
    # Order Methods (migrated from KISAPIManager)
    # ====================================================================

    def place_buy_order(
        self,
        stock_code: str,
        quantity: int,
        price: int,
        order_type: str = "00",
    ) -> Dict[str, Any]:
        """
        Place a buy order.

        Args:
            stock_code: Stock ticker (6 digits)
            quantity: Number of shares
            price: Order price (0 for market order when order_type="01")
            order_type: "00" limit, "01" market

        Returns:
            Dict with keys: success, order_id, message, data
        """
        return self._place_order("buy", stock_code, quantity, price, order_type)

    def place_sell_order(
        self,
        stock_code: str,
        quantity: int,
        price: int,
        order_type: str = "00",
    ) -> Dict[str, Any]:
        """
        Place a sell order.

        Args:
            stock_code: Stock ticker (6 digits)
            quantity: Number of shares
            price: Order price (0 for market order when order_type="01")
            order_type: "00" limit, "01" market

        Returns:
            Dict with keys: success, order_id, message, data
        """
        return self._place_order("sell", stock_code, quantity, price, order_type)

    def _place_order(
        self,
        side: str,
        stock_code: str,
        quantity: int,
        price: int,
        order_type: str,
    ) -> Dict[str, Any]:
        """Internal helper for buy/sell orders."""
        if not self._connected:
            self.logger.error("Broker not connected")
            return {"success": False, "order_id": "", "message": "Not connected", "data": None}

        try:
            from api import kis_order_api

            result = kis_order_api.get_order_cash(
                side, stock_code, quantity, price, "", order_type
            )

            if result is None or result.empty:
                return {"success": False, "order_id": "", "message": "No response", "data": None}

            data = result.iloc[0]
            order_id = data.get("ODNO", "")

            if order_id:
                return {
                    "success": True,
                    "order_id": order_id,
                    "message": f"{side} order success",
                    "data": data.to_dict(),
                }
            else:
                return {
                    "success": False,
                    "order_id": "",
                    "message": "No order ID in response",
                    "data": data.to_dict(),
                }

        except Exception as e:
            self.logger.error(f"Error placing {side} order for {stock_code}: {e}")
            return {"success": False, "order_id": "", "message": str(e), "data": None}

    def cancel_order(
        self,
        order_id: str,
        stock_code: str = "",
        order_type: str = "00",
    ) -> Dict[str, Any]:
        """
        Cancel a pending order.

        Args:
            order_id: Order ID to cancel
            stock_code: Stock ticker (for logging)
            order_type: Order division code

        Returns:
            Dict with keys: success, order_id, message, data
        """
        if not self._connected:
            self.logger.error("Broker not connected")
            return {"success": False, "order_id": order_id, "message": "Not connected", "data": None}

        try:
            from api import kis_order_api

            # 1. Get cancellable orders
            pending = kis_order_api.get_inquire_psbl_rvsecncl_lst()
            if pending is None or pending.empty:
                return {
                    "success": False,
                    "order_id": order_id,
                    "message": "No cancellable orders",
                    "data": None,
                }

            target = pending[pending["odno"] == order_id]
            if target.empty:
                return {
                    "success": False,
                    "order_id": order_id,
                    "message": f"Order {order_id} not found in cancellable list",
                    "data": None,
                }

            order_data = target.iloc[0]

            # Find org number
            ord_orgno = ""
            for field in ["krx_fwdg_ord_orgno", "ord_orgno", "ord_gno_brno"]:
                if field in order_data and order_data[field]:
                    ord_orgno = order_data[field]
                    break

            if not ord_orgno:
                return {
                    "success": False,
                    "order_id": order_id,
                    "message": "Cannot find order org number",
                    "data": None,
                }

            result = kis_order_api.get_order_rvsecncl(
                ord_orgno, order_id, order_type, "02", 0, 0, "Y"
            )

            if result is None or result.empty:
                return {
                    "success": False,
                    "order_id": order_id,
                    "message": "Cancel API returned no response",
                    "data": None,
                }

            cancel_data = result.iloc[0]
            rt_cd = cancel_data.get("rt_cd", "")

            if rt_cd == "0":
                return {
                    "success": True,
                    "order_id": order_id,
                    "message": "Order cancelled",
                    "data": cancel_data.to_dict(),
                }
            else:
                msg = cancel_data.get("msg1", "Unknown error")
                return {
                    "success": False,
                    "order_id": order_id,
                    "message": f"Cancel failed: {msg}",
                    "data": cancel_data.to_dict(),
                }

        except Exception as e:
            self.logger.error(f"Error cancelling order {order_id}: {e}")
            return {"success": False, "order_id": order_id, "message": str(e), "data": None}

    def get_order_status(self, order_id: str) -> Optional[Dict[str, Any]]:
        """
        Get order status by checking pending orders and daily executions.

        Args:
            order_id: Order ID to check

        Returns:
            Dict with order status info, or None if not found
        """
        if not self._connected:
            self.logger.error("Broker not connected")
            return None

        try:
            from api import kis_order_api
            from datetime import datetime

            # Check pending (cancellable) orders
            pending = kis_order_api.get_inquire_psbl_rvsecncl_lst()
            if pending is not None and not pending.empty:
                target = pending[pending["odno"] == order_id]
                if not target.empty:
                    row = target.iloc[0].to_dict()
                    row["_status"] = "pending"
                    return row

            # Check daily executions
            today = datetime.today().strftime("%Y%m%d")
            daily = kis_order_api.get_inquire_daily_ccld_lst("01", today, today)
            if daily is not None and not daily.empty:
                target = daily[daily["odno"] == order_id]
                if not target.empty:
                    row = target.iloc[0].to_dict()
                    row["_status"] = "executed"
                    return row

            # Not found anywhere
            return {"odno": order_id, "_status": "unknown", "cncl_yn": "Y"}

        except Exception as e:
            self.logger.error(f"Error getting order status {order_id}: {e}")
            return None

    # ====================================================================
    # Utility Methods
    # ====================================================================

    def health_check(self) -> bool:
        """
        Check API health by fetching Samsung Electronics price.

        Returns:
            bool: True if API is responsive
        """
        if not self._connected:
            return False

        try:
            price = self.get_current_price("005930")
            return price is not None
        except Exception:
            return False

    @property
    def is_connected(self) -> bool:
        """Check if broker is connected."""
        return self._connected

    @property
    def api_manager(self) -> Optional[Any]:
        """Get the underlying API manager for advanced operations."""
        return self._api_manager


# ============================================================================
# Fund Manager
# ============================================================================

class FundManager:
    """
    Fund management for trading.

    Tracks available funds, reserved amounts, and position sizing.
    Thread-safe implementation for concurrent order processing.

    Features:
    - Track total and available funds
    - Reserve funds for pending orders
    - Calculate max buy amounts per stock
    - Prevent double-spending on concurrent orders

    Usage:
        fund_manager = FundManager(initial_funds=10000000)

        # Reserve funds for order
        if fund_manager.reserve_funds("order_001", 500000):
            # Execute order
            ...
            # Confirm order with actual amount
            fund_manager.confirm_order("order_001", 495000)
    """

    def __init__(self, initial_funds: float = 0):
        """
        Initialize fund manager.

        Args:
            initial_funds: Initial available funds (0 = fetch from API later)
        """
        self.logger = setup_logger(__name__)
        self._lock = threading.RLock()

        # Fund tracking
        self.total_funds = initial_funds
        self.available_funds = initial_funds
        self.reserved_funds = 0.0
        self.invested_funds = 0.0

        # Order reservations: order_id -> reserved_amount
        self._reservations: Dict[str, float] = {}

        # Settings
        self.max_position_ratio = 0.09  # Max 9% per stock
        self.max_total_investment = 0.90  # Max 90% total investment

        self.logger.info(f"FundManager initialized with {initial_funds:,.0f} won")

    def update_total_funds(self, new_total: float) -> None:
        """
        Update total available funds.

        Args:
            new_total: New total fund amount
        """
        with self._lock:
            old_total = self.total_funds
            self.total_funds = new_total

            # Recalculate available funds
            self.available_funds = new_total - self.reserved_funds - self.invested_funds

            self.logger.info(
                f"Funds updated: {old_total:,.0f} -> {new_total:,.0f} "
                f"(available: {self.available_funds:,.0f})"
            )

    def get_max_buy_amount(self, stock_code: str) -> float:
        """
        Calculate maximum buy amount for a stock.

        Considers:
        - Per-stock position limit (max_position_ratio)
        - Total investment limit (max_total_investment)
        - Currently available funds

        Args:
            stock_code: Stock code

        Returns:
            float: Maximum amount available for buying
        """
        with self._lock:
            # Per-stock limit
            max_per_stock = self.total_funds * self.max_position_ratio

            # Total investment limit
            max_investment = self.total_funds * self.max_total_investment
            remaining_capacity = max_investment - self.invested_funds - self.reserved_funds

            # Available funds limit
            available = self.available_funds

            # Return minimum of all limits
            max_amount = max(0, min(max_per_stock, remaining_capacity, available))

            self.logger.debug(
                f"Max buy for {stock_code}: {max_amount:,.0f} "
                f"(per_stock: {max_per_stock:,.0f}, capacity: {remaining_capacity:,.0f}, "
                f"available: {available:,.0f})"
            )

            return max_amount

    def reserve_funds(self, order_id: str, amount: float) -> bool:
        """
        Reserve funds for a pending order.

        Thread-safe method to prevent double-spending on concurrent orders.

        Args:
            order_id: Unique order identifier
            amount: Amount to reserve

        Returns:
            bool: True if reservation successful
        """
        with self._lock:
            if amount > self.available_funds:
                self.logger.warning(
                    f"Insufficient funds: need {amount:,.0f}, have {self.available_funds:,.0f}"
                )
                return False

            if order_id in self._reservations:
                self.logger.warning(f"Order already reserved: {order_id}")
                return False

            self.available_funds -= amount
            self.reserved_funds += amount
            self._reservations[order_id] = amount

            self.logger.info(
                f"Reserved {amount:,.0f} for order {order_id} "
                f"(available: {self.available_funds:,.0f})"
            )

            return True

    def confirm_order(self, order_id: str, actual_amount: float) -> None:
        """
        Confirm order and move reserved funds to invested.

        Call this after an order is filled to update fund tracking.

        Args:
            order_id: Order identifier
            actual_amount: Actual filled amount
        """
        with self._lock:
            if order_id not in self._reservations:
                self.logger.warning(f"Order not found in reservations: {order_id}")
                return

            reserved = self._reservations.pop(order_id)
            self.reserved_funds -= reserved
            self.invested_funds += actual_amount

            # Refund difference if actual < reserved
            refund = reserved - actual_amount
            if refund > 0:
                self.available_funds += refund

            self.logger.info(
                f"Order {order_id} confirmed: invested {actual_amount:,.0f}, "
                f"refunded {refund:,.0f}"
            )

    def cancel_order(self, order_id: str) -> None:
        """
        Cancel order reservation and return funds.

        Call this when an order is cancelled to release reserved funds.

        Args:
            order_id: Order identifier
        """
        with self._lock:
            if order_id not in self._reservations:
                self.logger.warning(f"Order not in reservations: {order_id}")
                return

            amount = self._reservations.pop(order_id)
            self.reserved_funds -= amount
            self.available_funds += amount

            self.logger.info(
                f"Reservation cancelled: {order_id}, returned {amount:,.0f}"
            )

    def release_investment(self, amount: float) -> None:
        """
        Release invested funds (after selling).

        Call this after a sell order is filled to update fund tracking.

        Args:
            amount: Amount to release
        """
        with self._lock:
            self.invested_funds -= amount
            self.available_funds += amount

            self.logger.info(
                f"Investment released: {amount:,.0f} "
                f"(available: {self.available_funds:,.0f})"
            )

    def get_status(self) -> Dict[str, float]:
        """
        Get current fund status.

        Returns:
            Dict: Fund status summary with keys:
                - total_funds: Total funds
                - available_funds: Available for trading
                - reserved_funds: Reserved for pending orders
                - invested_funds: Currently invested
                - utilization_rate: Investment utilization ratio
        """
        with self._lock:
            return {
                'total_funds': self.total_funds,
                'available_funds': self.available_funds,
                'reserved_funds': self.reserved_funds,
                'invested_funds': self.invested_funds,
                'utilization_rate': (
                    (self.reserved_funds + self.invested_funds) / self.total_funds
                    if self.total_funds > 0 else 0
                )
            }

    def sync_with_broker(self, broker: KISBroker) -> bool:
        """
        Synchronize fund status with broker.

        Fetches actual balance from broker and updates internal tracking.

        Args:
            broker: KISBroker instance

        Returns:
            bool: True if sync successful
        """
        try:
            balance = broker.get_account_balance()
            if not balance:
                self.logger.error("Failed to get balance from broker")
                return False

            total_value = balance.get('total_balance', 0)
            available_cash = balance.get('available_cash', 0)
            invested = balance.get('invested_amount', 0)

            with self._lock:
                self.total_funds = total_value
                self.invested_funds = invested
                self.available_funds = available_cash - self.reserved_funds

            self.logger.info(
                f"Synced with broker: total={total_value:,.0f}, "
                f"available={self.available_funds:,.0f}, invested={invested:,.0f}"
            )
            return True

        except Exception as e:
            self.logger.error(f"Failed to sync with broker: {e}")
            return False
