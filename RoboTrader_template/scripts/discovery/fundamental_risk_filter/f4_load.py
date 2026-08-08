"""F(4) PIT 재무 적재 — 이 파이프라인의 «유일한» DB 쓰기.

🔴 쓰는 대상은 신규 테이블 `dart_financials_asfiled` 뿐이다.
   기존 테이블(daily_prices 등)에는 UPDATE/DELETE 문이 이 파일에 존재하지 않는다.
🔴 retention policy 를 설정하지 않고 hypertable 로 만들지 않는다(영구 규칙).
🔴 결측은 NULL 이다. 0 으로 채우지 않는다.
🔑 013(무자료) 행도 남긴다 — 어느 종목·연도가 왜 비었는지가 기록이어야 한다.
🔴 `CREATE TABLE IF NOT EXISTS` 는 이름이 같은 남의 테이블이 있으면 조용히
   no-op 한다 — `--create` 뒤·`--load` 시작 시 컬럼 집합을 확인해(`verify_table_columns`)
   그 위험을 실행 시점에 잡는다(불일치면 exit 6).
🔴 적재 트랜잭션은 REPEATABLE READ — READ COMMITTED 라면 다른 프로세스(16:00 EOD
   수집기·라이브 봇)의 동시 커밋이 불변 증명의 전/후 지문을 갈라놓아 스푸리어스
   롤백을 낸다.

멱등: PK(stock_code, bsns_year) 에 ON CONFLICT DO UPDATE.

usage:
  PYTHONUTF8=1 python scripts/discovery/fundamental_risk_filter/f4_load.py --create
  PYTHONUTF8=1 python scripts/discovery/fundamental_risk_filter/f4_load.py --load
"""
import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import psycopg2  # noqa: E402
from psycopg2.extras import execute_values  # noqa: E402

from dart_client import OUT_DIR  # noqa: E402
from f3_normalize import NORM_JSONL  # noqa: E402

TABLE = "dart_financials_asfiled"
PROOF_TXT = os.path.join(OUT_DIR, "f4_invariance_proof.txt")

# 🔴 UPSERT 로 넘기는(=적재하는) 컬럼의 순서 SSOT. read_rows() 가 여기서 튜플
#    순서를 만들고, UPSERT 의 INSERT 컬럼 목록도 반드시 이 순서와 같아야 한다.
#    7개 숫자 컬럼이 전부 BIGINT라 두 개가 바뀌어도 에러 없이 조용히 틀린 값이
#    들어간다 — 순서 불일치를 테스트가 아니라 타입 오류로는 못 잡는다.
FIELD_ORDER = (
    "stock_code", "bsns_year", "status", "rcept_dt", "fs_div",
    "total_equity", "issued_capital", "total_liabilities",
    "operating_income", "interest_expense", "finance_costs", "interest_paid_cf",
)

# 🔴 테이블이 «우리 것»인지 증명하는 기대 컬럼 집합. CREATE TABLE IF NOT EXISTS 는
#    이름이 같은 남의 테이블이 이미 있으면 조용히 no-op 하고, 그 뒤 UPSERT 가
#    남의 행을 덮어쓸 수 있다. FIELD_ORDER + created_at(DEFAULT now(), INSERT
#    대상은 아니지만 DDL 컬럼이다) 이 DDL 에 실제로 정의된 컬럼과 정확히 같아야
#    한다 — 테스트가 이 동등성을 문자열로 직접 검사한다.
EXPECTED_COLUMNS = set(FIELD_ORDER) | {"created_at"}

DDL = f"""
CREATE TABLE IF NOT EXISTS {TABLE} (
    stock_code         VARCHAR(20) NOT NULL,
    bsns_year          VARCHAR(4)  NOT NULL,
    status             TEXT,                  -- DART 응답 요약. 000 / 013 / 000_EMPTY
                                              -- 🔑 왜 비었는지가 함께 남아야 커버리지에서
                                              --    「신고 부재」와 「매핑 실패」가 갈린다
    rcept_dt           DATE,                  -- 접수일 = 이 값을 알 수 있게 된 날
    fs_div             TEXT,                  -- CFS | OFS | NULL(무자료)
    total_equity       BIGINT,
    issued_capital     BIGINT,
    total_liabilities  BIGINT,
    operating_income   BIGINT,
    interest_expense   BIGINT,                -- 국내 실측 0.0%. 「찾아봤다」는 기록으로 남긴다
    finance_costs      BIGINT,                -- 금융원가(CIS). 값 확보율 80.4%(계정 존재 84.8%)
    interest_paid_cf   BIGINT,                -- 이자지급(CF, 현금주의). 값 확보율 80.4%(계정 존재 91.3%)
    created_at         TIMESTAMP NOT NULL DEFAULT now(),
    PRIMARY KEY (stock_code, bsns_year)
);
CREATE INDEX IF NOT EXISTS idx_{TABLE}_rcept ON {TABLE} (rcept_dt);
CREATE INDEX IF NOT EXISTS idx_{TABLE}_code ON {TABLE} (stock_code);
"""

UPSERT = f"""
INSERT INTO {TABLE}
  (stock_code, bsns_year, status, rcept_dt, fs_div, total_equity,
   issued_capital, total_liabilities, operating_income, interest_expense,
   finance_costs, interest_paid_cf)
VALUES %s
ON CONFLICT (stock_code, bsns_year) DO UPDATE SET
  status            = EXCLUDED.status,
  rcept_dt          = EXCLUDED.rcept_dt,
  fs_div            = EXCLUDED.fs_div,
  total_equity      = EXCLUDED.total_equity,
  issued_capital    = EXCLUDED.issued_capital,
  total_liabilities = EXCLUDED.total_liabilities,
  operating_income  = EXCLUDED.operating_income,
  interest_expense  = EXCLUDED.interest_expense,
  finance_costs     = EXCLUDED.finance_costs,
  interest_paid_cf  = EXCLUDED.interest_paid_cf
  -- 🔑 created_at 을 의도적으로 뺀다 — 최초 적재 시각을 보존하기 위함
"""

DP_FINGERPRINT = """
SELECT count(*),
       coalesce(sum(hashtext(d::text)::bigint), 0)
FROM daily_prices d
"""

VERIFY_COLUMNS_SQL = """
SELECT column_name FROM information_schema.columns
WHERE table_name = %s
"""


def verify_table_columns(cur):
    """테이블이 «우리 것»인지 확인 — 컬럼 집합이 EXPECTED_COLUMNS 와 정확히 같아야 한다.

    🔴 `CREATE TABLE IF NOT EXISTS` 는 이름이 같은 테이블이 이미 있으면 조용히
       no-op 한다. 그 뒤 UPSERT 는 자기 테이블이라 믿고 남의 행을 덮어쓸 수
       있다. 컬럼이 하나도 없으면(테이블 자체가 없으면) EXPECTED_COLUMNS 와
       빈 집합이 달라 여기서 잡힌다 — «없음»도 «남의 것」과 같은 취급이다.
    """
    cur.execute(VERIFY_COLUMNS_SQL, (TABLE,))
    actual = {r[0] for r in cur.fetchall()}
    if actual != EXPECTED_COLUMNS:
        missing = sorted(EXPECTED_COLUMNS - actual)
        extra = sorted(actual - EXPECTED_COLUMNS)
        print(
            f"🔴 {TABLE} 의 컬럼이 기대와 다르다 — 우리 테이블이 아닐 수 있다.\n"
            f"   누락: {missing}\n"
            f"   초과: {extra}\n"
            f"   중단한다 — UPSERT 를 진행하면 남의 행을 덮어쓸 위험이 있다.",
            file=sys.stderr,
        )
        sys.exit(6)


def rw_conn():
    return psycopg2.connect(
        host=os.getenv("TIMESCALE_HOST", "127.0.0.1"),
        port=int(os.getenv("TIMESCALE_PORT", 5433)),
        database="kis_template",
        user=os.getenv("TIMESCALE_USER", "robotrader"),
        password=os.getenv("TIMESCALE_PASSWORD", "1234"),
    )


def fingerprint(cur):
    cur.execute(DP_FINGERPRINT)
    n, h = cur.fetchone()
    return {"rows": int(n), "hash": int(h)}


def read_rows():
    """FIELD_ORDER 순서로 튜플을 만든다 — INSERT 컬럼 순서와 어긋나면 안 된다.

    🔴 손으로 베낀 리터럴 튜플이 아니라 실제 module-level 시퀀스(FIELD_ORDER)를
       순회해서 만든다. 이래야 테스트가 「INSERT 컬럼 목록 == FIELD_ORDER」를
       비교할 때, 손으로 두 번 베낀 두 문자열이 «우연히 같아서» 통과하는 게
       아니라 진짜 같은 소스를 참조하고 있음을 검증할 수 있다.
    """
    out = []
    with open(NORM_JSONL, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            r = json.loads(line)
            out.append(tuple(r.get(field) for field in FIELD_ORDER))
    return out


def main():
    import time
    ap = argparse.ArgumentParser()
    ap.add_argument("--create", action="store_true")
    ap.add_argument("--load", action="store_true")
    args = ap.parse_args()

    os.makedirs(OUT_DIR, exist_ok=True)
    conn = rw_conn()
    conn.autocommit = False
    cur = conn.cursor()

    try:
        if args.create:
            cur.execute(DDL)
            conn.commit()
            verify_table_columns(cur)   # exit(6)이면 여기서 끝난다
            conn.commit()               # 읽기뿐이었지만 트랜잭션을 깔끔히 닫는다
            print(f"{TABLE} 준비 완료")

        if args.load:
            # 🔴 FIX7: READ COMMITTED 는 전/후 지문이 별개 스냅샷이라, 이 트랜잭션과
            #    무관한 다른 프로세스(16:00 EOD 수집기·라이브 봇)의 커밋이 끼면
            #    「내가 바꿨다」와 「누가 바꿨다」가 섞여 스푸리어스 롤백이 난다.
            #    REPEATABLE READ 로 트랜잭션 시작 시점 스냅샷을 고정한다 — 내
            #    쓰기(dart_financials_asfiled)는 여전히 보이고, 남의 커밋은
            #    안 보인다. set_session 은 트랜잭션이 열려 있지 않을 때만
            #    호출 가능하므로 위 --create 분기가 commit 으로 반드시 닫혀 있어야 한다.
            conn.set_session(isolation_level="REPEATABLE READ")
            verify_table_columns(cur)   # exit(6)이면 여기서 끝난다 — REPEATABLE READ 트랜잭션의 첫 문장

            # 🔴 불변 증명: 쓰기 «전»에 검사하고, 통과할 때만 커밋한다
            t0 = time.time()
            before = fingerprint(cur)
            t_before = time.time() - t0

            rows = read_rows()
            execute_values(cur, UPSERT, rows, page_size=1000)

            t0 = time.time()
            after = fingerprint(cur)
            t_after = time.time() - t0

            ok = before == after
            if not ok:
                # 증명 실패 → 롤백
                conn.rollback()
                text = (
                    f"🔴 적재 {len(rows)}행 검증 실패\n"
                    f"daily_prices before: {before}\n"
                    f"daily_prices after : {after}\n"
                    f"불변: 변경됨\n"
                    f"fingerprint 계산시간: {t_before:.2f}s / {t_after:.2f}s\n"
                )
                with open(PROOF_TXT, "w", encoding="utf-8") as f:
                    f.write(text)
                print(text)
                sys.exit(4)

            # 증명 통과 → 커밋
            conn.commit()

            # 커밋 후 행 수 조회
            cur.execute(f"SELECT count(*), count(rcept_dt), count(status) FROM {TABLE}")
            n_all, n_dt, n_status = cur.fetchone()

            text = (
                f"적재 {len(rows)}행 → {TABLE} 총 {n_all}행 (rcept_dt {n_dt}건, status {n_status}건)\n"
                f"daily_prices before: {before}\n"
                f"daily_prices after : {after}\n"
                f"불변: OK\n"
                f"fingerprint 계산시간: {t_before:.2f}s / {t_after:.2f}s\n"
            )
            with open(PROOF_TXT, "w", encoding="utf-8") as f:
                f.write(text)
            print(text)
    finally:
        cur.close()
        conn.close()


if __name__ == "__main__":
    main()
