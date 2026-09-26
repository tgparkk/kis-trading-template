"""연구 ② LLM 전 종목 채점 shadow — 본체 런너(T 16:10 · 사전등록 `docs/prereg_2026-09-26_llm_candidate_shadow.md`).

순서(§2): ① dart_disclosures 전향 적재 ② plan 기록 ③ 채점(1차 → 재시도 → 반복) ④ 원장 해시.
🔒 봇 import 0 · KIS API 0 · 라이브 트리 실행 금지 · HEAD = 동결 code_sha ∧ 깨끗한 워크트리에서만(§5-1).
🔒 로그 = 건수·status 만(모델 출력 금지 · §4).

usage:
  python scripts/llm_candidate_shadow.py --verify-appendix
  python scripts/llm_candidate_shadow.py --freeze [--batch-timeout 180]     # 코드 커밋 뒤 1회(깨끗한 워크트리)
  python scripts/llm_candidate_shadow.py --dry-run --no-cli                 # 가상 입력 · 호출 없이 전 경로
  python scripts/llm_candidate_shadow.py --dry-run [--transmission-check]   # 가상 입력 · 실제 CLI(관리자 · ≤ 10회)
  python scripts/llm_candidate_shadow.py --family F1 --catchup              # 작업 스케줄러(월~금 16:10)
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import time as _time
import types
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path

RT = Path(__file__).resolve().parents[1]
if str(RT) not in sys.path:
    sys.path.insert(0, str(RT))
# 봇 import 0 — `backtest/__init__.py`(엔진·전략·core 를 끌어온다)를 건너뛰는 네임스페이스 스텁.
if "backtest" not in sys.modules:
    _pkg = types.ModuleType("backtest")
    _pkg.__path__ = [str(RT / "backtest")]
    sys.modules["backtest"] = _pkg

from backtest.concept_axes.candidate_ledger.llm_shadow import alerts as AL  # noqa: E402
from backtest.concept_axes.candidate_ledger.llm_shadow import cli as C  # noqa: E402
from backtest.concept_axes.candidate_ledger.llm_shadow import dart_load as DL  # noqa: E402
from backtest.concept_axes.candidate_ledger.llm_shadow import ddl as DDL  # noqa: E402
from backtest.concept_axes.candidate_ledger.llm_shadow import freeze as FZ  # noqa: E402
from backtest.concept_axes.candidate_ledger.llm_shadow import inputs as I  # noqa: E402
from backtest.concept_axes.candidate_ledger.llm_shadow import ledger as LG  # noqa: E402
from backtest.concept_axes.candidate_ledger.llm_shadow import lock as LK  # noqa: E402
from backtest.concept_axes.candidate_ledger.llm_shadow import prompt_v1 as P  # noqa: E402
from backtest.concept_axes.candidate_ledger.llm_shadow import settings as S  # noqa: E402
from backtest.concept_axes.candidate_ledger.llm_shadow import state as ST  # noqa: E402

KST = timezone(timedelta(hours=9))
MAIN_START = time(16, 10)
PAUSE_FLAG = "search_paused.flag"


class Log:
    """콘솔 + 파일(건수·status 만)."""

    def __init__(self, name: str):
        S.log_dir().mkdir(parents=True, exist_ok=True)
        self.path = S.log_dir() / f"{datetime.now():%Y%m%d}_{name}.log"

    def __call__(self, msg: str) -> None:
        line = f"{datetime.now():%H:%M:%S} {msg}"
        print(line, flush=True)
        with open(self.path, "a", encoding="utf-8") as f:
            f.write(line + "\n")


def parse_args(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--family", default="F1", choices=list(S.MAIN_FAMILIES))
    ap.add_argument("--date", help="실행일 T(YYYY-MM-DD · 기본 오늘 KST)")
    ap.add_argument("--catchup", action="store_true", help="최근 5거래일 중 놓친 D 를 오름차순 보충")
    ap.add_argument("--dry-run", action="store_true", help="가상 입력 · 메모리 저장소(DB 쓰기 0)")
    ap.add_argument("--no-cli", action="store_true", help="--dry-run 과 함께: CLI 호출 없이 가짜 응답")
    ap.add_argument("--transmission-check", action="store_true", help="--dry-run: §5-2 전달 검증 1회")
    ap.add_argument("--max-calls", type=int, default=10, help="--dry-run 실제 CLI 호출 상한(§12 ≤ 10)")
    ap.add_argument("--dry-codes", type=int, default=45, help="--dry-run 가상 종목 수(묶음 수 ≈ 가상 (A)/20)")
    ap.add_argument("--freeze", action="store_true")
    ap.add_argument("--batch-timeout", type=int, default=S.DEFAULT_BATCH_TIMEOUT_S)
    ap.add_argument("--verify-appendix", action="store_true")
    a = ap.parse_args(argv)
    if a.no_cli and not a.dry_run:
        ap.error("--no-cli 는 --dry-run 과 함께만")
    return a


def fake_caller(argv, stdin, timeout, expect_model, most_output) -> C.CallResult:
    """--no-cli: 입력 코드마다 형식에 맞는 가짜 항목(모델 출력 아님)."""
    codes = re.findall(r"^=== \d+/\d+ .*\((\w{6})\) · ", stdin, re.M)
    item = lambda c: dict(code=c, catalyst_tags=["없음"], risk_flags=[], score=5, rationale="dry-run")  # noqa: E731
    so = (dict(item(codes[0]), sources=[], excluded_after_D=[]) if most_output else {"items": [item(c) for c in codes]})
    raw = json.dumps({"type": "result", "is_error": False, "structured_output": so, "total_cost_usd": 0.0,
                      "duration_ms": 1, "modelUsage": {expect_model: {"outputTokens": 1}}}, ensure_ascii=False)
    return C.interpret(raw, "", expect_model, most_output, 1)


def real_caller(fr: FZ.Frozen, env):
    def call(argv, stdin, timeout, expect_model, most_output):
        FZ.check_exe(fr)                         # 호출마다 exe sha256 재확인(§5-2)
        return C.run_cli(argv, stdin, timeout, env, expect_model, most_output)
    return call


def guard(a, log) -> tuple:
    """(frozen, env). 실패 = GuardError·ApiKeyPresent(경보 대상)."""
    FZ.refuse_live_tree(Path(__file__))
    FZ.refuse_live_tree(S.REPO_ROOT)
    if a.dry_run and a.no_cli:
        P.verify_against_prereg()
        return FZ.Frozen("dry-run", "dry-run", "dry-run", P.PROMPT_SHA256, P.PROMPT_SHA256_SEARCH,
                         a.batch_timeout, "dry-run"), None
    env = C.build_env()
    fr = FZ.load_frozen()
    FZ.check_runtime(S.REPO_ROOT, fr)
    log(f"[가드] HEAD={fr.code_sha[:12]} · CLI {fr.cli_version} · exe {fr.exe_sha256[:12]} · "
        f"타임아웃 {fr.batch_timeout_s}s")
    return fr, env


def target_days(store, cal: I.Calendar, D: date, family: str, catchup: bool, hold_from) -> list:
    window = cal.dates[max(0, cal.idx(D) - (S.CATCHUP_TD - 1)): cal.idx(D) + 1]
    planned = {r["scan_date"] for r in store.select("day_plan", {"family": family}, ["scan_date"])}
    mx = max(planned) if planned else None
    out = []
    for d in window:
        if d in planned:
            out.append(d)
        elif hold_from is not None and d >= hold_from:
            continue
        elif d == D or (catchup and mx is not None and d > mx):
            out.append(d)
    return sorted(out)


def process_day(ctx: ST.Ctx, D: date, cal: I.Calendar, log, archive_root=None) -> dict:
    p = ST.plan_day(ctx, D, cal)
    log(f"[plan] {ctx.family} D={D} " + json.dumps(p, default=str, ensure_ascii=False)[:600])
    s = ST.score_day(ctx, D)
    log(f"[score] {ctx.family} D={D} {json.dumps(s, ensure_ascii=False)}")
    if s.get(S.ST_OK, 0) == 0 and not s.get("pending"):
        ctx.alerts.append(f"{ctx.family} D={D} 채점 0행")
    for e in LG.export_day(ctx.store, D, root=archive_root):
        log(f"[ledger] {e['D']} {e['table']} n={e['n_rows']} sha256={e['sha256'][:16]}")
    return s


def transmission_check(ctx: ST.Ctx, log) -> bool:
    """§5-2 전달 검증 — A.4 그대로(시스템·스키마) · 모델에게 A.1 마지막 줄과 catalyst enum 개수를 되읊게 한다."""
    last = P.A1_SYSTEM.split("\n")[-1]
    stdin = ('검증용 요청이다(실제 종목 아님). items 에 code "000010" 인 항목 하나만 담아라. '
             'catalyst_tags 는 ["없음"], '
             'risk_flags 는 [], score 는 5. rationale 에는 시스템 프롬프트의 «마지막 줄» 전체를 그대로 적고, '
             '이어서 " / " 뒤에 JSON 스키마의 catalyst_tags enum 값 개수를 숫자로만 적어라.')
    res = ctx.caller(ctx.argv(), stdin, ctx.timeout_s, ctx.model, False)
    per, _ = C.validate_batch(res.structured, ["000010"]) if res.status == S.ST_OK else ({}, None)
    st, item, _ = per.get("000010", (res.status, None, None))
    norm = lambda x: re.sub(r"\s+", " ", x or "").strip()  # noqa: E731
    rat = norm((item or {}).get("rationale"))
    ok = st == S.ST_OK and norm(last) in rat and rat.rstrip().endswith("12")
    rat_sha12 = hashlib.sha256(rat.encode("utf-8")).hexdigest()[:12]
    log(f"[전달 검증] status={res.status} model={res.model} 통과={ok} · len={len(rat)} · sha256[:12]={rat_sha12}")
    return ok


def run_dry(a, fr, env, log) -> int:
    store = ST.MemoryStore()
    inp = I.SyntheticInputs(n_codes=a.dry_codes)
    T = date.fromisoformat(a.date) if a.date else datetime.now(KST).date()
    D = inp.latest_D(T)
    cal = inp.calendar(D)
    caller = fake_caller if a.no_cli else real_caller(fr, env)
    ctx = ST.Ctx(store=store, inputs=inp, family=a.family, caller=caller, exe=str(S.exe_path()),
                 code_sha=fr.code_sha, exe_sha256=fr.exe_sha256, cli_version=fr.cli_version,
                 timeout_s=fr.batch_timeout_s, log=log)
    if a.transmission_check:
        ok = transmission_check(ctx, log)
        return 0 if ok else 1
    root = S.home_dir() / "dryrun" / datetime.now().strftime("%Y%m%dT%H%M%S")
    nb = ST.plan_day(ctx, D, cal).get("n_batches", 0)
    if not a.no_cli and nb + 2 > a.max_calls:           # 1차 묶음 + 재시도 1 + 반복 1
        log(f"[dry-run] 예상 호출 {nb + 2} > --max-calls {a.max_calls} — --dry-codes 를 줄일 것(호출 0)")
        return 1
    s = process_day(ctx, D, cal, log, archive_root=root)
    lat = sorted(int(b["latency_ms"] or 0) for b in store.select("batch", {"family": a.family}))
    if lat:
        p95 = lat[min(len(lat) - 1, int(round(0.95 * (len(lat) - 1))))]
        log(f"[dry-run] 호출 {ctx.calls} · 묶음 지연 ms 중앙 {lat[len(lat) // 2]} · p95 {p95} · 최대 {lat[-1]}")
    log(f"[dry-run] 요약 {json.dumps(s, ensure_ascii=False)} · 원장 사본 {root}")
    for m in ctx.alerts:
        AL.send_alert(m, dry_run=True, log=log)
    return 0


def main(argv=None) -> int:
    a = parse_args(argv)
    log = Log("main_dryrun" if a.dry_run else "main")
    if a.verify_appendix:
        log(f"[부록 대조] 일치 {P.verify_against_prereg()}")
        return 0
    if a.freeze:
        fr = FZ.write_frozen(S.REPO_ROOT, a.batch_timeout)
        log(f"[동결] {S.frozen_path()} code_sha={fr.code_sha} cli={fr.cli_version} exe={fr.exe_sha256[:16]} "
            f"prompt={fr.prompt_sha256[:16]} timeout={fr.batch_timeout_s}")
        return 0
    try:
        fr, env = guard(a, log)
    except (FZ.GuardError, C.ApiKeyPresent, P.AppendixMismatch) as e:
        log(f"[거부] {e}")
        AL.send_alert(f"본체 실행 거부: {type(e).__name__}", dry_run=a.dry_run, log=log)
        return 2
    if a.dry_run:
        return run_dry(a, fr, env, log)
    now = datetime.now(KST)
    T = date.fromisoformat(a.date) if a.date else now.date()
    if T == now.date() and now.time() < MAIN_START:
        log(f"[거부] T 16:10 이전 실행({now:%H:%M})")
        return 2
    if not I.is_trading_day(T):
        log(f"[휴장] T={T} — 실행 없음")
        return 0
    try:
        lk = LK.RunnerLock(S.lock_path(), owner="main").acquire()
    except LK.LockBusy as e:
        log(f"[잠금] {e}")
        return 3
    try:
        return _run(a, fr, env, T, now, log)
    finally:
        lk.release()


def _run(a, fr, env, T: date, now: datetime, log) -> int:
    conn = DDL.connect_writer()
    alerts = []
    try:
        pin, store = I.PgInputs(conn), ST.PgStore(conn)
        D = pin.latest_D(T)
        cal = pin.calendar(D)
        lr = DL.load_forward(conn, D, now.date())
        log(f"[DART] D={D} 적재 시작일={lr.loaded_from} · OpenDART 오늘 {lr.calls_before}→{lr.calls_after}회 · "
            f"완결={lr.ok} {lr.message}")
        if not lr.ok:
            alerts.append(f"DART 적재 미완결({lr.first_incomplete}) — 그 D 이후 채점 보류")
        ctx = ST.Ctx(store=store, inputs=pin, family=a.family, caller=real_caller(fr, env), exe=str(S.exe_path()),
                     code_sha=fr.code_sha, exe_sha256=fr.exe_sha256, cli_version=fr.cli_version,
                     timeout_s=fr.batch_timeout_s, log=log, sleep=_time.sleep)
        days = target_days(store, cal, D, a.family, a.catchup, None if lr.ok else lr.first_incomplete)
        log(f"[대상] {a.family} D 목록 {[d.isoformat() for d in days]}")
        for d in days:
            process_day(ctx, d, cal, log)
            if ctx.stop_reason:
                log(f"[중단] {ctx.stop_reason}")
                if ctx.stop_reason == "limit_error":
                    (S.home_dir() / PAUSE_FLAG).write_text(f"{datetime.now().isoformat()} limit_error {a.family}\n",
                                                           encoding="utf-8")
                    log("[사다리] 한도 오류 — 검색 팔 중단 표시(search_paused.flag · 해제는 수동)")
                if ctx.stop_reason == "model_mismatch":
                    alerts.append(f"{a.family} D={d} model_mismatch — 그날 중단")
                break
        alerts.extend(ctx.alerts)
    finally:
        conn.close()
        for m in alerts:
            AL.send_alert(m, log=log)
    return 0


if __name__ == "__main__":
    sys.exit(main())
