"""
차트 렌더링 전용 클래스 (Facade 패턴)
PostMarketChartGenerator에서 차트 그리기 로직을 분리

이 모듈은 하위 호환성을 위해 유지되며, 실제 구현은 renderers 서브모듈로 분리됨:
- renderers/candlestick_renderer.py: 캔들스틱 및 거래량 차트
- renderers/indicator_renderer.py: 기술적 지표 (볼린저밴드, 가격박스 등)
- renderers/signal_renderer.py: 매수/매도 신호 표시
- renderers/chart_axis_helper.py: 축 설정 및 데이터 유틸리티
"""
from pathlib import Path
from typing import Dict, Any, List, Optional

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import pandas as pd

from utils.logger import setup_logger
from utils.korean_time import now_kst

# 서브모듈 import
from .renderers import (
    CandlestickRenderer,
    IndicatorRenderer,
    SignalRenderer,
    ChartAxisHelper,
)


class ChartRenderer:
    """
    차트 렌더링 전용 클래스 (Facade)

    각 기능별 렌더러를 조합하여 완성된 차트를 생성합니다.
    기존 인터페이스를 유지하여 하위 호환성을 보장합니다.
    """

    def __init__(self):
        """초기화"""
        self.logger = setup_logger(__name__)

        # 차트 설정
        plt.rcParams['font.family'] = ['Malgun Gothic', 'DejaVu Sans']
        plt.rcParams['axes.unicode_minus'] = False

        # 서브 렌더러 초기화
        self._candlestick_renderer = CandlestickRenderer()
        self._indicator_renderer = IndicatorRenderer()
        self._signal_renderer = SignalRenderer()
        self._axis_helper = ChartAxisHelper()

        # 현재 시간프레임 (내부 상태)
        self.current_timeframe = "1min"

        self.logger.info("차트 렌더러 초기화 완료")

    def create_strategy_chart(self, stock_code: str, stock_name: str, target_date: str,
                             strategy, data: pd.DataFrame,
                             indicators_data: Dict[str, Any], selection_reason: str,
                             chart_suffix: str = "", timeframe: str = "1min",
                             trade_simulation_results: Optional[List[Dict[str, Any]]] = None) -> Optional[str]:
        """
        전략별 차트 생성

        Args:
            stock_code: 종목 코드
            stock_name: 종목명
            target_date: 대상 날짜 (YYYYMMDD)
            strategy: 전략 객체
            data: OHLCV 데이터프레임
            indicators_data: 지표 데이터 딕셔너리
            selection_reason: 종목 선정 사유
            chart_suffix: 파일명 접미사
            timeframe: 시간프레임 ('1min', '3min', '5min')
            trade_simulation_results: 체결 시뮬레이션 결과 리스트

        Returns:
            저장된 차트 파일 경로 또는 None
        """
        try:
            # 시간프레임 저장
            self.current_timeframe = timeframe

            # 서브플롯 설정 (가격 + 거래량)
            fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(16, 12),
                                         gridspec_kw={'height_ratios': [3, 1]})

            # Axis 클리어 (중복 방지)
            ax1.clear()
            ax2.clear()

            # 데이터 검증 및 중복 제거
            cleaned_data = self._axis_helper.validate_and_clean_data(
                data, target_date, timeframe)

            # X축 위치 계산
            x_positions = self._axis_helper.calculate_x_positions(
                cleaned_data, timeframe)

            # 기본 캔들스틱 차트
            self._candlestick_renderer.draw_candlestick(
                ax1, cleaned_data, x_positions, timeframe)

            # 전략별 지표 표시
            self._indicator_renderer.draw_strategy_indicators(
                ax1, cleaned_data, strategy, indicators_data, x_positions)

            # 체결 시뮬레이션 결과 기반 매수/매도 신호 표시
            if trade_simulation_results:
                self._signal_renderer.draw_simulation_signals(
                    ax1, cleaned_data, trade_simulation_results, x_positions)
            else:
                # 폴백: 기존 신호 표시 방식
                self._signal_renderer.draw_buy_signals(
                    ax1, cleaned_data, strategy, x_positions)
                self._signal_renderer.draw_sell_signals(
                    ax1, cleaned_data, strategy, x_positions)

            # 거래량 차트
            self._candlestick_renderer.draw_volume_chart(
                ax2, cleaned_data, x_positions)

            # 차트 제목 및 설정
            title = f"{stock_code} {stock_name} - {strategy.name} ({strategy.timeframe})"
            if selection_reason:
                title += f"\n{selection_reason}"

            ax1.set_title(title, fontsize=14, fontweight='bold', pad=20)
            ax1.set_ylabel('가격 (원)', fontsize=12)
            ax1.grid(True, alpha=0.3)
            ax1.legend(loc='upper left')

            ax2.set_ylabel('거래량', fontsize=12)
            ax2.set_xlabel('시간', fontsize=12)
            ax2.grid(True, alpha=0.3)

            # 08:00~09:00 구간 회색 배경 표시 (데이터 없는 구간)
            self._axis_helper.draw_no_data_background(
                ax1, ax2, cleaned_data, strategy.timeframe)

            # X축 시간 레이블 설정 (08:00 ~ 15:30)
            self._axis_helper.set_time_axis_labels(
                ax1, ax2, cleaned_data, strategy.timeframe, x_positions)

            plt.tight_layout()

            # 파일 저장
            timestamp = now_kst().strftime("%Y%m%d_%H%M%S")
            suffix_part = f"_{chart_suffix}" if chart_suffix else ""
            filename = f"strategy_chart_{stock_code}_{strategy.timeframe}_{target_date}{suffix_part}_{timestamp}.png"
            filepath = Path(filename)

            plt.savefig(filepath, dpi=150, bbox_inches='tight')
            plt.close()

            return str(filepath)

        except Exception as e:
            self.logger.error(f"전략 차트 생성 실패: {e}")
            plt.close()
            return None

    def create_basic_chart(self, stock_code: str, stock_name: str,
                          chart_df: pd.DataFrame, target_date: str,
                          selection_reason: str = "") -> Optional[str]:
        """
        기본 차트 생성 (폴백용)

        Args:
            stock_code: 종목 코드
            stock_name: 종목명
            chart_df: OHLCV 데이터프레임
            target_date: 대상 날짜 (YYYYMMDD)
            selection_reason: 종목 선정 사유

        Returns:
            저장된 차트 파일 경로 또는 None
        """
        try:
            # 데이터 검증 및 날짜 필터링
            chart_df = self._axis_helper.validate_and_clean_data(
                chart_df, target_date)

            if chart_df.empty:
                self.logger.error(f"기본 차트 생성 실패: 데이터 없음 ({stock_code})")
                return None

            fig, ax = plt.subplots(1, 1, figsize=(12, 8))

            if 'close' in chart_df.columns:
                ax.plot(chart_df['close'], label='가격', linewidth=2)
                ax.set_title(f"{stock_code} {stock_name} - {target_date}")
                ax.set_ylabel('가격 (원)')
                ax.grid(True, alpha=0.3)
                ax.legend()

                # 기본 차트도 시간축 설정
                self._axis_helper.set_basic_time_axis_labels(ax, chart_df)

            timestamp = now_kst().strftime("%Y%m%d_%H%M%S")
            filename = f"basic_chart_{stock_code}_{target_date}_{timestamp}.png"
            filepath = Path(filename)

            plt.savefig(filepath, dpi=150, bbox_inches='tight')
            plt.close()

            return str(filepath)

        except Exception as e:
            self.logger.error(f"기본 차트 생성 오류: {e}")
            plt.close()
            return None

    # =========================================================================
    # 하위 호환성을 위한 내부 메서드 (deprecated, 서브모듈로 위임)
    # =========================================================================

    def _draw_candlestick(self, ax, data: pd.DataFrame):
        """캔들스틱 차트 그리기 (deprecated: CandlestickRenderer 사용 권장)"""
        x_positions = self._axis_helper.calculate_x_positions(
            data, self.current_timeframe)
        self._candlestick_renderer.draw_candlestick(
            ax, data, x_positions, self.current_timeframe)

    def _draw_strategy_indicators(self, ax, data: pd.DataFrame, strategy,
                                 indicators_data: Dict[str, Any]):
        """전략별 지표 그리기 (deprecated: IndicatorRenderer 사용 권장)"""
        x_positions = self._axis_helper.calculate_x_positions(
            data, self.current_timeframe)
        self._indicator_renderer.draw_strategy_indicators(
            ax, data, strategy, indicators_data, x_positions)

    def _draw_buy_signals(self, ax, data: pd.DataFrame, strategy):
        """매수 신호 표시 (deprecated: SignalRenderer 사용 권장)"""
        x_positions = self._axis_helper.calculate_x_positions(
            data, self.current_timeframe)
        self._signal_renderer.draw_buy_signals(ax, data, strategy, x_positions)

    def _draw_sell_signals(self, ax, data: pd.DataFrame, strategy):
        """매도 신호 표시 (deprecated: SignalRenderer 사용 권장)"""
        x_positions = self._axis_helper.calculate_x_positions(
            data, self.current_timeframe)
        self._signal_renderer.draw_sell_signals(ax, data, strategy, x_positions)

    def _draw_simulation_signals(self, ax, data: pd.DataFrame,
                                trades: List[Dict[str, Any]]):
        """체결 시뮬레이션 신호 표시 (deprecated: SignalRenderer 사용 권장)"""
        x_positions = self._axis_helper.calculate_x_positions(
            data, self.current_timeframe)
        self._signal_renderer.draw_simulation_signals(
            ax, data, trades, x_positions)

    def _draw_price_box(self, ax, box_data, data: pd.DataFrame):
        """가격박스 그리기 (deprecated: IndicatorRenderer 사용 권장)"""
        x_positions = self._axis_helper.calculate_x_positions(
            data, self.current_timeframe)
        self._indicator_renderer._draw_price_box(ax, box_data, data, x_positions)

    def _draw_bisector_line(self, ax, bisector_data, data: pd.DataFrame):
        """이등분선 그리기 (deprecated: IndicatorRenderer 사용 권장)"""
        x_positions = self._axis_helper.calculate_x_positions(
            data, self.current_timeframe)
        self._indicator_renderer._draw_bisector_line(
            ax, bisector_data, data, x_positions)

    def _draw_bollinger_bands(self, ax, bb_data, data: pd.DataFrame):
        """볼린저밴드 그리기 (deprecated: IndicatorRenderer 사용 권장)"""
        x_positions = self._axis_helper.calculate_x_positions(
            data, self.current_timeframe)
        self._indicator_renderer._draw_bollinger_bands(
            ax, bb_data, data, x_positions)

    def _draw_multi_bollinger_bands(self, ax, multi_bb_data, data: pd.DataFrame):
        """다중 볼린저밴드 그리기 (deprecated: IndicatorRenderer 사용 권장)"""
        x_positions = self._axis_helper.calculate_x_positions(
            data, self.current_timeframe)
        self._indicator_renderer._draw_multi_bollinger_bands(
            ax, multi_bb_data, data, x_positions)

    def _draw_volume_chart(self, ax, data: pd.DataFrame):
        """거래량 차트 그리기 (deprecated: CandlestickRenderer 사용 권장)"""
        x_positions = self._axis_helper.calculate_x_positions(
            data, self.current_timeframe)
        self._candlestick_renderer.draw_volume_chart(ax, data, x_positions)

    def _align_data_length(self, data_series, target_len: int,
                           reference_data: pd.DataFrame):
        """데이터 길이 맞추기 (deprecated: IndicatorRenderer 사용 권장)"""
        return self._indicator_renderer._align_data_length(
            data_series, target_len, reference_data)

    def _validate_and_clean_data(self, data: pd.DataFrame,
                                 target_date: str = None) -> pd.DataFrame:
        """데이터 검증 (deprecated: ChartAxisHelper 사용 권장)"""
        return self._axis_helper.validate_and_clean_data(
            data, target_date, self.current_timeframe)

    def _calculate_x_positions(self, data: pd.DataFrame,
                               timeframe: str = None) -> list:
        """X축 위치 계산 (deprecated: ChartAxisHelper 사용 권장)"""
        tf = timeframe if timeframe else self.current_timeframe
        return self._axis_helper.calculate_x_positions(data, tf)

    def _set_time_axis_labels(self, ax1, ax2, data: pd.DataFrame,
                              timeframe: str):
        """시간 축 레이블 설정 (deprecated: ChartAxisHelper 사용 권장)"""
        self._axis_helper.set_time_axis_labels(ax1, ax2, data, timeframe)

    def _set_basic_time_axis_labels(self, ax, data: pd.DataFrame):
        """기본 차트 시간축 레이블 (deprecated: ChartAxisHelper 사용 권장)"""
        self._axis_helper.set_basic_time_axis_labels(ax, data)

    def _draw_no_data_background(self, ax1, ax2, data: pd.DataFrame,
                                 timeframe: str):
        """데이터 없는 구간 배경 (deprecated: ChartAxisHelper 사용 권장)"""
        self._axis_helper.draw_no_data_background(ax1, ax2, data, timeframe)
