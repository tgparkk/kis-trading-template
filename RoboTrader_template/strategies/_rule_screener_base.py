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

    @staticmethod
    def _passes_market_cap(
        mcap: Optional[float],
        *,
        min_cap: Optional[float] = None,
        max_cap: Optional[float] = None,
        max_inclusive: bool = False,
    ) -> bool:
        """시총 가드 (fail-closed). 통과 시 True, 제외 시 False.

        결측(None)·0·음수면 전략 컨셉(대형/중소형) 검증이 불가능하므로 **무조건 제외**.
        라이브 경로는 ``COALESCE(market_cap,0)`` 로 결측이 0 으로 들어오므로 ``<=0`` 가
        실제 결측을 잡는다(None 은 방어). 시총이 채워진 종목엔 하한/상한 컷만 적용해
        기존(라이브) 동작을 그대로 보존한다.

        Args:
            mcap: 종목 시가총액(원). None/0/음수 = 결측 → 제외.
            min_cap: 하한(이상). ``mcap < min_cap`` 이면 제외.
            max_cap: 상한. ``max_inclusive=False``(기본)면 ``mcap >= max_cap`` 제외
                ('미만' 컨셉, daytrading). True 면 ``mcap > max_cap`` 제외('이하' 컨셉,
                ma5/ma20).
        """
        if mcap is None or mcap <= 0:
            return False
        if min_cap is not None and mcap < min_cap:
            return False
        if max_cap is not None:
            if max_inclusive:
                if mcap > max_cap:
                    return False
            elif mcap >= max_cap:
                return False
        return True

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
