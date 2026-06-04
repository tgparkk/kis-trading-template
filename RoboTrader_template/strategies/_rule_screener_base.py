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

    @abstractmethod
    def base_filter(self, universe: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """유니버스(dict 리스트)에서 전략 성격에 맞는 종목만 추린다."""

    @abstractmethod
    def match(self, df: pd.DataFrame, params: Dict[str, Any]) -> Optional[Tuple[float, str]]:
        """진입룰 적용. 통과 시 (score, reason), 탈락 시 None."""

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
            scored.append((score, CandidateStock(
                code=code, name=u.get("name", code), market=u.get("market", "KRX"),
                score=float(score), reason=reason,
                prev_close=float(df["close"].iloc[-1]),
            )))
        scored.sort(key=lambda t: t[0], reverse=True)
        return [c for _, c in scored[:max_candidates]]

    def _load_universe(self, scan_date: date) -> List[Dict[str, Any]]:
        from strategies.historical_data import get_sectors
        market_map: Dict[str, Dict[str, str]] = {}
        try:
            sdf = get_sectors()
            for _, r in sdf.iterrows():
                market_map[str(r["stock_code"])] = {
                    "name": str(r.get("stock_name", "") or ""),
                    "market": str(r.get("market", "") or ""),
                }
        except Exception:
            market_map = {}
        rows: List[Dict[str, Any]] = []
        if self._db_manager is None:
            return rows
        try:
            with self._db_manager.price_repo._get_connection() as conn:
                cur = conn.cursor()
                cur.execute(
                    "SELECT stock_code, market_cap, trading_value FROM daily_prices WHERE date = %s",
                    (scan_date.strftime("%Y-%m-%d"),),
                )
                for code, mcap, tval in cur.fetchall():
                    meta = market_map.get(str(code), {})
                    rows.append({
                        "code": str(code),
                        "name": meta.get("name", str(code)),
                        "market": meta.get("market", "KRX"),
                        "market_cap": float(mcap or 0),
                        "trading_value": float(tval or 0),
                    })
        except Exception:
            return rows
        return rows

    def _load_daily(self, code: str, scan_date: date) -> Optional[pd.DataFrame]:
        if self._db_manager is None:
            return None
        try:
            return self._db_manager.price_repo.get_daily_prices(code, days=self.lookback_days)
        except Exception:
            return None
