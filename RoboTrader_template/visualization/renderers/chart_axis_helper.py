"""
차트 축 및 데이터 유틸리티 모듈 (Facade)
X축 위치 계산, 시간 레이블 설정, 데이터 검증 등 공통 기능 담당

실제 구현은 다음 모듈로 분리됨:
- data_validator.py: 데이터 검증 및 X축 위치 계산
- time_axis_formatter.py: 시간축 레이블 및 배경 설정
"""
from typing import List
import pandas as pd

from utils.logger import setup_logger
from .data_validator import DataValidator
from .time_axis_formatter import TimeAxisFormatter


class ChartAxisHelper:
    """
    차트 축 및 데이터 유틸리티 (Facade)

    DataValidator와 TimeAxisFormatter를 조합하여
    기존 인터페이스를 유지합니다.
    """

    def __init__(self):
        self.logger = setup_logger(__name__)
        self._data_validator = DataValidator()
        self._time_axis_formatter = TimeAxisFormatter()

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
        return self._data_validator.validate_and_clean_data(
            data, target_date, timeframe)

    def calculate_x_positions(self, data: pd.DataFrame,
                              timeframe: str = '1min') -> List[float]:
        """
        시간프레임에 따른 x 위치 계산

        Args:
            data: OHLCV 데이터프레임
            timeframe: 시간프레임 ('1min', '3min', '5min')

        Returns:
            X축 위치 리스트
        """
        return self._data_validator.calculate_x_positions(data, timeframe)

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
        self._time_axis_formatter.set_time_axis_labels(
            ax1, ax2, data, timeframe, x_positions)

    def set_basic_time_axis_labels(self, ax, data: pd.DataFrame):
        """
        기본 차트용 X축 시간 레이블 설정

        Args:
            ax: matplotlib axis 객체
            data: OHLCV 데이터프레임
        """
        self._time_axis_formatter.set_basic_time_axis_labels(ax, data)

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
        self._time_axis_formatter.draw_no_data_background(
            ax1, ax2, data, timeframe)
