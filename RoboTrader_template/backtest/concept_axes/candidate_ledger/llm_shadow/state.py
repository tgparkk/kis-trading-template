"""§5-3 상태 기계 · §5-4 묶음·재시도 · §5-5 한도 · §5-6 반복 🔒.

- 호출 «전»에 그날 계획을 `plan`(+`day_plan`)에 INSERT → 호출 → `shadow`. 모든 쓰기 = INSERT … ON CONFLICT DO NOTHING.
- 재개 = `plan` 에 있고 `shadow` 에 종결 status 가 없는 칸만 · D 오름차순 · 이미 있는 칸은 재호출하지 않는다.
  1차 묶음을 이미 부른 칸(= `batch` 행 있음)은 1차를 다시 부르지 않고 재시도 풀로 간다.
- 묶음 = `default_rng([20261004, 82, D])` 로 섞어 20개씩 · 하루 ≤ 20호출(1차 ≤ 18 + 반복 1 + 재시도 1) · 동시 ≤ 3.
- 재시도 = 실패 종목을 모아 한 묶음(`[20261004, 91, D]` 순서 · ≤ 20) · 429/529 = 180초 뒤 1회(따로 · `overload_retry`).
- 한도 오류 = 그 묶음 `limit_error` 종결 + 그날 남은 1차 호출 중단(재개는 다음 실행) · `model_mismatch` = 그날 중단 + 경보.
- 반복 = 1차 ok 중 min(20, ceil(0.05·n_ok)) 개(`[…, 83, D]`) → 새로 섞은 묶음(`[…, 90, D]`) → `rep`.
- 🔒 봉인: 모델 출력은 `shadow.output_json`·`batch.raw_result`·`rep.output_json` 에만. 로그는 건수·status 만.
"""
from __future__ import annotations

import json
import math
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any, Callable, Dict, Iterable, List, Optional, Sequence, Tuple

from . import cli as C
from . import inputs as I
from . import prompt_v1 as P
from . import schedule as SC
from . import settings as S

PK = {
    "day_plan": ("family", "scan_date"),
    "plan": ("family", "scan_date", "stock_code"),
    "shadow": ("family", "scan_date", "stock_code"),
    "batch": ("family", "scan_date", "batch_id"),
    "rep": ("family", "scan_date", "stock_code"),
    "search": ("family", "scan_date", "stock_code"),
    "search_daily_agg": ("family", "scan_date"),
}
TABLES = tuple(PK)


# ── 저장소 ───────────────────────────────────────────────────────────────────────
class MemoryStore:
    """dry-run·테스트용. PK 충돌 = 무시(DO NOTHING)."""

    def __init__(self) -> None:
        self.t: Dict[str, Dict[tuple, Dict[str, Any]]] = {k: {} for k in PK}
        self.lock = threading.Lock()

    def insert_many(self, items: Sequence[Tuple[str, List[Dict[str, Any]]]]) -> int:
        n = 0
        with self.lock:
            for table, rows in items:
                for r in rows:
                    key = tuple(r[k] for k in PK[table])
                    if key not in self.t[table]:
                        self.t[table][key] = dict(r, created_at=r.get("created_at") or datetime.now())
                        n += 1
        return n

    def select(self, table: str, where: Dict[str, Any], cols: Optional[Sequence[str]] = None) -> List[Dict[str, Any]]:
        with self.lock:
            rows = [r for r in self.t[table].values() if all(r.get(k) == v for k, v in where.items())]
        rows.sort(key=lambda r: tuple(str(r[k]) for k in PK[table]))
        return [dict(r) if cols is None else {c: r.get(c) for c in cols} for r in rows]


class PgStore:
    """`llm_shadow` 스키마 · 쓰기 역할 연결. insert_many 는 한 트랜잭션."""

    def __init__(self, conn) -> None:
        self.conn = conn
        self.lock = threading.Lock()

    @staticmethod
    def _adapt(v: Any) -> Any:
        if isinstance(v, dict):
            import psycopg2.extras
            return psycopg2.extras.Json(v)
        return v

    def insert_many(self, items: Sequence[Tuple[str, List[Dict[str, Any]]]]) -> int:
        n = 0
        with self.lock:
            try:
                with self.conn.cursor() as cur:
                    for table, rows in items:
                        for r in rows:
                            cols = list(r.keys())
                            cur.execute(
                                f"INSERT INTO llm_shadow.{table} ({', '.join(cols)}) VALUES "
                                f"({', '.join(['%s'] * len(cols))}) ON CONFLICT DO NOTHING",
                                [self._adapt(r[c]) for c in cols])
                            n += cur.rowcount
                self.conn.commit()
            except Exception:
                self.conn.rollback()
                raise
        return n

    def select(self, table: str, where: Dict[str, Any], cols: Optional[Sequence[str]] = None) -> List[Dict[str, Any]]:
        sel = ", ".join(cols) if cols else "*"
        cond = " AND ".join(f"{k} = %s" for k in where) or "TRUE"
        with self.lock, self.conn.cursor() as cur:
            cur.execute(f"SELECT {sel} FROM llm_shadow.{table} WHERE {cond} ORDER BY {', '.join(PK[table])}",
                        list(where.values()))
            names = [d[0] for d in cur.description]
            out = [dict(zip(names, row)) for row in cur.fetchall()]
        self.conn.commit()
        return out


# ── 묶음 · 선택(순수) ─────────────────────────────────────────────────────────────
def make_batches(codes: Iterable[str], D: date, family: str) -> List[Tuple[str, List[str]]]:
    order = sorted(set(codes))
    perm = SC.rng_of(S.SEED_BATCH_SHUFFLE, D).permutation(len(order))
    sh = [order[i] for i in perm]
    return [(f"{family}:{D.isoformat()}:p{j // S.BATCH_SIZE + 1:02d}", sh[j:j + S.BATCH_SIZE])
            for j in range(0, len(sh), S.BATCH_SIZE)]


def retry_order(codes: Iterable[str], D: date) -> List[str]:
    order = sorted(set(codes))
    perm = SC.rng_of(S.SEED_RETRY_ORDER, D).permutation(len(order))
    return [order[i] for i in perm][:S.BATCH_SIZE]


def repeat_pick(ok_codes: Iterable[str], D: date) -> List[str]:
    """min(20, ceil(0.05·n_ok)) 개를 [83] 로 고르고 [90] 로 새로 섞은 호출 순서."""
    ok = sorted(set(ok_codes))
    m = min(S.REPEAT_MAX, math.ceil(S.REPEAT_FRAC * len(ok)))
    if m == 0:
        return []
    picked = sorted(ok[i] for i in SC.rng_of(S.SEED_REPEAT_PICK, D).permutation(len(ok))[:m])
    return [picked[j] for j in SC.rng_of(S.SEED_REPEAT_SHUFFLE, D).permutation(m)]


def u_sha256(codes: Iterable[str]) -> str:
    return P.sha256_text("\n".join(sorted(codes)))


# ── 실행 문맥 ────────────────────────────────────────────────────────────────────
Caller = Callable[[List[str], str, float, str, bool], C.CallResult]


@dataclass
class Ctx:
    store: Any
    inputs: Any
    family: str
    caller: Caller                      # (argv, stdin, timeout, expect_model, most_output) → CallResult
    exe: str
    code_sha: str
    exe_sha256: str
    cli_version: str
    timeout_s: float = S.DEFAULT_BATCH_TIMEOUT_S
    sleep: Callable[[float], None] = lambda s: None
    log: Callable[[str], None] = print
    stop_reason: Optional[str] = None
    alerts: List[str] = field(default_factory=list)
    calls: int = 0

    @property
    def model(self) -> str:
        return S.FAMILIES[self.family]["model"]

    @property
    def rules(self) -> str:
        return S.FAMILIES[self.family]["rules"]

    def argv(self) -> List[str]:
        return P.argv_main(self.exe, self.model)


# ── ② 계획 ───────────────────────────────────────────────────────────────────────
def family_history(ctx: Ctx, cal: I.Calendar) -> Tuple[Optional[date], Dict[str, int], Dict[str, int]]:
    """(가족 첫 D, first_seen_idx, last_ok_idx) — 인덱스 = 가족 첫 D 부터 KOSPI 거래일 순번."""
    days = ctx.store.select("day_plan", {"family": ctx.family}, ["scan_date", "u_codes"])
    if not days:
        return None, {}, {}
    D0 = min(r["scan_date"] for r in days)
    base = cal.idx(D0)
    first: Dict[str, int] = {}
    for r in sorted(days, key=lambda x: x["scan_date"]):
        n = cal.idx(r["scan_date"]) - base
        for c in r["u_codes"] or []:
            first.setdefault(c, n)
    last: Dict[str, int] = {}
    for r in ctx.store.select("shadow", {"family": ctx.family, "status": S.ST_OK}, ["stock_code", "scan_date"]):
        n = cal.idx(r["scan_date"]) - base
        last[r["stock_code"]] = max(last.get(r["stock_code"], -10 ** 9), n)
    return D0, first, last


def compute_schedule(ctx: Ctx, D: date, cal: I.Calendar):
    """(Schedule, U(D), (A) 공시 종목, T, 가족 순번 n) — 쓰기 없음(검색 팔도 같은 목록을 쓴다 · §5-9)."""
    T = I.next_trading_day(D)
    D0, first, last = family_history(ctx, cal)
    D0 = D0 or D
    n = cal.idx(D) - cal.idx(D0)
    D_prev = cal.prev(D)
    U = ctx.inputs.universe(D)
    a_all, a_disc, _ = ctx.inputs.new_items(D_prev, D, T, set(U))
    carried_in = set()
    if D_prev >= D0:
        carried_in = {r["stock_code"] for r in ctx.store.select(
            "shadow", {"family": ctx.family, "scan_date": D_prev, "status": S.ST_SKIP}, ["stock_code"])}
    sch = SC.build_schedule(ctx.family, D, n, U, a_all, carried_in, last, first, ctx.rules)
    return sch, U, a_disc, T, n


def plan_day(ctx: Ctx, D: date, cal: I.Calendar) -> Dict[str, Any]:
    """그날 계획을 INSERT(이미 있으면 그대로 · 멱등). 반환 = 요약 건수(로그용)."""
    if ctx.store.select("day_plan", {"family": ctx.family, "scan_date": D}, ["scan_date"]):
        return {"planned": "exists"}
    sch, U, a_disc, T, n = compute_schedule(ctx, D, cal)
    called = [c.code for c in sch.called]
    cand = ctx.inputs.cand_strategies(D)
    batches = make_batches(called, D, ctx.family)
    pos: Dict[str, Tuple[str, int, int]] = {c: (bid, i + 1, len(cs)) for bid, cs in batches for i, c in enumerate(cs)}
    ctxs, d10, d5 = ctx.inputs.stock_ctx(D, T, called, cal) if called else ({}, None, None)
    ush = u_sha256(U)
    plan_rows, shadow_rows = [], []
    n_disc_no_title = 0
    for cell in sch.cells:
        row = dict(family=ctx.family, scan_date=D, stock_code=cell.code, trigger=cell.trigger, slice=cell.slice,
                   gap_td=cell.gap_td, carried=cell.carried,
                   cand_strategies=(cand.get(cell.code, []) if cand is not None else None))
        text = None
        if cell.planned == "call":
            bid, i, k = pos[cell.code]
            fields = I.block_fields(cell.code, ctxs[cell.code], D, d10, d5)
            if cell.code in a_disc and fields["n_dart_all"] == 0:
                n_disc_no_title += 1
            text = P.render_block(i, k, fields)
            plan_rows.append(dict(row, planned="call", batch_id=bid, batch_pos=i, input_text=text,
                                  input_sha256=P.sha256_text(text), block_sha256=P.sha256_text(P.block_body(text)),
                                  u_sha256=ush, code_sha=ctx.code_sha))
        else:
            plan_rows.append(dict(row, planned=cell.planned, batch_id=None, batch_pos=None, input_text=None,
                                  input_sha256=None, block_sha256=None, u_sha256=ush, code_sha=ctx.code_sha))
            shadow_rows.append(dict(row, status=cell.planned, code_sha=ctx.code_sha,
                                    prompt_version=S.PROMPT_VERSION, prompt_sha256=P.PROMPT_SHA256))
    day = dict(family=ctx.family, scan_date=D, t_date=T, family_day_idx=n, u_codes=sorted(U), u_sha256=ush,
               peak_day=sch.peak_day, n_a_disc_no_title=n_disc_no_title, n_batches=len(batches),
               cand_snapshot=cand is not None, code_sha=ctx.code_sha, **sch.counts)
    ctx.store.insert_many([("day_plan", [day]), ("plan", plan_rows), ("shadow", shadow_rows)])
    return dict(day, u_codes=len(U))


# ── ③ 채점 ───────────────────────────────────────────────────────────────────────
def _per_cell(res: C.CallResult, codes: List[str]) -> Tuple[Dict[str, Tuple[str, Optional[dict], Optional[str]]],
                                                            Optional[str]]:
    if res.status == S.ST_OK:
        return C.validate_batch(res.structured, codes)
    st = S.ST_CLI if res.status == C.ST_OVERLOAD else res.status
    return {c: (st, None, res.error_text) for c in codes}, None


def _batch_row(ctx: Ctx, D: date, bid: str, kind: str, stdin: str, argv: List[str], res: C.CallResult,
               cell_status: Dict[str, str], n_items: int, prompt_sha: str) -> Dict[str, Any]:
    return dict(family=ctx.family, scan_date=D, batch_id=bid, kind=kind, n_items=n_items,
                stdin_sha256=P.sha256_text(stdin), argv_sha256=P.argv_sha256(argv), status=res.status,
                is_error=res.is_error, api_error_status=res.api_error_status, error_text=res.error_text,
                limit_error=res.status == S.ST_LIMIT, overload=res.status == C.ST_OVERLOAD,
                raw_result=res.raw_result, model=res.model, model_usage_keys=res.model_keys,
                cli_version=ctx.cli_version, exe_sha256=ctx.exe_sha256, code_sha=ctx.code_sha,
                prompt_version=S.PROMPT_VERSION, prompt_sha256=prompt_sha, latency_ms=res.latency_ms,
                cost_usd=res.cost_usd, web_search_requests=res.web_search_requests,
                web_fetch_requests=res.web_fetch_requests, permission_denials=res.permission_denials,
                cell_status=cell_status, n_ok=sum(1 for v in cell_status.values() if v == S.ST_OK))


def _call(ctx: Ctx, stdin: str) -> Tuple[C.CallResult, Optional[C.CallResult]]:
    argv = ctx.argv()
    return C.call_with_overload_retry(lambda: ctx.caller(argv, stdin, ctx.timeout_s, ctx.model, False), ctx.sleep)


def _run_batch(ctx: Ctx, D: date, T: date, bid: str, kind: str, rows: List[Dict[str, Any]],
               attempt: int, final: bool) -> str:
    """묶음 1회(+429/529 재시도) 호출·기록. rows = 호출 순서대로(input_text 는 이미 i/k 번호). 반환 = 결과 status."""
    stdin = P.render_user(D.isoformat(), T.isoformat(), [r["input_text"] for r in rows])
    first, second = _call(ctx, stdin)
    ctx.calls += 1 + (second is not None)
    codes = [r["stock_code"] for r in rows]
    items: List[Tuple[str, List[Dict[str, Any]]]] = []
    argv = ctx.argv()
    if second is not None:
        items.append(("batch", [_batch_row(ctx, D, bid, kind, stdin, argv, first, {c: C.ST_OVERLOAD for c in codes},
                                           len(rows), P.PROMPT_SHA256)]))
        res, bid_eff, kind_eff = second, bid + ":o", "overload_retry"
    else:
        res, bid_eff, kind_eff = first, bid, kind
    per, _ = _per_cell(res, codes)
    cell_status = {c: st for c, (st, _, _) in per.items()}
    shadow_rows = []
    n = max(1, len(rows))
    for pos, r in enumerate(rows, 1):
        st, item, err = per[r["stock_code"]]
        terminal = st in (S.ST_OK, S.ST_LIMIT, S.ST_MODEL) or final
        if not terminal:
            continue
        shadow_rows.append(dict(
            family=ctx.family, scan_date=D, stock_code=r["stock_code"], trigger=r["trigger"], slice=r["slice"],
            gap_td=r["gap_td"], carried=r["carried"], cand_strategies=r["cand_strategies"], status=st,
            batch_id=bid_eff, batch_pos=pos, attempt=attempt, input_text=r["input_text"],
            input_sha256=P.sha256_text(r["input_text"]), block_sha256=P.sha256_text(P.block_body(r["input_text"])),
            output_json=item, model=res.model, cli_version=ctx.cli_version, exe_sha256=ctx.exe_sha256,
            code_sha=ctx.code_sha, argv_sha256=P.argv_sha256(argv), prompt_version=S.PROMPT_VERSION,
            prompt_sha256=P.PROMPT_SHA256, latency_ms=res.latency_ms,
            cost_usd=(res.cost_usd / n) if res.cost_usd is not None else None, error_text=err))
    items.append(("batch", [_batch_row(ctx, D, bid_eff, kind_eff, stdin, argv, res, cell_status, len(rows),
                                       P.PROMPT_SHA256)]))
    items.append(("shadow", shadow_rows))
    ctx.store.insert_many(items)
    if res.status == S.ST_MODEL:
        ctx.stop_reason = "model_mismatch"
    elif res.status == S.ST_LIMIT and ctx.stop_reason is None:
        ctx.stop_reason = "limit_error"
    return res.status


def _state(ctx: Ctx, D: date):
    plan = ctx.store.select("plan", {"family": ctx.family, "scan_date": D})
    done = {r["stock_code"]: r["status"] for r in ctx.store.select(
        "shadow", {"family": ctx.family, "scan_date": D}, ["stock_code", "status"])}
    batches = ctx.store.select("batch", {"family": ctx.family, "scan_date": D},
                               ["batch_id", "kind", "status", "cell_status", "created_at"])
    return plan, done, batches


def _last_cell_status(batches: List[Dict[str, Any]]) -> Dict[str, str]:
    out: Dict[str, str] = {}
    for b in sorted(batches, key=lambda x: (str(x.get("created_at")), x["batch_id"])):
        if b["kind"] == "repeat":
            continue
        cs = b.get("cell_status") or {}
        if isinstance(cs, str):
            cs = json.loads(cs)
        out.update(cs)
    return out


def score_day(ctx: Ctx, D: date) -> Dict[str, Any]:
    """재개 가능한 채점. 1차 → 재시도 → 종결 → 반복. 반환 = 건수 요약."""
    plan, done, batches = _state(ctx, D)
    if not plan:
        return {"skipped": "no plan"}
    T = ctx.store.select("day_plan", {"family": ctx.family, "scan_date": D}, ["t_date"])[0]["t_date"]
    calls = [r for r in plan if r["planned"] == "call"]
    attempted = {b["batch_id"] for b in batches if b["kind"] == "primary"}
    groups: Dict[str, List[Dict[str, Any]]] = {}
    for r in calls:
        if r["stock_code"] not in done and r["batch_id"] not in attempted:
            groups.setdefault(r["batch_id"], []).append(r)
    todo = [(bid, sorted(rs, key=lambda x: x["batch_pos"])) for bid, rs in sorted(groups.items())]
    if todo and ctx.stop_reason is None:
        with ThreadPoolExecutor(max_workers=S.CONCURRENCY) as ex:
            futs = {}
            for bid, rs in todo:
                futs[ex.submit(_guarded, ctx, D, T, bid, "primary", rs, 1, False)] = bid
            for f in as_completed(futs):
                f.result()
                if ctx.stop_reason:
                    for g in futs:
                        g.cancel()
    # 재시도(하루 1묶음)
    plan, done, batches = _state(ctx, D)
    attempted = {b["batch_id"] for b in batches if b["kind"] == "primary"}
    waiting = [r for r in calls if r["stock_code"] not in done and r["batch_id"] in attempted]
    if ctx.stop_reason is None and waiting:
        last = _last_cell_status(batches)
        if not any(b["kind"] == "retry" for b in batches):
            elig = [r["stock_code"] for r in waiting if last.get(r["stock_code"]) in S.RETRYABLE + (C.ST_OVERLOAD,)]
            order = retry_order(elig, D)
            if order:
                by = {r["stock_code"]: r for r in waiting}
                rows = [dict(by[c], input_text=P.renumber(by[c]["input_text"], i, len(order)))
                        for i, c in enumerate(order, 1)]
                _guarded(ctx, D, T, f"{ctx.family}:{D.isoformat()}:r01", "retry", rows, 2, True)
        if ctx.stop_reason is None:
            _finalize(ctx, D, calls)
    # 반복(하루 1묶음 · 전 칸 종결 뒤)
    plan, done, batches = _state(ctx, D)
    pending = [r for r in calls if r["stock_code"] not in done]
    if ctx.stop_reason is None and not pending and not any(b["kind"] == "repeat" for b in batches):
        run_repeat(ctx, D, T, plan, done)
    plan, done, _ = _state(ctx, D)
    summary: Dict[str, Any] = {"calls": ctx.calls, "pending": sum(1 for r in calls if r["stock_code"] not in done)}
    for st in done.values():
        summary[st] = summary.get(st, 0) + 1
    return summary


def _guarded(ctx: Ctx, D: date, T: date, bid: str, kind: str, rows, attempt: int, final: bool) -> Optional[str]:
    if ctx.stop_reason:
        return None
    try:
        return _run_batch(ctx, D, T, bid, kind, rows, attempt, final)
    except Exception as e:           # exe 해시 불일치(GuardError) 등 — 그날 중단 + 경보
        ctx.stop_reason = f"{type(e).__name__}"
        ctx.alerts.append(f"{D} {bid} 호출 중단: {type(e).__name__}")
        return None


def _finalize(ctx: Ctx, D: date, calls: List[Dict[str, Any]]) -> int:
    """재시도 뒤 남은 1차 실패 칸 = 마지막 status 로 종결(429/529 는 cli_error)."""
    plan, done, batches = _state(ctx, D)
    attempted = {b["batch_id"] for b in batches if b["kind"] == "primary"}
    last = _last_cell_status(batches)
    rows = []
    for r in calls:
        if r["stock_code"] in done or r["batch_id"] not in attempted:
            continue
        st = last.get(r["stock_code"], S.ST_CLI)
        st = S.ST_CLI if st in (C.ST_OVERLOAD, S.ST_OK) else st
        rows.append(dict(family=ctx.family, scan_date=D, stock_code=r["stock_code"], trigger=r["trigger"],
                         slice=r["slice"], gap_td=r["gap_td"], carried=r["carried"],
                         cand_strategies=r["cand_strategies"], status=st, batch_id=r["batch_id"],
                         batch_pos=r["batch_pos"], attempt=1, input_text=r["input_text"],
                         input_sha256=r["input_sha256"], block_sha256=r["block_sha256"], code_sha=ctx.code_sha,
                         cli_version=ctx.cli_version, exe_sha256=ctx.exe_sha256, prompt_version=S.PROMPT_VERSION,
                         prompt_sha256=P.PROMPT_SHA256, error_text="재시도 대상 밖·재시도 소진"))
    return ctx.store.insert_many([("shadow", rows)])


def run_repeat(ctx: Ctx, D: date, T: date, plan, done) -> Optional[str]:
    ok = [c for c, st in done.items() if st == S.ST_OK]
    order = repeat_pick(ok, D)
    if not order:
        return None
    by = {r["stock_code"]: r for r in plan}
    rows = [dict(by[c], input_text=P.renumber(by[c]["input_text"], i, len(order))) for i, c in enumerate(order, 1)]
    stdin = P.render_user(D.isoformat(), T.isoformat(), [r["input_text"] for r in rows])
    bid = f"{ctx.family}:{D.isoformat()}:rep1"
    try:
        first, second = _call(ctx, stdin)
    except Exception as e:
        ctx.stop_reason = type(e).__name__
        ctx.alerts.append(f"{D} {bid} 호출 중단: {type(e).__name__}")
        return None
    ctx.calls += 1 + (second is not None)
    res = second or first
    codes = [r["stock_code"] for r in rows]
    per, _ = _per_cell(res, codes)
    argv = ctx.argv()
    n = max(1, len(rows))
    rep_rows = [dict(family=ctx.family, scan_date=D, stock_code=r["stock_code"], batch_id=bid, batch_pos=pos,
                     status=per[r["stock_code"]][0], input_text=r["input_text"],
                     input_sha256=P.sha256_text(r["input_text"]),
                     block_sha256=P.sha256_text(P.block_body(r["input_text"])), output_json=per[r["stock_code"]][1],
                     model=res.model, cli_version=ctx.cli_version, exe_sha256=ctx.exe_sha256, code_sha=ctx.code_sha,
                     argv_sha256=P.argv_sha256(argv), prompt_version=S.PROMPT_VERSION, prompt_sha256=P.PROMPT_SHA256,
                     latency_ms=res.latency_ms, cost_usd=(res.cost_usd / n) if res.cost_usd is not None else None,
                     error_text=per[r["stock_code"]][2]) for pos, r in enumerate(rows, 1)]
    ctx.store.insert_many([("batch", [_batch_row(ctx, D, bid, "repeat", stdin, argv, res,
                                                 {c: v[0] for c, v in per.items()}, len(rows), P.PROMPT_SHA256)]),
                           ("rep", rep_rows)])
    if res.status == S.ST_MODEL:
        ctx.stop_reason = "model_mismatch"
    return res.status
