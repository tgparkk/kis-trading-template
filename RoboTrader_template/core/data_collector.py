"""
실시간 데이터 수집 모듈
"""
import asyncio
from datetime import datetime
from typing import Any, List, Dict, Optional
from concurrent.futures import ThreadPoolExecutor

from .models import Stock, OHLCVData, TradingConfig
from framework import KISBroker
from utils.logger import setup_logger
from utils.korean_time import now_kst, is_market_open
from utils.async_helpers import run_with_timeout


class RealTimeDataCollector:
    """실시간 OHLCV 데이터 수집기"""
    
    def __init__(self, config: TradingConfig, broker: KISBroker):
        self.config = config
        self.broker = broker
        self.logger = setup_logger(__name__)
        
        self.stocks: Dict[str, Stock] = {}
        self.is_running = False
        self.executor = ThreadPoolExecutor(max_workers=4)
        self._consecutive_failures: Dict[str, int] = {}
        
        # 후보 종목 초기화
        self._initialize_stocks()
    
    def _initialize_stocks(self) -> None:
        """후보 종목 초기화"""
        for stock_code in self.config.data_collection.candidate_stocks:
            # TODO: 종목명 조회 API 추가 필요
            stock_name = f"Stock_{stock_code}"
            self.stocks[stock_code] = Stock(
                code=stock_code,
                name=stock_name,
                is_candidate=True
            )
            self.logger.info(f"종목 초기화: {stock_code} ({stock_name})")
    
    def add_candidate_stock(self, stock_code: str, stock_name: Optional[str] = None) -> None:
        """후보 종목 추가"""
        if stock_code not in self.stocks:
            self.stocks[stock_code] = Stock(
                code=stock_code,
                name=stock_name or f"Stock_{stock_code}",
                is_candidate=True
            )
            self.config.data_collection.candidate_stocks.append(stock_code)
            self.logger.info(f"후보 종목 추가: {stock_code} : {stock_name}")
    
    def remove_candidate_stock(self, stock_code: str) -> None:
        """후보 종목 제거"""
        if stock_code in self.stocks:
            self.stocks[stock_code].is_candidate = False
            if stock_code in self.config.data_collection.candidate_stocks:
                self.config.data_collection.candidate_stocks.remove(stock_code)
            self.logger.info(f"후보 종목 제거: {stock_code}")
    
    async def start_collection(self) -> None:
        """데이터 수집 시작"""
        self.is_running = True
        self.logger.info("실시간 데이터 수집 시작")
        
        while self.is_running:
            # 장중에만 데이터 수집
            if not is_market_open():
                #self.logger.debug("장 마감 시간 - 데이터 수집 중단")
                await asyncio.sleep(60)  # 1분 대기
                continue
            
            try:
                # 후보 종목들의 데이터 수집
                await self._collect_all_stocks_data()
                
                # 설정된 주기만큼 대기
                await asyncio.sleep(self.config.data_collection.interval_seconds)
                
            except Exception as e:
                self.logger.error(f"데이터 수집 중 오류: {e}")
                await asyncio.sleep(10)  # 오류 시 10초 대기
    
    async def _collect_all_stocks_data(self) -> None:
        """모든 후보 종목 데이터 수집"""
        tasks = []
        stock_codes = []

        for stock_code in self.config.data_collection.candidate_stocks:
            if stock_code in self.stocks:
                task = self._collect_stock_data(stock_code)
                tasks.append(task)
                stock_codes.append(stock_code)

        if tasks:
            results = await asyncio.gather(*tasks, return_exceptions=True)

            for stock_code, result in zip(stock_codes, results):
                if isinstance(result, Exception):
                    self._consecutive_failures[stock_code] = \
                        self._consecutive_failures.get(stock_code, 0) + 1
                    count = self._consecutive_failures[stock_code]

                    if count >= 5:
                        self.logger.warning(
                            f"종목 {stock_code} 데이터 수집 {count}회 연속 실패: {result}"
                        )
                else:
                    # 성공 시 카운트 리셋
                    if stock_code in self._consecutive_failures:
                        del self._consecutive_failures[stock_code]
    
    async def _collect_stock_data(self, stock_code: str) -> None:
        """개별 종목 데이터 수집"""
        try:
            # API 호출을 별도 스레드에서 실행 (타임아웃 15초)
            price_data = await run_with_timeout(
                self.executor,
                self._get_current_price_sync,
                stock_code,
                timeout_seconds=15,
                default=None
            )
            
            if price_data:
                # OHLCV 데이터 생성 (현재가 기준으로 임시 생성)
                ohlcv = OHLCVData(
                    timestamp=now_kst(),
                    stock_code=stock_code,
                    open_price=price_data.current_price,  # 실제로는 1분봉 데이터 필요
                    high_price=price_data.current_price,
                    low_price=price_data.current_price,
                    close_price=price_data.current_price,
                    volume=price_data.volume
                )
                
                # 종목 데이터 업데이트
                stock = self.stocks[stock_code]
                stock.add_ohlcv(ohlcv)
                
                #self.logger.debug(f"데이터 수집 완료: {stock_code} - 가격: {price_data.current_price:,.0f}원")
            
        except Exception as e:
            self.logger.error(f"종목 데이터 수집 실패 {stock_code}: {e}")
    
    def _get_current_price_sync(self, stock_code: str) -> Any:
        """현재가 조회 (동기 버전)"""
        return self.broker.get_current_price(stock_code)
    
    async def get_1min_ohlcv(self, stock_code: str, count: int = 30) -> Any:
        """1분봉 OHLCV 데이터 조회"""
        try:
            # 1분봉 데이터 조회 (타임아웃 15초)
            ohlcv_data = await run_with_timeout(
                self.executor,
                self._get_ohlcv_sync,
                stock_code, "1", count,
                timeout_seconds=15,
                default=None
            )
            
            return ohlcv_data
            
        except Exception as e:
            self.logger.error(f"1분봉 데이터 조회 실패 {stock_code}: {e}")
            return None
    
    def _get_ohlcv_sync(self, stock_code: str, period: str, days: int) -> Any:
        """OHLCV 데이터 조회 (동기 버전)"""
        return self.broker.get_ohlcv_data(stock_code, period, days)
    
    def get_stock(self, stock_code: str) -> Optional[Stock]:
        """종목 정보 반환"""
        return self.stocks.get(stock_code)
    
    def get_all_stocks(self) -> Dict[str, Stock]:
        """모든 종목 정보 반환"""
        return self.stocks.copy()
    
    def get_candidate_stocks(self) -> List[Stock]:
        """후보 종목들만 반환"""
        return [stock for stock in self.stocks.values() if stock.is_candidate]
    
    def has_stock(self, stock_code: str) -> bool:
        """종목 존재 여부 확인"""
        return stock_code in self.stocks
    
    async def collect_once(self) -> None:
        """1회 데이터 수집 (메인루프에서 호출)"""
        try:
            await self._collect_all_stocks_data()
        except Exception as e:
            self.logger.error(f"1회 데이터 수집 오류: {e}")

    def stop_collection(self) -> None:
        """데이터 수집 중단"""
        self.is_running = False
        self.logger.info("실시간 데이터 수집 중단")
    
    def __del__(self) -> None:
        """소멸자"""
        if hasattr(self, 'executor'):
            self.executor.shutdown(wait=False)