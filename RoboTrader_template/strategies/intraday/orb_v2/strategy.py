"""ORB v2 — 거래량 + KOSPI 시장환경 필터 추가."""

from datetime import time
from typing import Optional

import pandas as pd

from strategies.intraday._base_intraday import IntradayBaseStrategy
from strategies.base import Signal
from utils.intraday_indicators import orb_levels


class OrbV2Strategy(IntradayBaseStrategy):
    """ORB v1 진입 게이트 + 거래량 필터 + KOSPI 시장환경 필터.

    필요한 일별 외부 데이터 (set_daily_context로 주입):
      ctx["prev_day_volume"]: dict[stock_code -> float] — 전일 일봉 거래량
      ctx["kospi_market_up"]: bool — 직전 거래일 KOSPI 종가 > 그 전 거래일 종가이면 True

    결손 fallback: 누락 시 해당 필터 미적용 (통과시킴).
    """

    name = "ORB_v2"
    version = "2.0.0"
    description = "ORB + 거래량/시장환경 필터"
    author = "Template"

    def __init__(self, config=None):
        super().__init__(config)
        params = self.config.get("parameters", {}) if isinstance(self.config, dict) else {}
        self._box_minutes = int(params.get("box_minutes", 30))
        self._volume_ratio_threshold = float(params.get("volume_ratio_threshold", 1.0))
        self._use_market_filter = bool(params.get("use_market_filter", True))
        cutoff_min = self._box_minutes
        cutoff_hour = 9 + cutoff_min // 60
        cutoff_min_rem = cutoff_min % 60
        self._breakout_after = time(cutoff_hour, cutoff_min_rem)
        self._warned_missing_kospi: set = set()
        self._warned_missing_prev_vol: set = set()

    def on_init(self, broker, data_provider, executor) -> bool:
        self._broker = broker
        self._data_provider = data_provider
        self._executor = executor
        self._is_initialized = True
        self.logger.info(
            f"{self.name} v{self.version} 초기화 완료 "
            f"(box={self._box_minutes}, vol_ratio≥{self._volume_ratio_threshold}, "
            f"market_filter={self._use_market_filter})"
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
        if not isinstance(data, pd.DataFrame) or len(data) < self._box_minutes + 5:
            return None
        if self._is_after_eod_cutoff(data["datetime"].iloc[-1]):
            return None

        last_dt = pd.to_datetime(data["datetime"].iloc[-1])
        if last_dt.time() < self._breakout_after:
            return None

        levels = orb_levels(data, window_minutes=self._box_minutes)
        or_high = levels.get("or_high")
        or_low = levels.get("or_low")
        if or_high is None or pd.isna(or_high):
            return None

        last_close = float(data["close"].iloc[-1])
        if not (last_close > float(or_high)):
            return None

        # 필터 1: 거래량
        if not self._volume_filter_passes(stock_code, data):
            return None

        # 필터 2: 시장환경
        if not self._market_filter_passes(last_dt):
            return None

        return self._make_buy_signal(
            stock_code,
            last_close,
            reason=(
                f"ORB v2 breakout: close={last_close:.0f} > or_high={or_high:.0f} "
                f"| vol_ratio≥{self._volume_ratio_threshold} | mkt={self._use_market_filter}"
            ),
            or_high=or_high,
            or_low=or_low,
            or_range=levels.get("or_range"),
        )

    # ---------- internal filters ----------

    def _volume_filter_passes(self, stock_code: str, data: pd.DataFrame) -> bool:
        prev_vol_map = self._daily_ctx.get("prev_day_volume", {}) if self._daily_ctx else {}
        prev_vol = prev_vol_map.get(stock_code, 0.0)
        if prev_vol <= 0:
            if stock_code not in self._warned_missing_prev_vol:
                self.logger.warning(
                    f"{stock_code} 전일 일봉 거래량 누락 — volume 필터 미적용"
                )
                self._warned_missing_prev_vol.add(stock_code)
            return True  # fallback

        cum_vol = float(data["volume"].fillna(0.0).sum())
        ratio = cum_vol / float(prev_vol)
        return ratio >= self._volume_ratio_threshold

    def _market_filter_passes(self, last_dt: pd.Timestamp) -> bool:
        if not self._use_market_filter:
            return True
        ctx = self._daily_ctx or {}
        flag = ctx.get("kospi_market_up")
        if flag is None:
            date_key = self._daily_ctx_date or "unknown"
            if date_key not in self._warned_missing_kospi:
                self.logger.warning(
                    f"{date_key} kospi_market_up 결손 — market 필터 미적용"
                )
                self._warned_missing_kospi.add(date_key)
            return True  # fallback
        return bool(flag)
