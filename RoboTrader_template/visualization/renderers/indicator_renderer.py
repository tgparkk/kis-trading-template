"""
기술적 지표 렌더링 전용 모듈
가격박스, 이등분선, 볼린저밴드 등 지표 시각화 담당
"""
from typing import Dict, Any, List
import pandas as pd

from utils.logger import setup_logger


class IndicatorRenderer:
    """기술적 지표 차트 렌더링"""

    def __init__(self):
        self.logger = setup_logger(__name__)

    def draw_strategy_indicators(self, ax, data: pd.DataFrame, strategy,
                                 indicators_data: Dict[str, Any],
                                 x_positions: List[float]):
        """
        전략별 지표 그리기

        Args:
            ax: matplotlib axis 객체
            data: OHLCV 데이터프레임
            strategy: 전략 객체 (indicators 속성 필요)
            indicators_data: 지표 데이터 딕셔너리
            x_positions: X축 위치 리스트
        """
        try:
            for indicator_name in strategy.indicators:
                if indicator_name in indicators_data:
                    indicator_data = indicators_data[indicator_name]

                    if indicator_name == "price_box":
                        self._draw_price_box(ax, indicator_data, data, x_positions)
                    elif indicator_name == "bisector_line":
                        self._draw_bisector_line(ax, indicator_data, data, x_positions)
                    elif indicator_name == "bollinger_bands":
                        self._draw_bollinger_bands(ax, indicator_data, data, x_positions)
                    elif indicator_name == "multi_bollinger_bands":
                        self._draw_multi_bollinger_bands(ax, indicator_data, data, x_positions)

        except Exception as e:
            self.logger.error(f"지표 그리기 오류: {e}")

    def _draw_price_box(self, ax, box_data: Dict, data: pd.DataFrame,
                        x_positions: List[float]):
        """
        가격박스 그리기 - 정확한 x 위치 기준

        Args:
            ax: matplotlib axis 객체
            box_data: 가격박스 데이터 딕셔너리
            data: OHLCV 데이터프레임
            x_positions: X축 위치 리스트
        """
        try:
            if 'resistance' in box_data and 'support' in box_data:
                data_len = len(data)

                # 가격박스 라인들 그리기
                if 'resistance' in box_data:
                    resistance_data = self._align_data_length(
                        box_data['resistance'], data_len, data)
                    ax.plot(x_positions, resistance_data, color='red', linestyle='--',
                           alpha=0.8, label='박스상한선', linewidth=1.5)

                if 'support' in box_data:
                    support_data = self._align_data_length(
                        box_data['support'], data_len, data)
                    ax.plot(x_positions, support_data, color='purple', linestyle='--',
                           alpha=0.8, label='박스하한선', linewidth=1.5)

                # 중심선 (앞의 두 선보다 굵게)
                if 'center' in box_data and box_data['center'] is not None:
                    center_data = self._align_data_length(
                        box_data['center'], data_len, data)
                    ax.plot(x_positions, center_data, color='green', linestyle='-',
                           alpha=0.9, label='박스중심선', linewidth=2.5)

                # 박스 영역 채우기
                if 'resistance' in box_data and 'support' in box_data:
                    resistance_fill = self._align_data_length(
                        box_data['resistance'], data_len, data)
                    support_fill = self._align_data_length(
                        box_data['support'], data_len, data)

                    ax.fill_between(x_positions, resistance_fill, support_fill,
                                   alpha=0.1, color='gray', label='가격박스')

        except Exception as e:
            self.logger.error(f"가격박스 그리기 오류: {e}")

    def _draw_bisector_line(self, ax, bisector_data: Dict, data: pd.DataFrame,
                            x_positions: List[float]):
        """
        이등분선 그리기 - 정확한 x 위치 기준

        Args:
            ax: matplotlib axis 객체
            bisector_data: 이등분선 데이터 딕셔너리
            data: OHLCV 데이터프레임
            x_positions: X축 위치 리스트
        """
        try:
            if 'line_values' in bisector_data:
                data_len = len(data)
                line_values = self._align_data_length(
                    bisector_data['line_values'], data_len, data)

                ax.plot(x_positions, line_values, color='blue', linestyle='-',
                       alpha=0.8, label='이등분선', linewidth=2)

        except Exception as e:
            self.logger.error(f"이등분선 그리기 오류: {e}")

    def _draw_bollinger_bands(self, ax, bb_data: Dict, data: pd.DataFrame,
                              x_positions: List[float]):
        """
        볼린저밴드 그리기 - 정확한 x 위치 기준

        Args:
            ax: matplotlib axis 객체
            bb_data: 볼린저밴드 데이터 딕셔너리
            data: OHLCV 데이터프레임
            x_positions: X축 위치 리스트
        """
        try:
            if all(k in bb_data for k in ['upper', 'middle', 'lower']):
                data_len = len(data)

                upper_data = self._align_data_length(bb_data['upper'], data_len, data)
                middle_data = self._align_data_length(bb_data['middle'], data_len, data)
                lower_data = self._align_data_length(bb_data['lower'], data_len, data)

                ax.plot(x_positions, upper_data, color='red', linestyle='-',
                       alpha=0.6, label='볼린저 상단')
                ax.plot(x_positions, middle_data, color='blue', linestyle='-',
                       alpha=0.8, label='볼린저 중심')
                ax.plot(x_positions, lower_data, color='red', linestyle='-',
                       alpha=0.6, label='볼린저 하단')

                # 밴드 영역 채우기
                ax.fill_between(x_positions, upper_data, lower_data,
                               alpha=0.1, color='blue', label='볼린저밴드')

        except Exception as e:
            self.logger.error(f"볼린저밴드 그리기 오류: {e}")

    def _draw_multi_bollinger_bands(self, ax, multi_bb_data: Dict, data: pd.DataFrame,
                                    x_positions: List[float]):
        """
        다중 볼린저밴드 그리기 - 정확한 x 위치 기준

        Args:
            ax: matplotlib axis 객체
            multi_bb_data: 다중 볼린저밴드 데이터 딕셔너리
            data: OHLCV 데이터프레임
            x_positions: X축 위치 리스트
        """
        try:
            data_len = len(data)

            # 다중 볼린저밴드 색상 및 기간 설정
            colors = ['red', 'orange', 'green', 'blue']
            periods = [50, 40, 30, 20]

            for i, period in enumerate(periods):
                if i < len(colors):
                    color = colors[i]

                    # 각 기간별 데이터 키 확인
                    sma_key = f'sma_{period}'
                    upper_key = f'upper_{period}'
                    lower_key = f'lower_{period}'

                    if period in [50, 40, 30]:
                        # 상한선만 그리기 (50, 40, 30 기간)
                        if upper_key in multi_bb_data:
                            upper_data = self._align_data_length(
                                multi_bb_data[upper_key], data_len, data)
                            ax.plot(x_positions, upper_data, color=color, linestyle='--',
                                   alpha=0.8, label=f'상한선({period})', linewidth=1.5)

                    elif period == 20:
                        # 20 기간은 중심선, 상한선, 하한선 모두 그리기
                        if sma_key in multi_bb_data:
                            sma_data = self._align_data_length(
                                multi_bb_data[sma_key], data_len, data)
                            ax.plot(x_positions, sma_data, color=color, linestyle='-',
                                   alpha=0.9, label=f'중심선({period})', linewidth=2)

                        if upper_key in multi_bb_data:
                            upper_data = self._align_data_length(
                                multi_bb_data[upper_key], data_len, data)
                            ax.plot(x_positions, upper_data, color=color, linestyle='--',
                                   alpha=0.8, label=f'상한선({period})', linewidth=1.5)

                        if lower_key in multi_bb_data:
                            lower_data = self._align_data_length(
                                multi_bb_data[lower_key], data_len, data)
                            ax.plot(x_positions, lower_data, color=color, linestyle='--',
                                   alpha=0.8, label=f'하한선({period})', linewidth=1.5)

            # 이등분선 그리기 (다중볼린저밴드에 포함된 경우)
            if 'bisector_line' in multi_bb_data:
                bisector_data = self._align_data_length(
                    multi_bb_data['bisector_line'], data_len, data)
                ax.plot(x_positions, bisector_data, color='purple', linestyle=':',
                       alpha=0.8, label='이등분선', linewidth=2)

            # 상한선 밀집 구간 표시 (있는 경우)
            if 'upper_convergence' in multi_bb_data:
                convergence_data = self._align_data_length(
                    multi_bb_data['upper_convergence'], data_len, data)

                # 밀집 구간 배경 표시 (안전한 인덱스 범위 체크)
                max_len = min(len(convergence_data), len(x_positions))
                for i in range(max_len):
                    try:
                        # 안전한 데이터 접근
                        if hasattr(convergence_data, 'iloc'):
                            convergence_value = convergence_data.iloc[i]
                        else:
                            convergence_value = convergence_data[i]

                        if convergence_value and i < len(x_positions):
                            x_start = x_positions[i] - 0.4
                            x_end = x_positions[i] + 0.4
                            ax.axvspan(x_start, x_end, alpha=0.2, color='yellow')
                    except (IndexError, KeyError):
                        # 인덱스 오류 시 무시
                        continue

        except Exception as e:
            self.logger.error(f"다중 볼린저밴드 그리기 오류: {e}")

    def _align_data_length(self, data_series, target_len: int,
                           reference_data: pd.DataFrame):
        """
        데이터 길이를 맞추는 헬퍼 함수

        Args:
            data_series: 정렬할 데이터 시리즈
            target_len: 목표 길이
            reference_data: 참조 데이터프레임

        Returns:
            길이가 조정된 데이터 시리즈
        """
        try:
            if len(data_series) > target_len:
                return data_series.iloc[:target_len]
            elif len(data_series) < target_len:
                return data_series.reindex(reference_data.index, method='ffill')
            return data_series
        except Exception:
            return data_series
