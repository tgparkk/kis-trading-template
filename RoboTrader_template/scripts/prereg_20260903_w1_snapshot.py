# -*- coding: utf-8 -*-
"""(E′) 배포 전/후 판정용 **읽기 전용** 스냅샷 — 사전등록 §5-① (a)~(f).

사양: docs/prereg_2026-09-03_write_path_rawprice_upsert.md
  · §4 판정식 J1·J2·J5·J6·J7 의 «기준선»을 뜬다.
  · §6-23 — 쓰기 경로의 효과를 «그 경로가 돈 뒤»의 스냅샷으로 재지 않는다.
    ⇒ 🔴 **반드시 W1 이 도는 07:40 «전»에 돌린다**(장 마감 후 EOD 완료 뒤가 가장 안전).

이 스크립트는 SELECT 만 한다 — 세션을 `READ ONLY` 로 고정하고, 실패하면 그 사실을
출력한다. DB 에 한 줄도 쓰지 않는다. KIS API 도 부르지 않는다(토큰 캐시 무관).

    cd <라이브 트리>
    python scripts/prereg_20260903_w1_snapshot.py                       # (b)(d)(f)
    python scripts/prereg_20260903_w1_snapshot.py --targets 001210,900300,950220
    python scripts/prereg_20260903_w1_snapshot.py --targets-file logs/t1_targets.txt
    python scripts/prereg_20260903_w1_snapshot.py --asof 2026-09-03 --out-dir <경로>

산출물(기본 `<repo>/scratchpad/prereg_20260903_eprime/<asof>_<HHMMSS>/`):
  a_targets_ohlcv_md5.tsv       J1 기준선 (§5-①-(a)) — `--targets` 를 준 경우만
  b_window_convention_gap.tsv   J6 기준선 (§5-①-(b))
  c_targets_window_rowcount.tsv J5 기준선 (§5-①-(c)) — `--targets` 를 준 경우만
  d_j7_w2_exposure.tsv          J7 기준선 (§5-①-(d))
  f_pre_w1_window_snapshot.tsv  🔴 W1 «직전» 전 종목 창 스냅샷 (§5-①-(f))
  manifest.json                 asof·창·DB·행수·파일 sha256·실행 SQL 전문

🔑 (f) 가 J2 의 분해를 가능하게 한다 — W1 이 돈 «뒤» 같은 쿼리를 다시 떠서
   종목별로 비교하면 「행이 있었는데 md5 가 바뀜」 = UPDATE, 「없던 행이 생김」
   = INSERT 다. W1 대상 명단은 07:40 전에는 알 수 없으므로 (f) 는 «전 종목»을 뜬다.
🔴 산출물을 세션 Temp 스크래치에 두지 말 것(§5-① · 2026-08-30 산출물 소실 사고).
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import datetime, timedelta
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

EXIT_OK = 0
EXIT_INPUT = 5      # 실행 전제가 안 갖춰졌다(대상 DB 불일치 등)

# 창 = [asof - 150 캘린더일, asof] — §1-0 기호 정의(W1 이 한 번에 덮어쓰는 구간).
WINDOW_CALENDAR_DAYS = 150

# --- SQL (사전등록 §5-① 인쇄본 그대로. 문자열을 고치면 판정이 갈린다) ------------

SQL_A_TARGETS_HASH = """
SELECT stock_code, count(*) AS n,
       md5(string_agg(date||':'||open||':'||high||':'||low||':'||close||':'||volume,
                      ',' ORDER BY date)) AS ohlcv_md5
  FROM daily_prices WHERE stock_code = ANY(%(targets)s) AND date <= %(asof)s
 GROUP BY 1 ORDER BY 1
"""

SQL_B_WINDOW_GAP = """
SELECT count(DISTINCT stock_code) AS codes, count(*) AS rows
  FROM daily_prices
 WHERE date >= %(win_start)s
   AND adj_factor IS NOT NULL AND adj_factor <> 1
"""

SQL_C_TARGETS_WINDOW_ROWS = """
SELECT stock_code, count(*) AS n_rows FROM daily_prices
 WHERE stock_code = ANY(%(targets)s) AND date >= %(win_start)s
 GROUP BY 1 ORDER BY 1
"""

# J7 — W 중 E_j 가 «최근 7 거래일(양끝 포함)» 안인 종목. 경계는 >= 다(§4-1 J7).
SQL_D_J7 = """
WITH b AS (SELECT stock_code, date, close, volume,
                  ROW_NUMBER() OVER (PARTITION BY stock_code ORDER BY date) AS rn
             FROM daily_prices WHERE stock_code ~ '^[0-9]{6}$'),
g AS (SELECT b.*, rn - ROW_NUMBER() OVER (PARTITION BY stock_code,(volume=0) ORDER BY date) AS grp FROM b),
r AS (SELECT stock_code, date, close,
             CASE WHEN volume=0
                  THEN ROW_NUMBER() OVER (PARTITION BY stock_code,(volume=0),grp ORDER BY date)
                  ELSE 0 END AS zrun
        FROM g),
p AS (SELECT stock_code, date, close,
             LAG(close) OVER (PARTITION BY stock_code ORDER BY date) AS prev_close,
             LAG(zrun)  OVER (PARTITION BY stock_code ORDER BY date) AS halt_run
        FROM r),
be AS (SELECT stock_code, date, halt_run, close/prev_close AS ratio
         FROM p WHERE date >= '2024-01-01' AND date <= %(asof)s
           AND close > 0 AND prev_close > 0
           AND (close/prev_close > 1.45 OR close/prev_close < 0.69)),
J  AS (SELECT DISTINCT stock_code FROM be WHERE ratio > 1.45 AND halt_run >= 9),
X1 AS (SELECT DISTINCT stock_code FROM be WHERE halt_run < 3),
W  AS (SELECT stock_code FROM J
        EXCEPT SELECT stock_code FROM X1
        EXCEPT SELECT unnest(ARRAY['010120','003350','058430','001510'])
        EXCEPT SELECT unnest(ARRAY['005930','012210','336060','355150'])
        EXCEPT SELECT unnest(ARRAY['001530','006040','036630','053950','086520',
                                   '355150','260970','380540'])),
EJ  AS (SELECT stock_code, max(date) AS e_j FROM be
         WHERE ratio > 1.45 AND halt_run >= 9 GROUP BY stock_code),
W7D AS (SELECT min(d) AS w2_start FROM (
          SELECT DISTINCT date AS d FROM daily_prices
           WHERE date <= %(asof)s ORDER BY d DESC LIMIT 7) z)
SELECT w.stock_code, e.e_j, W7D.w2_start
  FROM W w JOIN EJ e USING (stock_code), W7D
 WHERE e.e_j >= W7D.w2_start
 ORDER BY e.e_j, w.stock_code
"""

# (f) W1 직전 «전 종목» 창 스냅샷. n_null_close 는 md5 가 NULL 행을 조용히
#     빠뜨리는 성질(string_agg 는 NULL 입력을 건너뛴다)을 보이게 하려고 같이 뜬다.
SQL_F_PRE_W1 = """
SELECT stock_code,
       count(*) AS n_rows,
       min(date) AS min_date,
       max(date) AS max_date,
       count(*) FILTER (WHERE close IS NULL) AS n_null_close,
       md5(string_agg(date||':'||open||':'||high||':'||low||':'||close||':'||volume,
                      ',' ORDER BY date)) AS ohlcv_md5
  FROM daily_prices
 WHERE date >= %(win_start)s AND date <= %(asof)s
 GROUP BY 1 ORDER BY 1
"""


def _write_tsv(path: Path, header, rows) -> int:
    with path.open("w", encoding="utf-8", newline="\n") as f:
        f.write("\t".join(header) + "\n")
        for r in rows:
            f.write("\t".join("" if v is None else str(v) for v in r) + "\n")
    return len(rows)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _query(conn, sql, params):
    with conn.cursor() as cur:
        cur.execute(sql, params)
        cols = [d[0] for d in cur.description]
        return cols, cur.fetchall()


def _resolve_targets(a) -> list:
    if a.targets_file:
        p = Path(a.targets_file)
        if not p.is_absolute():
            p = REPO / p
        if not p.exists():
            print(f"🔴 대상 파일이 없다: {p}")
            return None
        codes = [ln.strip() for ln in p.read_text(encoding="utf-8").splitlines()]
        return [c for c in codes if c and not c.startswith("#")]
    if a.targets:
        return [c.strip() for c in a.targets.split(",") if c.strip()]
    return []


def main() -> int:
    ap = argparse.ArgumentParser(
        description="(E′) 판정 기준선 스냅샷 — 읽기 전용. W1(07:40) «전»에 실행할 것.")
    ap.add_argument("--targets", default=None, help="쉼표 구분 종목코드 ((a)·(c) 용)")
    ap.add_argument("--targets-file", default=None, help="한 줄에 한 종목코드")
    ap.add_argument("--asof", default=None, help="기준일 YYYY-MM-DD (기본: KST 오늘)")
    ap.add_argument("--out-dir", default=None,
                    help="산출물 경로 (기본: <repo>/scratchpad/prereg_20260903_eprime/…)")
    a = ap.parse_args()

    from utils.korean_time import now_kst
    from config.constants import resolve_daily_source_db
    from db.kis_db_connection import KisDbConnection

    run_at = now_kst()
    asof = a.asof or run_at.strftime("%Y-%m-%d")
    win_start = (datetime.strptime(asof, "%Y-%m-%d")
                 - timedelta(days=WINDOW_CALENDAR_DAYS)).strftime("%Y-%m-%d")

    targets = _resolve_targets(a)
    if targets is None:
        return EXIT_INPUT

    # 🔑 DB 접속은 프로젝트 표준 경로로만 한다 — DSN 하드코딩 금지.
    #    읽는 DB 가 W1 이 «쓰는» DB 와 다르면 이 스냅샷은 다른 세계를 잰다 ⇒ fail-closed.
    import os
    cfg = KisDbConnection.get_config()
    want = resolve_daily_source_db()
    if cfg["database"] != want:
        print(f"🔴 대상 DB 불일치 — KIS_DB_NAME={cfg['database']} 인데 resolver 는 {want}. 중단.")
        return EXIT_INPUT
    ts_db = os.getenv("TIMESCALE_DB")
    if ts_db and ts_db != want:
        print(f"🔴 W1 의 «쓰기» DB 와 다르다 — TIMESCALE_DB={ts_db}, 여기서 읽는 DB={want}. 중단.")
        return EXIT_INPUT

    out_dir = Path(a.out_dir) if a.out_dir else (
        REPO / "scratchpad" / "prereg_20260903_eprime" / f"{asof}_{run_at.strftime('%H%M%S')}")
    out_dir.mkdir(parents=True, exist_ok=True)

    params = {"targets": targets, "asof": asof, "win_start": win_start}
    files = {}
    counts = {}

    try:
        with KisDbConnection.get_connection() as conn:
            conn.rollback()
            try:
                conn.set_session(readonly=True)
                ro = True
            except Exception as e:  # noqa: BLE001 — 실패를 «조용히» 넘기지 않는다
                ro = False
                print(f"⚠️ 세션 READ ONLY 설정 실패({e}) — 쿼리는 전부 SELECT 이지만 "
                      f"「읽기 전용이 강제됐다」고 기록하지 않는다.")

            if targets:
                cols, rows = _query(conn, SQL_A_TARGETS_HASH, params)
                counts["a_rows"] = _write_tsv(out_dir / "a_targets_ohlcv_md5.tsv", cols, rows)
                files["a_targets_ohlcv_md5.tsv"] = SQL_A_TARGETS_HASH

                cols, rows = _query(conn, SQL_C_TARGETS_WINDOW_ROWS, params)
                counts["c_rows"] = _write_tsv(out_dir / "c_targets_window_rowcount.tsv", cols, rows)
                files["c_targets_window_rowcount.tsv"] = SQL_C_TARGETS_WINDOW_ROWS
            else:
                print("ℹ️ --targets 미지정 — (a)·(c) 는 건너뛴다(③ 배치 대상이 정해지면 다시 뜰 것).")

            cols, rows = _query(conn, SQL_B_WINDOW_GAP, params)
            counts["b_rows"] = _write_tsv(out_dir / "b_window_convention_gap.tsv", cols, rows)
            files["b_window_convention_gap.tsv"] = SQL_B_WINDOW_GAP
            b_codes, b_rowcnt = (rows[0][0], rows[0][1]) if rows else (0, 0)

            cols, rows = _query(conn, SQL_D_J7, params)
            counts["d_rows"] = _write_tsv(out_dir / "d_j7_w2_exposure.tsv", cols, rows)
            files["d_j7_w2_exposure.tsv"] = SQL_D_J7
            j7 = len(rows)
            w2_start = rows[0][2] if rows else None

            cols, rows = _query(conn, SQL_F_PRE_W1, params)
            counts["f_rows"] = _write_tsv(out_dir / "f_pre_w1_window_snapshot.tsv", cols, rows)
            files["f_pre_w1_window_snapshot.tsv"] = SQL_F_PRE_W1
            f_codes = len(rows)
    finally:
        KisDbConnection.close_all()

    manifest = {
        "prereg": "docs/prereg_2026-09-03_write_path_rawprice_upsert.md (§5-①)",
        "run_at_kst": run_at.strftime("%Y-%m-%d %H:%M:%S%z"),
        "asof": asof,
        "window": {"calendar_days": WINDOW_CALENDAR_DAYS, "start": win_start, "end": asof},
        "db": {k: v for k, v in cfg.items() if k != "password"},
        "session_read_only": ro,
        "targets": targets,
        "counts": counts,
        "sha256": {p.name: _sha256(p) for p in sorted(out_dir.glob("*.tsv"))},
        "sql": files,
    }
    (out_dir / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"\n스냅샷 완료 → {out_dir}")
    print(f"  (b) J6 기준선  : 창 안 adj_factor∉{{NULL,1}} — {b_codes}종목 / {b_rowcnt}행")
    print(f"  (d) J7 기준선  : W 중 E_j 가 최근 7 거래일(>= {w2_start}) 안 — {j7}종목")
    print(f"  (f) W1 직전    : 창 [{win_start} ~ {asof}] 안 {f_codes}종목 스냅샷")
    if targets:
        print(f"  (a)/(c)        : 대상 {len(targets)}종목")
    print("🔴 W1 이 돈 «뒤» 같은 명령을 --asof 그대로 다시 돌려 (f) 를 종목별로 비교할 것 "
          "— md5 변경 = UPDATE · 행수 증가 = INSERT (§4-1 J2).")
    return EXIT_OK


if __name__ == "__main__":
    # Windows 콘솔 기본 cp949 에서 요약 출력이 UnicodeEncodeError 로 죽지 않게 한다
    # (scripts/backfill_daily_for_codes.py:88 과 같은 규약).
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    raise SystemExit(main())
