"""
데이터 검증 및 X축 위치 계산 모듈
데이터 정제, 날짜 필터링, X축 위치 계산 기능 담당
"""
from typing import List
import pandas as pd

from utils.logger import setup_logger


class DataValidator:
    """데이터 검증 및 X축 위치 계산"""

    def __init__(self):
        self.logger = setup_logger(__name__)

    def validate_and_clean_data(self, data: pd.DataFrame,
                                target_date: str = None,
                                timeframe: str = '1min') -> pd.DataFrame:
        """
        데이터 검증 및 중복 제거

        Args:
            data: OHLCV 데이터프레임
            target_date: 대상 날짜 (YYYYMMDD 형식)
            timeframe: 시간프레임

        Returns:
            정제된 데이터프레임
        """
        try:
            self.logger.debug(f"데이터 검증 시작 ({timeframe}):")
            self.logger.debug(f"   - 입력 데이터: {len(data)}개")
            self.logger.debug(f"   - target_date: {target_date}")

            if data.empty:
                return data

            # 날짜 필터링 (target_date가 제공된 경우)
            if target_date:
                data = self._filter_by_date(data, target_date)

            if 'time' not in data.columns:
                return data

            # 시간 중복 제거
            original_count = len(data)
            cleaned_data = data.drop_duplicates(subset=['time'], keep='first')

            if len(cleaned_data) != original_count:
                self.logger.warning(
                    f"중복 시간 데이터 제거: {original_count} -> {len(cleaned_data)}")

            # 시간 순 정렬
            cleaned_data = cleaned_data.sort_values('time')

            # 인덱스 재설정
            cleaned_data = cleaned_data.reset_index(drop=True)

            return cleaned_data

        except Exception as e:
            self.logger.error(f"데이터 검증 오류: {e}")
            return data

    def _filter_by_date(self, data: pd.DataFrame, target_date: str) -> pd.DataFrame:
        """
        날짜 기준으로 데이터 필터링

        Args:
            data: OHLCV 데이터프레임
            target_date: 대상 날짜 (YYYYMMDD 형식)

        Returns:
            필터링된 데이터프레임
        """
        original_count = len(data)

        if 'datetime' in data.columns:
            # datetime 컬럼이 있는 경우
            data = data.copy()
            data['date_str'] = pd.to_datetime(data['datetime']).dt.strftime('%Y%m%d')
            self.logger.debug(f"   - datetime 기반 날짜 필터링")
            data = data[data['date_str'] == target_date].drop('date_str', axis=1)

        elif 'time' in data.columns:
            # time 컬럼이 있는 경우 - 형식 확인
            time_samples = data['time'].head(5).astype(str).tolist()
            self.logger.debug(f"   - time 컬럼 샘플: {time_samples}")

            # time이 HHMMSS 형식인지 YYYYMMDDHHMM 형식인지 확인
            first_time = str(data['time'].iloc[0])
            if len(first_time) <= 6:
                # HHMMSS 형식 - datetime 컬럼을 기준으로 필터링
                self.logger.debug(f"   - time이 HHMMSS 형식, datetime 컬럼으로 날짜 필터링")
                if 'datetime' in data.columns:
                    data = data.copy()
                    data['date_str'] = pd.to_datetime(data['datetime']).dt.strftime('%Y%m%d')
                    data = data[data['date_str'] == target_date].drop('date_str', axis=1)
                else:
                    self.logger.debug(f"   - datetime 컬럼 없음, 날짜 필터링 스킵")
            else:
                # YYYYMMDDHHMM 형식
                self.logger.debug(f"   - time이 YYYYMMDDHHMM 형식")
                data = data.copy()
                data['date_str'] = data['time'].astype(str).str[:8]
                data = data[data['date_str'] == target_date].drop('date_str', axis=1)

        if len(data) != original_count:
            self.logger.debug(
                f"   - 날짜 필터링 결과: {original_count} -> {len(data)} (target_date: {target_date})")
            if len(data) < original_count // 2:
                self.logger.warning(f"   데이터가 절반 이상 사라짐! 날짜 필터링 문제 의심")
        else:
            self.logger.debug(f"   - 날짜 필터링: 변화 없음")

        return data

    def calculate_x_positions(self, data: pd.DataFrame,
                              timeframe: str = '1min') -> List[float]:
        """
        시간프레임에 따른 x 위치 계산
        - 1분봉: 09:00부터의 실제 분 단위 인덱스 (0, 1, 2, 3...)
        - 5분봉: 연속 인덱스 (0, 1, 2, 3...) - 캔들들이 이어지도록
        - 3분봉: 연속 인덱스 (0, 1, 2, 3...) - 캔들들이 이어지도록

        Args:
            data: OHLCV 데이터프레임
            timeframe: 시간프레임 ('1min', '3min', '5min')

        Returns:
            X축 위치 리스트
        """
        # time 또는 datetime 컬럼 확인
        if 'time' in data.columns:
            time_values = data['time'].astype(str).str.zfill(6)
        elif 'datetime' in data.columns:
            # datetime에서 시간 부분 추출 (HHMMSS 형식)
            time_values = pd.to_datetime(data['datetime']).dt.strftime('%H%M%S')
        else:
            self.logger.warning(
                f"{timeframe}: 시간 컬럼 없음. 사용 가능한 컬럼: {list(data.columns)}")
            return list(range(len(data)))

        # 데이터의 실제 시작 시간을 감지하여 기준점 설정
        start_minutes = self._detect_start_minutes(time_values)

        if timeframe == "1min":
            # 1분봉은 실제 시간 기반 인덱스
            return self._calculate_1min_positions(time_values, start_minutes)
        else:
            # 5분봉, 3분봉: 실제 시간 기반 인덱스 계산
            timeframe_minutes = int(timeframe.replace('min', ''))
            return self._calculate_multi_min_positions(
                time_values, start_minutes, timeframe_minutes, timeframe)

    def _detect_start_minutes(self, time_values) -> int:
        """
        데이터의 실제 시작 시간 감지

        Args:
            time_values: 시간 값 시리즈

        Returns:
            시작 시간 (분 단위)
        """
        if len(time_values) > 0:
            first_time = time_values.iloc[0] if hasattr(time_values, 'iloc') else time_values[0]
            if len(str(first_time)) == 6:
                try:
                    first_hour = int(str(first_time)[:2])
                    # 데이터가 09:00 이후에 시작하면 09:00 기준, 그렇지 않으면 08:00 기준
                    if first_hour >= 9:
                        self.logger.debug(
                            f"KRX 시간 기준 설정: 09:00 시작 (첫 데이터: {first_time})")
                        return 9 * 60  # 09:00 = 540분 (KRX 전용)
                    else:
                        self.logger.debug(
                            f"NXT 시간 기준 설정: 08:00 시작 (첫 데이터: {first_time})")
                        return 8 * 60  # 08:00 = 480분 (NXT 포함)
                except ValueError:
                    self.logger.warning(f"시간 파싱 실패, 기본값 08:00 사용")
                    return 8 * 60
            else:
                return 8 * 60
        else:
            return 8 * 60

    def _calculate_1min_positions(self, time_values, start_minutes: int) -> List[float]:
        """
        1분봉 X축 위치 계산

        Args:
            time_values: 시간 값 시리즈
            start_minutes: 시작 시간 (분 단위)

        Returns:
            X축 위치 리스트
        """
        x_positions = []
        prev_x_pos = -1

        for i, time_str in enumerate(time_values):
            if len(time_str) == 6:
                try:
                    hour = int(time_str[:2])
                    minute = int(time_str[2:4])
                    current_minutes = hour * 60 + minute

                    # 시작 시간부터의 분 단위 인덱스 계산 (연속)
                    x_pos = current_minutes - start_minutes

                    # 중복되거나 이상한 x 위치 방지
                    if x_pos == prev_x_pos:
                        x_pos = prev_x_pos + 1
                    elif x_pos < prev_x_pos:
                        x_pos = prev_x_pos + 1

                    x_positions.append(x_pos)
                    prev_x_pos = x_pos

                except ValueError:
                    x_pos = prev_x_pos + 1 if prev_x_pos >= 0 else i
                    x_positions.append(x_pos)
                    prev_x_pos = x_pos
            else:
                x_pos = prev_x_pos + 1 if prev_x_pos >= 0 else i
                x_positions.append(x_pos)
                prev_x_pos = x_pos

        # 디버깅 로그 (중복 확인)
        unique_positions = len(set(x_positions))
        total_positions = len(x_positions)
        if unique_positions != total_positions:
            self.logger.warning(
                f"X 위치 중복 감지: {total_positions}개 중 {unique_positions}개 고유값")

        return x_positions

    def _calculate_multi_min_positions(self, time_values, start_minutes: int,
                                       timeframe_minutes: int,
                                       timeframe: str) -> List[float]:
        """
        다중 분봉(3분, 5분 등) X축 위치 계산

        Args:
            time_values: 시간 값 시리즈
            start_minutes: 시작 시간 (분 단위)
            timeframe_minutes: 시간프레임 분 단위
            timeframe: 시간프레임 문자열

        Returns:
            X축 위치 리스트
        """
        x_positions = []
        prev_x_pos = -1

        for i, time_str in enumerate(time_values):
            if len(time_str) == 6:
                try:
                    hour = int(time_str[:2])
                    minute = int(time_str[2:4])
                    current_minutes = hour * 60 + minute

                    # 시작 시간 기준으로 계산
                    minutes_from_start = current_minutes - start_minutes

                    # timeframe에 맞는 인덱스 계산 (3분봉이면 3분 단위로)
                    x_pos = minutes_from_start // timeframe_minutes

                    # 중복 방지
                    if x_pos == prev_x_pos:
                        x_pos = prev_x_pos + 1
                    elif x_pos < prev_x_pos:
                        x_pos = prev_x_pos + 1

                    x_positions.append(x_pos)
                    prev_x_pos = x_pos

                except ValueError:
                    x_pos = prev_x_pos + 1 if prev_x_pos >= 0 else i
                    x_positions.append(x_pos)
                    prev_x_pos = x_pos
            else:
                x_pos = prev_x_pos + 1 if prev_x_pos >= 0 else i
                x_positions.append(x_pos)
                prev_x_pos = x_pos

        # 성공 로그
        if x_positions:
            self.logger.info(
                f"{timeframe} 시간 기반 X축 계산 완료: "
                f"{min(x_positions)} ~ {max(x_positions)} ({len(x_positions)}개)")
        else:
            self.logger.warning(f"{timeframe} X 위치 계산 실패")

        return x_positions
