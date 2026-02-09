"""
장중 실시간 데이터 업데이트 모듈

실시간 분봉 데이터 업데이트 및 배치 업데이트 로직을 담당합니다.
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
    get_div_code_for_stock
)
from core.realtime_data_logger import log_intraday_data

if TYPE_CHECKING:
    from core.intraday_stock_manager import IntradayStockManager

logger = setup_logger(__name__)


class RealtimeDataUpdater:
    """
    실시간 데이터 업데이트 클래스

    실시간 분봉 데이터 업데이트 및 배치 처리를 담당합니다.
    """

    def __init__(self, manager: 'IntradayStockManager') -> None:
        """
        Args:
            manager: IntradayStockManager 인스턴스
        """
        self.manager = manager
        self.logger = setup_logger(__name__)

    async def update_realtime_data(self, stock_code: str) -> bool:
        """
        실시간 분봉 데이터 업데이트 (매수 판단용) + 전날 데이터 이중 검증

        Args:
            stock_code: 종목코드

        Returns:
            bool: 업데이트 성공 여부
        """
        try:
            with self.manager._lock:
                if stock_code not in self.manager.selected_stocks:
                    return False

            # 1. 현재 보유한 전체 데이터 확인
            combined_data = self.manager.get_combined_chart_data(stock_code)

            # 2. 기본 데이터가 충분한지 체크
            if not self._check_sufficient_base_data(combined_data, stock_code):
                self.logger.warning(f"⚠️ {stock_code} 기본 데이터 부족, 전체 재수집 시도")
                return await self.manager.data_collector.collect_historical_data(stock_code)

            # 3. 최신 분봉 수집
            current_time = now_kst()
            latest_minute_data = await self._get_latest_minute_bar(stock_code, current_time)

            if latest_minute_data is None:
                current_hour = current_time.strftime("%H%M")
                if current_hour <= "0915":
                    self.logger.warning(f"⚠️ {stock_code} 장초반 실시간 업데이트 실패, 전체 재수집 시도")
                    return await self.manager.data_collector.collect_historical_data(stock_code)
                else:
                    self.logger.debug(f"📊 {stock_code} 최신 분봉 수집 실패, 기존 데이터 유지")
                    return True

            # 2차 검증: 당일 데이터 확인
            latest_minute_data = self._validate_today_data(latest_minute_data, current_time, stock_code)
            if latest_minute_data is None or latest_minute_data.empty:
                return False

            # 4. realtime_data에 최신 데이터 추가
            with self.manager._lock:
                if stock_code in self.manager.selected_stocks:
                    updated_realtime = self._merge_realtime_data(
                        stock_code, latest_minute_data, current_time
                    )

                    if updated_realtime is None or updated_realtime.empty:
                        return False

                    self.manager.selected_stocks[stock_code].realtime_data = updated_realtime
                    self.manager.selected_stocks[stock_code].last_update = current_time

            return True

        except Exception as e:
            self.logger.error(f"❌ {stock_code} 실시간 분봉 업데이트 오류: {e}")
            return False

    def _check_sufficient_base_data(self, combined_data: Optional[pd.DataFrame], stock_code: str) -> bool:
        """기본 데이터가 충분한지 체크"""
        try:
            if combined_data is None or combined_data.empty:
                return False

            current_time = now_kst()
            today_str = current_time.strftime('%Y%m%d')

            # 동적 시장 시작 시간
            market_hours = MarketHours.get_market_hours('KRX', current_time)
            market_open = market_hours['market_open']
            expected_start_hour = market_open.hour

            # 당일 데이터만 필터링
            if 'date' in combined_data.columns:
                today_data = combined_data[combined_data['date'].astype(str) == today_str].copy()
                if today_data.empty:
                    return False
                combined_data = today_data
            elif 'datetime' in combined_data.columns:
                try:
                    combined_data['date_str'] = pd.to_datetime(combined_data['datetime']).dt.strftime('%Y%m%d')
                    today_data = combined_data[combined_data['date_str'] == today_str].copy()
                    if today_data.empty:
                        return False
                    combined_data = today_data.drop('date_str', axis=1)
                except Exception as e:
                    self.logger.debug(f"datetime 컬럼 기반 날짜 필터링 실패: {e}")

            # 최소 데이터 개수 체크
            if len(combined_data) < 5:
                return False

            # 시작 시간 체크
            if 'time' in combined_data.columns:
                start_time_str = str(combined_data.iloc[0]['time']).zfill(6)
                start_hour = int(start_time_str[:2])
                if start_hour != expected_start_hour:
                    return False
            elif 'datetime' in combined_data.columns:
                start_dt = combined_data.iloc[0]['datetime']
                if hasattr(start_dt, 'hour') and start_dt.hour != expected_start_hour:
                    return False

            return True

        except Exception as e:
            self.logger.warning(f"⚠️ {stock_code} 기본 데이터 체크 오류: {e}")
            return False

    async def _get_latest_minute_bar(self, stock_code: str, current_time: datetime) -> Optional[pd.DataFrame]:
        """완성된 최신 분봉 수집"""
        try:
            # 완성된 마지막 분봉 시간 계산
            current_minute_start = current_time.replace(second=0, microsecond=0)
            last_completed_minute = current_minute_start - timedelta(minutes=1)
            target_hour = last_completed_minute.strftime("%H%M%S")
            today_str = current_time.strftime("%Y%m%d")

            div_code = get_div_code_for_stock(stock_code)

            result = get_inquire_time_itemchartprice(
                div_code=div_code,
                stock_code=stock_code,
                input_hour=target_hour,
                past_data_yn="Y"
            )

            if result is None:
                return None

            summary_df, chart_df = result

            if chart_df.empty:
                return None

            # 당일 데이터만 필터링
            chart_df = self._filter_today_data(chart_df, today_str, stock_code, target_hour)

            if chart_df is None or chart_df.empty:
                return None

            # 최근 2개 분봉 추출
            return self._extract_recent_bars(chart_df, target_hour, stock_code)

        except Exception as e:
            self.logger.error(f"❌ {stock_code} 최신 분봉 수집 오류: {e}")
            return None

    def _filter_today_data(
        self, chart_df: pd.DataFrame, today_str: str,
        stock_code: str, target_hour: str
    ) -> Optional[pd.DataFrame]:
        """당일 데이터만 필터링"""
        before_filter_count = len(chart_df)

        if 'date' in chart_df.columns:
            chart_df = chart_df[chart_df['date'].astype(str) == today_str].copy()
        elif 'datetime' in chart_df.columns:
            chart_df['_date_str'] = pd.to_datetime(chart_df['datetime']).dt.strftime('%Y%m%d')
            chart_df = chart_df[chart_df['_date_str'] == today_str].copy()
            if '_date_str' in chart_df.columns:
                chart_df = chart_df.drop('_date_str', axis=1)

        if before_filter_count != len(chart_df):
            removed = before_filter_count - len(chart_df)
            self.logger.warning(
                f"🚨 {stock_code} 실시간 업데이트에서 전날 데이터 {removed}건 제거"
            )

        if chart_df.empty:
            self.logger.error(f"❌ {stock_code} 전날 데이터만 반환됨 (요청: {target_hour})")
            return None

        return chart_df

    def _extract_recent_bars(
        self, chart_df: pd.DataFrame, target_hour: str, stock_code: str
    ) -> pd.DataFrame:
        """최근 2개 분봉 추출"""
        if 'time' in chart_df.columns and len(chart_df) > 0:
            chart_df_sorted = chart_df.sort_values('time')
            target_time = int(target_hour)

            # 1분 전 시간 계산
            prev_hour = int(target_hour[:2])
            prev_min = int(target_hour[2:4])
            if prev_min == 0:
                prev_hour = prev_hour - 1
                prev_min = 59
            else:
                prev_min = prev_min - 1
            prev_time = prev_hour * 10000 + prev_min * 100

            target_times = [prev_time, target_time]
            matched_data = chart_df_sorted[chart_df_sorted['time'].isin(target_times)]

            if not matched_data.empty:
                return matched_data.copy()
            else:
                return chart_df_sorted.tail(2).copy()
        else:
            return chart_df.copy()

    def _validate_today_data(
        self, data: pd.DataFrame, current_time: datetime, stock_code: str
    ) -> Optional[pd.DataFrame]:
        """당일 데이터 검증"""
        today_str = current_time.strftime("%Y%m%d")
        before_count = len(data)

        if 'date' in data.columns:
            data = data[data['date'].astype(str) == today_str].copy()
        elif 'datetime' in data.columns:
            data['_date_str'] = pd.to_datetime(data['datetime']).dt.strftime('%Y%m%d')
            data = data[data['_date_str'] == today_str].copy()
            if '_date_str' in data.columns:
                data = data.drop('_date_str', axis=1)

        if before_count != len(data):
            removed = before_count - len(data)
            self.logger.error(f"🚨 {stock_code} 2차 검증에서 전날 데이터 {removed}건 제거!")

        if data.empty:
            self.logger.error(f"❌ {stock_code} 2차 검증 실패")
            return None

        return data

    def _merge_realtime_data(
        self, stock_code: str, latest_data: pd.DataFrame, current_time: datetime
    ) -> Optional[pd.DataFrame]:
        """실시간 데이터 병합"""
        today_str = current_time.strftime("%Y%m%d")
        current_realtime = self.manager.selected_stocks[stock_code].realtime_data.copy()
        before_count = len(current_realtime)

        if current_realtime.empty:
            updated_realtime = latest_data
        else:
            updated_realtime = pd.concat([current_realtime, latest_data], ignore_index=True)

            if 'datetime' in updated_realtime.columns:
                updated_realtime = updated_realtime.drop_duplicates(
                    subset=['datetime'], keep='last'
                ).sort_values('datetime').reset_index(drop=True)
            elif 'time' in updated_realtime.columns:
                updated_realtime = updated_realtime.drop_duplicates(
                    subset=['time'], keep='last'
                ).sort_values('time').reset_index(drop=True)

        # 3차 검증
        before_final_count = len(updated_realtime)

        if 'date' in updated_realtime.columns:
            updated_realtime = updated_realtime[
                updated_realtime['date'].astype(str) == today_str
            ].copy()
        elif 'datetime' in updated_realtime.columns:
            updated_realtime['_date_str'] = pd.to_datetime(
                updated_realtime['datetime']
            ).dt.strftime('%Y%m%d')
            updated_realtime = updated_realtime[
                updated_realtime['_date_str'] == today_str
            ].copy()
            if '_date_str' in updated_realtime.columns:
                updated_realtime = updated_realtime.drop('_date_str', axis=1)

        if before_final_count != len(updated_realtime):
            removed = before_final_count - len(updated_realtime)
            self.logger.error(f"🚨 {stock_code} 3차 검증에서 {removed}건 제거!")

        if updated_realtime.empty:
            self.logger.error(f"❌ {stock_code} 3차 검증 실패")
            return None

        # 결과 로깅
        after_count = len(updated_realtime)
        new_added = after_count - before_count
        if new_added > 0:
            self.logger.debug(f"✅ {stock_code} realtime_data 업데이트: +{new_added}개")

        return updated_realtime

    async def batch_update_realtime_data(self) -> None:
        """모든 관리 종목의 실시간 데이터 일괄 업데이트"""
        try:
            current_time = now_kst()

            # 장 마감 시 데이터 저장
            self._check_and_save_market_close_data(current_time)

            with self.manager._lock:
                stock_codes = list(self.manager.selected_stocks.keys())

            if not stock_codes:
                return

            # 미완성 데이터 재수집
            await self._recollect_incomplete_stocks(stock_codes)

            # 품질 모니터링 초기화
            total_stocks = len(stock_codes)
            successful_minute_updates = 0
            successful_price_updates = 0
            quality_issues = []

            # 동적 배치 크기 계산
            batch_size, batch_delay = self.manager.batch_calculator.calculate_optimal_batch(total_stocks)

            for i in range(0, len(stock_codes), batch_size):
                batch = stock_codes[i:i + batch_size]

                # 분봉 및 현재가 업데이트
                minute_tasks = [self.update_realtime_data(code) for code in batch]
                price_tasks = [self._update_current_price_data(code) for code in batch]

                minute_results = await asyncio.gather(*minute_tasks, return_exceptions=True)
                price_results = await asyncio.gather(*price_tasks, return_exceptions=True)

                # 결과 처리
                for j, (minute_result, price_result) in enumerate(zip(minute_results, price_results)):
                    stock_code = batch[j]

                    if not isinstance(minute_result, Exception):
                        successful_minute_updates += 1
                        quality_check = self.manager.quality_checker.check_data_quality(stock_code)
                        if quality_check['has_issues']:
                            quality_issues.extend([f"{stock_code}: {issue}" for issue in quality_check['issues']])
                            # 분봉 누락 시 재수집
                            for issue in quality_check['issues']:
                                if '분봉 누락' in issue:
                                    asyncio.create_task(
                                        self.manager.data_collector.collect_historical_data(stock_code)
                                    )
                                    break

                    if not isinstance(price_result, Exception):
                        successful_price_updates += 1

                    # 실시간 데이터 로깅
                    self._log_realtime_data(stock_code, minute_result, price_result)

                if i + batch_size < len(stock_codes):
                    await asyncio.sleep(batch_delay)

            # 품질 리포트
            self._log_quality_report(
                total_stocks, successful_minute_updates,
                successful_price_updates, quality_issues
            )

        except Exception as e:
            self.logger.error(f"❌ 실시간 데이터 일괄 업데이트 오류: {e}")

    def _check_and_save_market_close_data(self, current_time: datetime) -> None:
        """장 마감 시 데이터 저장 체크"""
        market_hours = MarketHours.get_market_hours('KRX', current_time)
        market_close = market_hours['market_close']

        if current_time.hour == market_close.hour and current_time.minute >= market_close.minute:
            if not hasattr(self.manager, '_data_saved_today'):
                self.logger.info(f"🔔 장 마감 데이터 저장 시작...")
                self.manager.data_saver.save_all_data(self.manager)
                self.manager._data_saved_today = True
                self.logger.info(f"✅ 장 마감 데이터 저장 완료")

    async def _recollect_incomplete_stocks(self, stock_codes: list) -> None:
        """미완성 데이터 재수집"""
        incomplete_stocks = []
        with self.manager._lock:
            for code in stock_codes:
                stock_data = self.manager.selected_stocks.get(code)
                if stock_data and not stock_data.data_complete:
                    incomplete_stocks.append(code)

        if incomplete_stocks:
            self.logger.info(f"🔄 미완성 데이터 재수집: {len(incomplete_stocks)}개 종목")
            for stock_code in incomplete_stocks:
                try:
                    await self.manager.data_collector.collect_historical_data(stock_code)
                except Exception as e:
                    self.logger.error(f"❌ {stock_code} 재수집 오류: {e}")

    async def _update_current_price_data(self, stock_code: str) -> bool:
        """현재가 정보 업데이트"""
        try:
            current_price_info = self.manager.price_service.get_current_price_for_sell(stock_code)

            if current_price_info is None:
                return False

            with self.manager._lock:
                if stock_code in self.manager.selected_stocks:
                    self.manager.selected_stocks[stock_code].current_price_info = current_price_info

            return True

        except Exception as e:
            self.logger.error(f"❌ {stock_code} 현재가 업데이트 오류: {e}")
            return False

    def _log_realtime_data(self, stock_code: str, minute_result, price_result) -> None:
        """실시간 데이터 로깅"""
        try:
            stock_name = None
            with self.manager._lock:
                if stock_code in self.manager.selected_stocks:
                    stock_name = self.manager.selected_stocks[stock_code].stock_name

            if not stock_name:
                return

            minute_data = None
            if not isinstance(minute_result, Exception):
                with self.manager._lock:
                    if stock_code in self.manager.selected_stocks:
                        realtime_data = self.manager.selected_stocks[stock_code].realtime_data
                        if realtime_data is not None and not realtime_data.empty:
                            minute_data = realtime_data.tail(3)

            price_data = None
            if not isinstance(price_result, Exception):
                with self.manager._lock:
                    if stock_code in self.manager.selected_stocks:
                        price_info = self.manager.selected_stocks[stock_code].current_price_info
                        if price_info:
                            price_data = {
                                'current_price': price_info.get('current_price', 0),
                                'change_rate': price_info.get('change_rate', 0),
                                'volume': price_info.get('volume', 0),
                                'high_price': price_info.get('high_price', 0),
                                'low_price': price_info.get('low_price', 0),
                                'open_price': price_info.get('open_price', 0)
                            }

            log_intraday_data(stock_code, stock_name, minute_data, price_data, None)

        except Exception as e:
            self.logger.debug(f"실시간 데이터 로깅 실패: {e}")

    def _log_quality_report(
        self, total_stocks: int, successful_minute: int,
        successful_price: int, quality_issues: list
    ) -> None:
        """품질 리포트 로깅"""
        minute_rate = (successful_minute / total_stocks) * 100 if total_stocks > 0 else 0
        price_rate = (successful_price / total_stocks) * 100 if total_stocks > 0 else 0

        if minute_rate < 90 or price_rate < 80:
            self.logger.warning(
                f"⚠️ 품질 경고: 분봉 {minute_rate:.1f}%, 현재가 {price_rate:.1f}%"
            )

        if quality_issues:
            issues_to_log = quality_issues[:5]
            self.logger.warning(f"🔍 품질 이슈 {len(quality_issues)}건: {'; '.join(issues_to_log)}")
        else:
            self.logger.debug(
                f"✅ 업데이트 완료: 분봉 {successful_minute}/{total_stocks}, "
                f"현재가 {successful_price}/{total_stocks}"
            )
