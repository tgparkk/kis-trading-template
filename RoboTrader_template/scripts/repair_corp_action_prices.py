# -*- coding: utf-8 -*-
"""기업행위 가격 보정 — 큐 + 큐 밖 6종목을 KIS 수정주가로 고친다.

사양: docs/superpowers/specs/2026-08-20-corp-action-price-repair-design.md

🔴 기본은 dry-run 이다. `--apply` 를 줘야 쓴다. 백업 없이는 한 행도 안 고친다.
🔴 **라이브 봇과 «같은 작업 디렉터리»에서 실행할 것** — `api/kis_auth.py:32` 가
   토큰 캐시 경로를 `os.getcwd()` 로 만든다. 다른 디렉터리에서 돌리면 캐시를 못 찾아
   **새 토큰을 발급**받고, 브로커가 **라이브 봇의 기존 토큰을 무효화**한다(사양 §8-6).

    cd <라이브 트리>
    python scripts/repair_corp_action_prices.py --limit 1              # dry-run
    python scripts/repair_corp_action_prices.py --limit 1 --apply
    python scripts/repair_corp_action_prices.py --restore <BATCH_ID>
"""
from __future__ import annotations

import argparse
import sys
from datetime import date, datetime
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

HIST0, TODAY = "20210101", date.today().strftime("%Y%m%d")

# 종료코드 — 0 이 아닌 값은 「사람이 봐야 한다」는 뜻이다.
EXIT_OK = 0
EXIT_AUTH = 2       # KIS 인증 실패
EXIT_ABORT = 3      # 안전 게이트 작동(사양 §6-3 — 실행 전체를 멈춘다)
EXIT_FETCH = 4      # 브로커 조회 «실패» 종목이 있었다(= 미완료 실행)
EXIT_INPUT = 5      # 실행 전제가 안 갖춰졌다(큐 파일 없음·DB 대상 불일치)


class FeedFetchError(RuntimeError):
    """브로커 조회 «실패». 🔑 「데이터가 없다」와 «절대» 같은 값으로 보고하지 않는다.

    이 저장소가 바로 이 형태로 데였다 — provider 가 예외를 삼키고 `[]` 를 돌려줘
    DB 장애가 「조건에 맞는 종목 없음」(정상)으로 보고됐다
    (`changelog-2026-08-19-screener-provider-fail-closed.md`). 여기서 `df is None`
    (요청 실패)과 `df.empty`(정말 데이터가 없음)를 같은 `[]` 로 접으면 **브로커 장애가
    조용한 SKIP + 종료코드 0** 이 된다. 그래서 실패는 예외로 «튀어나가게» 둔다.
    """


def _kis_fetcher(code, start, end, adj_prc):
    """KIS 두 피드 어댑터. 실패는 예외, 「데이터 없음」은 빈 리스트.

    `get_inquire_daily_itemchartprice_extended` 는 **첫 호출이 실패했을 때만** `None`
    을 돌려준다(`api/kis_market_api.py:215-219`). 즉 `None` = 요청 실패이고,
    빈 DataFrame = 정상 응답인데 봉이 없음이다. 둘은 다른 사건이다.
    """
    from api import kis_market_api
    df = kis_market_api.get_inquire_daily_itemchartprice_extended(
        div_code="J", itm_no=code, inqr_strt_dt=start, inqr_end_dt=end,
        period_code="D", adj_prc=adj_prc, max_count=2000)
    if df is None:
        raise FeedFetchError(
            f"{code} adj_prc={adj_prc} 조회 실패 — 브로커/네트워크 장애이지 "
            f"「데이터 없음」이 아니다")
    if df.empty:
        return []
    return [dict(r) for _, r in df.iterrows()]


def _db_rows(conn, code):
    with conn.cursor() as cur:
        cur.execute(
            "SELECT date, open, high, low, close, volume, adj_factor "
            "FROM daily_prices WHERE stock_code=%s ORDER BY date", (code,))
        return {d: (o, h, l, c, v, f) for d, o, h, l, c, v, f in cur.fetchall()}


def has_split_event(conn, code) -> bool:
    """`corp_events` 에 `split_factor` 를 가진 split 이벤트가 있나 — **읽기 전용**.

    🔴 있으면 이 종목의 `adj_factor` 는 **다음 EOD 에 통째로 덮어써진다.**
    `collectors/daily_collector.py:102` 가 매일 `update_adj_factors(conn)` 를 부르고,
    그 경로(`collectors/daily_adj.py`)는 split 이벤트가 있는 종목의 **모든 날짜**
    `adj_factor` 를 이벤트 기준으로 «다시 쓴다»(1.0 포함). 지금 DB 에 있는 틀린 계수가
    나온 곳이 바로 거기다. ⇒ 그 종목에 대해 **지속되는 것은 OHLC 보정뿐**이다.
    술어는 `daily_adj.load_split_events` 의 WHERE 절과 동일하게 맞춘다.
    """
    with conn.cursor() as cur:
        cur.execute(
            "SELECT 1 FROM corp_events "
            "WHERE stock_code = %s AND event_type = 'split' "
            "  AND meta->>'split_factor' IS NOT NULL LIMIT 1", (code,))
        return cur.fetchone() is not None


def _close_seq(rows):
    """`(date, close)` 오름차순 시퀀스 — `close` 가 NULL 이거나 0 이하인 행은 뺀다.

    🔴 `close` NULL 은 실제로 나올 수 있다(무결성 결손 이력 있음). `float(None)` 은
    TypeError 로 죽고, 그러면 그 전까지 커밋된 종목들만 남긴 채 요약도 없이 죽는다.
    뺀 행에 0 이나 기본값을 채우지 않는다 — `count_impossible` 은 이미 `prev > 0` 을
    가정하므로 «빼는 것» 이 그 계약과 맞다.
    """
    out = []
    for d, v in rows.items():
        c = v[3]
        if c is None:
            continue
        c = float(c)
        if c <= 0:
            continue
        out.append((d, c))
    return sorted(out)


UPSERT = """
INSERT INTO daily_prices (stock_code, date, open, high, low, close, volume, adj_factor, updated_at)
VALUES (%(stock_code)s, %(date)s, %(open)s, %(high)s, %(low)s, %(close)s,
        %(volume)s, %(adj_factor)s, now())
ON CONFLICT (stock_code, date) DO UPDATE SET
    open=EXCLUDED.open, high=EXCLUDED.high, low=EXCLUDED.low, close=EXCLUDED.close,
    volume=EXCLUDED.volume, adj_factor=EXCLUDED.adj_factor, updated_at=now()
"""


def _abort(batch_id: str, code: str, n_committed: int, reason: str) -> int:
    """중단 — «커밋된 적 없는 트랜잭션」에 `conn.rollback()` 을 걸지 않는다.

    이 스크립트는 종목마다 개별 커밋한다(각 종목 루프 끝에서 `conn.commit()`).
    여기 도달했을 때 «이번» 종목은 UPDATE 를 실행한 적이 없으므로 되돌릴 것이 없고,
    «이전» 종목들은 이미 커밋돼 롤백으로 안 지워진다. `conn.rollback()` 을 부르는
    것은 아무것도 안 하면서 「되돌렸다」는 착각만 준다 — 그래서 안 부른다.
    """
    print(f"    ABORT — {code}: {reason}")
    if n_committed:
        print(f"    이전 {n_committed}개 종목은 이미 DB 에 커밋됐다(이번 실행으로는 안 지워진다). "
              f"되돌리려면: python scripts/repair_corp_action_prices.py --restore {batch_id}")
    else:
        print("    이번 실행에서 커밋된 종목 없음 — DB 는 안 바뀌었다.")
    return EXIT_ABORT


def _resolve_targets(a, R):
    """처리 대상 종목코드. 전제가 안 갖춰졌으면 `None` (= 조용히 진행하지 않는다).

    🔴 큐 파일이 없을 때 «조용히» `[]` 로 떨어지면, 하드코딩된 큐 밖 종목만 처리하고서
    「정상 완료」라고 말한다 — 큐 243건이 사라진 걸 아무도 모른다. 큐는 gitignore 된
    «라이브 트리» 산출물이라 워크트리에서 돌리면 «항상» 이 상황이다.
    """
    if a.codes:
        return [c.strip() for c in a.codes.split(",") if c.strip()]

    qp = REPO / "logs" / "corp_action_refetch_queue.jsonl"
    if not qp.exists():
        print(f"🔴 큐 파일이 없다: {qp}")
        print("   이 파일은 gitignore 된 «라이브 트리» 산출물이다 — 워크트리·클린 체크아웃엔 없다.")
        print("   그대로 진행하면 큐 243건을 조용히 건너뛰고 하드코딩 종목만 처리하게 된다.")
        print("   → 라이브 트리에서 실행하거나, 대상을 --codes 로 «명시»할 것.")
        return None
    lines = qp.read_text(encoding="utf-8").splitlines()
    return R.load_targets(lines, date.today().isoformat())


def _run(a, conn) -> int:
    from collectors import adj_repair as R
    from db import adj_backup as B

    if a.restore:
        B.ensure_table(conn)
        n = B.restore_batch(conn, a.restore)
        print(f"restored {n} rows from batch {a.restore}")
        return EXIT_OK

    targets = _resolve_targets(a, R)
    if targets is None:
        return EXIT_INPUT

    from api.kis_auth import auth
    if not auth():
        print("KIS auth failed")
        return EXIT_AUTH

    if a.limit is not None:
        targets = targets[:a.limit]

    batch_id = ("repair-" + datetime.now().strftime("%Y%m%d-%H%M%S")
                + ("-apply" if a.apply else "-dry"))
    if a.apply:
        B.ensure_table(conn)

    tot_before = tot_after = tot_rows = n_committed = 0
    tot_backed = n_fetch_err = n_volatile = 0
    for i, code in enumerate(targets, 1):
        # 🔧 직전 종목이 남긴 «읽기 전용» 트랜잭션을 닫는다. 안 닫으면 연결이
        #    idle in transaction 으로 몇 시간 남아 라이브 표의 VACUUM 을 막는다.
        conn.rollback()

        tag = f"[{i}/{len(targets)}] {code}"
        if has_split_event(conn, code):
            n_volatile += 1
            print(f"{tag} ⚠️ corp_events 에 split 이벤트가 있다 — 이 종목의 adj_factor 는")
            print("      «다음 EOD»에 update_adj_factors 가 전부 덮어쓴다"
                  " (daily_collector.py:102 → daily_adj.py).")
            print("      ⇒ 지속되는 것은 OHLC 보정뿐이다. 계수를 영구히 고치려면 틀린"
                  " corp_events 행을 고쳐야 한다(별도 승인 · 사양 §7).")

        try:
            raw, adj = R.fetch_both(code, HIST0, TODAY, _kis_fetcher)
        except FeedFetchError as e:
            n_fetch_err += 1
            print(f"{tag} ERROR — 피드 조회 «실패»: {e}")
            continue

        factors, diag = R.derive_factors(raw, adj)
        if not factors:
            print(f"{tag} SKIP — 계수 산출 0건 (diag {diag})")
            continue
        new_rows = R.build_repair_rows(code, raw, adj, factors)
        db = _db_rows(conn, code)
        todo = R.needs_repair(db, new_rows)
        n_absent = sum(1 for r in new_rows if r["date"] not in db)

        before = R.count_impossible(_close_seq(db))
        merged = dict(db)
        for r in todo:
            merged[r["date"]] = (r["open"], r["high"], r["low"], r["close"],
                                 r["volume"], r["adj_factor"])
        after = R.count_impossible(_close_seq(merged))
        tot_before += before
        tot_after += after
        tot_rows += len(todo)

        # 사양 §6-4 — volume 은 «불변»이어야 한다(기존도 원본, 새것도 adj_prc="1" 원본).
        # NULL 도 「바뀜」으로 센다: 전제를 «검증할 수 없다»를 「이상 없음」으로 접지 않는다.
        vol_diff = sum(1 for r in todo
                       if db[r["date"]][4] is not None
                       and int(db[r["date"]][4]) != int(r["volume"]))
        vol_null = sum(1 for r in todo if db[r["date"]][4] is None)

        print(f"{tag} rows={len(todo)} impossible {before}->{after} "
              f"derived={diag['n_derived']} filled={diag['n_filled']} "
              f"DB에 없는 날짜 {n_absent}건 제외")
        if vol_diff or vol_null:
            print(f"    🔴 volume 불변 전제 위반 — 값이 바뀌는 행 {vol_diff}건 · "
                  f"기존이 NULL 인 행 {vol_null}건")

        if not a.apply or not todo:
            continue

        if after > before:
            return _abort(batch_id, code, n_committed,
                          f"불가능봉이 늘었다({before}->{after}) — 이 종목은 쓰지 않았다")
        if vol_diff or vol_null:
            return _abort(batch_id, code, n_committed,
                          f"volume 이 바뀐다(값 변경 {vol_diff}건 · 기존 NULL {vol_null}건) — "
                          f"「기존도 원본, 새것도 원본」이라는 전제가 틀렸다는 뜻이다"
                          f"(사양 §6-4). 이 종목은 쓰지 않았다")

        # 🔴 UPSERT 가 «INSERT» 를 하면 --restore 로 못 되돌린다(복원 SQL 은
        #    UPDATE ... FROM backup 이라 행을 «지울» 수 없다). needs_repair 가 DB 에
        #    없는 날짜를 이미 뺐지만, 쓰기 직전에 한 번 더 확인한다 — 이 성질이
        #    깨지면 롤백 가능성 자체가 깨지므로 계약을 호출부에서도 못 박는다.
        absent = [r["date"] for r in todo if r["date"] not in db]
        if absent:
            return _abort(batch_id, code, n_committed,
                          f"보정 대상에 DB 에 없는 날짜가 {len(absent)}건 섞였다"
                          f"(예: {absent[:3]}) — INSERT 는 --restore 로 못 되돌린다. "
                          f"이 종목은 쓰지 않았다")

        # 🔴 백업이 실제로 몇 행 들어갔는지 확인한 뒤에만 UPSERT 한다.
        #    todo 는 «전부» DB 에 이미 있는 날짜이므로 기댓값은 정확히 len(todo) 다.
        #    부등호(<)가 아니라 «등호»로 본다 — 많아도 적어도 전제가 깨진 것이다.
        n_backed = B.backup_rows(conn, code, [r["date"] for r in todo], batch_id)
        if n_backed != len(todo):
            return _abort(batch_id, code, n_committed,
                          f"백업 확인 실패 — 기대 {len(todo)}건, 실제 {n_backed}건. "
                          f"이 종목은 쓰지 않았다")
        tot_backed += n_backed
        with conn.cursor() as cur:
            for r in todo:
                cur.execute(UPSERT, r)
        conn.commit()
        n_committed += 1

    conn.rollback()   # 마지막 종목의 읽기 트랜잭션을 닫는다

    print(f"\nbatch {batch_id} · rows {tot_rows} · impossible {tot_before} -> {tot_after}")
    if n_volatile:
        print(f"⚠️ split 이벤트 보유 {n_volatile}종목 — 그 종목의 adj_factor 는 다음 EOD 에 "
              f"덮어써진다(사양 §7). OHLC 보정만 지속된다.")
    if n_fetch_err:
        print(f"🔴 피드 조회 «실패» {n_fetch_err}종목 — 「데이터 없음」이 아니라 «못 받았다». "
              f"이 실행은 «미완료»다. 원인 확인 후 재실행할 것.")
    if tot_backed:
        print(f"백업 {tot_backed}행 · rollback: "
              f"python scripts/repair_corp_action_prices.py --restore {batch_id}")
    else:
        print("백업된 행이 없다 — 되돌릴 것도 없다(--restore 할 대상이 없다).")
    return EXIT_FETCH if n_fetch_err else EXIT_OK


def main() -> int:
    ap = argparse.ArgumentParser(
        description="기업행위 가격 보정(기본 dry-run). 라이브 봇과 같은 작업 디렉터리에서 실행할 것.")
    ap.add_argument("--apply", action="store_true", help="실제로 쓴다(기본은 dry-run)")
    ap.add_argument("--codes", default=None, help="쉼표 구분. 지정 시 큐를 무시한다")
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--restore", default=None, metavar="BATCH_ID")
    a = ap.parse_args()

    # 🔑 DB 접속은 프로젝트 표준 경로로만 한다 — DSN 하드코딩(호스트·포트·계정·비밀번호)
    #    금지. DB «이름»은 resolver 가 정하고(SSOT 규칙), 접속 자체는 KisDbConnection
    #    이 한다(NUMERIC→float 어댑터 등록 + KIS_DB_* env override 를 같이 얻는다).
    from config.constants import resolve_daily_source_db
    from db.kis_db_connection import KisDbConnection

    cfg = KisDbConnection.get_config()
    want = resolve_daily_source_db()
    if cfg["database"] != want:
        # env 로 «다른» DB 를 가리킨 채 쓰기 도구를 돌리는 것은 사고다 — fail-closed.
        print(f"🔴 대상 DB 불일치 — KIS_DB_NAME={cfg['database']} 인데 "
              f"resolver 는 {want} 를 가리킨다. 중단.")
        return EXIT_INPUT
    print(f"DB {cfg['host']}:{cfg['port']}/{cfg['database']} (user={cfg['user']})")

    try:
        with KisDbConnection.get_connection() as conn:
            try:
                return _run(a, conn)
            finally:
                # 읽기 전용 트랜잭션을 열어둔 채 끝내지 않는다(VACUUM 차단 방지).
                # 커밋된 것은 이 호출로 안 지워진다 — 되돌리기는 --restore 뿐이다.
                conn.rollback()
    finally:
        KisDbConnection.close_all()


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.exit(main())
