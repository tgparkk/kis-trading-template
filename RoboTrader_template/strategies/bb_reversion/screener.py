"""
BB Reversion Screener
=====================

Screen stocks from low-volatility sectors with sideways (ADX < 20) conditions.
Queries stock_sector table for sector filtering.
"""

import os
from typing import List, Dict, Optional

try:
    import psycopg2
except ImportError:
    psycopg2 = None

import logging

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
