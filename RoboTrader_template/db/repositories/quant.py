"""
퀀트 팩터/포트폴리오 Repository (TimescaleDB)
"""
import json
from typing import List, Dict, Any

from .base import BaseRepository
from utils.korean_time import now_kst


class QuantRepository(BaseRepository):
    """퀀트 팩터/포트폴리오 데이터 접근 클래스"""

    def upsert_financial_data(self, financial_rows: List[Dict[str, Any]]) -> bool:
        """재무 지표 데이터 저장/갱신"""
        try:
            if not financial_rows:
                self.logger.debug("재무 데이터 입력 없음")
                return True

            with self._get_connection() as conn:
                cursor = conn.cursor()
                now_str = now_kst().strftime('%Y-%m-%d %H:%M:%S')

                for row in financial_rows:
                    values = (
                        row.get('stock_code', '').strip(),
                        str(row.get('base_year', '')).strip(),
                        str(row.get('base_quarter', '')).strip(),
                        str(row.get('report_date', '') or ''),
                        self.to_float(row.get('per')),
                        self.to_float(row.get('pbr')),
                        self.to_float(row.get('eps')),
                        self.to_float(row.get('bps')),
                        self.to_float(row.get('roe')),
                        self.to_float(row.get('roa')),
                        self.to_float(row.get('debt_ratio')),
                        self.to_float(row.get('operating_margin')),
                        self.to_float(row.get('sales')),
                        self.to_float(row.get('net_income')),
                        self.to_float(row.get('market_cap')),
                        str(row.get('industry_code', '') or '').strip(),
                        row.get('retrieved_at') or now_str,
                        now_str
                    )

                    cursor.execute('''
                        INSERT INTO financial_data (
                            stock_code, base_year, base_quarter, report_date,
                            per, pbr, eps, bps, roe, roa, debt_ratio, operating_margin,
                            sales, net_income, market_cap, industry_code,
                            retrieved_at, created_at, updated_at
                        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, NOW())
                        ON CONFLICT(stock_code, base_year, base_quarter) DO UPDATE SET
                            report_date = EXCLUDED.report_date,
                            per = EXCLUDED.per, pbr = EXCLUDED.pbr,
                            eps = EXCLUDED.eps, bps = EXCLUDED.bps,
                            roe = EXCLUDED.roe, roa = EXCLUDED.roa,
                            debt_ratio = EXCLUDED.debt_ratio,
                            operating_margin = EXCLUDED.operating_margin,
                            sales = EXCLUDED.sales, net_income = EXCLUDED.net_income,
                            market_cap = EXCLUDED.market_cap,
                            industry_code = EXCLUDED.industry_code,
                            retrieved_at = EXCLUDED.retrieved_at,
                            updated_at = NOW()
                    ''', values)

                conn.commit()
                self.logger.info(f"재무 데이터 {len(financial_rows)}건 저장/갱신")
                return True

        except Exception as e:
            self.logger.error(f"재무 데이터 저장 실패: {e}")
            return False

    def save_quant_factors(self, calc_date: str, factor_rows: List[Dict[str, Any]]) -> bool:
        """일자별 팩터 스코어 저장"""
        try:
            if not factor_rows:
                self.logger.warning("저장할 팩터 데이터가 없습니다")
                return True

            calc_date = str(calc_date)
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute('DELETE FROM quant_factors WHERE calc_date = %s', (calc_date,))

                now_str = now_kst().strftime('%Y-%m-%d %H:%M:%S')
                rows = []
                for idx, row in enumerate(factor_rows, start=1):
                    factor_details = row.get('factor_details')
                    if isinstance(factor_details, dict):
                        factor_details = json.dumps(factor_details, ensure_ascii=False)
                    rows.append((
                        calc_date,
                        row.get('stock_code', '').strip(),
                        float(row.get('value_score', 0) or 0),
                        float(row.get('momentum_score', 0) or 0),
                        float(row.get('quality_score', 0) or 0),
                        float(row.get('growth_score', 0) or 0),
                        float(row.get('total_score', 0) or 0),
                        int(row.get('rank') or row.get('factor_rank') or idx),
                        factor_details or '',
                        now_str, now_str
                    ))

                for row_data in rows:
                    cursor.execute('''
                        INSERT INTO quant_factors (
                            calc_date, stock_code,
                            value_score, momentum_score, quality_score, growth_score,
                            total_score, factor_rank, factor_details,
                            created_at, updated_at
                        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    ''', row_data)

                conn.commit()
                self.logger.info(f"{calc_date} 팩터 스코어 {len(rows)}건 저장")
                return True

        except Exception as e:
            self.logger.error(f"팩터 스코어 저장 실패: {e}")
            return False

    def save_quant_portfolio(self, calc_date: str, portfolio_rows: List[Dict[str, Any]]) -> bool:
        """일자별 상위 포트폴리오 저장"""
        try:
            calc_date = str(calc_date)
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute('DELETE FROM quant_portfolio WHERE calc_date = %s', (calc_date,))

                if not portfolio_rows:
                    conn.commit()
                    self.logger.info(f"{calc_date} 포트폴리오 데이터 없음")
                    return True

                now_str = now_kst().strftime('%Y-%m-%d %H:%M:%S')
                rows = []
                for row in portfolio_rows:
                    rows.append((
                        calc_date,
                        row.get('stock_code', '').strip(),
                        row.get('stock_name', ''),
                        int(row.get('rank') or row.get('portfolio_rank') or 0),
                        float(row.get('total_score', 0) or 0),
                        row.get('reason', ''),
                        now_str, now_str
                    ))

                for row_data in rows:
                    cursor.execute('''
                        INSERT INTO quant_portfolio (
                            calc_date, stock_code, stock_name, rank, total_score, reason,
                            created_at, updated_at
                        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                    ''', row_data)

                conn.commit()
                self.logger.info(f"{calc_date} 포트폴리오 {len(rows)}건 저장")
                return True

        except Exception as e:
            self.logger.error(f"포트폴리오 저장 실패: {e}")
            return False

    def get_quant_portfolio(self, calc_date: str, limit: int = 50) -> List[Dict[str, Any]]:
        """일자별 상위 포트폴리오 조회"""
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    SELECT stock_code, stock_name, rank, total_score, reason
                    FROM quant_portfolio
                    WHERE calc_date = %s
                    ORDER BY rank ASC
                    LIMIT %s
                ''', (calc_date, limit))
                rows = cursor.fetchall()
                return [
                    {
                        'stock_code': row[0], 'stock_name': row[1],
                        'rank': row[2], 'total_score': row[3], 'reason': row[4] or ''
                    }
                    for row in rows
                ]
        except Exception as e:
            self.logger.error(f"포트폴리오 조회 실패: {e}")
            return []

    def get_quant_factors(self, calc_date: str, stock_code: str = None) -> List[Dict[str, Any]]:
        """일자별 팩터 점수 조회"""
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                if stock_code:
                    cursor.execute('''
                        SELECT stock_code, value_score, momentum_score, quality_score,
                               growth_score, total_score, factor_rank
                        FROM quant_factors
                        WHERE calc_date = %s AND stock_code = %s
                    ''', (calc_date, stock_code))
                else:
                    cursor.execute('''
                        SELECT stock_code, value_score, momentum_score, quality_score,
                               growth_score, total_score, factor_rank
                        FROM quant_factors
                        WHERE calc_date = %s
                        ORDER BY factor_rank ASC
                    ''', (calc_date,))

                rows = cursor.fetchall()
                return [
                    {
                        'stock_code': row[0], 'value_score': row[1],
                        'momentum_score': row[2], 'quality_score': row[3],
                        'growth_score': row[4], 'total_score': row[5], 'factor_rank': row[6]
                    }
                    for row in rows
                ]
        except Exception as e:
            self.logger.error(f"팩터 점수 조회 실패: {e}")
            return []
