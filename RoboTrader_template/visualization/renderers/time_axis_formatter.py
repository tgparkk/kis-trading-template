"""
시간축 레이블 설정 모듈
X축 시간 레이블, 거래시간 표시, 빈 구간 배경 등 담당
"""
from typing import List, Tuple, Callable
import pandas as pd

from utils.logger import setup_logger


class TimeAxisFormatter:
    """시간축 레이블 및 배경 설정"""

    def __init__(self):
        self.logger = setup_logger(__name__)

    def set_time_axis_labels(self, ax1, ax2, data: pd.DataFrame,
                             timeframe: str, x_positions: List[float] = None):
        """
        X축 시간 레이블 설정 - 08:00~15:30 연속 거래시간 기반

        Args:
            ax1: 가격 차트 axis
            ax2: 거래량 차트 axis
            data: OHLCV 데이터프레임
            timeframe: 시간프레임
            x_positions: X축 위치 리스트 (선택)
        """
        try:
            data_len = len(data)
            if data_len == 0:
                return

            # 실제 데이터의 시간 정보 확인
            if 'time' not in data.columns and 'datetime' not in data.columns:
                self.logger.warning("시간 정보가 없어 기본 인덱스 사용")
                return

            # 시간 컬럼 선택 및 파싱 함수 설정
            time_values, parse_time = self._get_time_parser(data)

            # 시간 간격 설정 (timeframe에 따라)
            interval_minutes = 5 if timeframe == "5min" else 30

            # 시작/종료 시간 및 총 거래시간 계산
            start_hour, total_trading_minutes = self._calculate_trading_time_range(
                time_values, parse_time)

            # 레이블 생성
            time_labels, label_x_positions = self._generate_time_labels(
                start_hour, total_trading_minutes, interval_minutes,
                timeframe, data_len)

            # X축 레이블 설정
            if label_x_positions and time_labels:
                ax1.set_xticks(label_x_positions)
                ax1.set_xticklabels(time_labels, rotation=45, fontsize=10)
                ax2.set_xticks(label_x_positions)
                ax2.set_xticklabels(time_labels, rotation=45, fontsize=10)

                # X축 범위 설정
                if timeframe in ["5min", "3min"]:
                    # 5분봉/3분봉은 실제 데이터 길이에 맞춤
                    ax1.set_xlim(-0.5, len(data) - 0.5)
                    ax2.set_xlim(-0.5, len(data) - 0.5)
                else:
                    # 1분봉은 전체 거래시간 기준
                    total_candles = total_trading_minutes
                    ax1.set_xlim(-0.5, total_candles - 0.5)
                    ax2.set_xlim(-0.5, total_candles - 0.5)

                self.logger.debug(f"시간축 설정 완료: {len(label_x_positions)}개 레이블")

        except Exception as e:
            self.logger.error(f"시간 축 레이블 설정 오류: {e}")
            self._set_fallback_labels(ax1, ax2, data)

    def _get_time_parser(self, data: pd.DataFrame) -> Tuple:
        """
        시간 파싱 함수 반환

        Args:
            data: OHLCV 데이터프레임

        Returns:
            (time_values, parse_time 함수) 튜플
        """
        if 'time' in data.columns:
            time_values = data['time'].astype(str).str.zfill(6)
            def parse_time(time_str):
                if len(time_str) == 6:
                    hour = int(time_str[:2])
                    minute = int(time_str[2:4])
                    return hour, minute
                return 9, 0
        elif 'datetime' in data.columns:
            time_values = data['datetime']
            def parse_time(dt):
                if pd.isna(dt):
                    return 9, 0
                return dt.hour, dt.minute
        else:
            time_values = pd.Series([])
            def parse_time(x):
                return 9, 0

        return time_values, parse_time

    def _calculate_trading_time_range(self, time_values,
                                       parse_time: Callable) -> Tuple[int, int]:
        """
        거래시간 범위 계산

        Args:
            time_values: 시간 값 시리즈
            parse_time: 시간 파싱 함수

        Returns:
            (시작 시간, 총 거래분) 튜플
        """
        if len(time_values) > 0:
            first_hour, first_minute = parse_time(time_values.iloc[0])
            last_hour, last_minute = parse_time(time_values.iloc[-1])

            self.logger.debug(
                f"데이터 시간 범위: {first_hour:02d}:{first_minute:02d} ~ "
                f"{last_hour:02d}:{last_minute:02d}")

            # 09:00 이후 시작하면 KRX, 그렇지 않으면 NXT 포함
            if first_hour >= 9:
                start_hour = 9
                total_trading_minutes = 390  # 09:00~15:30 = 6.5시간
                self.logger.debug(
                    f"KRX 시간축 설정: 09:00~15:30 ({total_trading_minutes}분)")
            else:
                start_hour = 8
                total_trading_minutes = 450  # 08:00~15:30 = 7.5시간
                self.logger.debug(
                    f"NXT 시간축 설정: 08:00~15:30 ({total_trading_minutes}분)")
        else:
            start_hour = 8
            total_trading_minutes = 450

        return start_hour, total_trading_minutes

    def _generate_time_labels(self, start_hour: int, total_trading_minutes: int,
                              interval_minutes: int, timeframe: str,
                              data_len: int) -> Tuple[List[str], List[float]]:
        """
        시간 레이블 생성

        Args:
            start_hour: 시작 시간 (시)
            total_trading_minutes: 총 거래시간 (분)
            interval_minutes: 레이블 간격 (분)
            timeframe: 시간프레임
            data_len: 데이터 길이

        Returns:
            (레이블 리스트, X 위치 리스트) 튜플
        """
        time_labels = []
        x_positions = []

        start_minutes = start_hour * 60
        end_minutes = 15 * 60 + 30  # 15:30 = 930분

        current_time_minutes = start_minutes
        while current_time_minutes <= end_minutes:
            hour = current_time_minutes // 60
            minute = current_time_minutes % 60

            # 해당 시간의 데이터 인덱스 계산
            real_data_start_minutes = start_hour * 60

            if timeframe == "1min":
                data_index = current_time_minutes - real_data_start_minutes
            elif timeframe == "5min":
                data_index = (current_time_minutes - real_data_start_minutes) // 5
                if data_index >= data_len:
                    break
            else:  # 3min
                data_index = (current_time_minutes - real_data_start_minutes) // 3
                if data_index >= data_len:
                    break

            time_label = f"{hour:02d}:{minute:02d}"
            time_labels.append(time_label)
            x_positions.append(data_index)

            current_time_minutes += interval_minutes

        return time_labels, x_positions

    def _set_fallback_labels(self, ax1, ax2, data: pd.DataFrame):
        """
        오류 시 기본 인덱스 레이블 사용

        Args:
            ax1: 가격 차트 axis
            ax2: 거래량 차트 axis
            data: OHLCV 데이터프레임
        """
        if len(data) > 0:
            x_ticks = range(0, len(data), max(1, len(data) // 10))
            ax1.set_xticks(x_ticks)
            ax1.set_xticklabels([str(i) for i in x_ticks])
            ax2.set_xticks(x_ticks)
            ax2.set_xticklabels([str(i) for i in x_ticks])

    def set_basic_time_axis_labels(self, ax, data: pd.DataFrame):
        """
        기본 차트용 X축 시간 레이블 설정 - 08:00~15:30 연속 거래시간 기준

        Args:
            ax: matplotlib axis 객체
            data: OHLCV 데이터프레임
        """
        try:
            data_len = len(data)
            if data_len == 0:
                return

            # 실제 데이터의 시간 정보 확인
            if 'time' not in data.columns and 'datetime' not in data.columns:
                self.logger.warning("시간 정보가 없어 기본 인덱스 사용")
                return

            # 30분 간격으로 시간 레이블 생성
            interval_minutes = 30
            time_labels = []
            x_positions = []

            # 전체 거래시간 기준 (08:00~15:30 = 7.5시간 * 60분 = 450분)
            total_trading_minutes = 450
            total_candles = total_trading_minutes

            # 08:00부터 15:30까지 30분 간격으로 레이블 생성
            start_minutes = 8 * 60  # 08:00 = 480분
            end_minutes = 15 * 60 + 30  # 15:30 = 930분

            current_time_minutes = start_minutes
            while current_time_minutes <= end_minutes:
                hour = current_time_minutes // 60
                minute = current_time_minutes % 60

                # 해당 시간의 데이터 인덱스 계산 (연속, 1분봉 기준)
                data_index = current_time_minutes - start_minutes

                time_label = f"{hour:02d}:{minute:02d}"
                time_labels.append(time_label)
                x_positions.append(data_index)

                current_time_minutes += interval_minutes

            # X축 레이블 설정
            if x_positions and time_labels:
                ax.set_xticks(x_positions)
                ax.set_xticklabels(time_labels, rotation=45, fontsize=10)

                # 전체 거래시간 범위로 설정 (08:00~15:30)
                # 08:00~09:00 구간 포함하여 X축 범위 확장
                timeframe_str = time_labels[0] if time_labels else ''
                timeframe_minutes = 3  # 기본값
                if '분' in timeframe_str:
                    try:
                        timeframe_minutes = int(timeframe_str.replace('분', ''))
                    except ValueError:
                        pass
                no_data_positions = 60 // timeframe_minutes  # 08:00~09:00 = 60분
                ax.set_xlim(-no_data_positions - 0.5, total_candles - 0.5)

        except Exception as e:
            self.logger.error(f"기본 차트 시간 축 레이블 설정 오류: {e}")
            self._set_single_axis_fallback(ax, data)

    def _set_single_axis_fallback(self, ax, data: pd.DataFrame):
        """
        단일 axis에 대한 폴백 레이블 설정

        Args:
            ax: matplotlib axis 객체
            data: OHLCV 데이터프레임
        """
        if len(data) > 0:
            x_ticks = range(0, len(data), max(1, len(data) // 10))
            ax.set_xticks(x_ticks)
            ax.set_xticklabels([str(i) for i in x_ticks])

    def draw_no_data_background(self, ax1, ax2, data: pd.DataFrame,
                                timeframe: str):
        """
        08:00~09:00 구간에 회색 배경 표시 (데이터 없는 구간)

        Args:
            ax1: 가격 차트 axis
            ax2: 거래량 차트 axis
            data: OHLCV 데이터프레임
            timeframe: 시간프레임
        """
        try:
            if data.empty:
                return

            # 1분 = 1위치, 3분 = 3위치 등으로 계산
            timeframe_minutes = int(timeframe.replace('min', ''))

            # 08:00~09:00 = 60분 구간
            no_data_minutes = 60
            no_data_positions = no_data_minutes // timeframe_minutes

            # 실제 데이터 시작 시간 확인
            if 'time' in data.columns:
                first_time_str = str(data['time'].iloc[0]).zfill(6)
                first_hour = int(first_time_str[:2])
                if first_hour >= 9:  # 09:00 이후부터 데이터 시작
                    # 08:00~09:00 구간 회색 배경
                    ax1.axvspan(-no_data_positions, 0, alpha=0.2,
                               color='lightgray', label='거래시간 외')
                    ax2.axvspan(-no_data_positions, 0, alpha=0.2,
                               color='lightgray')

                    # 텍스트 표시
                    ylim = ax1.get_ylim()
                    ax1.text(-no_data_positions/2, ylim[1] * 0.95,
                            '08:00~09:00\n거래시간 외',
                            ha='center', va='top', fontsize=10, alpha=0.7)

        except Exception as e:
            self.logger.debug(f"데이터 없는 구간 배경 표시 오류: {e}")
