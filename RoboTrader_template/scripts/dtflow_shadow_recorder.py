"""daytrading 수급 4종 봉인 기록기 — 스펙 §4 · `backtest/concept_axes/dtflow_shadow/PREREG.md`.

usage:
  python scripts/dtflow_shadow_recorder.py --freeze           # 동결 커밋 detached 워크트리에서 1회
  python scripts/dtflow_shadow_recorder.py --record           # 작업 스케줄러 월~금 07:52
  python scripts/dtflow_shadow_recorder.py --check-snapshot   # 작업 스케줄러 월~금 09:05
  python scripts/dtflow_shadow_recorder.py --choose-k         # 시험 10거래일 뒤 신용 시차 표
  python scripts/dtflow_shadow_recorder.py --record --dry-run --date 2026-10-12 --no-guard --home <tmp> --archive <tmp>

🔴 봇 import 0 · KIS 조회 TR 4개 · 토큰 발급 0 · 라이브 트리 실행 거부 · 로그엔 건수·status·sha·예외 «형식 이름»만.
D(직전 거래일)·달력 = `utils.korean_holidays`(라이브 봇과 같은 달력 · DB 적재 상태와 무관).
--dry-run = KIS 스텁(실 토큰·key.ini·KIS 호출 0) + 메모리 저장(DB 쓰기 0) · 입력 DB 는 읽기 전용으로 읽는다.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
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
_d_complete = C.d_complete
_compute = C.compute
_load_snapshot = C.load_snapshot

CAL_DAYS = 40                                   # 신용 시차·스캔 창·D′ 에 쓰는 달력 길이(거래일)
EXIT2 = ("too_early", "already_recorded")       # 아무것도 쓰지 않고 끝난 실행 = 종료 코드 2


def _is_trading_day(d: date) -> bool:
    """라이브 봇과 같은 달력(utils.korean_holidays · 주말·공휴일·KIS 휴장 캐시) + KRX 연말 휴장(12-31)."""
    from utils.korean_holidays import is_holiday
    return d.weekday() < 5 and (d.month, d.day) != (12, 31) and not is_holiday(datetime(d.year, d.month, d.day))


def _prev_day(T: date) -> Optional[date]:
    """D = T 의 직전 거래일(달력 기준). KOSPI 의사티커처럼 늦게 적재되는 표로 정하지 않는다."""
    d = T - timedelta(days=1)
    for _ in range(31):
        if _is_trading_day(d):
            return d
        d -= timedelta(days=1)
    return None


def _cal(D: date, n: int = CAL_DAYS) -> List[date]:
    """D 를 포함한 최근 n 거래일(오름차순)."""
    out, d = [D], D - timedelta(days=1)
    while len(out) < n and d > D - timedelta(days=n * 3):
        if _is_trading_day(d):
            out.append(d)
        d -= timedelta(days=1)
    return sorted(out)


def _scan_days_desc(D: date) -> List[date]:
    """D 부터 내림차순 — [0] = 지금 기록하는 D · [1:] = 끝난 스캔일."""
    return sorted(_cal(D), reverse=True)


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
    cur_D: Optional[date] = None        # 예외 시 error 행을 남길 위치(run_record·run_snapshot 이 채운다)
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


def _already_recorded(store, D: date) -> bool:
    """그 scan_date 의 record run 행(단계·상태 무관)이 하나라도 있는가 — 스펙 «나중에 채우지 않음»."""
    return any(r.get("scan_date") == D and r.get("run_kind") == "record"
               for ph in ("trial", "sealed") for r in store.runs(ph))


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
    D = _prev_day(ctx.T)
    if D is None:
        _persist_error(ctx, "record", "NoPrevTradingDay")
        return "error"
    ctx.cur_D = D
    if _already_recorded(ctx.store, D):              # 다시 돌려도 덮거나 늦게 채우지 않는다 — 아무것도 안 씀
        _alert(ctx, D, "already_recorded")
        return "already_recorded"
    days_desc = _scan_days_desc(D)
    done = days_desc[1:1 + S.TRIAL_DAYS]             # 끝난 스캔일(지금 기록하는 D 제외) 로 시험→봉인 판정
    phase = PH.decide(ctx.store, done, ctx.k, _trial_lags(ctx, done))
    ctx.cur_phase = phase
    if now.time() >= S.REFUSE_AFTER:
        ctx.store.write_run(phase, _run_row(ctx, D, "record", "missed_host"))
        _alert(ctx, D, "missed_host")
        return "missed_host"
    ok, info = _d_complete(cur, D, days_desc[1] if len(days_desc) > 1 else None)
    if not ok:
        st = "universe_stale" if info.get("universe_date") != D.isoformat() else "missed_sweep"
        ctx.store.write_run(phase, _run_row(ctx, D, "record", st, universe_date=info.get("universe_date"),
                                            d_rows=info.get("d_rows"), dprev_rows=info.get("dprev_rows")))
        _alert(ctx, D, st)
        return st
    cands = _compute(cur, D)
    cal = _cal(D)
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
    try:
        return _run_snapshot(ctx)
    except Exception as e:  # noqa: BLE001 — run_record 와 같게: error 행 + 경보 뒤 그대로 올린다
        _persist_error(ctx, "snapshot_check", type(e).__name__)
        raise


def _run_snapshot(ctx: Ctx) -> str:
    cur = ctx.inputs_cur
    D = _prev_day(ctx.T)
    if D is None:
        _persist_error(ctx, "snapshot_check", "NoPrevTradingDay")
        return "error"
    ctx.cur_D = D
    phase = "sealed" if ctx.store.runs("sealed") else "trial"   # 봉인이 시작됐으면 놓친 날의 행도 봉인 표로
    ctx.cur_phase = phase
    mine = [C.Cand(r["stock_code"], float(r["score"]), int(r["rank"])) for r in ctx.store.cands(phase, D)]
    if not mine and not any(r["scan_date"] == D and r["run_kind"] == "record" and r["status"] == "ok"
                            for r in ctx.store.runs(phase)):
        ctx.store.write_run(phase, _run_row(ctx, D, "snapshot_check", "no_record"))
        _alert(ctx, D, "no_record")
        return "no_record"
    snap = _load_snapshot(cur, D)
    if not snap:                                      # 09:00 스냅샷 자체가 없음 ≠ 불일치
        ctx.store.write_run(phase, _run_row(ctx, D, "snapshot_check", "no_snapshot", snapshot_n=0, mine_n=len(mine)))
        _alert(ctx, D, "no_snapshot", len(mine))
        return "no_snapshot"
    m = C.compare(sorted(mine, key=lambda c: c.rank), snap)
    ctx.store.write_run(phase, _run_row(ctx, D, "snapshot_check", "ok", snapshot_match=m["match"],
                                        snapshot_n=m["snapshot_n"], mine_n=m["mine_n"],
                                        max_score_diff=m["max_score_diff"]))
    if not m["match"]:
        _alert(ctx, D, "snapshot_mismatch", m["mine_n"])
    return "ok"


def run_choose_k(ctx: Ctx) -> None:
    """신용 시차 k 표 — ok 시험 기록이 있는 날만(아직 기록 전인 날·실패한 날은 가용률 0 으로 섞지 않는다)."""
    D = _prev_day(ctx.T)
    ok_days = {r.get("scan_date") for r in ctx.store.runs("trial")
               if r.get("run_kind") == "record" and r.get("status") == "ok"}
    days = [d for d in _scan_days_desc(D) if d in ok_days][:S.TRIAL_DAYS]
    if not days:
        ctx.log("ok 시험 기록 없음 — k 표 없음")
        return
    ctx.log(f"ok 시험 기록 {len(days)}일 · {days[-1]}~{days[0]}")
    for k, mn, mean in PH.choose_k_table(_trial_lags(ctx, days)):
        ctx.log(f"k={k} · 최소 일 가용률 {mn:.3f} · 평균 {mean:.3f}")


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
        print(f"동결 거부: GuardError/{e.reason}")
        return 2
    print(f"동결 {fr.code_sha[:10]} · k={fr.credit_lag_k}")
    return 0


# ---- main 배선(테스트가 바꿔 끼운다) ----
class _StubKis:
    """--dry-run 전용 KIS 스텁 — 실 토큰·key.ini 읽기 0 · KIS 호출 0. rt_cd "0" + 빈 출력."""

    def __init__(self) -> None:
        self.calls = 0

    def get(self, kind: str, params: Dict[str, str]):
        self.calls += 1
        return ({"rt_cd": "0", "msg_cd": "DRYRUN", "msg1": "dry-run stub", "output": [], "output1": {}, "output2": []},
                datetime.now().isoformat(timespec="milliseconds"))


def _real_kis_factory():
    conf = K.read_kis_conf(S.key_ini_path())
    tok = K.read_token(S.token_path(), datetime.now())
    return K.Client(conf["base_url"], tok, conf["appkey"], conf["appsecret"])


def _open_inputs():
    from backtest.concept_axes.replayer.loader import dsn
    import psycopg2
    rconn = psycopg2.connect(**dsn())
    rconn.set_session(readonly=True)
    return rconn.cursor()


def _open_store(dry_run: bool):
    return ST.MemoryStore() if dry_run else _open_writer_store()


def _log_line(root: Path, text: str) -> None:
    """작업 스케줄러에선 stdout 이 사라진다 — 일자 로그 파일에 한 줄(비밀 없음: 코드·status·예외 형식 이름만)."""
    try:
        root.mkdir(parents=True, exist_ok=True)
        now = datetime.now()
        with open(root / f"recorder_{now:%Y%m%d}.log", "a", encoding="utf-8") as f:
            f.write(f"{now.isoformat(timespec='seconds')} pid={os.getpid()} {text}\n")
    except OSError:
        pass


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
    if a.freeze and a.dry_run:
        ap.error("--freeze 는 --dry-run 과 함께 쓸 수 없다(동결은 실제 frozen.json·DB 를 건드린다)")
    if (a.date or a.no_guard or a.home or a.archive or a.now) and not a.dry_run:
        ap.error("--date/--no-guard/--home/--archive/--now 는 --dry-run 과 함께만")
    fake_t = None
    if a.now:
        try:
            fake_t = datetime.strptime(a.now, "%H:%M").time()
        except ValueError:
            ap.error("--now 는 HH:MM")
    T_arg = None
    if a.date:
        try:
            T_arg = date.fromisoformat(a.date)
        except ValueError:
            ap.error("--date 는 YYYY-MM-DD")
    job = "freeze" if a.freeze else "record" if a.record else "snapshot" if a.check_snapshot else "choose_k"
    log_root = Path(a.home) / "logs" if a.home else S.log_dir()

    def note(text: str) -> None:                       # stdout + 일자 로그 파일 한 줄
        print(text)
        _log_line(log_root, f"{job} {text}")

    if a.freeze:
        try:
            rc = run_freeze()
        except Exception as e:  # noqa: BLE001 — 메시지 대신 형식 이름만(비밀 노출 방지)
            note(f"예외 {type(e).__name__}")
            return 1
        _log_line(log_root, f"{job} rc={rc}")
        return rc
    code_sha = "dry-run"
    if not (a.dry_run and a.no_guard):
        try:
            G.refuse_live_tree(__file__)
            fr = G.load_frozen()
            code_sha = G.check_runtime(S.REPO_ROOT, fr)
        except Exception as e:  # noqa: BLE001 — GuardError 밖 예외(깨진 파일 등)도 조용히 죽지 않게
            tag = f"GuardError/{e.reason}" if isinstance(e, G.GuardError) else type(e).__name__
            AL.send(f"guard_refused {tag}", dry_run=a.dry_run)
            note(f"guard_refused {tag} — 가드 거부")
            return 2
    T = T_arg or datetime.now().date()
    try:
        if not _is_trading_day(T):
            print(f"[휴장] {T}")
            return 0
    except Exception as e:  # noqa: BLE001 — 달력 모듈 실패 = D 를 정할 수 없음
        AL.send(f"error {type(e).__name__}", dry_run=a.dry_run)
        note(f"예외 {type(e).__name__}")
        return 1
    if a.record and not a.dry_run and datetime.now().time() < S.START_NOT_BEFORE:
        note("시작 시각 전 — 거부")
        return 2
    lk = RunnerLock(Path(a.home or S.home_dir()) / "runner.lock", owner=job)
    try:
        lk.acquire()
    except LockBusy:
        note("LockBusy — 다른 실행이 잠금을 쥐고 있다")
        return 3
    pending: List[str] = []                            # 한 실행 경보 1통
    try:
        cur = _open_inputs()
        store = _open_store(a.dry_run)
        now_fn = ((lambda: datetime.combine(T, fake_t or datetime.now().time())) if a.dry_run else datetime.now)
        ctx = Ctx(T=T, now_fn=now_fn, store=store, inputs_cur=cur,
                  kis_factory=_StubKis if a.dry_run else _real_kis_factory, code_sha=code_sha,
                  archive=Path(a.archive) if a.archive else (None if a.dry_run else S.archive_dir()),
                  log=note, alerts=pending, k=S.CREDIT_LAG_K, dry_run=a.dry_run)
        if a.record:
            st = run_record(ctx)
        elif a.check_snapshot:
            st = run_snapshot(ctx)
        else:
            run_choose_k(ctx)
            st = "ok"
        note(f"status={st}")
        return 2 if st in EXIT2 else 0
    except Exception as e:  # noqa: BLE001 — 메시지 대신 형식 이름만(비밀 노출 방지)
        pending.append(f"error {type(e).__name__}")
        note(f"예외 {type(e).__name__}")
        return 1
    finally:
        try:
            if pending:
                AL.send(" | ".join(pending), dry_run=a.dry_run)
        finally:
            lk.release()


if __name__ == "__main__":
    sys.exit(main())
