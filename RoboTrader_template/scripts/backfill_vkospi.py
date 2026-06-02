"""
VKOSPI 일봉 백필 스크립트 (Phase 5 — S2-01)

기능:
  1. pykrx get_index_ohlcv_by_date("VKOSPI", fromdate, todate) 로 VKOSPI 일봉 수집
  2. 연도별 배치로 2021-01 ~ 현재 (5.4년치) 수집
  3. robotrader.vkospi_daily 에 INSERT ON CONFLICT DO NOTHING (멱등)

PIT 보장:
  - trade_date = T일 (VKOSPI 일봉 종가 확정: 장 마감 15:30 KST)
  - T+1 시초가 의사결정에 T일 데이터 사용
  - 백테스트: T일 종가 → T+1 진입 강제

실행:
  python scripts/backfill_vkospi.py --dry-run     # dry-run (DB 저장 없음)
  python scripts/backfill_vkospi.py --pilot       # 2024-01 ~ 현재 (파일럿)
  python scripts/backfill_vkospi.py --yes         # 전체 5.4년 백필 (사장님 결재 필요)

환경:
  .env 파일: TIMESCALE_HOST, TIMESCALE_PORT, TIMESCALE_USER, TIMESCALE_PASSWORD, TIMESCALE_DB

절대 금지:
  - DELETE/UPDATE 없음 (INSERT ON CONFLICT DO NOTHING만)
  - rate limit 준수: 연도별 배치 + sleep 1.5초
"""
from __future__ import annotations

import argparse
import logging
import os
import sys
import time
from datetime import date, datetime

import psycopg2
import psycopg2.extras

# ─────────────────────────────────────────────────────────────────────────────
# 프로젝트 루트를 sys.path에 추가
# ─────────────────────────────────────────────────────────────────────────────
_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(_ROOT))

from dotenv import load_dotenv
load_dotenv(os.path.join(_ROOT, ".env"))

# ─────────────────────────────────────────────────────────────────────────────
# 로깅
# ─────────────────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────────────────────
# 설정
# ─────────────────────────────────────────────────────────────────────────────
TODAY = date.today()
BACKFILL_START = date(2021, 1, 4)   # 5.4년치 시작일
PILOT_START    = date(2024, 1, 2)   # 파일럿: ~1.4년

PYKRX_SLEEP = 1.5   # 연도별 호출 사이 sleep (rate limit)

# VKOSPI pykrx 티커 코드
# pykrx get_index_ohlcv_by_date(fromdate, todate, ticker) 에서
# ticker = group_id(1자) + index_id(나머지)
# VKOSPI는 KRX 인덱스 그룹 "5" (변동성지수), 코드 "030"
# 전체 티커: "5030"
# 확인 방법: stock.get_index_ticker_list(market="KOSPI") 실행 후
#            stock.get_index_ticker_name(ticker) 으로 "VKOSPI" 이름 확인
VKOSPI_TICKER = "5030"

# 대안 티커 후보 (KRX API 응답값이 달라질 경우 시도)
_VKOSPI_TICKER_CANDIDATES = ["5030", "VKOSPI"]

_DB_DEFAULTS = dict(
    host=os.getenv("TIMESCALE_HOST", "127.0.0.1"),
    port=int(os.getenv("TIMESCALE_PORT", "5433")),
    user=os.getenv("TIMESCALE_USER", "robotrader"),
    password=os.getenv("TIMESCALE_PASSWORD", "1234"),
    database=os.getenv("TIMESCALE_DB", "robotrader"),
)


def _get_conn():
    return psycopg2.connect(**_DB_DEFAULTS)


# ─────────────────────────────────────────────────────────────────────────────
# 연도별 윈도우 생성
# ─────────────────────────────────────────────────────────────────────────────

def _yearly_windows(start: date, end: date) -> list[tuple[str, str]]:
    """start ~ end 기간을 연도별 (fromdate, todate) 윈도우로 분할."""
    windows = []
    cur_year = start.year
    while cur_year <= end.year:
        win_start = max(start, date(cur_year, 1, 1))
        win_end   = min(end,   date(cur_year, 12, 31))
        if win_start <= win_end:
            windows.append((win_start.strftime("%Y%m%d"), win_end.strftime("%Y%m%d")))
        cur_year += 1
    return windows


# ─────────────────────────────────────────────────────────────────────────────
# pykrx 데이터 수집
# ─────────────────────────────────────────────────────────────────────────────

def _fetch_vkospi_year(fromdate: str, todate: str) -> list[dict]:
    """pykrx로 VKOSPI 일봉 수집.

    Returns list of dicts: {trade_date, open, high, low, close, volume}
    """
    try:
        from pykrx import stock as pykrx_stock
    except ImportError:
        logger.error("[pykrx] pykrx 미설치 — pip install pykrx")
        return []

    # pykrx VKOSPI 조회: 여러 티커 후보를 순서대로 시도
    df = None
    fn = getattr(pykrx_stock, "get_index_ohlcv_by_date", None)
    if fn is None:
        fn = getattr(pykrx_stock, "get_index_ohlcv", None)

    if fn is None:
        logger.error("[pykrx] get_index_ohlcv_by_date 함수 없음")
        return []

    for ticker_candidate in _VKOSPI_TICKER_CANDIDATES:
        try:
            df = fn(fromdate, todate, ticker_candidate)
            if df is not None and not df.empty:
                logger.debug("[pykrx] VKOSPI 티커 '%s' 성공", ticker_candidate)
                break
            df = None
        except Exception as exc:
            logger.debug("[pykrx] 티커 '%s' 실패: %s", ticker_candidate, exc)
            df = None

    if df is None or df.empty:
        # 대안: get_market_ohlcv_by_date 계열도 시도
        logger.warning("[pykrx] VKOSPI %s~%s 조회 결과 없음", fromdate, todate)
        return []

    rows = []
    import pandas as pd

    # Index가 날짜, 컬럼: 시가, 고가, 저가, 종가, 거래량 (또는 영문)
    for idx, row in df.iterrows():
        # 날짜 파싱
        if hasattr(idx, 'date'):
            trade_date = idx.date()
        elif isinstance(idx, str):
            try:
                trade_date = datetime.strptime(idx, "%Y%m%d").date()
            except ValueError:
                try:
                    trade_date = datetime.strptime(idx[:10], "%Y-%m-%d").date()
                except ValueError:
                    continue
        else:
            continue

        def _safe(col_candidates, default=None):
            for c in col_candidates:
                if c in row.index and pd.notna(row[c]):
                    return float(row[c])
            return default

        open_  = _safe(["시가", "Open", "open"])
        high   = _safe(["고가", "High", "high"])
        low    = _safe(["저가", "Low", "low"])
        close  = _safe(["종가", "Close", "close"])
        volume = None
        for c in ["거래량", "Volume", "volume"]:
            if c in row.index and pd.notna(row[c]):
                volume = int(row[c])
                break

        if close is None:
            continue

        rows.append({
            "trade_date": trade_date,
            "open": open_,
            "high": high,
            "low": low,
            "close": close,
            "volume": volume,
        })

    return rows


# ─────────────────────────────────────────────────────────────────────────────
# DB 삽입
# ─────────────────────────────────────────────────────────────────────────────

def _insert_batch(rows: list[dict], dry_run: bool) -> int:
    """rows를 vkospi_daily에 INSERT ON CONFLICT DO NOTHING.

    Returns: 신규 삽입 건수 (dry-run 시 수집 건수 반환)
    """
    if not rows:
        return 0
    if dry_run:
        return len(rows)

    sql = """
        INSERT INTO vkospi_daily (trade_date, open, high, low, close, volume)
        VALUES %s
        ON CONFLICT (trade_date) DO NOTHING
    """
    values = [
        (r["trade_date"], r["open"], r["high"], r["low"], r["close"], r["volume"])
        for r in rows
    ]
    conn = _get_conn()
    try:
        with conn.cursor() as cur:
            psycopg2.extras.execute_values(cur, sql, values, page_size=500)
            inserted = cur.rowcount
        conn.commit()
    except Exception as exc:
        conn.rollback()
        logger.error("[DB] INSERT 실패: %s", exc)
        inserted = 0
    finally:
        conn.close()
    return inserted


# ─────────────────────────────────────────────────────────────────────────────
# 메인
# ─────────────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="VKOSPI 일봉 백필 스크립트 (Phase 5 S2-01)")
    parser.add_argument("--dry-run", action="store_true",
                        help="DB 저장 없이 예상 건수만 출력")
    parser.add_argument("--pilot", action="store_true",
                        help="파일럿: 2024-01 ~ 현재 (~1.4년)")
    parser.add_argument("--yes", action="store_true",
                        help="전체 5.4년 본 적재 확인 대화 건너뜀")
    args = parser.parse_args()

    # 기간 결정
    if args.pilot:
        start_date = PILOT_START
        mode = "파일럿 (2024-01 ~ 현재)"
    else:
        start_date = BACKFILL_START
        mode = "전체 5.4년 (2021-01 ~ 현재)"

    end_date = TODAY

    # 전체 본 적재 확인
    if not args.pilot and not args.dry_run and not args.yes:
        print("=" * 60)
        print("경고: 전체 5.4년 본 적재를 시도합니다.")
        print("사장님 결재 완료 후 진행하세요.")
        print("dry-run 먼저 실행하려면 --dry-run 옵션을 사용하세요.")
        print("=" * 60)
        confirm = input("계속하시겠습니까? (yes 입력): ").strip().lower()
        if confirm != "yes":
            print("취소됨.")
            return

    windows = _yearly_windows(start_date, end_date)

    logger.info("=" * 60)
    logger.info("VKOSPI 일봉 백필 시작")
    logger.info("모드: %s", mode)
    logger.info("기간: %s ~ %s (%d개 연도별 윈도우)", start_date, end_date, len(windows))
    logger.info("dry-run: %s", args.dry_run)
    logger.info("=" * 60)

    est_sec = len(windows) * PYKRX_SLEEP
    logger.info("예상 소요 시간: %.0f초 (빠름)", est_sec)

    total_fetched = 0
    total_inserted = 0
    missing_years: list[str] = []

    for win_from, win_to in windows:
        logger.info("[VKOSPI] %s ~ %s 수집 중...", win_from, win_to)
        rows = _fetch_vkospi_year(win_from, win_to)

        if not rows:
            missing_years.append(win_from[:4])
            logger.warning("[VKOSPI] %s 데이터 없음", win_from[:4])
            time.sleep(PYKRX_SLEEP)
            continue

        total_fetched += len(rows)
        inserted = _insert_batch(rows, dry_run=args.dry_run)
        total_inserted += inserted

        logger.info(
            "[VKOSPI] %s: %d건 수집, %d건 %s (close 범위: %.2f ~ %.2f)",
            win_from[:4], len(rows), inserted,
            "(dry-run)" if args.dry_run else "삽입",
            min(r["close"] for r in rows),
            max(r["close"] for r in rows),
        )
        time.sleep(PYKRX_SLEEP)

    # 최종 보고
    logger.info("")
    logger.info("=" * 60)
    logger.info("VKOSPI 일봉 백필 완료")
    logger.info("=" * 60)
    logger.info("  총 수집: %d건", total_fetched)
    logger.info("  총 삽입 (신규): %d건", total_inserted)
    logger.info("  데이터 없는 연도: %d개", len(missing_years))
    if missing_years:
        for y in missing_years:
            logger.warning("    - 누락: %s", y)

    # 영업일 기준 예상 행 수 안내
    years = (end_date - start_date).days / 365.25
    est_rows = int(years * 252)  # 연간 약 252 영업일
    logger.info("  예상 행 수 (참고): ~%d건 (연 252 영업일 기준)", est_rows)

    if not args.dry_run:
        try:
            conn = _get_conn()
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT COUNT(*), MIN(trade_date), MAX(trade_date), "
                    "MIN(close), MAX(close) FROM vkospi_daily"
                )
                row = cur.fetchone()
            conn.close()
            if row:
                logger.info("")
                logger.info("[DB] vkospi_daily 현황:")
                logger.info("  총 행 수: %d", row[0])
                logger.info("  날짜 범위: %s ~ %s", row[1], row[2])
                logger.info("  VKOSPI 범위: %.2f ~ %.2f", float(row[3]), float(row[4]))
        except Exception as exc:
            logger.warning("[DB] 현황 확인 실패: %s", exc)

    if args.dry_run:
        logger.info("")
        logger.info("[dry-run] 실제 DB 저장은 하지 않았습니다.")
        logger.info("[dry-run] 실제 백필하려면 --pilot 또는 --yes 옵션으로 재실행하세요.")


if __name__ == "__main__":
    main()
