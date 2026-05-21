"""
눌림목(Pullback) 전략 (전략 #10)
==================================

추세(EMA 단조 상승) 중 close가 EMA 근처로 후퇴 후 직전봉 대비 회복 시 진입.

진입 조건:
  1. 직전 lookback_bars개 EMA가 단조 상승
  2. 현재 close가 직전 EMA의 lower_band ~ upper_band 범위 내 (눌림목 구간)
  3. 현재 close > 직전 close (반등 확인)
"""

from typing import Optional

import pandas as pd

from strategies.intraday._base_intraday import IntradayBaseStrategy
from strategies.base import Signal
from utils.intraday_indicators import ema_minute


class PullbackStrategy(IntradayBaseStrategy):
    """추세(EMA 단조 상승) 중 눌림목 후 반등 시 진입."""

    name = "Pullback"
    version = "1.0.0"
    description = "눌림목 매수 — EMA 단조 상승 추세 중 EMA 근처 후퇴 후 회복 시 매수"
    author = "Template"

    def __init__(self, config=None):
        super().__init__(config)
        params = self.config.get("parameters", {})
        self._ema_period = int(params.get("ema_period", 5))
        self._lookback_bars = int(params.get("lookback_bars", 5))
        self._lower_band = float(params.get("lower_band", 0.99))
        self._upper_band = float(params.get("upper_band", 1.005))
        # lookback_bars개 EMA + 현재봉 + EMA 계산 여유
        self._min_data = self._ema_period + self._lookback_bars + 5

    def on_init(self, broker, data_provider, executor) -> bool:
        self._broker = broker
        self._data_provider = data_provider
        self._executor = executor
        self._is_initialized = True
        self.logger.info(
            f"{self.name} v{self.version} 초기화 완료 "
            f"(ema={self._ema_period}, lookback={self._lookback_bars}, "
            f"band=[{self._lower_band}, {self._upper_band}])"
        )
        return True

    def generate_signal(
        self,
        stock_code: str,
        data: pd.DataFrame,
        timeframe: str = "minute",
    ) -> Optional[Signal]:
        if timeframe != "minute":
            return None
        if not isinstance(data, pd.DataFrame) or len(data) < self._min_data:
            return None
        if self._is_after_eod_cutoff(data["datetime"].iloc[-1]):
            return None

        ema = ema_minute(data, period=self._ema_period)

        # 단조 상승 확인: 직전 lookback_bars개 EMA 값 (현재봉 제외)
        # 인덱스: [-lookback_bars-1 : -1] = lookback_bars개
        ema_window = ema.iloc[-(self._lookback_bars + 1):-1]
        if ema_window.isna().any():
            return None

        values = ema_window.values
        monotone_up = all(values[i + 1] >= values[i] for i in range(len(values) - 1))
        if not monotone_up:
            return None

        last_close = float(data["close"].iloc[-1])
        prev_close = float(data["close"].iloc[-2])
        prev_ema = float(ema.iloc[-2])

        if prev_ema <= 0:
            return None

        # 눌림목 구간: lower_band * prev_ema <= last_close <= upper_band * prev_ema
        in_pullback_zone = (
            self._lower_band * prev_ema <= last_close <= self._upper_band * prev_ema
        )
        # 반등 확인: 현재 close > 직전 close
        rebounding = last_close > prev_close

        if in_pullback_zone and rebounding:
            return self._make_buy_signal(
                stock_code,
                last_close,
                reason=(
                    f"Pullback to EMA{self._ema_period}={prev_ema:.0f}: "
                    f"close={last_close:.0f}, rebounding"
                ),
                ema_value=prev_ema,
                lookback_bars=self._lookback_bars,
            )
        return None
