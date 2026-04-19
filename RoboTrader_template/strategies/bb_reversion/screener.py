"""
BB Reversion Screener
=====================

Screen stocks from low-volatility sectors with sideways (ADX < 20) conditions.
Queries stock_sector table for sector filtering.
"""

import os
from datetime import date, datetime
from typing import Any, Dict, List, Optional

try:
    import psycopg2
except ImportError:
    psycopg2 = None

import logging
from core.candidate_selector import CandidateStock
from strategies.screener_base import ScreenerBase
from strategies.historical_data import get_sectors, get_trading_value_at

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
        today = datetime.now().date()
        if scan_date >= today:
            return self._scan_realtime(params)
        return self._scan_historical(scan_date, params)

    def _scan_realtime(self, params: Dict[str, Any]) -> List[CandidateStock]:
        """현재 시점 데이터 기반 스캔 (기존 로직 래핑)."""
        merged = {**self.default_params(), **(params or {})}
        target_sectors: List[str] = merged.get("target_sectors", [])
        max_candidates: int = int(merged.get("max_candidates", 30))

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

    def _scan_historical(self, scan_date: date, params: Dict[str, Any]) -> List[CandidateStock]:
        """과거 특정일 기준 후보 재구성.

        1) get_sectors 로 대상 섹터 종목 취득
        2) get_trading_value_at 으로 직전 20일 평균 거래대금 조회
        3) min_trading_value 이상 필터 후 상위 max_candidates 선정
        """
        merged = {**self.default_params(), **(params or {})}
        target_sectors: List[str] = merged.get("target_sectors", [])
        min_trading_value: float = float(merged.get("min_trading_value", 500_000_000))
        max_candidates: int = int(merged.get("max_candidates", 30))

        # 1. 대상 섹터 종목 조회 — SECTOR_KEYWORDS 를 통해 한국어 키워드로 변환
        korean_keywords: List[str] = []
        for key in target_sectors:
            korean_keywords.extend(SECTOR_KEYWORDS.get(key, [key]))

        sectors_df = get_sectors(target_sectors=korean_keywords if korean_keywords else None)
        if sectors_df.empty:
            logger.warning("BB historical scan: no sector stocks found for %s", target_sectors)
            return []

        stock_codes: List[str] = sectors_df["stock_code"].tolist()
        # stock_code → {name, sector_name} 매핑
        meta = {
            row["stock_code"]: row
            for _, row in sectors_df.iterrows()
        }

        # 2. 직전 20일 평균 거래대금
        tv_df = get_trading_value_at(stock_codes, scan_date, lookback_days=20)
        if tv_df.empty:
            logger.warning("BB historical scan: trading_value data empty for %s", scan_date)
            return []

        # 3. min_trading_value 필터 + 내림차순 정렬
        tv_df = tv_df[tv_df["avg_trading_value"] >= min_trading_value]
        tv_df = tv_df.sort_values("avg_trading_value", ascending=False)

        candidates: List[CandidateStock] = []
        for _, row in tv_df.head(max_candidates).iterrows():
            code = row["stock_code"]
            info = meta.get(code, {})
            candidates.append(
                CandidateStock(
                    code=code,
                    name=info.get("stock_name", ""),
                    market=info.get("market", ""),
                    score=float(row["avg_trading_value"]) / 1e9,  # 단위: 십억 원
                    reason=f"sector={info.get('sector_name', '')}, scan_date={scan_date}",
                )
            )

        logger.info(
            "BB historical scan (%s): %d candidates (sectors=%s, min_tv=%.0f)",
            scan_date, len(candidates), target_sectors, min_trading_value,
        )
        return candidates
