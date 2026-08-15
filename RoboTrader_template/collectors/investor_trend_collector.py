# -*- coding: utf-8 -*-
"""종목별 일자별 투자자 매매동향 수집 → `investor_trend_daily`.

공급: KIS TR `FHKST01010900` (`api.kis_market_api.get_investor_trend_daily`).

🔴 **이 데이터는 놓치면 영영 못 채운다.** TR 이 «최근 30 거래일」만 주고 조회 시작일
   파라미터가 없다. 하루 안 돌리면 그 하루가 30일 뒤 영구 결손이 된다.
   ⇒ EOD 파이프라인에 붙이는 것이 정석이다(현재는 수동 실행).

왜 만들었나: 기존 수급 테이블 `foreign_flow` 는 **627 종목**뿐이고 외국인 «수량» 한 컬럼이라
   유니버스 백분위를 못 낸다. 태쏘 후보선정 역추론에서 특징 9개가 전부 가격·거래대금·변동성이고
   **수급 축이 통째로 빠져 있었다.**

실행:
    python -m collectors.investor_trend_collector --codes 199430,058610
    python -m collectors.investor_trend_collector --all            # 유니버스 전체
    python -m collectors.investor_trend_collector --all --limit 50 # 부분 시험
"""
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

import psycopg2  # noqa: E402

from api.kis_market_api import get_investor_trend_daily  # noqa: E402
from config.constants import resolve_daily_source_db  # noqa: E402
from utils.logger import setup_logger  # noqa: E402

logger = setup_logger(__name__)

# 의사티커 — 유니버스에서 제외 (지수를 종목으로 세면 백분위가 오염된다)
PSEUDO = ("KOSPI", "KOSDAQ", "KS11", "KQ11")

CALL_INTERVAL = 0.08     # 초. KIS 유량제한 여유분.

# 🔴 재시도는 선택이 아니다. 실측(2026-08-15): 유니버스 수집에서 공매도 3종목이 실패했는데
#    개별 재시도하니 **3/3 이 정상 32행**을 돌려줬다 — 일시 오류였다. 재시도가 없으면
#    ***일시 실패가 조용한 영구 결손이 된다***. 이 TR 들은 롤링 창이라 나중에 못 채운다.
RETRY = 3
RETRY_BACKOFF = 1.0      # 초. 시도마다 배로 늘린다.


def with_retry(fn, *args, what: str = "", **kwargs):
    """None/빈 결과를 실패로 보고 재시도한다. 마지막 시도까지 실패하면 None."""
    delay = RETRY_BACKOFF
    for attempt in range(1, RETRY + 1):
        try:
            r = fn(*args, **kwargs)
        except Exception as e:              # noqa: BLE001 - 어떤 예외든 재시도 대상
            logger.warning(f"[retry {attempt}/{RETRY}] {what} 예외: {e}")
            r = None
        if r is not None and not (hasattr(r, "empty") and r.empty):
            return r
        if attempt < RETRY:
            time.sleep(delay)
            delay *= 2
    return None

_UPSERT = """
INSERT INTO investor_trend_daily (
    stock_code, date, close, prdy_vrss,
    prsn_ntby_qty, frgn_ntby_qty, orgn_ntby_qty,
    prsn_ntby_tr_pbmn, frgn_ntby_tr_pbmn, orgn_ntby_tr_pbmn,
    prsn_shnu_vol, frgn_shnu_vol, orgn_shnu_vol,
    prsn_seln_vol, frgn_seln_vol, orgn_seln_vol)
VALUES (%(stock_code)s, %(date)s, %(close)s, %(prdy_vrss)s,
        %(prsn_ntby_qty)s, %(frgn_ntby_qty)s, %(orgn_ntby_qty)s,
        %(prsn_ntby_tr_pbmn)s, %(frgn_ntby_tr_pbmn)s, %(orgn_ntby_tr_pbmn)s,
        %(prsn_shnu_vol)s, %(frgn_shnu_vol)s, %(orgn_shnu_vol)s,
        %(prsn_seln_vol)s, %(frgn_seln_vol)s, %(orgn_seln_vol)s)
ON CONFLICT (stock_code, date) DO UPDATE SET
    close = EXCLUDED.close, prdy_vrss = EXCLUDED.prdy_vrss,
    prsn_ntby_qty = EXCLUDED.prsn_ntby_qty, frgn_ntby_qty = EXCLUDED.frgn_ntby_qty,
    orgn_ntby_qty = EXCLUDED.orgn_ntby_qty,
    prsn_ntby_tr_pbmn = EXCLUDED.prsn_ntby_tr_pbmn,
    frgn_ntby_tr_pbmn = EXCLUDED.frgn_ntby_tr_pbmn,
    orgn_ntby_tr_pbmn = EXCLUDED.orgn_ntby_tr_pbmn,
    prsn_shnu_vol = EXCLUDED.prsn_shnu_vol, frgn_shnu_vol = EXCLUDED.frgn_shnu_vol,
    orgn_shnu_vol = EXCLUDED.orgn_shnu_vol,
    prsn_seln_vol = EXCLUDED.prsn_seln_vol, frgn_seln_vol = EXCLUDED.frgn_seln_vol,
    orgn_seln_vol = EXCLUDED.orgn_seln_vol
"""

_INT_COLS = (
    "close", "prdy_vrss",
    "prsn_ntby_qty", "frgn_ntby_qty", "orgn_ntby_qty",
    "prsn_ntby_tr_pbmn", "frgn_ntby_tr_pbmn", "orgn_ntby_tr_pbmn",
    "prsn_shnu_vol", "frgn_shnu_vol", "orgn_shnu_vol",
    "prsn_seln_vol", "frgn_seln_vol", "orgn_seln_vol",
)
_SRC = {"close": "stck_clpr", "prdy_vrss": "prdy_vrss"}


def dsn() -> dict:
    return dict(host="127.0.0.1", port=5433, user="robotrader",
                password="1234", dbname=resolve_daily_source_db())


def _to_int(v):
    """KIS 는 수치를 문자열로 준다. 빈 값·부호만 있는 값은 None 으로."""
    try:
        s = str(v).strip().replace(",", "")
        return int(float(s)) if s not in ("", "-", "+") else None
    except (TypeError, ValueError):
        return None


def rows_from_df(code: str, df) -> list[dict]:
    out = []
    for _, r in df.iterrows():
        ymd = str(r.get("stck_bsop_date", "")).strip()
        if len(ymd) != 8 or not ymd.isdigit():
            continue                      # 형식 위반 행은 조용히 버리지 않고 건너뛴 뒤 아래서 센다
        row = {"stock_code": code, "date": f"{ymd[:4]}-{ymd[4:6]}-{ymd[6:]}"}
        for c in _INT_COLS:
            row[c] = _to_int(r.get(_SRC.get(c, c)))
        out.append(row)
    return out


def universe(conn, as_of: str = "2026-08-14") -> list[str]:
    with conn.cursor() as cur:
        cur.execute(
            "SELECT DISTINCT stock_code FROM daily_prices "
            "WHERE date=%s AND stock_code <> ALL(%s) ORDER BY stock_code",
            (as_of, list(PSEUDO)))
        return [r[0] for r in cur.fetchall()]


# ── EOD 파이프라인 진입점 ────────────────────────────────────────────────────
# 🔴 이 TR 은 **최근 30 거래일**만 준다. 하루 거른 게 30일 뒤 영구 결손이 되므로 EOD 에 붙인다.
#    다만 매일 2,763 종목을 때리면 EOD 시간·유량을 크게 먹는다 —
#    🔑 ***TR 이 30일치를 주므로 5일 간격이면 며칠 걸러도 결손이 안 난다.***
#    ⇒ 「마지막 적재일이 STALE_DAYS 이상 낡았을 때만」 돈다. 며칠 쉬어도 **자동 복구**된다.
STALE_DAYS = 5


def is_stale(conn, table: str, days: int = STALE_DAYS) -> tuple[bool, str]:
    from datetime import date as _date
    with conn.cursor() as cur:
        cur.execute(f"SELECT max(date) FROM {table}")  # noqa: S608 - 테이블명은 코드 상수
        m = cur.fetchone()[0]
    if m is None:
        return True, "비어 있음"
    gap = (_date.today() - m).days
    return gap >= days, f"최신 {m} · {gap}일 경과"


def collect_investor_trend(trade_date: str = None) -> dict:
    """EOD 단계. 신선하면 건너뛴다(결과 dict 에 사유를 남긴다 — 조용히 넘기지 않는다)."""
    from api.kis_auth import auth
    conn = psycopg2.connect(**dsn())
    conn.autocommit = True
    try:
        stale, why = is_stale(conn, "investor_trend_daily")
        if not stale:
            logger.info(f"[investor_trend] 신선 — 건너뜀 ({why})")
            return {"skipped": True, "reason": why}
        if not auth():
            return {"error": "KIS 인증 실패"}
        codes = universe(conn)
        ok = fail = rows = 0
        failed: list[str] = []
        for code in codes:
            df = with_retry(get_investor_trend_daily, code, what=f"investor {code}")
            r = rows_from_df(code, df) if df is not None and not df.empty else []
            if not r:
                fail += 1
                failed.append(code)
                continue
            with conn.cursor() as cur:
                for row in r:
                    cur.execute(_UPSERT, row)
            ok += 1
            rows += len(r)
            time.sleep(CALL_INTERVAL)
        logger.info(f"[investor_trend] 종목 {ok}/{len(codes)} · {rows:,}행 · 실패 {fail}")
        return {"codes": ok, "rows": rows, "failed": len(failed),
                "failed_codes": failed[:20], "trigger": why}
    finally:
        conn.close()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--codes", help="쉼표 구분 종목코드")
    ap.add_argument("--all", action="store_true", help="유니버스 전체")
    ap.add_argument("--limit", type=int, help="앞에서 N종목만 (시험용)")
    a = ap.parse_args()

    from api.kis_auth import auth
    if not auth():
        print("🔴 KIS 인증 실패")
        return 2

    conn = psycopg2.connect(**dsn())
    conn.autocommit = True

    if a.codes:
        codes = [c.strip() for c in a.codes.split(",") if c.strip()]
    elif a.all:
        codes = universe(conn)
    else:
        print("🔴 --codes 또는 --all 중 하나가 필요하다")
        return 2
    if a.limit:
        codes = codes[:a.limit]

    print(f"대상 {len(codes):,}종목")
    ok = fail = 0
    total_rows = 0
    failed_codes = []
    for i, code in enumerate(codes, 1):
        df = with_retry(get_investor_trend_daily, code, what=f"investor {code}")
        if df is None or df.empty:
            fail += 1
            failed_codes.append(code)
        else:
            rows = rows_from_df(code, df)
            if rows:
                with conn.cursor() as cur:
                    for r in rows:
                        cur.execute(_UPSERT, r)
                total_rows += len(rows)
                ok += 1
            else:
                fail += 1
                failed_codes.append(code)
        if i % 200 == 0:
            print(f"  {i:,}/{len(codes):,} · 성공 {ok:,} · 실패 {fail:,} · 행 {total_rows:,}")
        time.sleep(CALL_INTERVAL)

    print(f"\n완료 — 종목 성공 {ok:,} / 실패 {fail:,} · 적재(upsert) {total_rows:,}행")
    if failed_codes:
        # 🔴 실패를 요약 숫자로만 남기면 아무도 안 본다. 코드를 찍어 재시도가 가능하게 한다.
        print(f"🔴 실패 종목 {len(failed_codes)}개 (재시도: --codes {','.join(failed_codes)})")
    conn.close()
    return 0 if not failed_codes else 1


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.exit(main())
