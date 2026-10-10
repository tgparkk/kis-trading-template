"""daytrading 수급 4종 봉인 기록기 — 스펙 §4 · `backtest/concept_axes/dtflow_shadow/PREREG.md`.

usage:
  python scripts/dtflow_shadow_recorder.py --freeze           # 동결 커밋 detached 워크트리에서 1회
  python scripts/dtflow_shadow_recorder.py --record           # 작업 스케줄러 월~금 07:52
  python scripts/dtflow_shadow_recorder.py --check-snapshot   # 작업 스케줄러 월~금 09:05
  python scripts/dtflow_shadow_recorder.py --choose-k         # 시험 10거래일 뒤 신용 시차 표
  python scripts/dtflow_shadow_recorder.py --record --dry-run --date 2026-10-12 --no-guard --home <tmp> --archive <tmp>

🔴 봇 import 0 · KIS 조회 TR 4개 · 토큰 발급 0 · 라이브 트리 실행 거부 · 로그엔 건수·status·sha 만.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
import time as _time
import types
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

import requests

RT = Path(__file__).resolve().parents[1]
if str(RT) not in sys.path:
    sys.path.insert(0, str(RT))
if "backtest" not in sys.modules:
    _pkg = types.ModuleType("backtest")
    _pkg.__path__ = [str(RT / "backtest")]
    sys.modules["backtest"] = _pkg

from backtest.concept_axes.dtflow_shadow import alerts as AL      # noqa: E402
from backtest.concept_axes.dtflow_shadow import candidates as C    # noqa: E402
from backtest.concept_axes.dtflow_shadow import features as F      # noqa: E402
from backtest.concept_axes.dtflow_shadow import guard as G         # noqa: E402
from backtest.concept_axes.dtflow_shadow import kis as K           # noqa: E402
from backtest.concept_axes.dtflow_shadow import phase as PH        # noqa: E402
from backtest.concept_axes.dtflow_shadow import settings as S      # noqa: E402
from backtest.concept_axes.dtflow_shadow import store as ST        # noqa: E402
from backtest.concept_axes.dtflow_shadow.lock import LockBusy, RunnerLock   # noqa: E402

# DB 읽기 훅(테스트가 바꿔 끼운다)
_prev_day = C.prev_trading_day
_d_complete = C.d_complete
_compute = C.compute
_load_snapshot = C.load_snapshot


def _cal(cur, D: date) -> List[date]:
    cur.execute("SELECT DISTINCT date FROM daily_prices WHERE stock_code = 'KOSPI' AND date <= %s "
                "ORDER BY date DESC LIMIT 40", (D.isoformat(),))
    return sorted(date.fromisoformat(str(r[0])[:10]) for r in cur.fetchall())


def _scan_days_desc(cur, D: date) -> List[date]:
    return sorted(_cal(cur, D), reverse=True)


@dataclass
class Ctx:
    T: date
    now_fn: Callable[[], datetime]
    store: Any
    inputs_cur: Any
    kis_factory: Callable[[], Any]
    code_sha: str
    archive: Optional[Path]
    log: Callable[..., None]
    alerts: List[str] = field(default_factory=list)
    k: Optional[int] = None
    dry_run: bool = False
    t0: float = field(default_factory=_time.perf_counter)
    cur_D: Optional[date] = None        # 예외 시 error 행을 남길 위치(run_record 가 채운다)
    cur_phase: Optional[str] = None

    def ms(self) -> int:
        return int((_time.perf_counter() - self.t0) * 1000)


def _run_row(ctx: Ctx, D: date, kind: str, status: str, **kw) -> Dict[str, Any]:
    r = {c: None for c in ST.RUN_COLS}
    r.update(rule_v=S.RULE_V, scan_date=D, run_kind=kind, run_at=ctx.now_fn().isoformat(timespec="seconds"),
             status=status, code_sha=ctx.code_sha, duration_ms=ctx.ms(), **kw)
    return r


def _alert(ctx: Ctx, D: date, status: str, n: Optional[int] = None) -> None:
    ctx.alerts.append(AL.body(D, status, n))


def _trial_lags(ctx: Ctx, days: List[date]) -> Dict[date, List[Optional[int]]]:
    return {d: [r.get("credit_lag") for r in ctx.store.cands("trial", d)] for d in days}


def _persist_error(ctx: Ctx, kind: str, error_text: str, **kw) -> None:
    """error 행을 best-effort 로 남긴다 — 쓰기 자체가 실패해도 원래 예외를 가리지 않는다. error_text = 예외 «타입명»만."""
    try:
        D = ctx.cur_D or ctx.T
        phase = ctx.cur_phase or ("sealed" if ctx.store.runs("sealed") else "trial")
        ctx.store.write_run(phase, _run_row(ctx, D, kind, "error", error_text=error_text, **kw))
        _alert(ctx, D, "error")
    except Exception as e:  # noqa: BLE001
        ctx.log(f"error 행 기록 실패(무시): {type(e).__name__}")


def run_record(ctx: Ctx) -> str:
    try:
        return _run_record(ctx)
    except Exception as e:  # noqa: BLE001 — 예상 밖 예외도 error 행 + 경보 뒤 그대로 올린다
        _persist_error(ctx, "record", type(e).__name__)
        raise


def _run_record(ctx: Ctx) -> str:
    now = ctx.now_fn()
    cur = ctx.inputs_cur
    D = _prev_day(cur, ctx.T)
    if D is None:
        _persist_error(ctx, "record", "NoPrevTradingDay")
        return "error"
    ctx.cur_D = D
    days_desc = _scan_days_desc(cur, D)
    phase = PH.decide(ctx.store, days_desc, ctx.k, _trial_lags(ctx, days_desc[:S.TRIAL_DAYS]))
    ctx.cur_phase = phase
    if now.time() >= S.REFUSE_AFTER:
        ctx.store.write_run(phase, _run_row(ctx, D, "record", "missed_host"))
        _alert(ctx, D, "missed_host")
        return "missed_host"
    ok, info = _d_complete(cur, D)
    if not ok:
        st = "universe_stale" if info.get("universe_date") != D.isoformat() else "missed_sweep"
        ctx.store.write_run(phase, _run_row(ctx, D, "record", st, universe_date=info.get("universe_date"),
                                            d_rows=info.get("d_rows"), dprev_rows=info.get("dprev_rows")))
        _alert(ctx, D, st)
        return st
    cands = _compute(cur, D)
    cal = _cal(cur, D)
    try:
        client = ctx.kis_factory()
    except (K.TokenUnavailable, OSError, UnicodeDecodeError):   # 토큰 읽기·클라이언트 생성만(봇이 07:40 파일을 다시 쓰는 중 포함)
        ctx.store.write_run(phase, _run_row(ctx, D, "record", "missed_token", n_cands=len(cands)))
        _alert(ctx, D, "missed_token", len(cands))
        return "missed_token"
    raws: List[Dict[str, Any]] = []
    rows: List[Dict[str, Any]] = []
    n_fail = 0
    try:
        for c in cands:
            bodies: Dict[str, dict] = {}
            for kind in S.KINDS:
                body, at = client.get(kind, K.params_for(kind, c.stock_code, D, ctx.T))
                bodies[kind] = body
                n_fail += int(str(body.get("rt_cd")) != "0")
                canon = json.dumps(body, ensure_ascii=False, sort_keys=True)
                raws.append(dict(rule_v=S.RULE_V, scan_date=D, stock_code=c.stock_code, kind=kind, vintage=1,
                                 fetched_at=at, rt_cd=str(body.get("rt_cd")), msg_cd=str(body.get("msg_cd") or ""),
                                 body=body, body_sha256=hashlib.sha256(canon.encode("utf-8")).hexdigest()))
            feat = F.compute(D, bodies, cal, ctx.k)
            r = {col: None for col in ST.CAND_COLS}
            r.update(rule_v=S.RULE_V, scan_date=D, stock_code=c.stock_code, rank=c.rank, score=c.score,
                     run_at=ctx.now_fn().isoformat(timespec="seconds"), code_sha=ctx.code_sha, **feat)
            rows.append(r)
    except K.TokenUnavailable:                       # 조회 중 만료 응답
        ctx.store.write_run(phase, _run_row(ctx, D, "record", "missed_token", n_cands=len(cands)))
        _alert(ctx, D, "missed_token", len(cands))
        return "missed_token"
    except requests.RequestException as e:           # 네트워크 실패 ≠ 토큰 문제
        ctx.store.write_run(phase, _run_row(ctx, D, "record", "error", n_cands=len(cands), n_calls=len(raws),
                                            n_fail=n_fail, error_text=type(e).__name__))
        _alert(ctx, D, "error", len(cands))
        return "error"
    if raws and n_fail >= len(raws):                 # 하루치 호출이 전부 실패 — 봉인 금지
        ctx.store.write_run(phase, _run_row(ctx, D, "record", "error", n_cands=len(cands), n_calls=len(raws),
                                            n_fail=n_fail, error_text="AllCallsFailed"))
        _alert(ctx, D, "error", len(cands))
        return "error"
    late = ctx.now_fn().time() > S.SEAL_DEADLINE
    for r in rows:
        r["late"] = late
        r["row_sha"] = ST.row_sha(r, ST.CAND_COLS)
    n = max(1, len(rows))
    avail = {k: sum(1 for r in rows if r[f"has_{k}"]) / n for k in ("investor", "program", "short", "credit")}
    status = "late" if late else "ok"
    run = _run_row(ctx, D, "record", status, n_cands=len(rows), n_calls=getattr(client, "calls", len(raws)),
                   n_fail=n_fail, avail_investor=avail["investor"], avail_program=avail["program"],
                   avail_short=avail["short"], avail_credit=avail["credit"] if ctx.k is not None else None,
                   universe_date=info.get("universe_date"), d_rows=info.get("d_rows"), dprev_rows=info.get("dprev_rows"),
                   rows_sha256=ST.rows_sha256(rows))
    ctx.store.write_day(phase, rows, raws, run)
    if late:
        _alert(ctx, D, "late", len(rows))
    if ctx.archive is not None:
        ST.export_ledger(rows, ST.CAND_COLS, ctx.archive / phase, D, "candidates")
    _vintage2(ctx, client, days_desc)
    return status


def _vintage2(ctx: Ctx, client, days_desc: List[date]) -> None:
    """판정 미사용 — 직전 스캔일 D′ 후보의 같은 D′ 값을 오늘 아침 다시 받아 원문만 저장(«아침 값 = 최종값» 비율 인쇄용).
    봉인 «뒤»에 따로 돌고, 실패해도 그날 기록 결과는 바뀌지 않는다."""
    if len(days_desc) < 2 or ctx.now_fn().time() >= S.REFUSE_AFTER:
        return
    pD = days_desc[1]
    pphase = "sealed" if ctx.store.cands("sealed", pD) else "trial"
    prev = ctx.store.cands(pphase, pD)
    if not prev:
        return
    try:
        v2: List[Dict[str, Any]] = []
        for r in prev:
            for kind in S.KINDS:
                body, at = client.get(kind, K.params_for(kind, r["stock_code"], pD, ctx.T))
                canon = json.dumps(body, ensure_ascii=False, sort_keys=True)
                v2.append(dict(rule_v=S.RULE_V, scan_date=pD, stock_code=r["stock_code"], kind=kind, vintage=2,
                               fetched_at=at, rt_cd=str(body.get("rt_cd")), msg_cd=str(body.get("msg_cd") or ""),
                               body=body, body_sha256=hashlib.sha256(canon.encode("utf-8")).hexdigest()))
        ctx.store.write_raws(pphase, v2)
    except Exception as e:  # noqa: BLE001 — 보조 수집 · 기록 결과 불변
        ctx.log(f"vintage2 실패(무시): {type(e).__name__}")


def run_snapshot(ctx: Ctx) -> str:
    if ctx.now_fn().time() < S.SNAPSHOT_NOT_BEFORE:
        return "too_early"                            # 아무것도 쓰지 않음 · main 이 종료 코드 2
    cur = ctx.inputs_cur
    D = _prev_day(cur, ctx.T)
    phase = "sealed" if ctx.store.cands("sealed", D) else "trial"
    mine = [C.Cand(r["stock_code"], float(r["score"]), int(r["rank"])) for r in ctx.store.cands(phase, D)]
    if not mine and not any(r["scan_date"] == D and r["run_kind"] == "record" and r["status"] == "ok"
                            for r in ctx.store.runs(phase)):
        ctx.store.write_run(phase, _run_row(ctx, D, "snapshot_check", "no_record"))
        _alert(ctx, D, "no_record")
        return "no_record"
    m = C.compare(sorted(mine, key=lambda c: c.rank), _load_snapshot(cur, D))
    ctx.store.write_run(phase, _run_row(ctx, D, "snapshot_check", "ok", snapshot_match=m["match"],
                                        snapshot_n=m["snapshot_n"], mine_n=m["mine_n"],
                                        max_score_diff=m["max_score_diff"]))
    if not m["match"]:
        _alert(ctx, D, "snapshot_mismatch", m["mine_n"])
    return "ok"


def run_choose_k(ctx: Ctx) -> None:
    D = _prev_day(ctx.inputs_cur, ctx.T)
    days = _scan_days_desc(ctx.inputs_cur, D)[:S.TRIAL_DAYS]
    for k, mn, mean in PH.choose_k_table(_trial_lags(ctx, days)):
        print(f"k={k} · 최소 일 가용률 {mn:.3f} · 평균 {mean:.3f}")


def _open_writer_store():
    return ST.PgStore(ST.connect_writer())


def run_freeze(opener: Callable[[], Any] = _open_writer_store, repo=None, path=None) -> int:
    """봉인 run 행이 하나라도 있으면(상태 무관) 재동결 거부. 표가 아직 없으면(DDL 미적용 · pgcode 42P01) «없음»."""
    try:
        has_sealed = bool(opener().runs("sealed"))
    except Exception as e:  # noqa: BLE001
        if getattr(e, "pgcode", None) != "42P01":
            raise
        has_sealed = False
    if has_sealed:
        print("봉인 기록이 있다 — 재동결 거부")
        return 2
    try:
        fr = G.write_frozen(repo or S.REPO_ROOT, path)
    except G.GuardError as e:
        print(f"동결 거부: {e}")
        return 2
    print(f"동결 {fr.code_sha[:10]} · k={fr.credit_lag_k}")
    return 0


def main(argv: Optional[List[str]] = None) -> int:
    for s in (sys.stdout, sys.stderr):
        try:
            s.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass
    ap = argparse.ArgumentParser(description="dtflow shadow recorder")
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--freeze", action="store_true")
    g.add_argument("--record", action="store_true")
    g.add_argument("--check-snapshot", action="store_true")
    g.add_argument("--choose-k", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--date")
    ap.add_argument("--no-guard", action="store_true")
    ap.add_argument("--home")
    ap.add_argument("--archive")
    ap.add_argument("--now", help="dry-run 전용 HH:MM — T 날짜의 시각을 덮어쓴다")
    a = ap.parse_args(argv)
    if (a.date or a.no_guard or a.home or a.archive or a.now) and not a.dry_run:
        ap.error("--date/--no-guard/--home/--archive/--now 는 --dry-run 과 함께만")
    fake_t = None
    if a.now:
        try:
            fake_t = datetime.strptime(a.now, "%H:%M").time()
        except ValueError:
            ap.error("--now 는 HH:MM")
    if a.freeze:
        return run_freeze()
    code_sha = "dry-run"
    if not (a.dry_run and a.no_guard):
        try:
            G.refuse_live_tree(__file__)
            fr = G.load_frozen()
            code_sha = G.check_runtime(S.REPO_ROOT, fr)
        except G.GuardError as e:
            AL.send(f"guard_refused {type(e).__name__}", dry_run=a.dry_run)
            print(f"가드 거부: {e}")
            return 2
    T = date.fromisoformat(a.date) if a.date else datetime.now().date()
    try:
        from utils.korean_holidays import is_holiday
        if T.weekday() >= 5 or is_holiday(datetime(T.year, T.month, T.day)) or (T.month, T.day) == (12, 31):
            print(f"[휴장] {T}")
            return 0
    except ImportError:
        pass
    if a.record and not a.dry_run and datetime.now().time() < S.START_NOT_BEFORE:
        print("시작 시각 전 — 거부")
        return 2
    lk = RunnerLock(Path(a.home or S.home_dir()) / "runner.lock", owner="record" if a.record else "other")
    try:
        lk.acquire()
    except LockBusy:
        return 3
    try:
        from backtest.concept_axes.replayer.loader import dsn
        import psycopg2
        rconn = psycopg2.connect(**dsn())
        rconn.set_session(readonly=True)
        cur = rconn.cursor()
        store = ST.MemoryStore() if a.dry_run else ST.PgStore(ST.connect_writer())

        def kis_factory():
            conf = K.read_kis_conf(S.key_ini_path())
            tok = K.read_token(S.token_path(), datetime.now())
            return K.Client(conf["base_url"], tok, conf["appkey"], conf["appsecret"])
        now_fn = ((lambda: datetime.combine(T, fake_t or datetime.now().time())) if a.dry_run else datetime.now)
        ctx = Ctx(T=T, now_fn=now_fn, store=store, inputs_cur=cur, kis_factory=kis_factory, code_sha=code_sha,
                  archive=Path(a.archive) if a.archive else (None if a.dry_run else S.archive_dir()),
                  log=print, k=S.CREDIT_LAG_K, dry_run=a.dry_run)
        if a.record:
            st = run_record(ctx)
        elif a.check_snapshot:
            st = run_snapshot(ctx)
        else:
            run_choose_k(ctx)
            st = "ok"
        print(f"status={st}")
        return 2 if st == "too_early" else 0
    except Exception as e:  # noqa: BLE001
        AL.send(f"error {type(e).__name__}", dry_run=a.dry_run)
        print(f"예외: {type(e).__name__}: {e}")
        return 1
    finally:
        try:
            if ctx.alerts:
                AL.send(" | ".join(ctx.alerts), dry_run=a.dry_run)
        except NameError:
            pass
        lk.release()


if __name__ == "__main__":
    sys.exit(main())
