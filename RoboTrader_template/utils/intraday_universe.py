"""
분봉 데이트레이딩용 일별 동적 universe 빌더.

필터:
- 일일 거래대금 (amount sum) >= 100억
- 변동성 (max(high) - min(low)) / day_close >= 3%
- 종가 >= 5,000원

저장: cache/intraday_universe/{trade_date}.parquet
"""
from __future__ import annotations

from pathlib import Path
from typing import Optional

import pandas as pd

from db.connection import DatabaseConnection
from utils.logger import setup_logger

logger = setup_logger(__name__)


def _apply_filters(
    df: pd.DataFrame,
    min_amount: float,
    min_volatility_pct: float,
    min_price: float,
) -> pd.DataFrame:
    """SQL 집계 결과 DataFrame에 메모리 필터 적용. 테스트 친화.

    Args:
        df: columns = [stock_code, amount_sum, day_high, day_low, day_close]
        min_amount: 최소 일별 거래대금 (원)
        min_volatility_pct: 최소 변동성 비율 (0.03 = 3%)
        min_price: 최소 종가 (원)

    Returns:
        필터 통과 행만 포함한 DataFrame (volatility_pct 컬럼 추가됨)
    """
    if df.empty:
        return df.copy()

    out = df.copy()
    out['volatility_pct'] = (
        (out['day_high'] - out['day_low'])
        / out['day_close'].replace(0, pd.NA)
    )
    out = out[
        (out['amount_sum'] >= min_amount)
        & (out['volatility_pct'] >= min_volatility_pct)
        & (out['day_close'] >= min_price)
    ]
    return out.reset_index(drop=True)


def build_universe_for_date(
    trade_date: str,
    *,
    min_amount: float = 10_000_000_000,  # 100억원
    min_volatility_pct: float = 0.03,    # 3%
    min_price: float = 5_000.0,
    cache_dir: Optional[Path] = None,
    top_n: Optional[int] = None,
    rank_by: str = "volatility_pct",
) -> list[str]:
    """주어진 거래일의 분봉 데이트레이딩 universe 추출.

    Args:
        trade_date: 거래일 YYYYMMDD 또는 YYYY-MM-DD
        min_amount: 최소 일별 거래대금 (원, 기본 100억)
        min_volatility_pct: 최소 변동성 비율 (기본 3%)
        min_price: 최소 종가 (원, 기본 5,000원)
        cache_dir: Parquet 캐시 저장 디렉토리. None이면 캐시 미사용.
        top_n: 상위 N개로 cap (None이면 무제한). 캐시 hit 시에도 적용됨.
        rank_by: top_n 적용 기준 컬럼명 ("volatility_pct" 또는 "amount_sum").

    Returns:
        필터 통과 종목 코드 리스트. 데이터 없으면 빈 리스트.
    """
    # YYYY-MM-DD → YYYYMMDD 정규화
    if len(trade_date) == 10 and trade_date[4] == '-':
        trade_date = trade_date.replace('-', '')

    # 1) 캐시 hit 확인
    if cache_dir is not None:
        cache_file = Path(cache_dir) / f"{trade_date}.parquet"
        if cache_file.exists():
            try:
                df_cached = pd.read_parquet(cache_file)
                if top_n is not None and len(df_cached) > top_n:
                    df_cached = df_cached.nlargest(top_n, rank_by)
                codes = df_cached['stock_code'].tolist()
                logger.debug(
                    f"universe 캐시 hit: {trade_date} "
                    f"({len(codes)}종목"
                    + (f", top_n={top_n} by {rank_by}" if top_n is not None else "")
                    + ")"
                )
                return codes
            except Exception as e:
                logger.warning(f"universe 캐시 읽기 실패 ({cache_file}): {e}")

    # 2) DB에서 분봉 집계 (거래대금 필터는 SQL HAVING으로 선처리)
    sql = """
        SELECT stock_code,
               SUM(amount)                                  AS amount_sum,
               MAX(high)                                    AS day_high,
               MIN(low)                                     AS day_low,
               (ARRAY_AGG(close ORDER BY datetime DESC))[1] AS day_close
        FROM minute_candles
        WHERE trade_date = %s
        GROUP BY stock_code
        HAVING SUM(amount) >= %s
    """
    try:
        with DatabaseConnection.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(sql, (trade_date, min_amount))
            rows = cursor.fetchall()
            if rows:
                columns = [desc[0] for desc in cursor.description]
                df_raw = pd.DataFrame(rows, columns=columns)
            else:
                df_raw = pd.DataFrame()
            cursor.close()
    except Exception as e:
        logger.error(f"universe DB 조회 실패 ({trade_date}): {e}")
        return []

    if df_raw.empty:
        logger.info(f"universe 데이터 없음: {trade_date}")
        return []

    # 3) 메모리 필터 적용
    df_filtered = _apply_filters(df_raw, min_amount, min_volatility_pct, min_price)

    # 4) top_n cap (캐시 저장 전에 적용하지 않음 — 캐시는 무제한 저장)
    df_for_return = df_filtered
    if top_n is not None and len(df_filtered) > top_n:
        df_for_return = df_filtered.nlargest(top_n, rank_by)

    codes = df_for_return['stock_code'].tolist()
    logger.info(
        f"universe 빌드 완료: {trade_date} "
        f"{len(df_raw)}종목 집계 -> {len(df_filtered)}종목 통과"
        + (f" -> top_n={top_n} by {rank_by} -> {len(codes)}종목" if top_n is not None else "")
    )

    # 5) 캐시 저장 (무제한 — 사용 시점에 top_n 적용)
    if cache_dir is not None:
        cache_file = Path(cache_dir) / f"{trade_date}.parquet"
        cache_file.parent.mkdir(parents=True, exist_ok=True)
        try:
            save_cols = ['stock_code', 'amount_sum', 'volatility_pct', 'day_close']
            df_filtered[save_cols].to_parquet(cache_file, index=False)
            logger.debug(f"universe 캐시 저장: {cache_file}")
        except Exception as e:
            logger.warning(f"universe 캐시 저장 실패: {e}")

    return codes


def build_universe_range(
    start_date: str,
    end_date: str,
    *,
    skip_dates: Optional[set[str]] = None,
    **kwargs,
) -> dict[str, list[str]]:
    """기간 내 거래일별 universe 일괄 빌드.

    Args:
        start_date: 시작 거래일 YYYYMMDD
        end_date: 종료 거래일 YYYYMMDD
        skip_dates: 제외할 일자 집합 (YYYYMMDD 전체 또는 prefix 예: '202603')
        **kwargs: build_universe_for_date에 전달할 키워드 인자

    Returns:
        dict[date_str, list[code]] — 거래일별 universe 코드 리스트
    """
    # 거래일 목록을 minute_candles에서 추출
    sql_dates = (
        "SELECT DISTINCT trade_date FROM minute_candles "
        "WHERE trade_date BETWEEN %s AND %s ORDER BY trade_date"
    )
    try:
        with DatabaseConnection.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(sql_dates, (start_date, end_date))
            rows = cursor.fetchall()
            dates_df = pd.DataFrame(rows, columns=['trade_date']) if rows else pd.DataFrame(columns=['trade_date'])
            cursor.close()
    except Exception as e:
        logger.error(f"거래일 목록 조회 실패 ({start_date}~{end_date}): {e}")
        return {}

    skip = skip_dates or set()
    out: dict[str, list[str]] = {}

    for d in dates_df['trade_date']:
        d_str = str(d)
        # 전체 일치 또는 prefix 일치 모두 skip
        if d_str in skip or any(d_str.startswith(p) for p in skip if len(p) < 8):
            logger.debug(f"universe skip: {d_str}")
            continue
        out[d_str] = build_universe_for_date(d_str, **kwargs)

    logger.info(
        f"universe range 빌드 완료: {start_date}~{end_date} "
        f"-> {len(out)}일, "
        f"총 {sum(len(v) for v in out.values())}슬롯"
    )
    return out
