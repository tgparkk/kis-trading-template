"""
ORB (Opening Range Breakout) 전략 (전략 #9)
============================================

개장 후 box_minutes분(기본 30분) 박스 고가 돌파 시 진입.
09:30 이후(09:00 + box_minutes) 에만 돌파 판정 수행.
"""

from datetime import time
from typing import Optional

import pandas as pd

from strategies.intraday._base_intraday import IntradayBaseStrategy
from strategies.base import Signal
from utils.intraday_indicators import orb_levels


class OrbStrategy(IntradayBaseStrategy):
    """개장 box_minutes분 박스 고가 돌파 시 진입."""

    name = "ORB"
    version = "1.0.0"
    description = "Opening Range Breakout — 개장 N분 박스 상단 돌파 시 매수"
    author = "Template"

    def __init__(self, config=None):
        super().__init__(config)
        params = self.config.get("parameters", {})
        self._box_minutes = int(params.get("box_minutes", 30))
        # 09:00 + box_minutes 이후에만 돌파 판정
        cutoff_min = self._box_minutes  # 09:00 기준 분 오프셋
        cutoff_hour = 9 + cutoff_min // 60
        cutoff_min_rem = cutoff_min % 60
        self._breakout_after = time(cutoff_hour, cutoff_min_rem)

    def on_init(self, broker, data_provider, executor) -> bool:
        self._broker = broker
        self._data_provider = data_provider
        self._executor = executor
        self._is_initialized = True
        self.logger.info(
            f"{self.name} v{self.version} 초기화 완료 "
            f"(box_minutes={self._box_minutes}, "
            f"breakout_after={self._breakout_after.strftime('%H:%M')})"
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
        # box_minutes + 여유 5봉 이상 필요
        if not isinstance(data, pd.DataFrame) or len(data) < self._box_minutes + 5:
            return None
        if self._is_after_eod_cutoff(data["datetime"].iloc[-1]):
            return None

        last_dt = pd.to_datetime(data["datetime"].iloc[-1])
        # 개장 박스가 완성된 이후에만 돌파 판정
        if last_dt.time() < self._breakout_after:
            return None

        levels = orb_levels(data, window_minutes=self._box_minutes)
        or_high = levels.get("or_high")
        or_low = levels.get("or_low")

        if or_high is None or pd.isna(or_high):
            return None

        last_close = float(data["close"].iloc[-1])

        if last_close > float(or_high):
            return self._make_buy_signal(
                stock_code,
                last_close,
                reason=f"ORB breakout: close={last_close:.0f} > or_high={or_high:.0f}",
                or_high=or_high,
                or_low=or_low,
                or_range=levels.get("or_range"),
            )
        return None
