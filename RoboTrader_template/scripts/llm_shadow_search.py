"""연구 ② 검색 팔(S1) 런너 — T 08:30 · 08:58 강제 종료(사전등록 §5-9 · 판정 밖 보조).

순서: 가드 → 잠금 → DART 전향 적재(합산 ≤ 60회/일) → 본체와 같은 채점 목록 → 5% 표본 단건 호출(재시도 1)
→ (ㄱ)(ㄷ) 집계(D+3 거래일) → 원장 해시.
🔒 봇 import 0 · KIS API 0 · 라이브 트리 실행 금지 · HEAD = 동결 code_sha ∧ 깨끗한 워크트리(§5-1).
🔒 본체 한도 오류 뒤(`search_paused.flag`)에는 실행하지 않는다(§5-8 · 해제는 수동).

usage:
  python scripts/llm_shadow_search.py --deadline 08:58                 # 작업 스케줄러(월~금 08:30)
  python scripts/llm_shadow_search.py --dry-run --no-cli               # 가상 입력 · 호출 없음
  python scripts/llm_shadow_search.py --dry-run --max-calls 3          # 가상 입력 · 실제 CLI(WebSearch 확인)
"""
from __future__ import annotations

import argparse
import json
import sys
import time as _time
import types
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path

RT = Path(__file__).resolve().parents[1]
if str(RT) not in sys.path:
    sys.path.insert(0, str(RT))
if "backtest" not in sys.modules:           # 봇 import 0 — backtest/__init__.py 건너뛰기
    _pkg = types.ModuleType("backtest")
    _pkg.__path__ = [str(RT / "backtest")]
    sys.modules["backtest"] = _pkg
sys.path.insert(0, str(Path(__file__).resolve().parent))

import llm_candidate_shadow as MAIN  # noqa: E402

from backtest.concept_axes.candidate_ledger.llm_shadow import alerts as AL  # noqa: E402
from backtest.concept_axes.candidate_ledger.llm_shadow import dart_load as DL  # noqa: E402
from backtest.concept_axes.candidate_ledger.llm_shadow import ddl as DDL  # noqa: E402
from backtest.concept_axes.candidate_ledger.llm_shadow import freeze as FZ  # noqa: E402
from backtest.concept_axes.candidate_ledger.llm_shadow import inputs as I  # noqa: E402
from backtest.concept_axes.candidate_ledger.llm_shadow import ledger as LG  # noqa: E402
from backtest.concept_axes.candidate_ledger.llm_shadow import lock as LK  # noqa: E402
from backtest.concept_axes.candidate_ledger.llm_shadow import cli as C  # noqa: E402
from backtest.concept_axes.candidate_ledger.llm_shadow import prompt_v1 as P  # noqa: E402
from backtest.concept_axes.candidate_ledger.llm_shadow import search_arm as SA  # noqa: E402
from backtest.concept_axes.candidate_ledger.llm_shadow import settings as S  # noqa: E402
from backtest.concept_axes.candidate_ledger.llm_shadow import state as ST  # noqa: E402

KST = timezone(timedelta(hours=9))
SEARCH_START = time(8, 30)


def parse_args(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--deadline", default=S.SEARCH_DEADLINE, help="HH:MM — 남은 호출 강제 종료(기본 08:58)")
    ap.add_argument("--main-family", default="F1", choices=list(S.MAIN_FAMILIES), help="채점 목록을 따를 본체 가족")
    ap.add_argument("--date", help="실행일 T(YYYY-MM-DD · dry-run 용)")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--no-cli", action="store_true")
    ap.add_argument("--max-calls", type=int, default=3, help="--dry-run 실제 CLI 호출 상한")
    ap.add_argument("--batch-timeout", type=int, default=S.DEFAULT_BATCH_TIMEOUT_S)
    a = ap.parse_args(argv)
    if a.no_cli and not a.dry_run:
        ap.error("--no-cli 는 --dry-run 과 함께만")
    return a


def main_codes(store, pin, cal, D: date, main_family: str) -> list:
    """본체와 같은 채점 목록 — 본체 plan 이 있으면 그것, 없으면 같은 규칙으로 계산(쓰기 없음)."""
    rows = store.select("plan", {"family": main_family, "scan_date": D}, ["stock_code", "planned"])
    if rows:
        return sorted(r["stock_code"] for r in rows if r["planned"] == "call")
    ctx = ST.Ctx(store=store, inputs=pin, family=main_family, caller=None, exe="", code_sha="", exe_sha256="",
                 cli_version="")
    sch = ST.compute_schedule(ctx, D, cal)[0]
    return sorted(c.code for c in sch.called)


def blocks_for(pin, D: date, T: date, codes: list, cal) -> dict:
    ctxs, d10, d5 = pin.stock_ctx(D, T, codes, cal) if codes else ({}, None, None)
    return {c: P.render_block(1, 1, I.block_fields(c, ctxs[c], D, d10, d5)) for c in codes}


def run_arm(a, fr, env, store, pin, conn, T: date, deadline: datetime, log, archive_root=None) -> list:
    D = pin.latest_D(T)
    cal = pin.calendar(D)
    T_D = I.next_trading_day(D)
    codes = main_codes(store, pin, cal, D, a.main_family)
    sample = SA.sample_codes(codes, D)
    if a.dry_run and not a.no_cli:
        sample = sample[: max(1, a.max_calls)]
    log(f"[표본] D={D} 목록 {len(codes)} → k={len(sample)}")
    caller = MAIN.fake_caller if (a.dry_run and a.no_cli) else MAIN.real_caller(fr, env)
    sc = SA.SearchCtx(store=store, caller=caller, exe=str(S.exe_path()), code_sha=fr.code_sha,
                      exe_sha256=fr.exe_sha256, cli_version=fr.cli_version, timeout_s=fr.batch_timeout_s,
                      deadline=deadline, sleep=(lambda s: None) if a.dry_run else _time.sleep, log=log)
    summ = SA.run_search(sc, D, T_D, sample, blocks_for(pin, D, T_D, sample, cal), a.main_family)
    ws = [b.get("web_search_requests") for b in store.select("batch", {"family": SA.FAMILY, "scan_date": D})]
    log(f"[검색 팔] {json.dumps(summ, ensure_ascii=False)} · web_search_requests {ws}")
    alerts = []
    if sc.stop_reason == "model_mismatch":
        alerts.append(f"S1 D={D} model_mismatch — 중단")
    for Dx in SA.agg_targets(store, cal, D):
        agg = SA.write_agg(store, conn, Dx, T, fr.code_sha)
        log(f"[집계 (ㄱ)(ㄷ)] D={Dx} {json.dumps(agg, ensure_ascii=False)}")
        LG.export_day(store, Dx, tables=("search_daily_agg",), root=archive_root)
    for e in LG.export_day(store, D, family_filter=[SA.FAMILY], tables=("search", "batch", "search_daily_agg"),
                           root=archive_root):
        log(f"[ledger] {e['D']} {e['table']} n={e['n_rows']} sha256={e['sha256'][:16]}")
    return alerts


def main(argv=None) -> int:
    a = parse_args(argv)
    log = MAIN.Log("search_dryrun" if a.dry_run else "search")
    try:
        fr, env = MAIN.guard(a, log)
    except (FZ.GuardError, C.ApiKeyPresent, P.AppendixMismatch) as e:
        log(f"[거부] {e}")
        AL.send_alert(f"검색 팔 실행 거부: {type(e).__name__}", dry_run=a.dry_run, log=log)
        return 2
    now = datetime.now(KST)
    T = date.fromisoformat(a.date) if a.date else now.date()
    hh, mm = (int(x) for x in a.deadline.split(":"))
    deadline = datetime.combine(now.date(), time(hh, mm))
    if a.dry_run:
        store, inp = ST.MemoryStore(), I.SyntheticInputs()
        root = S.home_dir() / "dryrun" / datetime.now().strftime("%Y%m%dT%H%M%S")
        deadline = datetime.now() + timedelta(minutes=28)
        for m in run_arm(a, fr, env, store, inp, None, T, deadline, log, archive_root=root):
            AL.send_alert(m, dry_run=True, log=log)
        return 0
    if (S.home_dir() / MAIN.PAUSE_FLAG).exists():
        log("[사다리] search_paused.flag 있음 — 본체 한도 오류 뒤 검색 팔 중단(해제는 수동)")
        return 0
    if now.time() < SEARCH_START or now.replace(tzinfo=None) >= deadline:
        log(f"[거부] 실행 창 08:30~{a.deadline} 밖({now:%H:%M})")
        return 2
    if not I.is_trading_day(T):
        log(f"[휴장] T={T}")
        return 0
    try:
        lk = LK.RunnerLock(S.lock_path(), owner="search").acquire()
    except LK.LockBusy as e:
        log(f"[잠금] {e}")
        return 3
    alerts = []
    conn = None
    try:
        conn = DDL.connect_writer()
        pin, store = I.PgInputs(conn), ST.PgStore(conn)
        D = pin.latest_D(T)
        lr = DL.load_forward(conn, D, now.date())
        log(f"[DART] D={D} OpenDART 오늘 {lr.calls_before}→{lr.calls_after}회 · 완결={lr.ok} {lr.message}")
        if not lr.ok:
            alerts.append(f"DART 적재 미완결({lr.first_incomplete}) — 검색 팔 보류")
        else:
            alerts += run_arm(a, fr, env, store, pin, conn, T, deadline, log)
    finally:
        if conn is not None:
            conn.close()
        lk.release()
        for m in alerts:
            AL.send_alert(m, log=log)
    return 0


if __name__ == "__main__":
    sys.exit(main())
