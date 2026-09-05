"""DART/KIS 재무 → kis_template UPSERT. **DB 쓰기는 이 파일 한 곳뿐.**

🔑 기존 dart_financials_asfiled 가 죽은 이유는 컬럼 부족이 아니라 «키가 기간»이었기 때문이다.
   여기 키는 «접수건»(rcept_no, fs_div)이라 정정공시가 원본을 덮어쓰는 일이
   정책이 아니라 «구조적으로» 불가능하다.
"""
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from utils.logger import setup_logger  # noqa: E402

logger = setup_logger(__name__)

DDL_FILINGS = """
CREATE TABLE IF NOT EXISTS dart_financial_filings (
    rcept_no     varchar(14) NOT NULL,
    fs_div       varchar(3)  NOT NULL,
    corp_code    varchar(8)  NOT NULL,
    stock_code   varchar(20) NOT NULL,
    bsns_year    varchar(4)  NOT NULL,
    reprt_code   varchar(5)  NOT NULL,
    rcept_dt     date,
    is_amendment boolean     NOT NULL DEFAULT false,
    raw_path     text,
    collected_at timestamp   NOT NULL DEFAULT now(),
    PRIMARY KEY (rcept_no, fs_div)
)
"""

DDL_FILINGS_IDX = [
    "CREATE INDEX IF NOT EXISTS idx_dff_key ON dart_financial_filings "
    "(stock_code, bsns_year, reprt_code, rcept_dt)",
    "CREATE INDEX IF NOT EXISTS idx_dff_rcept ON dart_financial_filings (rcept_dt)",
]

DDL_ACCOUNTS = """
CREATE TABLE IF NOT EXISTS dart_financial_accounts (
    rcept_no          varchar(14) NOT NULL,
    fs_div            varchar(3)  NOT NULL,
    sj_div            varchar(8)  NOT NULL,
    account_id        text        NOT NULL,
    ord               int         NOT NULL,
    account_nm        text,
    thstrm_amount     bigint,
    thstrm_add_amount bigint,
    frmtrm_amount     bigint,
    bfefrmtrm_amount  bigint,
    currency          text,
    PRIMARY KEY (rcept_no, fs_div, sj_div, account_id, ord)
)
"""

DDL_KIS_RATIO = """
CREATE TABLE IF NOT EXISTS kis_financial_ratio (
    stock_code  varchar(20) NOT NULL,
    stac_yymm   varchar(6)  NOT NULL,
    div_cls     varchar(1)  NOT NULL,
    roe_value               numeric,
    per                     numeric,
    eps                     numeric,
    sps                     numeric,
    bps                     numeric,
    reserve_ratio           numeric,
    liability_ratio         numeric,
    sales_growth            numeric,
    operating_income_growth numeric,
    net_income_growth       numeric,
    raw_json    jsonb,
    PRIMARY KEY (stock_code, stac_yymm, div_cls)
)
"""
# 🔴 kis_financial_ratio 에 날짜형 컬럼이 없는 것은 «의도»다.
#    KIS 응답엔 접수일이 없어 PIT 앵커를 만들 수 없다.
#    PIT 앵커가 없는 데이터에 날짜 컬럼을 붙이면 누군가 그걸 PIT 으로 쓴다.

DDL_NODATA = """
CREATE TABLE IF NOT EXISTS dart_financial_nodata (
    stock_code varchar(20) NOT NULL,
    bsns_year  varchar(4)  NOT NULL,
    reprt_code varchar(5)  NOT NULL,
    checked_at timestamp   NOT NULL DEFAULT now(),
    PRIMARY KEY (stock_code, bsns_year, reprt_code)
)
"""

_NUM_RE = re.compile(r"^-?[\d,]+$")


def parse_amount(v):
    """'1,234' → 1234. 실패는 None — 🔴 절대 0 이 아니다."""
    if v is None:
        return None
    s = str(v).strip()
    if not s or s == "-":
        return None
    if not _NUM_RE.match(s):
        return None
    try:
        return int(s.replace(",", ""))
    except ValueError:
        return None


def rows_from_dart_response(payload: dict, stock_code: str, fs_div: str):
    """fnlttSinglAcntAll 응답 → (filing_row, account_rows). 빈 list 면 (None, [])."""
    items = payload.get("list") or []
    if not items:
        return None, []
    head = items[0]
    filing = {
        "rcept_no": str(head.get("rcept_no", "")).strip(),
        "fs_div": fs_div,
        "corp_code": str(head.get("corp_code", "")).strip(),
        "stock_code": stock_code,
        "bsns_year": str(head.get("bsns_year", "")).strip(),
        "reprt_code": str(head.get("reprt_code", "")).strip(),
        "rcept_dt": None,          # list.json 또는 별도 조회로 채운다(Task 6)
        "is_amendment": False,     # 적재 후 SQL 로 재계산(Task 4 Step 7)
        "raw_path": None,          # collector 가 채운다
    }
    accounts = []
    for it in items:
        # ord 는 PK 의 일부 — malformed ord 는 다른 행과 충돌해 ON CONFLICT 로 침묵 덮어쓴다.
        # 스킵 + 경고(조용한 드롭 금지).
        raw_ord = str(it.get("ord", "")).strip()
        # 빈값도 유효하지 않음 — ord=0 폴백 금지
        if not raw_ord:
            rcept_no = filing["rcept_no"]
            account_id = str(it.get("account_id", "")).strip()
            logger.warning(
                "[financial_writer] ord 무효 계정 스킵: rcept_no=%s account_id=%s ord=%r",
                rcept_no, account_id, raw_ord,
            )
            continue
        try:
            ordv = int(raw_ord)
        except ValueError:
            rcept_no = filing["rcept_no"]
            account_id = str(it.get("account_id", "")).strip()
            logger.warning(
                "[financial_writer] ord 무효 계정 스킵: rcept_no=%s account_id=%s ord=%r",
                rcept_no, account_id, raw_ord,
            )
            continue
        accounts.append({
            "rcept_no": filing["rcept_no"],
            "fs_div": fs_div,
            "sj_div": str(it.get("sj_div", "")).strip(),
            "account_id": str(it.get("account_id", "")).strip(),
            "ord": ordv,
            "account_nm": it.get("account_nm"),
            "thstrm_amount": parse_amount(it.get("thstrm_amount")),
            "thstrm_add_amount": parse_amount(it.get("thstrm_add_amount")),
            "frmtrm_amount": parse_amount(it.get("frmtrm_amount")),
            "bfefrmtrm_amount": parse_amount(it.get("bfefrmtrm_amount")),
            "currency": it.get("currency"),
        })
    return filing, accounts


_UPSERT_FILING = """
INSERT INTO dart_financial_filings
  (rcept_no, fs_div, corp_code, stock_code, bsns_year, reprt_code,
   rcept_dt, is_amendment, raw_path)
VALUES (%(rcept_no)s, %(fs_div)s, %(corp_code)s, %(stock_code)s, %(bsns_year)s,
        %(reprt_code)s, %(rcept_dt)s, %(is_amendment)s, %(raw_path)s)
ON CONFLICT (rcept_no, fs_div) DO UPDATE SET
    rcept_dt=COALESCE(EXCLUDED.rcept_dt, dart_financial_filings.rcept_dt),
    raw_path=COALESCE(EXCLUDED.raw_path, dart_financial_filings.raw_path)
"""

_UPSERT_ACCOUNT = """
INSERT INTO dart_financial_accounts
  (rcept_no, fs_div, sj_div, account_id, ord, account_nm,
   thstrm_amount, thstrm_add_amount, frmtrm_amount, bfefrmtrm_amount, currency)
VALUES (%(rcept_no)s, %(fs_div)s, %(sj_div)s, %(account_id)s, %(ord)s, %(account_nm)s,
        %(thstrm_amount)s, %(thstrm_add_amount)s, %(frmtrm_amount)s,
        %(bfefrmtrm_amount)s, %(currency)s)
ON CONFLICT (rcept_no, fs_div, sj_div, account_id, ord) DO UPDATE SET
    account_nm=EXCLUDED.account_nm,
    thstrm_amount=EXCLUDED.thstrm_amount,
    thstrm_add_amount=EXCLUDED.thstrm_add_amount,
    frmtrm_amount=EXCLUDED.frmtrm_amount,
    bfefrmtrm_amount=EXCLUDED.bfefrmtrm_amount,
    currency=EXCLUDED.currency
"""

_UPSERT_KIS = """
INSERT INTO kis_financial_ratio
  (stock_code, stac_yymm, div_cls, roe_value, per, eps, sps, bps,
   reserve_ratio, liability_ratio, sales_growth, operating_income_growth,
   net_income_growth, raw_json)
VALUES (%(stock_code)s, %(stac_yymm)s, %(div_cls)s, %(roe_value)s, %(per)s, %(eps)s,
        %(sps)s, %(bps)s, %(reserve_ratio)s, %(liability_ratio)s, %(sales_growth)s,
        %(operating_income_growth)s, %(net_income_growth)s, %(raw_json)s::jsonb)
ON CONFLICT (stock_code, stac_yymm, div_cls) DO UPDATE SET
    roe_value=EXCLUDED.roe_value, per=EXCLUDED.per, eps=EXCLUDED.eps,
    sps=EXCLUDED.sps, bps=EXCLUDED.bps, reserve_ratio=EXCLUDED.reserve_ratio,
    liability_ratio=EXCLUDED.liability_ratio, sales_growth=EXCLUDED.sales_growth,
    operating_income_growth=EXCLUDED.operating_income_growth,
    net_income_growth=EXCLUDED.net_income_growth, raw_json=EXCLUDED.raw_json
"""


def ensure_tables(conn) -> None:
    try:
        with conn.cursor() as cur:
            cur.execute(DDL_FILINGS)
            for sql in DDL_FILINGS_IDX:
                cur.execute(sql)
            cur.execute(DDL_ACCOUNTS)
            cur.execute(DDL_KIS_RATIO)
            cur.execute(DDL_NODATA)
        conn.commit()
    except Exception:
        conn.rollback()
        raise


def upsert_filing(conn, filing: dict) -> None:
    try:
        with conn.cursor() as cur:
            cur.execute(_UPSERT_FILING, filing)
        conn.commit()
    except Exception:
        conn.rollback()
        raise


def upsert_accounts(conn, rows: list) -> int:
    if not rows:
        return 0
    try:
        with conn.cursor() as cur:
            for r in rows:
                cur.execute(_UPSERT_ACCOUNT, r)
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    return len(rows)


def upsert_kis_ratio(conn, rows: list) -> int:
    if not rows:
        return 0
    try:
        with conn.cursor() as cur:
            for r in rows:
                cur.execute(_UPSERT_KIS, r)
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    return len(rows)


def upsert_nodata(conn, stock_code: str, bsns_year: str, reprt_code: str) -> None:
    """CFS·OFS 둘 다 013(무자료) 확정분 기록 — 내일 다시 안 두드리게 한다."""
    try:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO dart_financial_nodata (stock_code, bsns_year, reprt_code, checked_at) "
                "VALUES (%s,%s,%s, now()) ON CONFLICT DO NOTHING",
                (stock_code, bsns_year, reprt_code))
        conn.commit()
    except Exception:
        conn.rollback()
        raise


def recompute_amendment_flags(conn) -> None:
    """is_amendment 를 rcept_dt 순서로 재계산.

    ⚠️ 파생값이다. 옛 접수건을 뒤늦게 받으면 뒤집히므로 «매번 다시» 계산한다.
    """
    try:
        with conn.cursor() as cur:
            cur.execute("""
                UPDATE dart_financial_filings f SET is_amendment = sub.amend
                FROM (
                    SELECT rcept_no, fs_div,
                           (row_number() OVER (PARTITION BY stock_code, bsns_year, reprt_code
                                               ORDER BY rcept_dt, rcept_no) > 1) AS amend
                    FROM dart_financial_filings WHERE rcept_dt IS NOT NULL
                ) sub
                WHERE f.rcept_no = sub.rcept_no AND f.fs_div = sub.fs_div
                  AND f.is_amendment IS DISTINCT FROM sub.amend
            """)
        conn.commit()
    except Exception:
        conn.rollback()
        raise


_UPSERT_RECON = """
INSERT INTO collection_reconciliation
  (trade_date, dataset, real_rows, new_rows, overlap, value_match_rate, coverage, verdict)
VALUES (%s, %s, 0, %s, 0, %s, %s, %s)
ON CONFLICT (trade_date, dataset) DO UPDATE SET
    new_rows=EXCLUDED.new_rows, value_match_rate=EXCLUDED.value_match_rate,
    coverage=EXCLUDED.coverage, verdict=EXCLUDED.verdict
"""


def upsert_reconciliation(conn, trade_date: str, dataset: str, new_rows: int,
                           value_match_rate, coverage, verdict: str) -> None:
    """collection_reconciliation UPSERT (financial_collector._write_recon 전용)."""
    try:
        with conn.cursor() as cur:
            cur.execute(_UPSERT_RECON,
                        (trade_date, dataset, new_rows, value_match_rate, coverage, verdict))
        conn.commit()
    except Exception:
        conn.rollback()
        raise
