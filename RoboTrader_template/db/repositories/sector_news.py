"""섹터 뉴스 점수 읽기 + 재정렬 기록 쓰기 (스펙 B §3.3 · §5.4).

- 읽기: sector_news_score(NewsQuant 가 쓴다) · fn_sector_map_as_of(스펙 A)
- 쓰기: sector_news_rerank_log (봇이 쓰는 유일한 표)
- 예외는 «그대로 올린다». 분류·fail-open 은 호출자(CandidateSelector._apply_sector_news_rerank)의 몫.
"""
from datetime import date, datetime
from typing import Dict, List, Optional, Tuple

from .base import BaseRepository

RERANK_LOG_DDL = """
CREATE TABLE IF NOT EXISTS sector_news_rerank_log (
    trade_date    date        NOT NULL,
    strategy      text        NOT NULL,
    stock_code    varchar(20) NOT NULL,
    sector_key    text,
    sector_score  double precision,
    orig_rank     integer     NOT NULL,
    new_rank      integer     NOT NULL,
    applied       boolean     NOT NULL,
    mode          text        NOT NULL,
    reason        text        NOT NULL,
    score_asof    timestamp,
    created_at    timestamp   NOT NULL DEFAULT now(),
    PRIMARY KEY (trade_date, strategy, stock_code)
)
"""

_UPSERT_LOG = """
INSERT INTO sector_news_rerank_log
    (trade_date, strategy, stock_code, sector_key, sector_score, orig_rank, new_rank,
     applied, mode, reason, score_asof, created_at)
VALUES
    (%(trade_date)s, %(strategy)s, %(stock_code)s, %(sector_key)s, %(sector_score)s, %(orig_rank)s, %(new_rank)s,
     %(applied)s, %(mode)s, %(reason)s, %(score_asof)s, now())
ON CONFLICT (trade_date, strategy, stock_code) DO UPDATE SET
    sector_key = EXCLUDED.sector_key, sector_score = EXCLUDED.sector_score,
    orig_rank = EXCLUDED.orig_rank, new_rank = EXCLUDED.new_rank,
    applied = EXCLUDED.applied, mode = EXCLUDED.mode, reason = EXCLUDED.reason,
    score_asof = EXCLUDED.score_asof, created_at = now()
"""


class SectorNewsRepository(BaseRepository):
    """섹터 뉴스 점수·명부 읽기, 재정렬 기록 쓰기."""

    def ensure_table(self) -> None:
        with self._get_connection() as conn:
            cur = conn.cursor()
            cur.execute(RERANK_LOG_DDL)
            conn.commit()
            cur.close()

    def get_scores(self, trade_date: date) -> Tuple[Dict[str, float], Optional[datetime]]:
        """({sector_key: score_signed}, max(computed_at)). 행 0 이면 ({}, None). 표 없음은 UndefinedTable 그대로."""
        with self._get_connection() as conn:
            cur = conn.cursor()
            cur.execute(
                "SELECT sector_key, score_signed, computed_at FROM sector_news_score "
                "WHERE trade_date = %s AND taxonomy = 'ksic3'",
                (trade_date,),
            )
            rows = cur.fetchall()
            cur.close()
        scores = {r[0]: float(r[1]) for r in rows if r[1] is not None}
        asof = max((r[2] for r in rows if r[2] is not None), default=None)
        return scores, asof

    def get_sector_map(self, as_of, codes: List[str]) -> Dict[str, str]:
        """{code: ksic3} — fn_sector_map_as_of(as_of). 함수 없음은 UndefinedFunction 그대로."""
        if not codes:
            return {}
        with self._get_connection() as conn:
            cur = conn.cursor()
            cur.execute(
                "SELECT stock_code, left(ksic_code, 3) FROM fn_sector_map_as_of(%s) "
                "WHERE stock_code = ANY(%s) AND ksic_code IS NOT NULL AND length(ksic_code) >= 3",
                (as_of, list(codes)),
            )
            rows = cur.fetchall()
            cur.close()
        return {r[0]: r[1] for r in rows}

    def save_rerank_log(self, rows: List[Dict]) -> int:
        """UPSERT. 저장 건수."""
        if not rows:
            return 0
        with self._get_connection() as conn:
            cur = conn.cursor()
            cur.executemany(_UPSERT_LOG, rows)
            conn.commit()
            cur.close()
        return len(rows)
