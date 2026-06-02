# -*- coding: utf-8 -*-
"""
외국인 순매수 백필 스크립트 (Phase 5 — F-06)
============================================
소스: 네이버 금융 frgn.naver (종목별 일별 외국인 순매매량)
대상: robotrader DB daily_prices 305종목
기간: 가능한 전체 (네이버 최대 약 40페이지 × 20일 = ~800일)
DB:   robotrader_quant.foreign_flow 신규 테이블

PIT 보장:
- 외국인 순매수는 T일 마감 후 발표 → T일 데이터를 T일로 저장
- 시그널 생성 시 shift(1)로 T-1 참조 (forward-leak 없음)

실행:
    python scripts/backfill_foreign_flow.py [--pilot] [--workers N] [--max-pages N]
"""
from __future__ import annotations

import argparse
import logging
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from io import StringIO

import psycopg2
import psycopg2.extras
import pandas as pd
import requests

# ─────────────────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)

PILOT_CODES = ["005930", "000660", "005380", "035420", "051910"]

DB_QUANT = dict(
    host="127.0.0.1", port=5433, dbname="robotrader_quant",
    user="robotrader", password="1234"
)
DB_RT = dict(
    host="127.0.0.1", port=5433, dbname="robotrader",
    user="robotrader", password="1234"
)

DDL = """
CREATE TABLE IF NOT EXISTS foreign_flow (
    stock_code      VARCHAR(10) NOT NULL,
    date            DATE        NOT NULL,
    foreign_net_vol BIGINT,
    source          VARCHAR(20) DEFAULT 'naver',
    created_at      TIMESTAMP   DEFAULT NOW(),
    PRIMARY KEY (stock_code, date)
);
CREATE INDEX IF NOT EXISTS ix_foreign_flow_date ON foreign_flow (date);
"""


# ─────────────────────────────────────────────────────────────────────────────
# 네이버 금융 수집
# ─────────────────────────────────────────────────────────────────────────────

def _make_session() -> requests.Session:
    s = requests.Session()
    s.headers.update({
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Referer": "https://finance.naver.com/",
        "Accept-Language": "ko-KR,ko;q=0.9",
    })
    return s


def fetch_foreign_naver(
    code: str,
    max_pages: int = 40,
    session: requests.Session | None = None,
) -> pd.DataFrame:
    """네이버 금융에서 종목별 일별 외국인 순매매량 수집.

    PIT 강제:
        - 네이버 frgn.naver는 T일 장 마감 후 발표된 T일 실적값 제공
        - T일 데이터를 T일로 저장, 시그널 생성 시 shift(1) 사용
        - shift(-N) 절대 금지
    """
    if session is None:
        session = _make_session()

    all_rows: list[pd.DataFrame] = []
    for page in range(1, max_pages + 1):
        try:
            r = session.get(
                "https://finance.naver.com/item/frgn.naver",
                params={"code": code, "page": page},
                timeout=15,
            )
            if r.status_code != 200:
                logger.warning("[%s] HTTP %d (page=%d)", code, r.status_code, page)
                break

            tables = pd.read_html(StringIO(r.text), encoding="utf-8")
            if len(tables) <= 3:
                break

            t = tables[3]
            if isinstance(t.columns, pd.MultiIndex):
                t.columns = ["_".join(str(c) for c in col).strip("_") for col in t.columns]
            t = t.dropna(how="all")

            date_col = next((c for c in t.columns if "날짜" in str(c)), None)
            foreign_col = next(
                (c for c in t.columns if "외국인" in str(c) and "순매매" in str(c)), None
            )
            if not date_col or not foreign_col:
                if t.shape[1] >= 7:
                    cols = (
                        ["날짜", "종가", "전일비", "등락률", "거래량", "기관_순매매량", "외국인_순매매량"]
                        + [f"col{i}" for i in range(t.shape[1] - 7)]
                    )
                    t.columns = cols[:t.shape[1]]
                    date_col, foreign_col = "날짜", "외국인_순매매량"
                else:
                    logger.debug("[%s] p%d: 컬럼 파싱 실패 %s", code, page, list(t.columns))
                    break

            sub = t[[date_col, foreign_col]].copy()
            sub.columns = ["date", "foreign_net_vol"]
            sub = sub.dropna(subset=["date"])
            sub = sub[sub["date"].astype(str).str.match(r"^\d{4}\.\d{2}\.\d{2}$")]
            if sub.empty:
                break

            sub["date"] = pd.to_datetime(sub["date"], format="%Y.%m.%d").dt.date
            sub["foreign_net_vol"] = (
                sub["foreign_net_vol"]
                .astype(str)
                .str.replace(",", "", regex=False)
                .str.replace("+", "", regex=False)
                .pipe(pd.to_numeric, errors="coerce")
            )

            all_rows.append(sub)
            if len(sub) < 10:
                break
            time.sleep(0.2)

        except Exception as e:
            logger.warning("[%s] p%d: %s", code, page, e)
            break

    if not all_rows:
        return pd.DataFrame(columns=["date", "foreign_net_vol"])

    result = pd.concat(all_rows, ignore_index=True)
    result = result.drop_duplicates(subset=["date"]).sort_values("date")
    return result


# ─────────────────────────────────────────────────────────────────────────────
# DB 헬퍼
# ─────────────────────────────────────────────────────────────────────────────

def ensure_table() -> None:
    conn = psycopg2.connect(**DB_QUANT)
    try:
        with conn.cursor() as cur:
            cur.execute(DDL)
        conn.commit()
        logger.info("[DB] foreign_flow 테이블 준비 완료")
    finally:
        conn.close()


def get_stock_codes(pilot: bool = False) -> list[str]:
    if pilot:
        return PILOT_CODES
    conn = psycopg2.connect(**DB_RT)
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT DISTINCT stock_code FROM daily_prices "
                "WHERE stock_code ~ %s ORDER BY stock_code",
                ("^[0-9]{6}$",),
            )
            return [r[0] for r in cur.fetchall()]
    finally:
        conn.close()


def get_existing_dates(code: str) -> set:
    conn = psycopg2.connect(**DB_QUANT)
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT date FROM foreign_flow WHERE stock_code = %s", (code,))
            return {r[0] for r in cur.fetchall()}
    finally:
        conn.close()


def upsert_rows(rows: list[tuple]) -> int:
    if not rows:
        return 0
    conn = psycopg2.connect(**DB_QUANT)
    try:
        with conn.cursor() as cur:
            psycopg2.extras.execute_values(
                cur,
                """
                INSERT INTO foreign_flow (stock_code, date, foreign_net_vol, source)
                VALUES %s
                ON CONFLICT (stock_code, date) DO NOTHING
                """,
                rows,
            )
        conn.commit()
        return len(rows)
    finally:
        conn.close()


# ─────────────────────────────────────────────────────────────────────────────
# 종목별 수집 + 적재 (스레드 단위)
# ─────────────────────────────────────────────────────────────────────────────

def collect_and_insert(code: str, max_pages: int) -> tuple[str, int, str]:
    """단일 종목 수집 + 적재. (code, inserted, status) 반환."""
    session = _make_session()
    try:
        df = fetch_foreign_naver(code, max_pages=max_pages, session=session)
        if df.empty:
            return code, 0, "empty"

        existing = get_existing_dates(code)
        rows = []
        for _, row in df.iterrows():
            if row["date"] not in existing:
                vol = int(row["foreign_net_vol"]) if pd.notna(row["foreign_net_vol"]) else None
                rows.append((code, row["date"], vol, "naver"))

        inserted = upsert_rows(rows)
        return code, inserted, "ok"
    except Exception as e:
        return code, 0, f"error: {e}"


# ─────────────────────────────────────────────────────────────────────────────
# 메인
# ─────────────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(description="외국인 순매수 백필 (네이버 금융)")
    parser.add_argument("--pilot", action="store_true", help="파일럿 5종목만")
    parser.add_argument("--workers", type=int, default=5, help="병렬 스레드 수 (기본 5)")
    parser.add_argument("--max-pages", type=int, default=40, help="종목당 최대 페이지 (기본 40 ≈ 800일)")
    args = parser.parse_args()

    logger.info("=" * 60)
    logger.info("외국인 순매수 백필 시작")
    logger.info("모드: %s | workers=%d | max_pages=%d",
                "파일럿" if args.pilot else "전체", args.workers, args.max_pages)
    logger.info("=" * 60)

    ensure_table()

    codes = get_stock_codes(pilot=args.pilot)
    logger.info("[대상] %d종목", len(codes))

    total_inserted = 0
    errors: list[tuple[str, str]] = []
    t_start = time.time()

    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        futures = {pool.submit(collect_and_insert, code, args.max_pages): code for code in codes}
        done = 0
        for future in as_completed(futures):
            code, inserted, status = future.result()
            done += 1
            total_inserted += inserted
            elapsed = time.time() - t_start
            eta = elapsed / done * (len(codes) - done) if done > 0 else 0
            if "error" in status:
                errors.append((code, status))
                logger.warning("[%d/%d] %s: %s", done, len(codes), code, status)
            else:
                logger.info("[%d/%d] %s: +%d행 (%s) ETA=%.0fs",
                            done, len(codes), code, inserted, status, eta)

    elapsed_total = time.time() - t_start
    logger.info("=" * 60)
    logger.info("백필 완료: 총 %d행 삽입 / %d종목 / %.1f초", total_inserted, len(codes), elapsed_total)
    if errors:
        logger.warning("오류 %d종목: %s", len(errors), errors[:10])

    conn = psycopg2.connect(**DB_QUANT)
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT COUNT(*), COUNT(DISTINCT stock_code), MIN(date), MAX(date) FROM foreign_flow"
            )
            row = cur.fetchone()
        logger.info("[DB] foreign_flow: 총 %s행 / %s종목 / %s ~ %s", *row)
    finally:
        conn.close()


if __name__ == "__main__":
    main()
