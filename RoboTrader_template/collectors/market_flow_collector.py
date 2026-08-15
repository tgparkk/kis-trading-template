# -*- coding: utf-8 -*-
"""공매도 · 프로그램매매 일별 수집 → `short_sale_daily` / `program_trade_daily`.

공급:
  - 공매도    KIS TR `FHPST04830000` — 🟢 **날짜 구간 파라미터를 받아** 과거 복구가 된다.
  - 프로그램  KIS TR `FHPPG04650201` — ⚠️ **최근 30 거래일 롤링**. 놓치면 영구 결손.

KIS 원문 필드는 `raw` JSONB 에 통째로 보존한다 — 컬럼을 골라 뽑으면 나중에 필요해진 필드가
사라지고, 그때는 창이 지나 복구가 안 된다.

실행:
    python -m collectors.market_flow_collector --kind short   --codes 199430
    python -m collectors.market_flow_collector --kind program --all
    python -m collectors.market_flow_collector --kind short   --all --from 20260701 --to 20260814
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

import psycopg2  # noqa: E402
from psycopg2.extras import Json  # noqa: E402

from api.kis_market_api import (  # noqa: E402
    get_credit_balance_daily, get_overtime_daily,
    get_program_trade_daily, get_short_sale_daily,
)
from collectors.investor_trend_collector import (  # noqa: E402
    CALL_INTERVAL, dsn, universe, with_retry,
)
from utils.logger import setup_logger  # noqa: E402

logger = setup_logger(__name__)

_SHORT_COLS = {
    "close": "stck_clpr", "open": "stck_oprc", "high": "stck_hgpr", "low": "stck_lwpr",
    "avg_price": "avrg_prc", "acml_vol": "acml_vol", "ssts_cntg_qty": "ssts_cntg_qty",
    "ssts_vol_rlim": "ssts_vol_rlim", "acml_ssts_cntg_qty": "acml_ssts_cntg_qty",
    "ssts_tr_pbmn": "ssts_tr_pbmn", "ssts_tr_pbmn_rlim": "ssts_tr_pbmn_rlim",
}
_PROG_COLS = {
    "close": "stck_clpr", "acml_vol": "acml_vol", "acml_tr_pbmn": "acml_tr_pbmn",
    "seln_vol": "whol_smtn_seln_vol", "shnu_vol": "whol_smtn_shnu_vol",
    "ntby_qty": "whol_smtn_ntby_qty", "seln_tr_pbmn": "whol_smtn_seln_tr_pbmn",
    "shnu_tr_pbmn": "whol_smtn_shnu_tr_pbmn", "ntby_tr_pbmn": "whol_smtn_ntby_tr_pbmn",
}

_CREDIT_COLS = {
    "close": "stck_prpr", "acml_vol": "acml_vol",
    "loan_new_stcn": "whol_loan_new_stcn", "loan_rdmp_stcn": "whol_loan_rdmp_stcn",
    "loan_rmnd_stcn": "whol_loan_rmnd_stcn", "loan_rmnd_amt": "whol_loan_rmnd_amt",
    "loan_rmnd_rate": "whol_loan_rmnd_rate", "loan_gvrt": "whol_loan_gvrt",
    "stln_new_stcn": "whol_stln_new_stcn", "stln_rdmp_stcn": "whol_stln_rdmp_stcn",
    "stln_rmnd_stcn": "whol_stln_rmnd_stcn", "stln_rmnd_amt": "whol_stln_rmnd_amt",
    "stln_rmnd_rate": "whol_stln_rmnd_rate", "stln_gvrt": "whol_stln_gvrt",
}
_OVTM_COLS = {
    "ovtm_close": "ovtm_untp_prpr", "ovtm_vol": "ovtm_untp_vol",
    "ovtm_tr_pbmn": "ovtm_untp_tr_pbmn", "ovtm_ctrt": "ovtm_untp_prdy_ctrt",
    "reg_close": "stck_clpr",
}

# (테이블, 컬럼맵, **날짜 필드명**) — 🔑 신용잔고만 `deal_date` 다. 하드코딩하면 조용히 0행이 된다.
KINDS = {
    "short":   ("short_sale_daily", _SHORT_COLS, "stck_bsop_date"),
    "program": ("program_trade_daily", _PROG_COLS, "stck_bsop_date"),
    "credit":  ("credit_balance_daily", _CREDIT_COLS, "deal_date"),
    "ovtm":    ("overtime_daily", _OVTM_COLS, "stck_bsop_date"),
}


def _fetch(kind: str, code: str, d1: str, d2: str):
    """kind 별 공급 함수 호출 (재시도 포함)."""
    if kind == "short":
        return with_retry(get_short_sale_daily, code, d1, d2, what=f"short {code}")
    if kind == "program":
        return with_retry(get_program_trade_daily, code, d2, what=f"program {code}")
    if kind == "credit":
        return with_retry(get_credit_balance_daily, code, d2, what=f"credit {code}")
    return with_retry(get_overtime_daily, code, what=f"ovtm {code}")


def _num(v):
    try:
        s = str(v).strip().replace(",", "")
        return float(s) if s not in ("", "-", "+") else None
    except (TypeError, ValueError):
        return None


def upsert_sql(table: str, cols: dict) -> str:
    names = ["stock_code", "date", *cols.keys(), "raw"]
    ph = ", ".join(f"%({n})s" for n in names)
    upd = ", ".join(f"{n} = EXCLUDED.{n}" for n in [*cols.keys(), "raw"])
    return (f"INSERT INTO {table} ({', '.join(names)}) VALUES ({ph}) "
            f"ON CONFLICT (stock_code, date) DO UPDATE SET {upd}")


# ── EOD 파이프라인 진입점 ────────────────────────────────────────────────────
def _collect(kind: str, d1: str, d2: str) -> dict:
    """신선하면 건너뛴다. 사유를 결과에 남긴다 — 조용히 넘기지 않는다."""
    from api.kis_auth import auth

    from collectors.investor_trend_collector import is_stale

    table, colmap, datefld = KINDS[kind]
    sql = upsert_sql(table, colmap)
    conn = psycopg2.connect(**dsn())
    conn.autocommit = True
    try:
        stale, why = is_stale(conn, table)
        if not stale:
            logger.info(f"[{kind}] 신선 — 건너뜀 ({why})")
            return {"skipped": True, "reason": why}
        if not auth():
            return {"error": "KIS 인증 실패"}
        codes = universe(conn)
        ok = fail = rows = 0
        failed: list[str] = []
        for code in codes:
            df = _fetch(kind, code, d1, d2)
            n = 0
            if df is not None and not df.empty:
                with conn.cursor() as cur:
                    for _, r in df.iterrows():
                        ymd = str(r.get(datefld, "")).strip()
                        if len(ymd) != 8 or not ymd.isdigit():
                            continue
                        row = {"stock_code": code,
                               "date": f"{ymd[:4]}-{ymd[4:6]}-{ymd[6:]}",
                               "raw": Json(json.loads(r.to_json()))}
                        for dst, src in colmap.items():
                            row[dst] = _num(r.get(src))
                        cur.execute(sql, row)
                        n += 1
            if n:
                ok += 1
                rows += n
            else:
                fail += 1
                failed.append(code)
            time.sleep(CALL_INTERVAL)
        logger.info(f"[{kind}] 종목 {ok}/{len(codes)} · {rows:,}행 · 실패 {fail}")
        return {"codes": ok, "rows": rows, "failed": len(failed),
                "failed_codes": failed[:20], "trigger": why}
    finally:
        conn.close()


def collect_short_sale(trade_date: str = None) -> dict:
    """EOD 단계 — 공매도. 🟢 날짜 구간 TR 이라 과거 복구가 되므로 창을 넉넉히 잡는다."""
    from datetime import date as _date, timedelta as _td
    end = (trade_date or _date.today().strftime("%Y%m%d")).replace("-", "")
    start = (_date.today() - _td(days=60)).strftime("%Y%m%d")
    return _collect("short", start, end)


def collect_program_trade(trade_date: str = None) -> dict:
    """EOD 단계 — 프로그램매매. ⚠️ 30일 롤링이라 거른 날은 복구 불가."""
    from datetime import date as _date
    end = (trade_date or _date.today().strftime("%Y%m%d")).replace("-", "")
    return _collect("program", end, end)


def collect_credit_balance(trade_date: str = None) -> dict:
    """EOD 단계 — 신용잔고. ⚠️ 30일 롤링이라 거른 날은 복구 불가."""
    from datetime import date as _date
    end = (trade_date or _date.today().strftime("%Y%m%d")).replace("-", "")
    return _collect("credit", end, end)


def collect_overtime(trade_date: str = None) -> dict:
    """EOD 단계 — 시간외 단일가. ⚠️ 30일 롤링이라 거른 날은 복구 불가."""
    from datetime import date as _date
    end = (trade_date or _date.today().strftime("%Y%m%d")).replace("-", "")
    return _collect("ovtm", end, end)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--kind", choices=sorted(KINDS), required=True)
    ap.add_argument("--codes", help="쉼표 구분 종목코드")
    ap.add_argument("--all", action="store_true", help="유니버스 전체")
    ap.add_argument("--limit", type=int)
    ap.add_argument("--from", dest="d1", default="20260701", help="공매도 조회 시작일")
    ap.add_argument("--to", dest="d2", default="20260814", help="공매도 조회 종료일")
    a = ap.parse_args()

    from api.kis_auth import auth
    if not auth():
        print("🔴 KIS 인증 실패")
        return 2

    table, colmap, datefld = KINDS[a.kind]
    sql = upsert_sql(table, colmap)

    conn = psycopg2.connect(**dsn())
    conn.autocommit = True

    if a.codes:
        codes = [c.strip() for c in a.codes.split(",") if c.strip()]
    elif a.all:
        codes = universe(conn)
    else:
        print("🔴 --codes 또는 --all 이 필요하다")
        return 2
    if a.limit:
        codes = codes[:a.limit]

    print(f"[{a.kind}] 대상 {len(codes):,}종목 → {table}")
    ok = fail = rows_tot = 0
    failed_codes: list[str] = []
    for i, code in enumerate(codes, 1):
        # 🔴 여기서 kind 분기를 손으로 다시 쓰면 새 kind 가 조용히 «다른 데이터»로 흐른다.
        #    실측(2026-08-15): credit 이 program 공급 함수로 흘러 0행이 됐다. 날짜 필드가
        #    같았다면 프로그램매매 데이터가 credit 테이블에 들어갔을 것이다.
        #    ⇒ 분기는 `_fetch` 한 곳에만 둔다.
        df = _fetch(a.kind, code, a.d1, a.d2)
        if df is None or df.empty:
            fail += 1
            failed_codes.append(code)
        else:
            n = 0
            with conn.cursor() as cur:
                for _, r in df.iterrows():
                    ymd = str(r.get(datefld, "")).strip()
                    if len(ymd) != 8 or not ymd.isdigit():
                        continue
                    row = {"stock_code": code,
                           "date": f"{ymd[:4]}-{ymd[4:6]}-{ymd[6:]}",
                           "raw": Json(json.loads(r.to_json()))}
                    for dst, src in colmap.items():
                        row[dst] = _num(r.get(src))
                    cur.execute(sql, row)
                    n += 1
            rows_tot += n
            ok += 1 if n else 0
            if not n:
                fail += 1
                failed_codes.append(code)
        if i % 200 == 0:
            print(f"  {i:,}/{len(codes):,} · 성공 {ok:,} · 실패 {fail:,} · 행 {rows_tot:,}")
        time.sleep(CALL_INTERVAL)

    print(f"\n완료 — 종목 성공 {ok:,} / 실패 {fail:,} · upsert {rows_tot:,}행")
    if failed_codes:
        print(f"🔴 실패 종목 {len(failed_codes)}개 "
              f"(재시도: --kind {a.kind} --codes {','.join(failed_codes)})")
    conn.close()
    return 0 if not failed_codes else 1


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.exit(main())
