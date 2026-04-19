"""
후보 종목 Repository (TimescaleDB)
"""
import json
import pandas as pd
from datetime import date, timedelta
from typing import Any, Dict, List, Optional

from .base import BaseRepository
from core.candidate_selector import CandidateStock
from utils.korean_time import now_kst


class CandidateRepository(BaseRepository):
    """후보 종목 데이터 접근 클래스"""

    def save_candidate_stocks(self, candidates: List[CandidateStock], selection_date=None) -> bool:
        """후보 종목 목록 저장"""
        try:
            if not candidates:
                self.logger.warning("저장할 후보 종목이 없습니다")
                return True

            if selection_date is None:
                selection_date = now_kst()

            with self._get_connection() as conn:
                cursor = conn.cursor()

                # 당일 이미 저장된 종목 조회
                target_date = selection_date.strftime('%Y-%m-%d')
                cursor.execute('''
                    SELECT DISTINCT stock_code FROM candidate_stocks
                    WHERE DATE(selection_date) = %s
                ''', (target_date,))

                existing_stocks = {row[0] for row in cursor.fetchall()}

                new_candidates = 0
                duplicate_candidates = 0

                for candidate in candidates:
                    if candidate.code not in existing_stocks:
                        cursor.execute('''
                            INSERT INTO candidate_stocks
                            (stock_code, stock_name, selection_date, score, reasons, status, created_at)
                            VALUES (%s, %s, %s, %s, %s, 'active', %s)
                        ''', (
                            candidate.code,
                            candidate.name,
                            selection_date.strftime('%Y-%m-%d %H:%M:%S'),
                            candidate.score,
                            candidate.reason,
                            now_kst().strftime('%Y-%m-%d %H:%M:%S')
                        ))
                        new_candidates += 1
                        existing_stocks.add(candidate.code)
                    else:
                        duplicate_candidates += 1

                conn.commit()

                if new_candidates > 0:
                    self.logger.info(f"새로운 후보 종목 {new_candidates}개 저장 완료")
                else:
                    self.logger.info(f"모든 후보 종목이 당일 이미 저장됨")

                return True

        except Exception as e:
            self.logger.error(f"후보 종목 저장 실패: {e}")
            return False

    def get_candidate_history(self, days: int = 30) -> pd.DataFrame:
        """후보 종목 선정 이력 조회"""
        try:
            start_date = now_kst() - timedelta(days=days)

            with self._get_connection() as conn:
                query = '''
                    SELECT
                        stock_code, stock_name, selection_date, score, reasons, status
                    FROM candidate_stocks
                    WHERE selection_date >= %s
                    ORDER BY selection_date DESC, score DESC
                '''

                cursor = conn.cursor()
                cursor.execute(query, (start_date.strftime('%Y-%m-%d %H:%M:%S'),))
                rows = cursor.fetchall()
                if rows:
                    columns = [desc[0] for desc in cursor.description]
                    df = pd.DataFrame(rows, columns=columns)
                else:
                    df = pd.DataFrame()
                cursor.close()
                if not df.empty:
                    df['selection_date'] = pd.to_datetime(df['selection_date'])

                self.logger.info(f"후보 종목 이력 {len(df)}건 조회 ({days}일)")
                return df

        except Exception as e:
            self.logger.error(f"후보 종목 이력 조회 실패: {e}")
            return pd.DataFrame()

    def get_candidate_performance(self, days: int = 30) -> pd.DataFrame:
        """후보 종목 성과 분석"""
        try:
            start_date = now_kst() - timedelta(days=days)

            with self._get_connection() as conn:
                query = '''
                    SELECT
                        c.stock_code, c.stock_name, c.selection_date, c.score,
                        COUNT(p.id) as price_records,
                        AVG(p.close_price) as avg_price,
                        MAX(p.high_price) as max_price,
                        MIN(p.low_price) as min_price
                    FROM candidate_stocks c
                    LEFT JOIN stock_prices p ON c.stock_code = p.stock_code
                        AND p.date_time >= c.selection_date
                    WHERE c.selection_date >= %s
                    GROUP BY c.id, c.stock_code, c.stock_name, c.selection_date, c.score
                    ORDER BY c.selection_date DESC, c.score DESC
                '''

                cursor = conn.cursor()
                cursor.execute(query, (start_date.strftime('%Y-%m-%d %H:%M:%S'),))
                rows = cursor.fetchall()
                if rows:
                    columns = [desc[0] for desc in cursor.description]
                    df = pd.DataFrame(rows, columns=columns)
                else:
                    df = pd.DataFrame()
                cursor.close()
                if not df.empty:
                    df['selection_date'] = pd.to_datetime(df['selection_date'])
                return df

        except Exception as e:
            self.logger.error(f"성과 분석 조회 실패: {e}")
            return pd.DataFrame()

    # =========================================================================
    # screener_snapshots 헬퍼
    # =========================================================================

    def save_screener_snapshot(
        self,
        strategy: str,
        scan_date: date,
        params_hash: str,
        params_json: Dict[str, Any],
        candidates: List[CandidateStock],
    ) -> bool:
        """스크리너 결과를 screener_snapshots 에 배치 저장. ON CONFLICT DO UPDATE."""
        try:
            if not candidates:
                return True

            rows = [
                (
                    strategy,
                    scan_date,
                    params_hash,
                    json.dumps(params_json, ensure_ascii=False),
                    c.code,
                    c.name,
                    idx + 1,          # rank_in_snapshot (1-based)
                    c.score if c.score else None,
                    None,             # metadata (Phase 1.2 에서 확장)
                )
                for idx, c in enumerate(candidates)
            ]

            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.executemany(
                    """
                    INSERT INTO screener_snapshots
                        (strategy, scan_date, params_hash, params_json,
                         stock_code, stock_name, rank_in_snapshot, score, metadata)
                    VALUES (%s, %s, %s, %s::jsonb, %s, %s, %s, %s, %s::jsonb)
                    ON CONFLICT (strategy, scan_date, params_hash, stock_code)
                    DO UPDATE SET
                        stock_name       = EXCLUDED.stock_name,
                        rank_in_snapshot = EXCLUDED.rank_in_snapshot,
                        score            = EXCLUDED.score,
                        metadata         = EXCLUDED.metadata
                    """,
                    rows,
                )
                conn.commit()
                self.logger.info(
                    f"screener_snapshots 저장: strategy={strategy} date={scan_date} "
                    f"hash={params_hash[:8]}… {len(candidates)}건"
                )
            return True

        except Exception as e:
            self.logger.error(f"screener_snapshots 저장 실패: {e}")
            return False

    def get_screener_snapshot(
        self,
        strategy: str,
        scan_date: date,
        params_hash: str,
    ) -> List[Dict[str, Any]]:
        """특정 전략·날짜·파라미터 조합의 스냅샷 조회."""
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    """
                    SELECT stock_code, stock_name, rank_in_snapshot, score, metadata
                    FROM screener_snapshots
                    WHERE strategy = %s AND scan_date = %s AND params_hash = %s
                    ORDER BY rank_in_snapshot
                    """,
                    (strategy, scan_date, params_hash),
                )
                cols = [d[0] for d in cursor.description]
                rows = [dict(zip(cols, row)) for row in cursor.fetchall()]
                cursor.close()
            return rows
        except Exception as e:
            self.logger.error(f"screener_snapshots 조회 실패: {e}")
            return []

    def get_snapshot_date_range(
        self,
        strategy: str,
        start_date: date,
        end_date: date,
        params_hash: Optional[str] = None,
    ) -> pd.DataFrame:
        """기간별 스냅샷 조회. params_hash 를 지정하면 특정 파라미터 조합만 반환."""
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                if params_hash:
                    cursor.execute(
                        """
                        SELECT strategy, scan_date, params_hash, params_json,
                               stock_code, stock_name, rank_in_snapshot, score, metadata
                        FROM screener_snapshots
                        WHERE strategy = %s
                          AND scan_date BETWEEN %s AND %s
                          AND params_hash = %s
                        ORDER BY scan_date, rank_in_snapshot
                        """,
                        (strategy, start_date, end_date, params_hash),
                    )
                else:
                    cursor.execute(
                        """
                        SELECT strategy, scan_date, params_hash, params_json,
                               stock_code, stock_name, rank_in_snapshot, score, metadata
                        FROM screener_snapshots
                        WHERE strategy = %s
                          AND scan_date BETWEEN %s AND %s
                        ORDER BY scan_date, params_hash, rank_in_snapshot
                        """,
                        (strategy, start_date, end_date),
                    )
                rows = cursor.fetchall()
                cols = [d[0] for d in cursor.description]
                cursor.close()
            if rows:
                return pd.DataFrame(rows, columns=cols)
            return pd.DataFrame(columns=cols)
        except Exception as e:
            self.logger.error(f"screener_snapshots 기간 조회 실패: {e}")
            return pd.DataFrame()

    def get_daily_candidate_count(self, days: int = 30) -> pd.DataFrame:
        """일별 후보 종목 선정 수"""
        try:
            start_date = now_kst() - timedelta(days=days)

            with self._get_connection() as conn:
                query = '''
                    SELECT
                        DATE(selection_date) as date,
                        COUNT(*) as count,
                        AVG(score) as avg_score,
                        MAX(score) as max_score
                    FROM candidate_stocks
                    WHERE selection_date >= %s
                    GROUP BY DATE(selection_date)
                    ORDER BY date DESC
                '''

                cursor = conn.cursor()
                cursor.execute(query, (start_date.strftime('%Y-%m-%d %H:%M:%S'),))
                rows = cursor.fetchall()
                if rows:
                    columns = [desc[0] for desc in cursor.description]
                    df = pd.DataFrame(rows, columns=columns)
                else:
                    df = pd.DataFrame()
                cursor.close()
                if not df.empty:
                    df['date'] = pd.to_datetime(df['date'])
                return df

        except Exception as e:
            self.logger.error(f"일별 통계 조회 실패: {e}")
            return pd.DataFrame()
