"""
BB Reversion Screener
=====================

Screen stocks from low-volatility sectors with sideways (ADX < 20) conditions.
Queries stock_sector table for sector filtering.
"""

import os
from datetime import date
from typing import Any, Dict, List, Optional

try:
    import psycopg2
except ImportError:
    psycopg2 = None

import logging
from core.candidate_selector import CandidateStock
from strategies.screener_base import ScreenerBase

logger = logging.getLogger(__name__)

# Sector keyword mapping: config key -> DB sector_name keywords (Korean)
SECTOR_KEYWORDS = {
    "bank": ["은행"],
    "insurance": ["보험"],
    "utility": ["전기", "가스", "유틸"],
    "food": ["음식", "식품", "음료"],
    "telecom": ["통신"],
    "dividend": ["배당"],
}


class BBReversionScreener:
    """Screen low-volatility sector stocks for BB reversion strategy."""

    def __init__(self):
        self._db_params = {
            "host": os.getenv('STRATEGY_DB_HOST', os.getenv('TIMESCALE_HOST', '172.23.208.1')),
            "port": int(os.getenv('STRATEGY_DB_PORT', os.getenv('TIMESCALE_PORT', 5433))),
            "user": os.getenv('STRATEGY_DB_USER', os.getenv('TIMESCALE_USER', 'postgres')),
            "password": os.getenv('STRATEGY_DB_PASSWORD', os.getenv('TIMESCALE_PASSWORD', '')),
            "dbname": os.getenv('STRATEGY_DB_NAME', 'strategy_analysis'),
        }

    def get_sector_stocks(self, target_sectors: List[str]) -> List[Dict]:
        """
        Query stock_sector table for stocks in target sectors.

        Returns:
            List of dicts with keys: stock_code, stock_name, sector_name, market
        """
        if psycopg2 is None:
            logger.warning("psycopg2 not installed, cannot query DB for sector stocks")
            return []

        keywords = []
        for sector_key in target_sectors:
            kws = SECTOR_KEYWORDS.get(sector_key, [sector_key])
            keywords.extend(kws)

        if not keywords:
            return []

        # Build LIKE conditions
        like_clauses = " OR ".join(
            ["sector_name LIKE %s"] * len(keywords)
        )
        params = [f"%{kw}%" for kw in keywords]

        query = f"""
            SELECT stock_code, stock_name, sector_name, market
            FROM stock_sector
            WHERE ({like_clauses})
            ORDER BY stock_code
        """

        results = []
        try:
            conn = psycopg2.connect(**self._db_params)
            try:
                with conn.cursor() as cur:
                    cur.execute(query, params)
                    rows = cur.fetchall()
                    for row in rows:
                        results.append({
                            "stock_code": row[0],
                            "stock_name": row[1],
                            "sector_name": row[2],
                            "market": row[3],
                        })
            finally:
                conn.close()
            logger.info(
                "BB screener: %d stocks found in sectors %s",
                len(results), target_sectors,
            )
        except Exception as e:
            logger.error("BB screener DB query failed: %s", e)

        return results


class BBReversionScreenerAdapter(ScreenerBase):
    """BBReversionScreener 를 ScreenerBase 인터페이스로 감싸는 어댑터."""

    strategy_name = "bb_reversion"

    def __init__(self, config=None, broker=None, db_manager=None) -> None:
        # BBReversionScreener 는 config/broker 미사용 — 시그니처 통일을 위해 수용
        self._screener = BBReversionScreener()

    def default_params(self) -> Dict[str, Any]:
        return {
            "target_sectors": ["bank", "insurance", "utility", "food", "telecom", "dividend"],
            "min_trading_value": 500_000_000,
            "max_candidates": 30,
        }

    def scan(self, scan_date: date, params: Dict[str, Any]) -> List[CandidateStock]:
        # scan_date 는 현재 기록 전용 — 실제 조회는 현재 시점 데이터 사용 (Phase 3 에서 소급 지원 예정)
        merged = {**self.default_params(), **(params or {})}
        target_sectors: List[str] = merged.get("target_sectors", [])
        max_candidates: int = int(merged.get("max_candidates", 30))
        # TODO: min_trading_value 필터 — BBReversionScreener 가 거래대금 데이터를 제공하지 않아 현재 미적용

        raw = self._screener.get_sector_stocks(target_sectors)

        candidates = [
            CandidateStock(
                code=item["stock_code"],
                name=item["stock_name"],
                market=item.get("market", ""),
                score=0.0,
                reason=f"sector={item.get('sector_name', '')}",
            )
            for item in raw
        ]

        return candidates[:max_candidates]
