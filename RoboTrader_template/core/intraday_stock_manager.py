"""
장중 종목 선정 및 과거 분봉 데이터 관리

이 모듈은 Facade 패턴을 사용하여 하위 모듈들을 통합합니다.
실제 로직은 core/intraday/ 패키지의 개별 모듈들에 구현되어 있습니다.
"""
from datetime import datetime
from typing import Dict, List, Optional, Any
import pandas as pd
import threading

from utils.logger import setup_logger
from utils.korean_time import now_kst, is_market_open
from config.market_hours import MarketHours
from core.dynamic_batch_calculator import DynamicBatchCalculator
from core.post_market_data_saver import PostMarketDataSaver

# 하위 모듈 임포트
from core.intraday.models import StockMinuteData
from core.intraday.data_collector import IntradayDataCollector
from core.intraday.realtime_updater import RealtimeDataUpdater
from core.intraday.data_quality import DataQualityChecker
from core.intraday.price_service import PriceService

logger = setup_logger(__name__)

# 하위 호환성을 위해 StockMinuteData를 이 모듈에서도 export
__all__ = ['IntradayStockManager', 'StockMinuteData']


class IntradayStockManager:
    """
    장중 종목 선정 및 과거 분봉 데이터 관리 클래스

    주요 기능:
    1. 조건검색으로 선정된 종목의 과거 분봉 데이터 수집
    2. 메모리에서 효율적인 데이터 관리
    3. 실시간 분봉 데이터 업데이트
    4. 데이터 분석을 위한 편의 함수 제공

    이 클래스는 Facade 패턴을 사용하여 다음 하위 모듈들을 통합합니다:
    - IntradayDataCollector: 데이터 수집
    - RealtimeDataUpdater: 실시간 업데이트
    - DataQualityChecker: 품질 검사
    - PriceService: 현재가 조회
    """

    def __init__(self, broker, config=None) -> None:
        """
        초기화

        Args:
            broker: KISBroker 인스턴스 (duck typing)
            config: 거래 설정 (선택, 리밸런싱 모드 확인용)
        """
        self.broker = broker
        self.config = config
        self.logger = setup_logger(__name__)

        # 메모리 저장소
        self.selected_stocks: Dict[str, StockMinuteData] = {}
        self.selection_history: List[Dict[str, Any]] = []

        # 설정
        self.max_stocks = 80

        # 동기화
        self._lock = threading.RLock()

        # 동적 배치 계산기
        self.batch_calculator = DynamicBatchCalculator()

        # 장 마감 후 데이터 저장기
        self.data_saver = PostMarketDataSaver()

        # 하위 모듈 초기화
        self.data_collector = IntradayDataCollector(self)
        self.realtime_updater = RealtimeDataUpdater(self)
        self.quality_checker = DataQualityChecker(self)
        self.price_service = PriceService(self)

        self.logger.info("🎯 장중 종목 관리자 초기화 완료")

    async def add_selected_stock(self, stock_code: str, stock_name: str,
                                selection_reason: str = "") -> bool:
        """
        조건검색으로 선정된 종목 추가 (비동기)

        Args:
            stock_code: 종목코드
            stock_name: 종목명
            selection_reason: 선정 사유

        Returns:
            bool: 추가 성공 여부
        """
        try:
            with self._lock:
                current_time = now_kst()

                if stock_code in self.selected_stocks:
                    return True

                if len(self.selected_stocks) >= self.max_stocks:
                    self.logger.warning(f"⚠️ 최대 관리 종목 수({self.max_stocks})에 도달")
                    return False

                if not is_market_open():
                    self.logger.warning(f"⚠️ 장 시간이 아님. {stock_code} 추가 보류")

                # 종목 데이터 객체 생성
                stock_data = StockMinuteData(
                    stock_code=stock_code,
                    stock_name=stock_name,
                    selected_time=current_time
                )

                self.selected_stocks[stock_code] = stock_data

                self.selection_history.append({
                    'stock_code': stock_code,
                    'stock_name': stock_name,
                    'selected_time': current_time,
                    'selection_reason': selection_reason,
                    'market_time': current_time.strftime('%H:%M:%S')
                })

            # 과거 데이터 수집
            self.logger.info(f"📈 {stock_code} 과거 데이터 수집 시작...")

            if hasattr(self, 'config') and getattr(self.config, 'rebalancing_mode', False):
                success = await self.data_collector.collect_daily_data_only(stock_code)
            else:
                success = await self.data_collector.collect_historical_data(stock_code)

                # 분봉 수집과 별도로 일봉 데이터도 DB에 저장 (매수 판단에 필요)
                try:
                    daily_data = self.broker.get_ohlcv_data(stock_code, "D", 140)
                    if daily_data is not None and not daily_data.empty:
                        await self.data_collector._save_daily_to_db(stock_code, daily_data)
                    else:
                        self.logger.warning(f"{stock_code} 일봉 데이터 조회 실패 - 매수 판단 불가 가능")
                except Exception as e:
                    self.logger.warning(f"{stock_code} 일봉 데이터 DB 저장 실패 (매수 판단 영향 가능): {e}")

            # 시장 시작 5분 이내 선정 처리
            current_time = now_kst()
            market_hours = MarketHours.get_market_hours('KRX', current_time)
            market_open = market_hours['market_open']
            is_early_selection = (
                current_time.hour == market_open.hour and
                current_time.minute < market_open.minute + 5
            )

            if not success and is_early_selection:
                self.logger.warning(f"⚠️ {stock_code} 장초반 데이터 부족, 나중에 재시도")
                with self._lock:
                    if stock_code in self.selected_stocks:
                        self.selected_stocks[stock_code].data_complete = False
                success = True

            if success:
                return True
            else:
                with self._lock:
                    if stock_code in self.selected_stocks:
                        del self.selected_stocks[stock_code]
                self.logger.error(f"❌ {stock_code} 과거 데이터 수집 실패")
                return False

        except Exception as e:
            with self._lock:
                if stock_code in self.selected_stocks:
                    del self.selected_stocks[stock_code]
            self.logger.error(f"❌ {stock_code} 종목 추가 오류: {e}")
            return False

    # ========================================
    # 데이터 수집 위임 메서드 (하위 호환성)
    # ========================================

    async def _collect_daily_data_only(self, stock_code: str) -> bool:
        """리밸런싱 모드: 일봉 데이터만 수집"""
        return await self.data_collector.collect_daily_data_only(stock_code)

    async def _collect_historical_data(self, stock_code: str) -> bool:
        """과거 분봉 데이터 수집"""
        return await self.data_collector.collect_historical_data(stock_code)

    async def _collect_historical_data_fallback(self, stock_code: str) -> bool:
        """과거 분봉 데이터 수집 폴백"""
        return await self.data_collector.collect_historical_data_fallback(stock_code)

    # ========================================
    # 실시간 업데이트 위임 메서드
    # ========================================

    async def update_realtime_data(self, stock_code: str) -> bool:
        """실시간 분봉 데이터 업데이트"""
        return await self.realtime_updater.update_realtime_data(stock_code)

    async def batch_update_realtime_data(self) -> None:
        """모든 관리 종목의 실시간 데이터 일괄 업데이트"""
        return await self.realtime_updater.batch_update_realtime_data()

    # ========================================
    # 현재가 조회 위임 메서드
    # ========================================

    def get_current_price_for_sell(self, stock_code: str) -> Optional[Dict[str, Any]]:
        """매도 판단용 실시간 현재가 조회"""
        return self.price_service.get_current_price_for_sell(stock_code)

    def get_cached_current_price(self, stock_code: str) -> Optional[Dict[str, Any]]:
        """캐시된 현재가 정보 조회"""
        return self.price_service.get_cached_current_price(stock_code)

    # ========================================
    # 데이터 조회 메서드
    # ========================================

    def get_stock_data(self, stock_code: str) -> Optional[StockMinuteData]:
        """종목의 전체 데이터 조회"""
        with self._lock:
            return self.selected_stocks.get(stock_code)

    def get_combined_chart_data(self, stock_code: str) -> Optional[pd.DataFrame]:
        """
        종목의 당일 전체 차트 데이터 조회 (08:00~현재, 완성된 봉만)
        """
        try:
            with self._lock:
                if stock_code not in self.selected_stocks:
                    return None

                stock_data = self.selected_stocks[stock_code]
                historical_data = stock_data.historical_data.copy() if not stock_data.historical_data.empty else pd.DataFrame()
                realtime_data = stock_data.realtime_data.copy() if not stock_data.realtime_data.empty else pd.DataFrame()

            # 데이터 결합
            if historical_data.empty and realtime_data.empty:
                return None
            elif historical_data.empty:
                combined_data = realtime_data.copy()
                return None
            elif realtime_data.empty:
                combined_data = historical_data.copy()
                if len(combined_data) < 15:
                    combined_data = self._try_auto_collect(stock_code, combined_data)
                    if combined_data is None:
                        return None
            else:
                combined_data = pd.concat([historical_data, realtime_data], ignore_index=True)

            if combined_data.empty:
                return None

            # 당일 데이터만 필터링
            combined_data = self._filter_today_data(combined_data)

            if combined_data.empty:
                return None

            # 중복 제거 및 정렬
            combined_data = self._deduplicate_and_sort(combined_data)

            return combined_data

        except Exception as e:
            self.logger.error(f"❌ {stock_code} 결합 차트 데이터 오류: {e}")
            return None

    def _filter_today_data(self, data: pd.DataFrame) -> pd.DataFrame:
        """당일 데이터만 필터링"""
        today_str = now_kst().strftime('%Y%m%d')

        if 'date' in data.columns:
            data = data[data['date'].astype(str) == today_str].copy()
        elif 'datetime' in data.columns:
            data['date_str'] = pd.to_datetime(data['datetime']).dt.strftime('%Y%m%d')
            data = data[data['date_str'] == today_str].copy()
            data = data.drop('date_str', axis=1, errors='ignore')

        return data

    def _deduplicate_and_sort(self, data: pd.DataFrame) -> pd.DataFrame:
        """중복 제거 및 정렬"""
        if 'datetime' in data.columns:
            data = data.drop_duplicates(subset=['datetime'], keep='last')
            data = data.sort_values('datetime').reset_index(drop=True)
        elif 'time' in data.columns:
            data = data.drop_duplicates(subset=['time'], keep='last')
            data = data.sort_values('time').reset_index(drop=True)
        return data

    def _try_auto_collect(self, stock_code: str, current_data: pd.DataFrame) -> Optional[pd.DataFrame]:
        """데이터 부족 시 자동 수집 시도"""
        try:
            from trade_analysis.data_sufficiency_checker import collect_minute_data_from_api

            today = now_kst().strftime('%Y%m%d')
            self.logger.info(f"🔄 {stock_code} 데이터 부족으로 자동 수집...")

            minute_data = collect_minute_data_from_api(stock_code, today)
            if minute_data is not None and not minute_data.empty:
                with self._lock:
                    if stock_code in self.selected_stocks:
                        self.selected_stocks[stock_code].historical_data = minute_data
                        self.selected_stocks[stock_code].data_complete = True
                        self.selected_stocks[stock_code].last_update = now_kst()

                self.logger.info(f"✅ {stock_code} 자동 수집 완료: {len(minute_data)}개")
                return minute_data
            else:
                self.logger.warning(f"❌ {stock_code} 자동 수집 실패")
                return None

        except Exception as e:
            self.logger.error(f"❌ {stock_code} 자동 수집 오류: {e}")
            return None

    def get_stock_analysis(self, stock_code: str) -> Optional[Dict[str, Any]]:
        """종목 분석 정보 조회"""
        try:
            combined_data = self.get_combined_chart_data(stock_code)

            if combined_data is None or combined_data.empty:
                return None

            with self._lock:
                if stock_code not in self.selected_stocks:
                    return None
                stock_data = self.selected_stocks[stock_code]

            analysis = {
                'stock_code': stock_code,
                'stock_name': stock_data.stock_name,
                'selected_time': stock_data.selected_time,
                'data_complete': stock_data.data_complete,
                'last_update': stock_data.last_update,
                'total_minutes': len(combined_data),
                'historical_minutes': len(stock_data.historical_data),
                'realtime_minutes': len(stock_data.realtime_data)
            }

            if 'close' in combined_data.columns and len(combined_data) > 0:
                prices = combined_data['close']
                analysis.update({
                    'first_price': float(prices.iloc[0]) if len(prices) > 0 else 0,
                    'current_price': float(prices.iloc[-1]) if len(prices) > 0 else 0,
                    'high_price': float(prices.max()),
                    'low_price': float(prices.min()),
                    'price_change': float(prices.iloc[-1] - prices.iloc[0]) if len(prices) > 1 else 0,
                    'price_change_rate': float((prices.iloc[-1] - prices.iloc[0]) / prices.iloc[0] * 100) if len(prices) > 1 and prices.iloc[0] > 0 else 0
                })

            if 'volume' in combined_data.columns:
                volumes = combined_data['volume']
                analysis.update({
                    'total_volume': int(volumes.sum()),
                    'avg_volume': int(volumes.mean()) if len(volumes) > 0 else 0,
                    'max_volume': int(volumes.max()) if len(volumes) > 0 else 0
                })

            return analysis

        except Exception as e:
            self.logger.error(f"❌ {stock_code} 분석 정보 오류: {e}")
            return None

    def get_all_stocks_summary(self) -> Dict[str, Any]:
        """모든 관리 종목 요약 정보"""
        try:
            with self._lock:
                stock_codes = list(self.selected_stocks.keys())

            summary = {
                'total_stocks': len(stock_codes),
                'max_stocks': self.max_stocks,
                'current_time': now_kst().strftime('%Y-%m-%d %H:%M:%S'),
                'stocks': []
            }

            for stock_code in stock_codes:
                analysis = self.get_stock_analysis(stock_code)
                if analysis:
                    summary['stocks'].append({
                        'stock_code': stock_code,
                        'stock_name': analysis['stock_name'],
                        'selected_time': analysis['selected_time'].strftime('%H:%M:%S'),
                        'data_complete': analysis['data_complete'],
                        'total_minutes': analysis['total_minutes'],
                        'price_change_rate': analysis.get('price_change_rate', 0)
                    })

            return summary

        except Exception as e:
            self.logger.error(f"❌ 전체 요약 정보 오류: {e}")
            return {}

    def remove_stock(self, stock_code: str) -> bool:
        """종목 제거"""
        try:
            with self._lock:
                if stock_code in self.selected_stocks:
                    stock_name = self.selected_stocks[stock_code].stock_name
                    del self.selected_stocks[stock_code]
                    self.logger.info(f"🗑️ {stock_code}({stock_name}) 제거")
                    return True
                return False

        except Exception as e:
            self.logger.error(f"❌ {stock_code} 제거 오류: {e}")
            return False

    # ========================================
    # 품질 검사 위임 메서드
    # ========================================

    def _check_data_quality(self, stock_code: str) -> dict:
        """실시간 데이터 품질 검사"""
        return self.quality_checker.check_data_quality(stock_code)

    # ========================================
    # 하위 호환성 유지 메서드 (deprecated)
    # ========================================

    def _save_minute_data_to_file(self) -> None:
        """[DEPRECATED] PostMarketDataSaver 사용"""
        self.logger.warning("⚠️ _save_minute_data_to_file은 deprecated입니다.")
        return self.data_saver.save_minute_data_to_file(self)
