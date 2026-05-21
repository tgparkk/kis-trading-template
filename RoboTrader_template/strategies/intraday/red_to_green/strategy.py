"""
레드 투 그린 전략 (전략 #8)
=============================

전일 종가를 처음 위로 교차(레드→그린 전환)하는 시점에 진입.
prev_close는 data.attrs['prev_close']에서 읽음 (없으면 None 반환).
분봉 close가 prev_close를 처음으로 상향 돌파할 때 매수 신호.
"""

from typing import Optional

import pandas as pd

from strategies.intraday._base_intraday import IntradayBaseStrategy
from strategies.base import Signal
from utils.intraday_indicators import red_to_green


class RedToGreenStrategy(IntradayBaseStrategy):
    """전일 종가 회복(처음 위로 교차) 시점에 진입."""

    name = "RedToGreen"
    version = "1.0.0"
    description = "레드 투 그린 — 전일 종가를 처음 상향 돌파하는 분봉에 매수"
    author = "Template"

    def __init__(self, config=None):
        super().__init__(config)

    def on_init(self, broker, data_provider, executor) -> bool:
        self._broker = broker
        self._data_provider = data_provider
        self._executor = executor
        self._is_initialized = True
        self.logger.info(f"{self.name} v{self.version} 초기화 완료")
        return True

    def generate_signal(
        self,
        stock_code: str,
        data: pd.DataFrame,
        timeframe: str = "minute",
    ) -> Optional[Signal]:
        if timeframe != "minute":
            return None
        if not isinstance(data, pd.DataFrame) or len(data) < 5:
            return None
        if self._is_after_eod_cutoff(data["datetime"].iloc[-1]):
            return None

        # prev_close는 DataFrame.attrs를 통해 주입받음
        prev_close = data.attrs.get("prev_close") if hasattr(data, "attrs") else None
        if prev_close is None:
            return None

        prev_close_f = float(prev_close)
        signals = red_to_green(data, prev_close_f)

        if bool(signals.iloc[-1]):
            last_close = float(data["close"].iloc[-1])
            return self._make_buy_signal(
                stock_code,
                last_close,
                reason=f"Red to Green: crossed prev_close={prev_close_f:.0f}",
                prev_close=prev_close_f,
            )
        return None
