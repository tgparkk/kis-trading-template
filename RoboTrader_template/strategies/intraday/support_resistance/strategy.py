"""
지지/저항(피벗) 매매 전략 (전략 #7)
=====================================

전일 OHLC 기반 Floor Trader's Pivot S1 근처 매수.
전일 OHLC는 data.attrs['prev_day_ohlc']에서 읽음 (없으면 None 반환).
S1 ± near_s1_band_pct (기본 0.5%) 범위에 현재가가 진입하면 매수 신호.
"""

from typing import Optional

import pandas as pd

from strategies.intraday._base_intraday import IntradayBaseStrategy
from strategies.base import Signal
from utils.intraday_indicators import pivot_sr_levels


class SupportResistanceStrategy(IntradayBaseStrategy):
    """전일 OHLC 기반 Floor Trader's Pivot S1 근처 매수."""

    name = "SupportResistance"
    version = "1.0.0"
    description = "전일 피벗 S1 지지선 근처 매수 — Floor Trader's Pivot 방법론"
    author = "Template"

    def __init__(self, config=None):
        super().__init__(config)
        params = self.config.get("parameters", {})
        self._near_s1_band_pct = float(params.get("near_s1_band_pct", 0.005))

    def on_init(self, broker, data_provider, executor) -> bool:
        self._broker = broker
        self._data_provider = data_provider
        self._executor = executor
        self._is_initialized = True
        self.logger.info(
            f"{self.name} v{self.version} 초기화 완료 "
            f"(near_s1_band_pct={self._near_s1_band_pct:.3f})"
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
        if not isinstance(data, pd.DataFrame) or len(data) < 10:
            return None
        if self._is_after_eod_cutoff(data["datetime"].iloc[-1]):
            return None

        # 전일 OHLC는 DataFrame.attrs를 통해 주입받음
        prev = data.attrs.get("prev_day_ohlc") if hasattr(data, "attrs") else None
        if not prev:
            return None
        if not all(k in prev for k in ("high", "low", "close")):
            return None

        levels = pivot_sr_levels(prev)
        s1 = levels["s1"]
        r1 = levels["r1"]

        last_close = float(data["close"].iloc[-1])

        # S1 ± band_pct 범위 진입 확인
        if s1 <= 0:
            return None
        if abs(last_close - s1) / s1 <= self._near_s1_band_pct:
            return self._make_buy_signal(
                stock_code,
                last_close,
                reason=f"Near S1={s1:.2f} (band={self._near_s1_band_pct:.1%})",
                s1=s1,
                r1=r1,
                pivot=levels["pivot"],
            )
        return None
