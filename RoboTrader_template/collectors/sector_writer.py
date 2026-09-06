"""섹터 명부·성적표 → kis_template. **DB 쓰기는 이 파일 한 곳뿐.**

🔑 SCD2 의 핵심은 «값 없음은 변경이 아니다» 이다. 소스가 하루 비어도 이력이 갈라지면
   안 된다 — 갈라진 이력은 fn_sector_map_as_of 에서 종목당 2행이 되고, 그건 성적표
   n_members 의 «이중 계산»이 된다(§8-8 이 FAIL 로 잡는 사고).
🔴 fn_sector_map_as_of 는 반환 타입이 바뀌면 CREATE OR REPLACE 가 거부한다 —
   DROP 을 «먼저» 해야 DDL 이 멱등이다.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from utils.logger import setup_logger  # noqa: E402

logger = setup_logger(__name__)

DDL_MAP = """
CREATE TABLE IF NOT EXISTS stock_sector_map (
    stock_code    varchar(20) NOT NULL,
    valid_from    date        NOT NULL,
    valid_to      date,
    ksic_code     varchar(10),
    ksic_source   text,
    ksic3_name    text,
    corp_code     varchar(8),
    market        text,
    kosdaq_dept   text,
    products      text,
    listing_date  date,
    settle_month  text,
    source        text        NOT NULL,
    source_asof   date,
    ksic_checked_at timestamp,
    collected_at  timestamp   NOT NULL DEFAULT now(),
    last_seen_at  timestamp   NOT NULL DEFAULT now(),
    PRIMARY KEY (stock_code, valid_from),
    CHECK (valid_to IS NULL OR valid_to >= valid_from)
)
"""

DDL_MAP_IDX = [
    "CREATE INDEX IF NOT EXISTS idx_ssm_open ON stock_sector_map (stock_code) WHERE valid_to IS NULL",
    "CREATE INDEX IF NOT EXISTS idx_ssm_asof ON stock_sector_map (stock_code, valid_from, valid_to)",
]

DDL_STATS = """
CREATE TABLE IF NOT EXISTS sector_daily_stats (
    date         date        NOT NULL,
    taxonomy     text        NOT NULL CHECK (taxonomy IN ('ksic2','ksic3','ksic5')),
    sector_key   text        NOT NULL,
    CHECK ((taxonomy='ksic2' AND sector_key ~ '^[0-9]{2}$')
        OR (taxonomy='ksic3' AND sector_key ~ '^[0-9]{3}$')
        OR (taxonomy='ksic5' AND sector_key ~ '^[0-9]{5}$')),
    n_members    int         NOT NULL,
    g_sectors    int         NOT NULL,
    ret_median   double precision,
    ret_mean     double precision,
    up_count     int,
    pos_ratio    double precision,
    rank_median  int,
    pct_median   double precision,
    rank_up      int,
    pct_up       double precision,
    rank_pos     int,
    pct_pos      double precision,
    computed_at  timestamp   NOT NULL DEFAULT now(),
    PRIMARY KEY (date, taxonomy, sector_key)
)
"""

DDL_STATS_IDX = [
    "CREATE INDEX IF NOT EXISTS idx_sds_tax_date ON sector_daily_stats (taxonomy, date)",
]

DDL_NODATA = """
CREATE TABLE IF NOT EXISTS sector_ksic_nodata (
    stock_code  varchar(20) PRIMARY KEY,
    checked_at  timestamp   NOT NULL DEFAULT now()
)
"""

DDL_NAMES = """
CREATE TABLE IF NOT EXISTS ksic_code_name (
    level       int         NOT NULL CHECK (level = 3),
    code        varchar(5)  NOT NULL CHECK (code ~ '^[0-9]{3}$'),
    name        text        NOT NULL,
    n_stocks    int         NOT NULL,
    share       double precision NOT NULL,
    built_at    timestamp   NOT NULL DEFAULT now(),
    PRIMARY KEY (level, code)
)
"""

DDL_FN_DROP = "DROP FUNCTION IF EXISTS fn_sector_map_as_of(date)"

DDL_FN_AS_OF = """
CREATE OR REPLACE FUNCTION fn_sector_map_as_of(p_as_of date)
RETURNS TABLE (stock_code varchar(20), ksic_code varchar(10), ksic_source text,
               ksic3_name text, valid_from date, source text)
LANGUAGE sql STABLE AS $$
    SELECT stock_code, ksic_code, ksic_source, ksic3_name, valid_from, source
    FROM stock_sector_map
    WHERE valid_from <= p_as_of AND (valid_to IS NULL OR p_as_of <= valid_to)
$$
"""


def ensure_tables(conn) -> None:
    """신규 4표 + 인덱스 + 함수. 멱등 — EOD 가 매일 부른다."""
    try:
        with conn.cursor() as cur:
            cur.execute(DDL_MAP)
            for sql in DDL_MAP_IDX:
                cur.execute(sql)
            cur.execute(DDL_STATS)
            for sql in DDL_STATS_IDX:
                cur.execute(sql)
            cur.execute(DDL_NODATA)
            cur.execute(DDL_NAMES)
            cur.execute(DDL_FN_DROP)
            cur.execute(DDL_FN_AS_OF)
        conn.commit()
    except Exception:
        conn.rollback()
        raise


def map_as_of(conn, as_of) -> list:
    """그 날짜의 명부 — (stock_code, ksic_code, ksic_source, ksic3_name, valid_from, source)."""
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT stock_code, ksic_code, ksic_source, ksic3_name, valid_from, source "
                        "FROM fn_sector_map_as_of(%s)", (as_of,))
            return cur.fetchall()
    except Exception:
        conn.rollback()
        raise
