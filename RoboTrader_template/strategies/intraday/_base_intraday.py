"""분봉 데이트레이딩 전략 공통 베이스. T+0, EOD 15:20 청산, SL 1% / TP 2% 디폴트."""
from datetime import time
from typing import Any, Dict, Optional

import pandas as pd

from strategies.base import BaseStrategy, Signal, SignalType


class IntradayBaseStrategy(BaseStrategy):
    """분봉 데이트레이딩 전략 공통 베이스.

    holding_period='intraday' -> BacktestEngine.run_minute 가 EOD 강제청산.
    표준 파라미터 (config.yaml에서 override 가능):
      - stop_loss_pct: 0.01 (1%)
      - take_profit_pct: 0.02 (2%)
      - max_holding_minutes: None (제한 없음)
      - eod_cutoff_buy: '15:00'
    """

    holding_period = "intraday"

    def __init__(self, config: Dict[str, Any] = None):
        super().__init__(config)
        cfg = self.config if isinstance(self.config, dict) else {}
        risk = cfg.get("risk_management", {})
        self.stop_loss_pct = float(risk.get("stop_loss_pct", 0.01))
        self.take_profit_pct = float(risk.get("take_profit_pct", 0.02))
        self.max_holding_minutes = risk.get("max_holding_minutes")
        self.eod_cutoff_buy = risk.get("eod_cutoff_buy", "15:00")
        self._daily_ctx: Dict[str, Any] = {}
        self._daily_ctx_date: Optional[str] = None

    def set_daily_context(self, date: str, ctx: Optional[Dict[str, Any]]) -> None:
        """엔진이 일자 루프 시작 시 호출. 외부 일별 데이터 주입용 훅.

        기본 구현은 dict 저장만. 서브클래스에서 추가 처리 필요 시 super() 호출.
        ctx=None이면 빈 dict로 리셋.
        """
        self._daily_ctx_date = date
        self._daily_ctx = ctx if ctx is not None else {}

    def _is_after_eod_cutoff(self, current_dt) -> bool:
        """current_dt 가 eod_cutoff_buy 이후인지 판단."""
        cutoff = self.eod_cutoff_buy
        if isinstance(cutoff, str) and ":" in cutoff:
            try:
                h, m = map(int, cutoff.split(":")[:2])
                ts = pd.to_datetime(current_dt)
                return ts.time() >= time(h, m)
            except Exception:
                return False
        return False

    def _make_buy_signal(
        self,
        stock_code: str,
        entry_price: float,
        reason: str,
        confidence: float = 70.0,
        **meta,
    ) -> Signal:
        """표준 매수 Signal 생성 헬퍼."""
        return Signal(
            signal_type=SignalType.BUY,
            stock_code=stock_code,
            confidence=confidence,
            target_price=entry_price * (1 + self.take_profit_pct),
            stop_loss=entry_price * (1 - self.stop_loss_pct),
            reasons=[reason],
            metadata=meta,
        )
