# -*- coding: utf-8 -*-
"""지정 종목·기간의 분봉을 KIS 에서 받아 `kis_template.minute_candles` 에 적재한다.

용도: 태쏘 매매일지 역추론에서 «장중 시각»이 필요해졌는데 DB 분봉이 7종목 중 3종목뿐이었다.
      일봉으로는 매수·매도가 «며칠»에 일어났는지까지만 가고, «몇 시»는 분봉이라야 나온다.

🔴 실측으로 확인한 함정 (2026-08-15)
   `inquire-time-dailychartprice` 는 `input_hour` 로부터 **뒤로 120봉**을 준다. 그래서
   이른 시각을 요청하면 응답이 **전날로 넘어간다**. 실측(199430, 20260728):

       end_hour=093000 → 20260727 **91행** + 20260728 29행
       end_hour=100000 → 20260727 61행 + 20260728 59행

   `get_full_trading_day_data` 는 구간을 2시간으로 잘라 `time` 으로만 거르므로 «우연히»
   안전하다(전날 오후 시각이 구간 밖). ***우연에 기대지 않기 위해 여기서는 날짜로 명시 필터한다.***

🔴 두 번째 함정: `get_full_trading_day_data` 는 데이터가 없으면 **최대 FALLBACK_MAX_DAYS 일
   이전 날짜로 조용히 폴백**한다. 요청 날짜와 응답 날짜를 대조하지 않으면 «다른 날 데이터»를
   그 날짜로 적재하게 된다. 아래 `_fetch_day` 가 그 대조를 강제한다.

안전장치:
  - 기존 행수보다 **적게** 받아오면 교체하지 않는다(부분 수신으로 좋은 데이터를 지우지 않는다).
  - `--dry-run` 으로 적재 없이 수신량만 확인한다.

실행 (봇이 안 도는 날에만 — 토큰 충돌 방지):
    python scripts/backfill_minute_for_codes.py --dry-run
    python scripts/backfill_minute_for_codes.py
"""
from __future__ import annotations

import argparse
import sys
from datetime import date, timedelta
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

import psycopg2  # noqa: E402

from config.constants import resolve_minute_source_db  # noqa: E402

# 태쏘 원장에서 등록일이 특정된 7건 — (종목코드, 등록일)
# 창은 [등록일 − PRE_DAYS 달력일, END_DATE]. 등록 «이전» 급등 구간도 봐야 하므로 앞을 연다.
TARGETS = [
    ("058610", "2026-07-31"),   # 에스피지
    ("304100", "2026-08-04"),   # 솔트룩스
    ("477850", "2026-08-05"),   # 마키나락스
    ("0039P0", "2026-08-06"),   # 매드업
    ("069540", "2026-08-05"),   # 빛과전자
    ("199430", "2026-07-28"),   # 케이엔알시스템
    ("413630", "2026-07-30"),   # 씨피시스템
]
PRE_DAYS = 7          # 등록일 이전 달력일
END_DATE = "2026-08-14"


def dsn() -> dict:
    # DB명은 하드코딩하지 않고 resolver 경유 (CLAUDE.md 데이터 소스 SSOT)
    return dict(host="127.0.0.1", port=5433, user="robotrader",
                password="1234", dbname=resolve_minute_source_db())


def _fetch_day(code: str, ymd: str):
    """그 날짜의 분봉만 돌려준다. 폴백·교차일은 여기서 잘라낸다."""
    from api.kis_chart_api import get_full_trading_day_data
    df = get_full_trading_day_data(code, ymd, "153000")
    if df is None or df.empty:
        return None
    if "date" not in df.columns:
        return None
    # 🔑 요청 날짜와 «다른» 날짜 행을 전부 버린다 — 폴백·교차일 양쪽을 한 번에 막는다.
    same = df[df["date"].astype(str) == ymd].copy()
    return same if not same.empty else None


def trading_days(conn, code: str, d0: str, d1: str) -> list[str]:
    """일봉이 있는 날 = 거래일. 휴장일에 API 를 때리지 않는다.

    ⚠️ `daily_prices.date` 는 **text**('YYYY-MM-DD')다 — `to_char` 를 쓰면 터진다.
       `minute_candles.date` 는 같은 text 인데 형식이 **'YYYYMMDD'** 로 달라서 변환이 필요하다.
    """
    with conn.cursor() as cur:
        cur.execute(
            "SELECT replace(date, '-', '') FROM daily_prices "
            "WHERE stock_code=%s AND date BETWEEN %s AND %s ORDER BY date",
            (code, d0, d1))
        return [r[0] for r in cur.fetchall()]


def existing_rows(conn, code: str, ymd: str) -> int:
    with conn.cursor() as cur:
        cur.execute("SELECT count(*) FROM minute_candles WHERE stock_code=%s AND date=%s",
                    (code, ymd))
        return cur.fetchone()[0]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true", help="적재하지 않고 수신량만 본다")
    ap.add_argument("--codes", help="쉼표 구분 종목코드 (기본: 위 TARGETS 7건)")
    ap.add_argument("--from", dest="d_from", help="시작일 YYYY-MM-DD (--codes 와 함께)")
    ap.add_argument("--to", dest="d_to", default=END_DATE, help="종료일 YYYY-MM-DD")
    ap.add_argument("--skip-complete", action="store_true",
                    help="이미 300행 이상 있는 (종목,날짜)는 API 호출 자체를 건너뛴다")
    args = ap.parse_args()

    # --codes 를 주면 (코드, 시작일) 쌍을 그 인자로 만든다.
    targets = ([(c.strip(), args.d_from) for c in args.codes.split(",") if c.strip()]
               if args.codes else TARGETS)
    pre_days = 0 if args.codes else PRE_DAYS   # --codes 는 시작일을 그대로 쓴다

    from api.kis_auth import auth
    from collectors.minute_writer import df_to_minute_rows, replace_minute_day

    if not auth():
        print("🔴 KIS 인증 실패")
        return 2

    conn = psycopg2.connect(**dsn())
    conn.autocommit = True
    tot_new = tot_skip = tot_fail = 0

    for code, reg in targets:
        d0 = (date.fromisoformat(reg) - timedelta(days=pre_days)).isoformat()
        days = trading_days(conn, code, d0, args.d_to)
        print(f"\n=== {code} · 창 {d0}~{args.d_to} · 거래일 {len(days)}일 ===")
        for ymd in days:
            before = existing_rows(conn, code, ymd)
            # 🔑 이미 온전한 날은 API 를 아예 안 때린다 — 유량과 시간을 아낀다.
            if args.skip_complete and before >= 300:
                continue
            df = _fetch_day(code, ymd)
            if df is None:
                print(f"  🔴 {ymd} 수신 실패/빈 응답 (기존 {before}행 유지)")
                tot_fail += 1
                continue
            got = len(df)
            # 🔑 부분 수신으로 좋은 데이터를 지우지 않는다.
            if before and got < before:
                print(f"  ⏭ {ymd} 수신 {got} < 기존 {before} ⇒ 교체하지 않음")
                tot_skip += 1
                continue
            rows = df_to_minute_rows(code, df)
            if args.dry_run:
                print(f"  · {ymd} 수신 {got}행 → 적재행 {len(rows)} (기존 {before}) [dry-run]")
                continue
            n = replace_minute_day(conn, code, ymd, rows)
            print(f"  ✅ {ymd} 적재 {n}행 (기존 {before} → 수신 {got})")
            tot_new += n

    print(f"\n적재 {tot_new:,}행 · 교체보류 {tot_skip} · 실패 {tot_fail}")
    conn.close()
    return 0


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.exit(main())
