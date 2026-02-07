"""
캔들스틱 차트 렌더링 전용 모듈
캔들스틱 및 거래량 차트를 그리는 기능 담당
"""
from typing import List
import pandas as pd
from matplotlib.patches import Rectangle

from utils.logger import setup_logger


class CandlestickRenderer:
    """캔들스틱 및 거래량 차트 렌더링"""

    def __init__(self):
        self.logger = setup_logger(__name__)

    def draw_candlestick(self, ax, data: pd.DataFrame, x_positions: List[float],
                         timeframe: str = '1min'):
        """
        캔들스틱 차트 그리기 - 실제 데이터 인덱스 기준

        Args:
            ax: matplotlib axis 객체
            data: OHLCV 데이터프레임
            x_positions: X축 위치 리스트
            timeframe: 시간프레임 ('1min', '3min', '5min')
        """
        try:
            self.logger.debug(f"캔들스틱 그리기 시작:")
            self.logger.debug(f"   - timeframe: {timeframe}")
            self.logger.debug(f"   - 입력 데이터 개수: {len(data)}")

            if not data.empty:
                self.logger.debug(f"   - 데이터 시간 범위: {data.iloc[0].get('time', 'N/A')} ~ {data.iloc[-1].get('time', 'N/A')}")

            self.logger.debug(f"   - X 위치 개수: {len(x_positions)}")
            self.logger.debug(f"   - X 위치 범위: {min(x_positions) if x_positions else 'N/A'} ~ {max(x_positions) if x_positions else 'N/A'}")

            # 캔들스틱 그리기
            drawn_candles = 0
            for idx, (_, row) in enumerate(data.iterrows()):
                if idx >= len(x_positions):
                    break

                x = x_positions[idx]
                open_price = row['open']
                high_price = row['high']
                low_price = row['low']
                close_price = row['close']

                # 캔들 색상 결정
                color = 'red' if close_price >= open_price else 'blue'

                # High-Low 선 (심지) - 캔들과 같은 색
                ax.plot([x, x], [low_price, high_price], color=color, linewidth=0.8)

                # 캔들 몸통
                candle_height = abs(close_price - open_price)
                candle_bottom = min(open_price, close_price)

                if candle_height > 0:
                    # 상승봉(빨간색) / 하락봉(파란색)
                    if close_price >= open_price:
                        # 상승봉 - 빨간색 채움
                        candle = Rectangle((x - 0.4, candle_bottom), 0.8, candle_height,
                                         facecolor='red', edgecolor='darkred',
                                         linewidth=0.5, alpha=0.9)
                    else:
                        # 하락봉 - 파란색 채움
                        candle = Rectangle((x - 0.4, candle_bottom), 0.8, candle_height,
                                         facecolor='blue', edgecolor='darkblue',
                                         linewidth=0.5, alpha=0.9)
                    ax.add_patch(candle)
                else:
                    # 시가와 종가가 같은 경우 (십자선)
                    line_color = 'red' if close_price >= open_price else 'blue'
                    ax.plot([x - 0.4, x + 0.4], [close_price, close_price],
                           color=line_color, linewidth=1.5)

                drawn_candles += 1

            self.logger.debug(f"   - 실제 그려진 캔들 개수: {drawn_candles}")
            if drawn_candles != len(data):
                self.logger.warning(f"   데이터({len(data)})와 그려진 캔들({drawn_candles}) 개수 불일치")

        except Exception as e:
            self.logger.error(f"캔들스틱 그리기 오류: {e}")

    def draw_volume_chart(self, ax, data: pd.DataFrame, x_positions: List[float]):
        """
        거래량 차트 그리기 - 정확한 x 위치 기준

        Args:
            ax: matplotlib axis 객체
            data: OHLCV 데이터프레임
            x_positions: X축 위치 리스트
        """
        try:
            for idx, (_, row) in enumerate(data.iterrows()):
                if idx >= len(x_positions):
                    break

                x = x_positions[idx]
                volume = row['volume']
                close_price = row['close']
                open_price = row['open']

                # 거래량 색상 (캔들과 동일)
                if close_price >= open_price:
                    color = 'red'
                    alpha = 0.7
                else:
                    color = 'blue'
                    alpha = 0.7

                ax.bar(x, volume, color=color, alpha=alpha, width=0.8,
                      edgecolor='none')

        except Exception as e:
            self.logger.error(f"거래량 차트 그리기 오류: {e}")
