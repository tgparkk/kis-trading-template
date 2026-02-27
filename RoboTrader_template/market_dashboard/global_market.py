"""해외시장 데이터 수집 (yfinance 기반)"""
from datetime import datetime
from typing import Optional, List, Dict, Any
from .models import IndexData, ExchangeRate, GlobalMarketSnapshot

try:
    from utils.logger import setup_logger
except ImportError:
    import logging
    def setup_logger(name):
        return logging.getLogger(name)

# 해외 지수 심볼 매핑
GLOBAL_INDEX_SYMBOLS = {
    'S&P 500': '^GSPC',
    'NASDAQ': '^IXIC',
    'DOW': '^DJI',
    '니케이225': '^N225',
    '상해종합': '000001.SS',
    '항셍': '^HSI',
}

# 환율 심볼 매핑
EXCHANGE_RATE_SYMBOLS = {
    'USD/KRW': 'KRW=X',
    'USD/JPY': 'JPY=X',
    'EUR/USD': 'EURUSD=X',
}


class GlobalMarketCollector:
    """해외시장 데이터 수집기 (yfinance 기반)"""

    def __init__(self, cache_ttl_seconds: int = 300):
        self.logger = setup_logger(__name__)
        self._cache: Dict[str, Any] = {}
        self._cache_time: Optional[datetime] = None
        self._cache_ttl = cache_ttl_seconds

    def _is_cache_valid(self) -> bool:
        if self._cache_time is None:
            return False
        elapsed = (datetime.now() - self._cache_time).total_seconds()
        return elapsed < self._cache_ttl

    def fetch_global_indices(self) -> List[IndexData]:
        """해외 주요 지수 조회"""
        results = []
        try:
            import yfinance as yf
        except ImportError:
            self.logger.warning("yfinance 미설치 - 해외시장 데이터 조회 불가")
            return results

        for name, symbol in GLOBAL_INDEX_SYMBOLS.items():
            try:
                ticker = yf.Ticker(symbol)
                info = ticker.fast_info
                last_price = getattr(info, 'last_price', None)
                prev_close = getattr(info, 'previous_close', None)

                if last_price is None or prev_close is None:
                    continue

                change = last_price - prev_close
                change_rate = (change / prev_close) * 100 if prev_close != 0 else 0.0

                results.append(IndexData(
                    name=name,
                    value=round(last_price, 2),
                    change=round(change, 2),
                    change_rate=round(change_rate, 2),
                    timestamp=datetime.now()
                ))
            except Exception as e:
                self.logger.warning(f"해외지수 {name}({symbol}) 조회 실패: {e}")
        return results

    def fetch_exchange_rates(self) -> List[ExchangeRate]:
        """환율 조회"""
        results = []
        try:
            import yfinance as yf
        except ImportError:
            return results

        for pair, symbol in EXCHANGE_RATE_SYMBOLS.items():
            try:
                ticker = yf.Ticker(symbol)
                info = ticker.fast_info
                rate = getattr(info, 'last_price', None)
                prev_close = getattr(info, 'previous_close', None)

                if rate is None or prev_close is None:
                    continue

                change = rate - prev_close
                change_rate = (change / prev_close) * 100 if prev_close != 0 else 0.0

                results.append(ExchangeRate(
                    pair=pair,
                    rate=round(rate, 2),
                    change=round(change, 2),
                    change_rate=round(change_rate, 2),
                    timestamp=datetime.now()
                ))
            except Exception as e:
                self.logger.warning(f"환율 {pair}({symbol}) 조회 실패: {e}")
        return results

    def fetch_snapshot(self, use_cache: bool = True) -> GlobalMarketSnapshot:
        """해외시장 종합 스냅샷 조회 (캐시 지원)"""
        if use_cache and self._is_cache_valid():
            cached = self._cache.get('snapshot')
            if cached is not None:
                return cached

        indices = self.fetch_global_indices()
        rates = self.fetch_exchange_rates()

        snapshot = GlobalMarketSnapshot(
            indices=indices,
            exchange_rates=rates,
            timestamp=datetime.now()
        )

        self._cache['snapshot'] = snapshot
        self._cache_time = datetime.now()
        return snapshot
