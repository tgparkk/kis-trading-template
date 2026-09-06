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


CHANGE_FIELDS = ("ksic_code", "ksic3_name")
# ⚠️ 부수 열은 «항상 제자리 갱신»이다(§3.1) — 그래서 캐시 CSV 의 빈 셀(_s() → None)이
#    저장된 값을 NULL 로 덮는다. 스펙 문자 그대로이며 의도된 동작이다:
#    「값 없음은 변경 아님」 규칙은 «변경 감지 필드»(CHANGE_FIELDS) 에만 적용된다.
#    캐시에 «행 자체가 없는» 종목은 키를 아예 안 넣어 보존한다(update_map 참조).
SIDE_FIELDS = ("corp_code", "market", "kosdaq_dept", "products",
               "listing_date", "settle_month", "source_asof")
MAX_CHANGE_RATIO = 0.05


def is_blank(v) -> bool:
    """None·공백 문자열 = «값 없음». 🔴 값 없음은 «변경»이 아니다 — 유지한다."""
    return v is None or (isinstance(v, str) and v.strip() == "")


def parent_code(stock_code):
    """우선주(끝자리 ≠ '0')의 부모 = 앞 5자리 + '0'. 보통주면 None."""
    s = (stock_code or "").strip()
    if len(s) != 6 or s[5] == "0":
        return None
    return s[:5] + "0"


def apply_parent_rule(candidates: dict, universe) -> dict:
    """우선주 후보에 부모 값을 «필드별로» 채운다.

    🔴 부모 규칙이 «열린 줄 값보다» 우선이다 — 부모 업종이 바뀌면 자식도 그날 바뀐다.
       그래서 호출측(collector)은 우선주 후보에 열린 줄 값을 «승계하지 않는다».
    - ksic_code·corp_code 는 부모가 ksic_code 를 가질 때만 함께 온다(한 몸).
      출처는 'parent:<부모코드>' 로 못박아 ② KSIC 채우기 대상에서 빠지게 한다.
    - ksic3_name 은 부모가 이름을 가지면 KSIC 와 «독립»으로 복사한다.
    - 자기 캐시 값이 있으면 그것이 우선한다(우선주 Industry 는 실측 전부 NULL).
    """
    universe = set(universe or ())
    out = {}
    for code, cand in candidates.items():
        p = parent_code(code)
        new = dict(cand)
        if p is not None and p in universe:
            prow = candidates.get(p) or {}
            if is_blank(new.get("ksic_code")) and not is_blank(prow.get("ksic_code")):
                new["ksic_code"] = prow.get("ksic_code")
                new["ksic_source"] = "parent:%s" % p
                new["corp_code"] = prow.get("corp_code")
            if is_blank(new.get("ksic3_name")) and not is_blank(prow.get("ksic3_name")):
                new["ksic3_name"] = prow.get("ksic3_name")
        out[code] = new
    return out


def plan_map_changes(open_rows: dict, candidates: dict, trade_date,
                     guard: bool = True, create_missing: bool = True) -> dict:
    """§3.1 규칙을 «쓰기 계획»으로 만든다. DB 를 만지지 않는 순수 함수다.

    open_rows  : {stock_code: {"valid_from": date, "ksic_code", "ksic3_name",
                               "ksic_source", "ksic_checked_at", ...}}
    candidates : {stock_code: {후보 값}} — 없는 키는 «새 값 없음»으로 본다.
    guard      : False 면 5% 급변 가드를 «판정만 하고 던지지 않는다».
                 🔴 운영 경로는 «항상» 기본값 True 다. False 는 분모가 1~2 인 단위
                 테스트 전용이다(표본 1종목이면 값→값 1건이 곧 100% 라 무조건 걸린다).
    create_missing : False 면 열린 줄이 없는 종목을 «새로 만들지 않고 건너뛴다».
                 🔴 KSIC 응답 재생(--regen-map)처럼 «기존 행만» 고쳐야 하는 경로용 —
                 이 플래그가 없으면 부수 열이 전부 NULL 인 유령 행이 INSERT 된다.
    반환       : {"inplace", "close", "open_new", "changed_codes", "skipped_past",
                  "skipped_missing", "counts", "guard"}
                 (`counts` 안에도 `skipped_missing` 이 있다 — 무징후 절단 금지)
    """
    from datetime import timedelta
    inplace, close, open_new, skipped, changed_codes = [], [], [], [], []
    skipped_missing = []
    changed = filled = new = unchanged = 0
    num = dict((f, 0) for f in CHANGE_FIELDS)
    den = dict((f, sum(1 for r in open_rows.values() if not is_blank(r.get(f))))
               for f in CHANGE_FIELDS)

    for code in sorted(candidates):
        cand = candidates[code]
        cur = open_rows.get(code)
        if cur is None and not create_missing:
            skipped_missing.append(code)     # 무징후 절단 금지 — 건수로 남긴다
            continue
        if cur is None:
            row = dict((f, cand.get(f)) for f in CHANGE_FIELDS + SIDE_FIELDS)
            row["stock_code"] = code
            row["ksic_source"] = cand.get("ksic_source")
            row["ksic_checked_at"] = cand.get("ksic_checked_at")
            row["valid_from"] = cand.get("valid_from") or trade_date
            open_new.append(row)
            new += 1
            continue
        vf = cur.get("valid_from")
        if vf is not None and vf > trade_date:
            skipped.append(code)
            continue
        hard = [f for f in CHANGE_FIELDS
                if not is_blank(cand.get(f)) and not is_blank(cur.get(f))
                and cand.get(f) != cur.get(f)]
        fills = [f for f in CHANGE_FIELDS
                 if not is_blank(cand.get(f)) and is_blank(cur.get(f))]
        sets = dict((f, cand.get(f)) for f in SIDE_FIELDS if f in cand)
        if hard:
            for f in hard:
                num[f] += 1
            changed += 1
            changed_codes.append(code)
        if hard and vf != trade_date:
            close.append({"stock_code": code, "valid_from": vf,
                          "valid_to": trade_date - timedelta(days=1)})
            row = {}
            for f in CHANGE_FIELDS:
                row[f] = cand.get(f) if not is_blank(cand.get(f)) else cur.get(f)
            row.update(sets)
            row["stock_code"] = code
            row["valid_from"] = trade_date
            row["ksic_source"] = (cand.get("ksic_source")
                                  if not is_blank(cand.get("ksic_code"))
                                  else cur.get("ksic_source"))
            # 🔴 승계 — NULL 로 떨어지면 재확인 큐(ASC NULLS FIRST) 맨 앞으로 튄다.
            row["ksic_checked_at"] = (cand.get("ksic_checked_at")
                                      or cur.get("ksic_checked_at"))
            open_new.append(row)
            continue
        if fills:
            filled += 1
        for f in hard + fills:
            sets[f] = cand.get(f)
        if "ksic_code" in sets:
            sets["ksic_source"] = cand.get("ksic_source")
        if cand.get("ksic_checked_at") is not None:
            sets["ksic_checked_at"] = cand.get("ksic_checked_at")
        if not hard and not fills:
            unchanged += 1
        inplace.append({"stock_code": code, "valid_from": vf, "set": sets})

    guard_stats = {}
    for f in CHANGE_FIELDS:
        if den[f] == 0:          # 분모 0 이면 생략(최초 수집)
            continue
        guard_stats[f] = {"num": num[f], "den": den[f], "ratio": float(num[f]) / den[f]}

    over = [f for f in sorted(guard_stats)
            if guard_stats[f]["ratio"] > MAX_CHANGE_RATIO]
    if guard and over:
        raise RuntimeError(
            "섹터 명부 소스 급변 — 한 행도 쓰지 않음(어제 명부 보존): "
            + " · ".join("%s %d/%d(%.1f%%) > %.0f%%"
                         % (f, guard_stats[f]["num"], guard_stats[f]["den"],
                            100.0 * guard_stats[f]["ratio"], 100.0 * MAX_CHANGE_RATIO)
                         for f in over))
    if over and not guard:
        logger.warning("[sector] 급변 가드 대상이지만 guard=False 로 통과: %s",
                       [(f, guard_stats[f]) for f in over])

    return {"inplace": inplace, "close": close, "open_new": open_new,
            "changed_codes": changed_codes, "skipped_past": skipped,
            "skipped_missing": skipped_missing,
            "counts": {"changed": changed, "filled": filled, "new": new,
                       "unchanged": unchanged, "skipped_past": len(skipped),
                       "skipped_missing": len(skipped_missing)},
            "guard": guard_stats}


_UPDATABLE = frozenset(CHANGE_FIELDS + SIDE_FIELDS + ("ksic_source", "ksic_checked_at"))

_INSERT_ROW = """
INSERT INTO stock_sector_map
  (stock_code, valid_from, valid_to, ksic_code, ksic_source, ksic3_name, corp_code,
   market, kosdaq_dept, products, listing_date, settle_month, source, source_asof,
   ksic_checked_at)
VALUES (%(stock_code)s, %(valid_from)s, NULL, %(ksic_code)s, %(ksic_source)s,
        %(ksic3_name)s, %(corp_code)s, %(market)s, %(kosdaq_dept)s, %(products)s,
        %(listing_date)s, %(settle_month)s, %(source)s, %(source_asof)s,
        %(ksic_checked_at)s)
"""

_CLOSE_ROW = ("UPDATE stock_sector_map SET valid_to=%(valid_to)s "
              "WHERE stock_code=%(stock_code)s AND valid_from=%(valid_from)s")

_OPEN_ROWS_SQL = (
    "SELECT stock_code, valid_from, ksic_code, ksic_source, ksic3_name, corp_code, "
    "       market, source, source_asof, ksic_checked_at, last_seen_at "
    "FROM stock_sector_map WHERE valid_to IS NULL")


def load_open_rows(conn) -> dict:
    """열린 줄 전부. 급변 가드의 «분모»이므로 표본이 아니라 전체를 읽는다."""
    try:
        with conn.cursor() as cur:
            cur.execute(_OPEN_ROWS_SQL)
            cols = [d[0] for d in cur.description]
            return dict((r[0], dict(zip(cols, r))) for r in cur.fetchall())
    except Exception:
        conn.rollback()
        raise


def open_market_counts(conn) -> dict:
    """열린 줄의 시장별 행수 — 캐시 CSV 규모 하한의 기준선."""
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT market, count(*) FROM stock_sector_map "
                        "WHERE valid_to IS NULL AND market IS NOT NULL GROUP BY 1")
            return dict((str(m), int(n)) for m, n in cur.fetchall())
    except Exception:
        conn.rollback()
        raise


def load_stock_industry(conn) -> dict:
    """🔴 stock_industry 는 «부트스트랩에서만» 읽는다(스냅샷 2026-08-07 · 갱신 소스 없음).

    ⚠️ §7 — 길이 5 초과 코드는 «저장은 하되» WARN 한다(현재 실측 0건 · varchar(10)).
       DART 응답 경로에만 경고를 달면 스냅샷 경로로 들어온 이상값이 조용히 지나간다.
    """
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT stock_code, induty_code FROM stock_industry "
                        "WHERE induty_code IS NOT NULL AND induty_code <> ''")
            out = dict((r[0], r[1]) for r in cur.fetchall())
    except Exception:
        conn.rollback()
        raise
    long_codes = [(c, v) for c, v in out.items() if len(v or "") > 5]
    if long_codes:
        logger.warning("[sector] stock_industry 에 길이 5 초과 induty_code %d건 - "
                       "저장은 하되 확인 필요: %s", len(long_codes), long_codes[:5])
    return out


def write_map(conn, plan: dict, source: str) -> dict:
    """계획을 «한 트랜잭션»으로 쓴다. 실패하면 통째로 롤백된다.

    ⚠️ collected_at 은 어느 경로에서도 쓰지 않는다(불변) · last_seen_at 은 «항상» 갱신.
    """
    n_close = n_new = n_up = 0
    try:
        with conn.cursor() as cur:
            for c in plan["close"]:
                cur.execute(_CLOSE_ROW, c)
                n_close += 1
            for r in plan["open_new"]:
                row = dict(r)
                for f in ("ksic_code", "ksic_source", "ksic3_name", "corp_code", "market",
                          "kosdaq_dept", "products", "listing_date", "settle_month",
                          "source_asof", "ksic_checked_at"):
                    row.setdefault(f, None)
                row["source"] = row.get("source") or source
                cur.execute(_INSERT_ROW, row)
                n_new += 1
            for u in plan["inplace"]:
                sets = dict(u["set"])
                bad = set(sets) - _UPDATABLE
                if bad:
                    raise ValueError("갱신 불가 컬럼: %s" % sorted(bad))
                cols = ", ".join("%s=%%(%s)s" % (k, k) for k in sorted(sets))
                sql = ("UPDATE stock_sector_map SET last_seen_at=now()"
                       + ((", " + cols) if cols else "")
                       + " WHERE stock_code=%(stock_code)s AND valid_from=%(valid_from)s")
                params = dict(sets)
                params["stock_code"] = u["stock_code"]
                params["valid_from"] = u["valid_from"]
                cur.execute(sql, params)
                n_up += 1
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    return {"closed": n_close, "inserted": n_new, "updated": n_up}
