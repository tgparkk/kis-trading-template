"""
VWAP 추세 전략 (전략 #6)
========================

close > VWAP + 거래량 z-score > 1.0 시 추세 추종 진입.
당일 VWAP를 기준으로 가격이 VWAP 위에 있고, 거래량이 평소보다 유의미하게
많을 때(z-score > vol_zscore_threshold) 매수 신호를 발생시킨다.
"""

from typing import Optional

import pandas as pd

from strategies.intraday._base_intraday import IntradayBaseStrategy
from strategies.base import Signal
from utils.intraday_indicators import vwap, volume_zscore


class VwapTradeStrategy(IntradayBaseStrategy):
    """close > VWAP + 거래량 z-score > 1.0 시 추세 추종 진입."""

    name = "VWAPTrade"
    version = "1.0.0"
    description = "VWAP 추세 추종 — 가격이 VWAP 위 + 거래량 z-score 임계값 초과 시 매수"
    author = "Template"

    def __init__(self, config=None):
        super().__init__(config)
        params = self.config.get("parameters", {})
        self._vol_zscore_threshold = float(params.get("vol_zscore_threshold", 1.0))
        self._vol_window = int(params.get("vol_window", 20))

    def on_init(self, broker, data_provider, executor) -> bool:
        self._broker = broker
        self._data_provider = data_provider
        self._executor = executor
        self._is_initialized = True
        self.logger.info(
            f"{self.name} v{self.version} 초기화 완료 "
            f"(vol_zscore_threshold={self._vol_zscore_threshold}, "
            f"vol_window={self._vol_window})"
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
        if not isinstance(data, pd.DataFrame) or len(data) < self._vol_window + 5:
            return None
        if self._is_after_eod_cutoff(data["datetime"].iloc[-1]):
            return None

        v = vwap(data)
        z = volume_zscore(data, window=self._vol_window)

        if v.isna().iloc[-1] or pd.isna(z.iloc[-1]):
            return None

        last_close = float(data["close"].iloc[-1])
        last_vwap = float(v.iloc[-1])
        last_z = float(z.iloc[-1])

        if last_close > last_vwap and last_z > self._vol_zscore_threshold:
            return self._make_buy_signal(
                stock_code,
                last_close,
                reason=f"VWAP trend: close={last_close:.0f} > VWAP={last_vwap:.0f}, vol z={last_z:.2f}",
                vwap=last_vwap,
                vol_zscore=last_z,
            )
        return None
