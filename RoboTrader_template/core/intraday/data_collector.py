"""
장중 종목 데이터 수집 모듈

과거 분봉 데이터 및 일봉 데이터 수집 로직을 담당합니다.
"""
import asyncio
from datetime import datetime, timedelta
from typing import Dict, Optional, Any, TYPE_CHECKING
import pandas as pd

from utils.logger import setup_logger
from utils.korean_time import now_kst
from config.market_hours import MarketHours
from api.kis_chart_api import (
    get_inquire_time_itemchartprice,
    get_full_trading_day_data_async,
    get_div_code_for_stock
)
from core.intraday_data_utils import (
    calculate_time_range_minutes,
    validate_minute_data_continuity,
)

if TYPE_CHECKING:
    from core.intraday_stock_manager import IntradayStockManager

logger = setup_logger(__name__)


class IntradayDataCollector:
    """
    장중 종목 데이터 수집 클래스

    과거 분봉 데이터 및 일봉 데이터 수집을 담당합니다.
    """

    def __init__(self, manager: 'IntradayStockManager'):
        """
        Args:
            manager: IntradayStockManager 인스턴스
        """
        self.manager = manager
        self.broker = manager.broker
        self.logger = setup_logger(__name__)

    async def collect_daily_data_only(self, stock_code: str) -> bool:
        """
        리밸런싱 모드: 일봉 데이터만 수집 (분봉 데이터 불필요)

        Args:
            stock_code: 종목코드

        Returns:
            bool: 수집 성공 여부
        """
        try:
            with self.manager._lock:
                if stock_code not in self.manager.selected_stocks:
                    return False

                stock_data = self.manager.selected_stocks[stock_code]
                selected_time = stock_data.selected_time

            self.logger.info(f"📊 {stock_code} 일봉 데이터만 수집 (리밸런싱 모드)")

            # 일봉 데이터 조회 (최근 30일)
            daily_data = self.broker.get_ohlcv_data(stock_code, "D", 30)

            if daily_data is None or daily_data.empty:
                self.logger.error(f"❌ {stock_code} 일봉 데이터 조회 실패 - 종목 추가 중단")
                with self.manager._lock:
                    if stock_code in self.manager.selected_stocks:
                        del self.manager.selected_stocks[stock_code]
                return False

            # 메모리에 저장
            with self.manager._lock:
                if stock_code in self.manager.selected_stocks:
                    self.manager.selected_stocks[stock_code].daily_data = daily_data
                    self.manager.selected_stocks[stock_code].historical_data = pd.DataFrame()
                    self.manager.selected_stocks[stock_code].data_complete = True
                    self.manager.selected_stocks[stock_code].last_update = now_kst()

            self.logger.info(f"✅ {stock_code} 일봉 데이터 수집 완료: {len(daily_data)}개")

            # DB에도 저장
            await self._save_daily_to_db(stock_code, daily_data)

            return True

        except Exception as e:
            self.logger.error(f"❌ {stock_code} 일봉 데이터 수집 오류: {e}")
            with self.manager._lock:
                if stock_code in self.manager.selected_stocks:
                    del self.manager.selected_stocks[stock_code]
            return False

    async def _save_daily_to_db(self, stock_code: str, daily_data: pd.DataFrame) -> bool:
        """일봉 데이터를 DB에 저장"""
        try:
            from core.ml_data_collector import MLDataCollector
            from pathlib import Path

            db_path = Path(__file__).parent.parent.parent / "data" / "robotrader.db"
            collector = MLDataCollector(str(db_path))

            success = await asyncio.to_thread(
                collector._save_daily_prices_to_db,
                stock_code,
                daily_data
            )

            if success:
                self.logger.info(f"💾 {stock_code} 일봉 데이터 DB 저장 완료")
            else:
                self.logger.debug(f"⚠️ {stock_code} 일봉 데이터 DB 저장 실패")

            return success

        except Exception as e:
            self.logger.error(f"❌ {stock_code} 일봉 데이터 DB 저장 오류: {e}")
            return False

    async def collect_historical_data(self, stock_code: str) -> bool:
        """
        당일 08:00부터 선정시점까지의 전체 분봉 데이터 수집

        Args:
            stock_code: 종목코드

        Returns:
            bool: 수집 성공 여부
        """
        try:
            with self.manager._lock:
                if stock_code not in self.manager.selected_stocks:
                    return False

                stock_data = self.manager.selected_stocks[stock_code]
                selected_time = stock_data.selected_time

            self.logger.info(f"📈 {stock_code} 전체 거래시간 분봉 데이터 수집 시작")
            self.logger.info(f"   선정 시간: {selected_time.strftime('%H:%M:%S')}")

            # 동적 시장 거래시간 가져오기
            market_hours = MarketHours.get_market_hours('KRX', selected_time)
            market_open = market_hours['market_open']
            start_time_str = market_open.strftime('%H%M%S')

            target_date = selected_time.strftime("%Y%m%d")
            target_hour = selected_time.strftime("%H%M%S")

            self.logger.info(f"📈 {stock_code} 과거 데이터 수집: {market_open.strftime('%H:%M')} ~ {selected_time.strftime('%H:%M:%S')}")

            historical_data = await get_full_trading_day_data_async(
                stock_code=stock_code,
                target_date=target_date,
                selected_time=target_hour,
                start_time=start_time_str
            )

            if historical_data is None or historical_data.empty:
                historical_data = await self._retry_with_adjusted_time(
                    stock_code, target_date, target_hour, start_time_str, selected_time
                )

                if historical_data is None or historical_data.empty:
                    self.logger.error(f"❌ {stock_code} 당일 전체 분봉 데이터 조회 실패")
                    return await self.collect_historical_data_fallback(stock_code)

            # 당일 데이터만 필터링
            historical_data = self._filter_today_data(historical_data, selected_time)

            if historical_data.empty:
                self.logger.error(f"❌ {stock_code} 당일 데이터 없음")
                return await self.collect_historical_data_fallback(stock_code)

            # 시간순 정렬 및 필터링
            filtered_data = self._sort_and_filter_by_time(historical_data, selected_time)

            # 1분봉 연속성 검증
            if not filtered_data.empty:
                validation_result = validate_minute_data_continuity(filtered_data, stock_code, self.logger)
                if not validation_result['valid']:
                    self.logger.error(f"❌ {stock_code} 1분봉 연속성 검증 실패: {validation_result['reason']}")
                    return await self.collect_historical_data_fallback(stock_code)

            # 메모리에 저장
            with self.manager._lock:
                if stock_code in self.manager.selected_stocks:
                    self.manager.selected_stocks[stock_code].historical_data = filtered_data
                    self.manager.selected_stocks[stock_code].daily_data = pd.DataFrame()
                    self.manager.selected_stocks[stock_code].data_complete = True
                    self.manager.selected_stocks[stock_code].last_update = now_kst()

            # 로깅
            self._log_collection_result(stock_code, filtered_data, market_open, selected_time)

            return True

        except Exception as e:
            self.logger.error(f"❌ {stock_code} 전체 거래시간 분봉 데이터 수집 오류: {e}")
            return await self.collect_historical_data_fallback(stock_code)

    async def _retry_with_adjusted_time(
        self, stock_code: str, target_date: str, target_hour: str,
        start_time_str: str, selected_time: datetime
    ) -> Optional[pd.DataFrame]:
        """시간 조정하여 재시도"""
        try:
            selected_time_dt = datetime.strptime(target_hour, "%H%M%S")
            new_time_dt = selected_time_dt + timedelta(minutes=1)
            new_target_hour = new_time_dt.strftime("%H%M%S")

            if new_target_hour > "153000":
                new_target_hour = now_kst().strftime("%H%M%S")

            self.logger.warning(f"🔄 {stock_code} 시간 조정하여 재시도: {target_hour} → {new_target_hour}")

            historical_data = await get_full_trading_day_data_async(
                stock_code=stock_code,
                target_date=target_date,
                selected_time=new_target_hour,
                start_time=start_time_str
            )

            if historical_data is not None and not historical_data.empty:
                with self.manager._lock:
                    if stock_code in self.manager.selected_stocks:
                        new_selected_time = selected_time.replace(
                            hour=new_time_dt.hour,
                            minute=new_time_dt.minute,
                            second=new_time_dt.second
                        )
                        self.manager.selected_stocks[stock_code].selected_time = new_selected_time
                        self.logger.info(f"✅ {stock_code} 시간 조정 성공")

            return historical_data

        except Exception as e:
            self.logger.error(f"❌ {stock_code} 시간 조정 중 오류: {e}")
            return None

    def _filter_today_data(self, data: pd.DataFrame, selected_time: datetime) -> pd.DataFrame:
        """당일 데이터만 필터링"""
        today_str = selected_time.strftime('%Y%m%d')
        before_count = len(data)

        if 'date' in data.columns:
            data = data[data['date'].astype(str) == today_str].copy()
        elif 'datetime' in data.columns:
            data['date_str'] = pd.to_datetime(data['datetime']).dt.strftime('%Y%m%d')
            data = data[data['date_str'] == today_str].copy()
            if 'date_str' in data.columns:
                data = data.drop('date_str', axis=1)

        if before_count != len(data):
            removed = before_count - len(data)
            self.logger.warning(f"⚠️ 전날 데이터 {removed}건 제외")

        return data

    def _sort_and_filter_by_time(self, data: pd.DataFrame, selected_time: datetime) -> pd.DataFrame:
        """시간순 정렬 및 선정 시점 이전 데이터만 필터링"""
        if 'datetime' in data.columns:
            data = data.sort_values('datetime').reset_index(drop=True)
            selected_time_naive = selected_time.replace(tzinfo=None)
            return data[data['datetime'] <= selected_time_naive].copy()
        elif 'time' in data.columns:
            data = data.sort_values('time').reset_index(drop=True)
            selected_time_str = selected_time.strftime("%H%M%S")
            data['time_str'] = data['time'].astype(str).str.zfill(6)
            filtered = data[data['time_str'] <= selected_time_str].copy()
            if 'time_str' in filtered.columns:
                filtered = filtered.drop('time_str', axis=1)
            return filtered
        return data.copy()

    def _log_collection_result(
        self, stock_code: str, data: pd.DataFrame,
        market_open: datetime, selected_time: datetime
    ):
        """수집 결과 로깅"""
        data_count = len(data)
        if data_count > 0:
            if 'time' in data.columns:
                start_time = data.iloc[0].get('time', 'N/A')
                end_time = data.iloc[-1].get('time', 'N/A')
            elif 'datetime' in data.columns:
                start_dt = data.iloc[0].get('datetime')
                end_dt = data.iloc[-1].get('datetime')
                start_time = start_dt.strftime('%H%M%S') if start_dt else 'N/A'
                end_time = end_dt.strftime('%H%M%S') if end_dt else 'N/A'
            else:
                start_time = end_time = 'N/A'

            time_range_minutes = calculate_time_range_minutes(start_time, end_time)

            self.logger.info(f"✅ {stock_code} 당일 전체 분봉 수집 성공!")
            self.logger.info(f"   총 데이터: {data_count}건, 시간 범위: {time_range_minutes}분")

            expected_3min_count = data_count // 3
            if expected_3min_count >= 5:
                self.logger.info(f"   ✅ 신호 생성 조건 충족! (3분봉 {expected_3min_count}개)")
            else:
                self.logger.warning(f"   ⚠️ 3분봉 데이터 부족: {expected_3min_count}/5")

    async def collect_historical_data_fallback(self, stock_code: str) -> bool:
        """
        과거 분봉 데이터 수집 폴백 함수 (기존 방식)

        Args:
            stock_code: 종목코드

        Returns:
            bool: 수집 성공 여부
        """
        try:
            with self.manager._lock:
                if stock_code not in self.manager.selected_stocks:
                    return False

                stock_data = self.manager.selected_stocks[stock_code]
                selected_time = stock_data.selected_time

            self.logger.warning(f"🔄 {stock_code} 폴백 방식으로 과거 분봉 데이터 수집")

            target_hour = selected_time.strftime("%H%M%S")
            div_code = get_div_code_for_stock(stock_code)

            result = get_inquire_time_itemchartprice(
                div_code=div_code,
                stock_code=stock_code,
                input_hour=target_hour,
                past_data_yn="Y"
            )

            if result is None:
                result = await self._retry_fallback_with_adjusted_time(
                    stock_code, div_code, target_hour, selected_time
                )

                if result is None:
                    self.logger.error(f"❌ {stock_code} 폴백 분봉 데이터 조회 실패")
                    return False

            summary_df, chart_df = result

            if chart_df.empty:
                self.logger.warning(f"⚠️ {stock_code} 폴백 분봉 데이터 없음")
                with self.manager._lock:
                    if stock_code in self.manager.selected_stocks:
                        self.manager.selected_stocks[stock_code].historical_data = pd.DataFrame()
                        self.manager.selected_stocks[stock_code].data_complete = True
                return True

            # 선정 시점 이전 데이터만 필터링
            if 'datetime' in chart_df.columns:
                selected_time_naive = selected_time.replace(tzinfo=None)
                historical_data = chart_df[chart_df['datetime'] <= selected_time_naive].copy()
            else:
                historical_data = chart_df.copy()

            # 메모리에 저장
            with self.manager._lock:
                if stock_code in self.manager.selected_stocks:
                    self.manager.selected_stocks[stock_code].historical_data = historical_data
                    self.manager.selected_stocks[stock_code].data_complete = True
                    self.manager.selected_stocks[stock_code].last_update = now_kst()

            data_count = len(historical_data)
            if data_count > 0:
                self.logger.info(f"✅ {stock_code} 폴백 분봉 수집 완료: {data_count}건")
                self.logger.warning(f"⚠️ 제한된 데이터 범위 (API 제한으로 최대 30분봉)")

            return True

        except Exception as e:
            self.logger.error(f"❌ {stock_code} 폴백 분봉 데이터 수집 오류: {e}")
            return False

    async def _retry_fallback_with_adjusted_time(
        self, stock_code: str, div_code: str,
        target_hour: str, selected_time: datetime
    ):
        """폴백 방식 시간 조정 재시도"""
        try:
            selected_time_dt = datetime.strptime(target_hour, "%H%M%S")
            new_time_dt = selected_time_dt + timedelta(minutes=1)
            new_target_hour = new_time_dt.strftime("%H%M%S")

            if new_target_hour > "153000":
                new_target_hour = now_kst().strftime("%H%M%S")

            self.logger.warning(f"🔄 {stock_code} 폴백 시간 조정: {target_hour} → {new_target_hour}")

            result = get_inquire_time_itemchartprice(
                div_code=div_code,
                stock_code=stock_code,
                input_hour=new_target_hour,
                past_data_yn="Y"
            )

            if result is not None:
                with self.manager._lock:
                    if stock_code in self.manager.selected_stocks:
                        new_selected_time = selected_time.replace(
                            hour=new_time_dt.hour,
                            minute=new_time_dt.minute,
                            second=new_time_dt.second
                        )
                        self.manager.selected_stocks[stock_code].selected_time = new_selected_time

            return result

        except Exception as e:
            self.logger.error(f"❌ {stock_code} 폴백 시간 조정 오류: {e}")
            return None
