"""RuleScreenerBase — 전략 진입룰을 daily_prices 유니버스에 적용하는 공통 스크리너."""
from __future__ import annotations

from abc import abstractmethod
from datetime import date
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd

from strategies.screener_base import ScreenerBase
from core.candidate_selector import CandidateStock


class RuleScreenerBase(ScreenerBase):
    strategy_name: str = "rule_screener_base"
    lookback_days: int = 120

    def __init__(self, config=None, broker=None, db_manager=None) -> None:
        self._config = config
        self._broker = broker
        self._db_manager = db_manager
        self._quant = None

    def _quant_reader(self):
        if self._quant is None:
            from db.quant_daily_reader import QuantDailyReader
            self._quant = QuantDailyReader()
        return self._quant

    @abstractmethod
    def base_filter(self, universe: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """유니버스(dict 리스트)에서 전략 성격에 맞는 종목만 추린다."""

    @abstractmethod
    def match(self, df: pd.DataFrame, params: Dict[str, Any]) -> Optional[Tuple[float, str]]:
        """진입룰 적용. 통과 시 (score, reason), 탈락 시 None."""

    def default_params(self) -> Dict[str, Any]:
        return {"max_candidates": 10}

    def scan(self, scan_date: date, params: Dict[str, Any]) -> List[CandidateStock]:
        merged = {**self.default_params(), **(params or {})}
        max_candidates = int(merged.get("max_candidates", 10))
        universe = self.base_filter(self._load_universe(scan_date))
        scored: List[Tuple[float, CandidateStock]] = []
        for u in universe:
            code = u["code"]
            df = self._load_daily(code, scan_date)
            if df is None or df.empty:
                continue
            df = df[df["date"].dt.date <= scan_date]
            if df.empty:
                continue
            verdict = self.match(df, merged)
            if verdict is None:
                continue
            score, reason = verdict
            prev_close = float(df["close"].iloc[-1])
            if not (prev_close > 0):
                continue
            scored.append((score, CandidateStock(
                code=code, name=u.get("name", code), market=u.get("market", "KRX"),
                score=float(score), reason=reason, prev_close=prev_close,
            )))
        scored.sort(key=lambda t: t[0], reverse=True)
        return [c for _, c in scored[:max_candidates]]

    def _load_universe(self, scan_date: date) -> List[Dict[str, Any]]:
        snapshot = self._quant_reader().get_universe_snapshot(scan_date)
        return [
            {"code": it["stock_code"], "name": it["stock_code"],
             "market_cap": it["market_cap"], "trading_value": it["trading_value"]}
            for it in snapshot
        ]

    def _load_daily(self, code: str, scan_date: date) -> Optional[pd.DataFrame]:
        return self._quant_reader().get_daily_prices(code, end_date=scan_date, days=self.lookback_days)
