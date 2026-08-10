"""C(2) c1 체크포인트 → 신규 테이블 `stock_industry` 적재 (멱등 + 무변경 증명).

🔴 기존 테이블은 한 줄도 건드리지 않는다. 신규 테이블에만 INSERT/UPSERT.
🔴 TimescaleDB retention policy 설정 금지(프로젝트 영구 규칙). hypertable 아님, 일반 테이블.
🔴 불변식에 sum(double precision) 을 쓰지 않는다 — 병렬 합산 순서가 실행마다 달라
   같은 데이터에서 값이 흔들리고 거짓 경보가 난다(2026-08-06 실측).
   → count(*) 와 sum(hashtext(row::text))::bigint (정수 합) 만 쓴다.

적재 대상: status == '000' 인 레코드만. 빈 응답·오류는 적재하지 않고 집계만 한다.

usage:
  PYTHONUTF8=1 python scripts/dart_industry_c2_load.py --dry-run
  PYTHONUTF8=1 python scripts/dart_industry_c2_load.py
"""
import argparse
import json
import os
import sys
import time
from collections import Counter
from datetime import datetime

import psycopg2

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from dart_mcap_common import OUT_DIR  # noqa: E402

CHECKPOINT = os.path.join(OUT_DIR, "c1_industry_checkpoint.jsonl")
PROOF_TXT = os.path.join(OUT_DIR, "c2_invariance_proof.txt")

TARGET = "stock_industry"

# 무변경 증명 대상 — 전 public 테이블 count(*), 아래 표기 테이블은 hashtext 합까지.
CHECKSUM_TABLES = ("daily_prices", "stock_market", "financial_data",
                   "market_cap_estimate", "corp_events")

DDL = f"""
CREATE TABLE IF NOT EXISTS {TARGET} (
    stock_code      VARCHAR(10) PRIMARY KEY,
    corp_code       VARCHAR(8)  NOT NULL,
    corp_name       TEXT,
    corp_name_eng   TEXT,
    stock_name      TEXT,
    dart_stock_code VARCHAR(10),
    corp_cls        VARCHAR(2),
    induty_code     VARCHAR(10),
    est_dt          VARCHAR(8),
    acc_mt          VARCHAR(2),
    jurir_no        VARCHAR(20),
    bizr_no         VARCHAR(20),
    source          TEXT NOT NULL DEFAULT 'dart_company_api',
    collected_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_stock_industry_induty ON {TARGET}(induty_code);
CREATE INDEX IF NOT EXISTS idx_stock_industry_cls ON {TARGET}(corp_cls);
"""

UPSERT = f"""
INSERT INTO {TARGET} (stock_code, corp_code, corp_name, corp_name_eng, stock_name,
                      dart_stock_code, corp_cls, induty_code, est_dt, acc_mt,
                      jurir_no, bizr_no, source, collected_at, updated_at)
VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,'dart_company_api',now(),now())
ON CONFLICT (stock_code) DO UPDATE SET
    corp_code = EXCLUDED.corp_code,
    corp_name = EXCLUDED.corp_name,
    corp_name_eng = EXCLUDED.corp_name_eng,
    stock_name = EXCLUDED.stock_name,
    dart_stock_code = EXCLUDED.dart_stock_code,
    corp_cls = EXCLUDED.corp_cls,
    induty_code = EXCLUDED.induty_code,
    est_dt = EXCLUDED.est_dt,
    acc_mt = EXCLUDED.acc_mt,
    jurir_no = EXCLUDED.jurir_no,
    bizr_no = EXCLUDED.bizr_no,
    updated_at = now()
"""


def conn(readonly=False):
    c = psycopg2.connect(host="127.0.0.1", port=5433, database="kis_template",
                         user="robotrader", password="1234")
    if readonly:
        c.set_session(readonly=True, autocommit=True)
    return c


def snapshot(cur):
    """정수 기준 스냅샷. float 합산 금지 — 순서 의존이라 거짓 경보가 난다."""
    cur.execute("""SELECT table_name FROM information_schema.tables
                   WHERE table_schema='public' AND table_type='BASE TABLE'
                   ORDER BY table_name""")
    tables = [r[0] for r in cur.fetchall() if r[0] != TARGET]
    snap = {}
    for t in tables:
        cur.execute(f'SELECT count(*) FROM "{t}"')
        n = cur.fetchone()[0]
        h = None
        if t in CHECKSUM_TABLES:
            cur.execute(f'SELECT COALESCE(sum(hashtext(x::text))::bigint,0) FROM "{t}" x')
            h = cur.fetchone()[0]
        snap[t] = (n, h)
    return snap


def read_checkpoint():
    rows, st, blanks = [], Counter(), 0
    seen = {}
    with open(CHECKPOINT, encoding="utf-8") as f:
        for line in f:
            if not line.strip():
                continue
            rec = json.loads(line)
            st[rec["status"]] += 1
            if rec["status"] != "000":
                continue
            d = rec.get("data") or {}
            if not d.get("corp_code"):
                blanks += 1
                continue
            seen[rec["stock_code"]] = (
                rec["stock_code"], rec["corp_code"], d.get("corp_name"),
                d.get("corp_name_eng"), d.get("stock_name"), d.get("stock_code"),
                d.get("corp_cls"), d.get("induty_code"), d.get("est_dt"),
                d.get("acc_mt"), d.get("jurir_no"), d.get("bizr_no"),
            )
    rows = list(seen.values())
    return rows, st, blanks


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--control-gap", type=int, default=20,
                    help="대조군 관측 창(초). 적재 소요보다 길게 잡아 보수적으로 판정")
    args = ap.parse_args()

    rows, st, blanks = read_checkpoint()
    print(f"체크포인트 {sum(st.values())}건, status={dict(st)}, "
          f"적재대상(status=000, corp_code 유효) {len(rows)}건, 빈응답 {blanks}건")
    if args.dry_run:
        return

    # 🔑 대조군 — 지금은 장중이고 라이브 봇이 minute_candles 등에 계속 쓰고 있다.
    # 단순 before/after 로는 "내 적재 탓"과 "봇이 쓴 것"이 안 갈린다.
    # A → (대기) → B 로 봇 단독 drift 집합을 먼저 측정하고, 적재 후 C 를 찍는다.
    # 판정: B≠C 인데 A≠B 가 아니었던 테이블 = 진짜 경보.
    rc = conn(readonly=True)
    snap_a = snapshot(rc.cursor())
    time.sleep(args.control_gap)
    snap_b = snapshot(rc.cursor())
    rc.close()
    drift = {t for t in snap_a if snap_a[t] != snap_b[t]}
    print(f"대조군: 적재 전 {args.control_gap}초 동안 라이브 봇이 바꾼 테이블 "
          f"{len(drift)}개 {sorted(drift)}")
    before = snap_b

    c = conn()
    cur = c.cursor()
    cur.execute(DDL)
    cur.executemany(UPSERT, rows)
    inserted = cur.rowcount
    c.commit()
    cur.execute(f"SELECT count(*) FROM {TARGET}")
    total = cur.fetchone()[0]
    c.close()

    rc = conn(readonly=True)
    after = snapshot(rc.cursor())
    rc.close()

    changed = {t for t in before if before[t] != after[t]}
    alarms = sorted(changed - drift)   # 봇 drift 로 설명 안 되는 변경 = 진짜 경보
    missing = set(before) ^ set(after)

    lines = [
        f"# stock_industry 적재 무변경 증명  {datetime.now():%Y-%m-%d %H:%M:%S}",
        f"적재 upsert {len(rows)}행 (rowcount={inserted}) → {TARGET} 총 {total}행",
        f"기존 테이블 {len(before)}개 검사 (count(*) 전부 + hashtext 합 {len(CHECKSUM_TABLES)}개)",
        f"⚠️ 불변식은 정수 기준(count / sum(hashtext)::bigint) — float 합산 미사용",
        f"🔑 장중이라 라이브 봇이 동시에 쓴다 → 대조군(A→{args.control_gap}s→B) 으로 봇 drift 분리",
        f"   봇 단독 drift 테이블 {len(drift)}개: {sorted(drift)}",
        f"   적재 전후(B→C) 변경 {len(changed)}개 / 그중 drift 로 설명 안 되는 것 = {len(alarms)}개 {alarms}",
        f"   테이블 집합 차이: {len(missing)}개",
        "",
    ]
    for t in sorted(before):
        n, h = before[t]
        n2, h2 = after[t]
        if (n, h) == (n2, h2):
            mark = "OK  "
        elif t in drift:
            mark = "봇  "   # 대조군에서 이미 변하던 테이블 = 라이브 봇 소행
        else:
            mark = "🔴  "
        hs = f"  hash={h}" if h is not None else ""
        extra = f"   → after rows={n2:,}" if n != n2 else ""
        lines.append(f"{mark}{t:40s} rows={n:>10,}{hs}{extra}")
    for t in alarms:
        lines.append(f"🔴 ALARM {t}: before={before[t]} after={after[t]}")

    txt = "\n".join(lines)
    with open(PROOF_TXT, "w", encoding="utf-8") as f:
        f.write(txt + "\n")
    print(txt)
    if alarms or missing:
        raise SystemExit("🔴 적재로 설명되는 기존 테이블 변경 감지 — 확인 필요")


if __name__ == "__main__":
    main()
