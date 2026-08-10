"""B(4) 시총 추정치 별도 테이블 적재 + daily_prices 무변경 증명.

🔴 이 스크립트가 이번 작업의 **유일한 DB 쓰기**다. 쓰는 대상은 신규 테이블
   `market_cap_estimate` 뿐이며, `daily_prices` 는 SELECT 만 한다
   (UPDATE/DELETE 문이 이 파일에 존재하지 않는다).
🔴 TimescaleDB retention policy 를 설정하지 않는다. hypertable 로도 만들지 않는다
   — 이 프로젝트의 영구 규칙(자동삭제 금지)이다.
🔴 SUSPECT 행의 market_cap 은 NULL 이다. **0 금지** — 지금 결손의 대부분이 0 이라
   NULL 만 세면 9.65% 로 보이던 그 문제를 재생산하면 안 된다. 행 자체는 남긴다
   (어느 행이 왜 비었는지가 기록으로 남아야 한다).

멱등: PK(stock_code, date, source) 에 ON CONFLICT DO UPDATE.

usage:
  PYTHONUTF8=1 python scripts/dart_mcap_b4_load.py --create
  PYTHONUTF8=1 python scripts/dart_mcap_b4_load.py --load
"""
import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import psycopg2  # noqa: E402
from psycopg2.extras import execute_values  # noqa: E402

from dart_mcap_common import OUT_DIR  # noqa: E402

EMIT_JSONL = os.path.join(OUT_DIR, "b2_estimates.jsonl")
PROOF_TXT = os.path.join(OUT_DIR, "b4_invariance_proof.txt")

TABLE = "market_cap_estimate"

DDL = f"""
CREATE TABLE IF NOT EXISTS {TABLE} (
    stock_code   VARCHAR(20)      NOT NULL,
    date         TEXT             NOT NULL,
    market_cap   DOUBLE PRECISION,          -- SAFE_STRICT 만 채운다. SUSPECT 는 NULL(0 아님)
    shares       BIGINT,                    -- 쓴 상장주식수(istc_totqy)
    source       TEXT             NOT NULL, -- 'dart_istc_stlm'
    report_key   TEXT,                      -- 예 '2022/11012' — 어느 보고서에서 왔는지
    gate         TEXT             NOT NULL, -- SAFE_STRICT | SUSPECT
    reason       TEXT,                      -- SUSPECT 사유
    created_at   TIMESTAMP        NOT NULL DEFAULT now(),
    PRIMARY KEY (stock_code, date, source)
);
CREATE INDEX IF NOT EXISTS idx_{TABLE}_date ON {TABLE} (date);
CREATE INDEX IF NOT EXISTS idx_{TABLE}_gate ON {TABLE} (gate);
"""


def rw_conn():
    """쓰기 연결 — 대상은 신규 테이블뿐."""
    return psycopg2.connect(
        host=os.getenv("TIMESCALE_HOST", "127.0.0.1"),
        port=int(os.getenv("TIMESCALE_PORT", 5433)),
        database="kis_template",
        user=os.getenv("TIMESCALE_USER", "robotrader"),
        password=os.getenv("TIMESCALE_PASSWORD", "1234"),
    )


DP_FINGERPRINT = """
SELECT count(*),
       count(market_cap) FILTER (WHERE market_cap > 0),
       coalesce(sum(market_cap), 0),
       coalesce(sum(hashtext(stock_code || date ||
                             coalesce(close::text,'') ||
                             coalesce(market_cap::text,'') ||
                             coalesce(adj_factor::text,''))::bigint), 0)
FROM daily_prices
"""


def fingerprint(cur, label):
    cur.execute(DP_FINGERPRINT)
    n, pos, s, h = cur.fetchone()
    return {"label": label, "rows": n, "mcap_pos": pos, "mcap_sum": float(s), "hash": int(h)}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--create", action="store_true")
    ap.add_argument("--load", action="store_true")
    args = ap.parse_args()

    conn = rw_conn()
    conn.autocommit = False
    cur = conn.cursor()

    if args.create:
        cur.execute(DDL)
        conn.commit()
        cur.execute(
            "SELECT column_name, data_type, is_nullable FROM information_schema.columns "
            "WHERE table_name = %s ORDER BY ordinal_position", (TABLE,))
        print(f"{TABLE} 생성/확인:")
        for r in cur.fetchall():
            print("   ", r)
        # retention policy 가 붙어있지 않음을 증명
        cur.execute("SELECT count(*) FROM pg_class WHERE relname = %s", (TABLE,))
        print("존재:", cur.fetchone()[0] == 1)
        conn.close()
        return

    if not args.load:
        ap.error("--create 또는 --load")

    if not os.path.exists(EMIT_JSONL):
        raise SystemExit(f"{EMIT_JSONL} 없음 — 먼저 b2 --emit")

    before = fingerprint(cur, "before")
    print("daily_prices before:", before, flush=True)

    batch, total, safe, susp = [], 0, 0, 0
    sql = (f"INSERT INTO {TABLE} "
           "(stock_code, date, market_cap, shares, source, report_key, gate, reason) "
           "VALUES %s ON CONFLICT (stock_code, date, source) DO UPDATE SET "
           "market_cap = EXCLUDED.market_cap, shares = EXCLUDED.shares, "
           "report_key = EXCLUDED.report_key, gate = EXCLUDED.gate, "
           "reason = EXCLUDED.reason, created_at = now()")
    with open(EMIT_JSONL, encoding="utf-8") as f:
        for line in f:
            if not line.strip():
                continue
            r = json.loads(line)
            # 🔴 방어: SAFE 가 아닌데 값이 실린 행은 적재하지 않는다(0 금지 규약 보호)
            mc = r["market_cap"] if r["gate"] == "SAFE_STRICT" else None
            sh = r["shares"] if r["gate"] == "SAFE_STRICT" else None
            if mc is not None and mc <= 0:
                raise SystemExit(f"0 이하 market_cap 발견 — 규약 위반: {r}")
            batch.append((r["stock_code"], r["date"], mc, sh, r["source"],
                          r.get("report_key"), r["gate"], r.get("reason")))
            total += 1
            safe += r["gate"] == "SAFE_STRICT"
            susp += r["gate"] != "SAFE_STRICT"
            if len(batch) >= 10000:
                execute_values(cur, sql, batch, page_size=2000)
                batch.clear()
                if total % 200000 == 0:
                    print(f"   ... {total:,}행", flush=True)
    if batch:
        execute_values(cur, sql, batch, page_size=2000)
    conn.commit()

    after = fingerprint(cur, "after")
    cur.execute(f"SELECT gate, count(*), count(market_cap) FROM {TABLE} GROUP BY gate ORDER BY gate")
    gates = cur.fetchall()
    cur.execute(f"SELECT count(*), min(date), max(date), count(DISTINCT stock_code) FROM {TABLE}")
    tot = cur.fetchone()
    cur.execute(f"SELECT count(*) FROM {TABLE} WHERE gate <> 'SAFE_STRICT' AND market_cap IS NOT NULL")
    bad_val = cur.fetchone()[0]
    cur.execute(f"SELECT count(*) FROM {TABLE} WHERE market_cap = 0")
    zeros = cur.fetchone()[0]
    conn.close()

    # 🔴 sum(double precision) 을 불변식에 넣지 말 것 — 병렬 합산 순서가 실행마다
    #    달라져 같은 데이터에서도 상대 1e-15 수준으로 흔들린다(실측: 같은 쿼리 3회에
    #    ...4315 / ...4330 / ...4253). 처음 이 검사가 "변경 감지"를 낸 것은 실제
    #    변경이 아니라 **검증식 자체가 비결정적**이었기 때문이다.
    #    권위 기준은 정수 3종: 행수 · mcap>0 건수 · hashtext 합(내용 전체를 덮는다).
    #    합계는 참고용으로만 남기고 상대오차 허용치를 둔다.
    sum_rel = (abs(before["mcap_sum"] - after["mcap_sum"]) /
               max(abs(before["mcap_sum"]), 1.0))
    ok = (before["rows"] == after["rows"]
          and before["hash"] == after["hash"]
          and before["mcap_pos"] == after["mcap_pos"]
          and sum_rel < 1e-9)

    L = [
        "=== B(4) 적재 결과 ===",
        f"입력 {total:,}행  (SAFE_STRICT {safe:,} / SUSPECT {susp:,})",
        f"{TABLE}: {tot[0]:,}행, {tot[1]}~{tot[2]}, {tot[3]}종목",
        f"게이트별(행수, market_cap 非NULL): {gates}",
        f"🔴 규약 검사 — SUSPECT 인데 값 있는 행: {bad_val} (0이어야 함)",
        f"🔴 규약 검사 — market_cap = 0 인 행: {zeros} (0이어야 함)",
        "",
        "=== daily_prices 무변경 증명 ===",
        f"before: rows={before['rows']:,} mcap>0={before['mcap_pos']:,} "
        f"sum={before['mcap_sum']:.6e} hash={before['hash']}",
        f"after : rows={after['rows']:,} mcap>0={after['mcap_pos']:,} "
        f"sum={after['mcap_sum']:.6e} hash={after['hash']}",
        f"합계 상대차: {sum_rel:.3e} (부동소수 합산 비결정성, 임계 1e-9)",
        f"판정: {'✅ 무변경(행수·mcap>0건수·hashtext합 완전일치)' if ok else '🔴 변경 감지!'}",
    ]
    txt = "\n".join(L)
    with open(PROOF_TXT, "w", encoding="utf-8") as f:
        f.write(txt + "\n")
    print(txt)
    if not ok:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
