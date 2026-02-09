"""
장중 데이터 품질 검사 모듈

실시간 데이터의 품질을 검사하고 이상치를 감지합니다.
"""
from typing import Dict, List, Optional, TYPE_CHECKING
import pandas as pd

from utils.logger import setup_logger
from utils.korean_time import now_kst
from core.intraday_data_utils import validate_today_data

if TYPE_CHECKING:
    from core.intraday_stock_manager import IntradayStockManager

logger = setup_logger(__name__)


class DataQualityChecker:
    """
    데이터 품질 검사 클래스

    실시간 데이터의 품질을 검사하고 이상치를 감지합니다.
    """

    def __init__(self, manager: 'IntradayStockManager') -> None:
        """
        Args:
            manager: IntradayStockManager 인스턴스
        """
        self.manager = manager
        self.logger = setup_logger(__name__)

    def check_data_quality(self, stock_code: str) -> dict:
        """
        실시간 데이터 품질 검사

        Args:
            stock_code: 종목코드

        Returns:
            dict: 품질 검사 결과 {'has_issues': bool, 'issues': list}
        """
        try:
            with self.manager._lock:
                stock_data = self.manager.selected_stocks.get(stock_code)

            if not stock_data:
                return {'has_issues': True, 'issues': ['데이터 없음']}

            # historical_data와 realtime_data 합치기
            all_data = pd.concat(
                [stock_data.historical_data, stock_data.realtime_data],
                ignore_index=True
            )

            if all_data.empty:
                return {'has_issues': True, 'issues': ['데이터 없음']}

            # 당일 데이터만 필터링
            all_data = self._filter_today_data(all_data, stock_code)

            if all_data.empty:
                return {'has_issues': True, 'issues': ['당일 데이터 없음']}

            # 중복 제거 및 정렬
            all_data = self._deduplicate_and_sort(all_data)

            issues = []
            data = all_data.to_dict('records')

            # 1. 데이터 양 검사
            if len(data) < 5:
                issues.append(f'데이터 부족 ({len(data)}개)')

            # 2. 시간 순서 및 연속성 검사
            time_issues = self._check_time_continuity(data)
            issues.extend(time_issues)

            # 3. 가격 이상치 검사
            price_issues = self._check_price_anomalies(data)
            issues.extend(price_issues)

            # 4. 데이터 지연 검사
            delay_issues = self._check_data_delay(data)
            issues.extend(delay_issues)

            # 5. 당일 날짜 검증
            date_issues = validate_today_data(all_data)
            issues.extend(date_issues)

            return {'has_issues': bool(issues), 'issues': issues}

        except Exception as e:
            return {'has_issues': True, 'issues': [f'품질검사 오류: {str(e)[:30]}']}

    def _filter_today_data(self, data: pd.DataFrame, stock_code: str) -> pd.DataFrame:
        """당일 데이터만 필터링"""
        today_str = now_kst().strftime('%Y%m%d')
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
            self.logger.warning(
                f"⚠️ {stock_code} 품질검사 시 전날 데이터 {removed}건 제외"
            )

        return data

    def _deduplicate_and_sort(self, data: pd.DataFrame) -> pd.DataFrame:
        """중복 제거 및 정렬"""
        if 'time' in data.columns:
            data = data.drop_duplicates(
                subset=['time'], keep='last'
            ).sort_values('time').reset_index(drop=True)
        elif 'datetime' in data.columns:
            data = data.drop_duplicates(
                subset=['datetime'], keep='last'
            ).sort_values('datetime').reset_index(drop=True)
        return data

    def _check_time_continuity(self, data: list) -> List[str]:
        """시간 순서 및 연속성 검사"""
        issues = []

        if len(data) < 2:
            return issues

        times = [row.get('time') for row in data if row.get('time')]

        if not times:
            return issues

        # 순서 확인
        if times != sorted(times):
            issues.append('시간 순서 오류')

        # 1분 간격 연속성 확인
        for i in range(1, len(times)):
            try:
                prev_time_str = str(times[i-1]).zfill(6)
                curr_time_str = str(times[i]).zfill(6)

                prev_hour = int(prev_time_str[:2])
                prev_min = int(prev_time_str[2:4])
                curr_hour = int(curr_time_str[:2])
                curr_min = int(curr_time_str[2:4])

                # 예상 다음 시간 계산
                if prev_min == 59:
                    expected_hour = prev_hour + 1
                    expected_min = 0
                else:
                    expected_hour = prev_hour
                    expected_min = prev_min + 1

                # 1분 간격이 아니면 누락
                if curr_hour != expected_hour or curr_min != expected_min:
                    issues.append(f'분봉 누락: {prev_time_str}→{curr_time_str}')
                    break
            except Exception as e:
                self.logger.debug(f"분봉 시간 연속성 검사 실패: {e}")

        return issues

    def _check_price_anomalies(self, data: list) -> List[str]:
        """가격 이상치 검사"""
        issues = []

        if len(data) < 2:
            return issues

        current_price = data[-1].get('close', 0)
        prev_price = data[-2].get('close', 0)

        if current_price > 0 and prev_price > 0:
            price_change = abs(current_price - prev_price) / prev_price
            if price_change > 0.3:  # 30% 이상 변동
                issues.append(f'가격 급변동 ({price_change*100:.1f}%)')

        return issues

    def _check_data_delay(self, data: list) -> List[str]:
        """데이터 지연 검사"""
        issues = []

        if not data:
            return issues

        latest_time_str = str(data[-1].get('time', '000000')).zfill(6)
        current_time = now_kst()

        try:
            latest_hour = int(latest_time_str[:2])
            latest_minute = int(latest_time_str[2:4])
            latest_time = current_time.replace(
                hour=latest_hour, minute=latest_minute,
                second=0, microsecond=0
            )

            time_diff = (current_time - latest_time).total_seconds()
            if time_diff > 300:  # 5분 이상 지연
                issues.append(f'데이터 지연 ({time_diff/60:.1f}분)')
        except Exception:
            issues.append('시간 파싱 오류')

        return issues
