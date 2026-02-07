"""
Trading Framework
=================

한국투자증권 API 기반 자동매매 프레임워크

Modules:
    - broker: KIS API 브로커 및 자금 관리
    - executor: 주문 실행
    - data: 시장 데이터 제공
    - utils: 유틸리티 함수
"""

from .broker import KISBroker, FundManager, Position, AccountInfo
from .executor import OrderExecutor, OrderRequest, OrderResult, OrderType, OrderSide, OrderStatus
from .data import DataProvider, RealtimeDataCollector, OHLCV, PriceQuote
from .utils import (
    setup_logger,
    now_kst,
    is_market_open,
    get_market_open_time,
    get_market_close_time,
    round_to_tick,
    validate_tick,
    calculate_change_rate,
    format_price,
    format_quantity,
    load_config
)

__all__ = [
    # Broker
    'KISBroker',
    'FundManager',
    'Position',
    'AccountInfo',

    # Executor
    'OrderExecutor',
    'OrderRequest',
    'OrderResult',
    'OrderType',
    'OrderSide',
    'OrderStatus',

    # Data
    'DataProvider',
    'RealtimeDataCollector',
    'OHLCV',
    'PriceQuote',

    # Utils
    'setup_logger',
    'now_kst',
    'is_market_open',
    'get_market_open_time',
    'get_market_close_time',
    'round_to_tick',
    'validate_tick',
    'calculate_change_rate',
    'format_price',
    'format_quantity',
    'load_config',
]

__version__ = '1.0.0'
