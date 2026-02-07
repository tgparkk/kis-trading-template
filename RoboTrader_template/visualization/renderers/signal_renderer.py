"""
매수/매도 신호 렌더링 전용 모듈
매수/매도/손절/익절 신호를 차트에 표시하는 기능 담당
"""
from typing import Dict, Any, List, Optional
import pandas as pd

from utils.logger import setup_logger


class SignalRenderer:
    """매수/매도 신호 차트 렌더링"""

    def __init__(self):
        self.logger = setup_logger(__name__)

    def draw_buy_signals(self, ax, data: pd.DataFrame, strategy,
                         x_positions: List[float]):
        """
        매수 신호 표시 (빨간색 화살표) - 정확한 x 위치 기준

        Args:
            ax: matplotlib axis 객체
            data: OHLCV 데이터프레임
            strategy: 전략 객체
            x_positions: X축 위치 리스트
        """
        try:
            # 별도 모듈에서 매수 신호 계산
            from ..signal_calculator import SignalCalculator
            signal_calc = SignalCalculator()
            buy_signals = signal_calc.calculate_buy_signals(data, strategy)

            if buy_signals is not None and buy_signals.any():
                # 매수 신호가 있는 지점 찾기
                signal_indices = buy_signals[buy_signals].index
                signal_x_positions = []
                signal_prices = []

                for idx in signal_indices:
                    data_idx = data.index.get_loc(idx)
                    if data_idx < len(x_positions):
                        signal_x_positions.append(x_positions[data_idx])
                        signal_prices.append(data.loc[idx, 'close'])

                if signal_x_positions:
                    # 빨간색 화살표로 표시
                    ax.scatter(signal_x_positions, signal_prices,
                              color='red', s=150, marker='^',
                              label='매수신호', zorder=10,
                              edgecolors='darkred', linewidth=2)

                    self.logger.info(f"매수 신호 {len(signal_x_positions)}개 표시됨")

        except Exception as e:
            self.logger.error(f"매수 신호 표시 오류: {e}")

    def draw_sell_signals(self, ax, data: pd.DataFrame, strategy,
                          x_positions: List[float]):
        """
        매도/손절/익절 신호 표시 (파란/검정 화살표)

        Args:
            ax: matplotlib axis 객체
            data: OHLCV 데이터프레임
            strategy: 전략 객체
            x_positions: X축 위치 리스트
        """
        try:
            # 눌림목 캔들패턴 전략인 경우만 상세 매도 신호 표시
            required_cols = ['open', 'high', 'low', 'close', 'volume']
            if ("pullback_candle_pattern" in strategy.indicators and
                all(col in data.columns for col in required_cols)):

                from core.indicators.pullback_candle_pattern import PullbackCandlePattern
                signals = PullbackCandlePattern.generate_trading_signals(data)
                if signals is None or signals.empty:
                    return

                def scatter_mask(mask, color, label, marker='v'):
                    if mask.any():
                        idxs = mask[mask].index
                        xs, ys = [], []
                        for idx in idxs:
                            pos = data.index.get_loc(idx)
                            if pos < len(x_positions):
                                xs.append(x_positions[pos])
                                ys.append(data.loc[idx, 'close'])
                        if xs:
                            ax.scatter(xs, ys, color=color, s=130,
                                      marker=marker, label=label, zorder=10)

                if 'stop_entry_low_break' in signals.columns:
                    scatter_mask(signals['stop_entry_low_break'], 'black', '손절(0.2%)')
                scatter_mask(signals['sell_bisector_break'], 'blue', '이등분선 이탈')
                scatter_mask(signals['sell_support_break'], 'purple', '지지 저점 이탈')
                if 'take_profit_3pct' in signals.columns:
                    scatter_mask(signals['take_profit_3pct'], 'green', '익절(+3%)', marker='^')

        except Exception as e:
            self.logger.error(f"매도 신호 표시 오류: {e}")

    def draw_simulation_signals(self, ax, data: pd.DataFrame,
                                trades: List[Dict[str, Any]],
                                x_positions: List[float]):
        """
        체결 시뮬레이션 결과 기반 매수/매도 신호 표시

        Args:
            ax: matplotlib axis 객체
            data: OHLCV 데이터프레임
            trades: 체결 시뮬레이션 결과 리스트
            x_positions: X축 위치 리스트
        """
        try:
            if not trades:
                self.logger.info("체결 시뮬레이션 결과 없음")
                return

            buy_signals_x = []
            buy_signals_y = []
            sell_signals_x = []
            sell_signals_y = []

            # 데이터의 시간 컬럼 확인
            if 'time' not in data.columns and 'datetime' not in data.columns:
                self.logger.warning("time 또는 datetime 컬럼이 없어 체결 시뮬레이션 신호 표시 불가")
                return

            for trade in trades:
                try:
                    # 매수 신호 처리
                    buy_result = self._process_buy_signal(
                        trade, data, x_positions)
                    if buy_result:
                        buy_signals_x.append(buy_result[0])
                        buy_signals_y.append(buy_result[1])

                    # 매도 신호 처리
                    sell_result = self._process_sell_signal(
                        trade, data, x_positions)
                    if sell_result:
                        sell_signals_x.append(sell_result[0])
                        sell_signals_y.append(sell_result[1])

                except Exception as e:
                    self.logger.warning(f"체결 시뮬레이션 신호 처리 오류: {e}")
                    continue

            # 매수 신호 표시 (빨간색 위 화살표)
            if buy_signals_x:
                ax.scatter(buy_signals_x, buy_signals_y,
                          color='red', s=150, marker='^',
                          label=f'매수신호({len(buy_signals_x)}개)', zorder=10,
                          edgecolors='darkred', linewidth=2)
                self.logger.info(f"체결 시뮬레이션 매수 신호 {len(buy_signals_x)}개 표시됨")

            # 매도 신호 표시 (파란색 아래 화살표)
            if sell_signals_x:
                ax.scatter(sell_signals_x, sell_signals_y,
                          color='blue', s=150, marker='v',
                          label=f'매도신호({len(sell_signals_x)}개)', zorder=10,
                          edgecolors='darkblue', linewidth=2)
                self.logger.info(f"체결 시뮬레이션 매도 신호 {len(sell_signals_x)}개 표시됨")

        except Exception as e:
            self.logger.error(f"체결 시뮬레이션 신호 표시 오류: {e}")

    def _process_buy_signal(self, trade: Dict[str, Any], data: pd.DataFrame,
                            x_positions: List[float]) -> Optional[tuple]:
        """
        매수 신호 처리

        Args:
            trade: 거래 정보 딕셔너리
            data: OHLCV 데이터프레임
            x_positions: X축 위치 리스트

        Returns:
            (x_position, price) 튜플 또는 None
        """
        buy_time_str = trade.get('buy_time', '')
        buy_price = trade.get('buy_price', 0.0)

        if not buy_time_str or buy_price <= 0:
            return None

        try:
            # 시간 문자열을 HH:MM 형식으로 파싱 (09:18 형식)
            hour, minute = buy_time_str.split(':')

            # 3분봉 캔들 시간으로 변환 (매수 시간을 포함하는 캔들 찾기)
            hour_int = int(hour)
            minute_int = int(minute)

            # 3분봉 캔들의 시작 시간 계산 (09:00 기준으로 3분 단위로 나누기)
            total_minutes_from_start = (hour_int - 9) * 60 + minute_int
            candle_index = total_minutes_from_start // 3
            candle_start_minute = candle_index * 3

            candle_hour = 9 + candle_start_minute // 60
            candle_min = candle_start_minute % 60

            buy_time_hhmm = f"{candle_hour:02d}{candle_min:02d}00"  # HHMMSS 형식

            self.logger.debug(f"매수 시간 변환: {buy_time_str} -> {buy_time_hhmm}")

            # 데이터에서 time 컬럼 기준으로 매칭
            matching_indices = self._find_matching_indices(
                data, buy_time_hhmm)

            if len(matching_indices) > 0:
                idx = matching_indices[0]
                data_idx = data.index.get_loc(idx)
                if data_idx < len(x_positions):
                    self.logger.debug(f"매수 신호 매칭: {buy_time_str} -> 데이터 인덱스 {data_idx}")
                    return (x_positions[data_idx], buy_price)
                else:
                    self.logger.warning(f"매수 신호 X축 범위 초과: {buy_time_str}")
            else:
                self.logger.warning(f"매수 신호 시간 매칭 실패: {buy_time_str} -> {buy_time_hhmm}")

        except Exception as e:
            self.logger.warning(f"매수 시간 파싱 오류: {buy_time_str} - {e}")

        return None

    def _process_sell_signal(self, trade: Dict[str, Any], data: pd.DataFrame,
                             x_positions: List[float]) -> Optional[tuple]:
        """
        매도 신호 처리

        Args:
            trade: 거래 정보 딕셔너리
            data: OHLCV 데이터프레임
            x_positions: X축 위치 리스트

        Returns:
            (x_position, price) 튜플 또는 None
        """
        sell_time_str = trade.get('sell_time', '')
        sell_price = trade.get('sell_price', 0.0)

        if not sell_time_str or sell_price <= 0:
            return None

        try:
            # 시간 문자열을 HH:MM 형식으로 파싱 (09:23 형식)
            hour, minute = sell_time_str.split(':')

            # 3분봉 캔들 시간으로 변환
            hour_int = int(hour)
            minute_int = int(minute)

            # 3분봉 캔들의 시작 시간 계산
            total_minutes_from_start = (hour_int - 9) * 60 + minute_int
            candle_index = total_minutes_from_start // 3
            candle_start_minute = candle_index * 3

            candle_hour = 9 + candle_start_minute // 60
            candle_min = candle_start_minute % 60

            sell_time_hhmm = f"{candle_hour:02d}{candle_min:02d}00"  # HHMMSS 형식

            self.logger.debug(f"매도 시간 변환: {sell_time_str} -> {sell_time_hhmm}")

            # 데이터에서 time 컬럼 기준으로 매칭
            matching_indices = self._find_matching_indices(
                data, sell_time_hhmm)

            if len(matching_indices) > 0:
                idx = matching_indices[0]
                data_idx = data.index.get_loc(idx)
                if data_idx < len(x_positions):
                    self.logger.debug(f"매도 신호 매칭: {sell_time_str} -> 데이터 인덱스 {data_idx}")
                    return (x_positions[data_idx], sell_price)
                else:
                    self.logger.warning(f"매도 신호 X축 범위 초과: {sell_time_str}")
            else:
                self.logger.warning(f"매도 신호 시간 매칭 실패: {sell_time_str} -> {sell_time_hhmm}")

        except Exception as e:
            self.logger.warning(f"매도 시간 파싱 오류: {sell_time_str} - {e}")

        return None

    def _find_matching_indices(self, data: pd.DataFrame,
                               time_hhmm: str) -> List[int]:
        """
        시간 문자열에 매칭되는 데이터 인덱스 찾기

        Args:
            data: OHLCV 데이터프레임
            time_hhmm: HHMMSS 형식의 시간 문자열

        Returns:
            매칭된 인덱스 리스트
        """
        if 'time' in data.columns:
            time_values = data['time'].astype(str).str.zfill(6)
            return data[time_values == time_hhmm].index.tolist()
        elif 'datetime' in data.columns:
            # datetime에서 시간 부분 추출하여 매칭
            data_times = pd.to_datetime(data['datetime']).dt.strftime('%H%M%S')
            return data[data_times == time_hhmm].index.tolist()
        else:
            return []
