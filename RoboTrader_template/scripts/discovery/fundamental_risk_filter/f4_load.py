"""F(4) PIT 재무 적재 — 이 파이프라인의 «유일한» DB 쓰기.

🔴 쓰는 대상은 신규 테이블 `dart_financials_asfiled` 뿐이다.
   기존 테이블(daily_prices 등)에는 UPDATE/DELETE 문이 이 파일에 존재하지 않는다.
🔴 retention policy 를 설정하지 않고 hypertable 로 만들지 않는다(영구 규칙).
🔴 결측은 NULL 이다. 0 으로 채우지 않는다.
🔑 013(무자료) 행도 남긴다 — 어느 종목·연도가 왜 비었는지가 기록이어야 한다.

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
"""

DP_FINGERPRINT = """
SELECT count(*),
       coalesce(sum(hashtext(stock_code || date ||
                             coalesce(close::text,'') ||
                             coalesce(market_cap::text,''))::bigint), 0)
FROM daily_prices
"""


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
    out = []
    with open(NORM_JSONL, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            r = json.loads(line)
            out.append((
                r["stock_code"], r["bsns_year"], r.get("status"),
                r.get("rcept_dt"), r.get("fs_div"),
                r.get("total_equity"), r.get("issued_capital"),
                r.get("total_liabilities"), r.get("operating_income"),
                r.get("interest_expense"),
                r.get("finance_costs"), r.get("interest_paid_cf"),
            ))
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--create", action="store_true")
    ap.add_argument("--load", action="store_true")
    args = ap.parse_args()

    os.makedirs(OUT_DIR, exist_ok=True)
    conn = rw_conn()
    conn.autocommit = False
    cur = conn.cursor()

    if args.create:
        cur.execute(DDL)
        conn.commit()
        print(f"{TABLE} 준비 완료")

    if args.load:
        before = fingerprint(cur)
        rows = read_rows()
        execute_values(cur, UPSERT, rows, page_size=1000)
        conn.commit()
        after = fingerprint(cur)

        cur.execute(f"SELECT count(*), count(rcept_dt) FROM {TABLE}")
        n_all, n_dt = cur.fetchone()

        ok = before == after
        text = (
            f"적재 {len(rows)}행 → {TABLE} 총 {n_all}행 (rcept_dt 있는 행 {n_dt})\n"
            f"daily_prices before: {before}\n"
            f"daily_prices after : {after}\n"
            f"불변: {'OK' if ok else '🔴 변경됨'}\n"
        )
        with open(PROOF_TXT, "w", encoding="utf-8") as f:
            f.write(text)
        print(text)
        if not ok:
            sys.exit(4)

    cur.close()
    conn.close()


if __name__ == "__main__":
    main()
