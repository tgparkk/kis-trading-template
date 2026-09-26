"""§5-9 검색 팔(S1) 🔒 — T 08:30 · 08:58 강제 종료 · 판정 밖(보조만).

- 목록 = 본체와 같은 채점 목록(§3-2·3-3 · 같은 08:30 컷) → k = min(15, max(5, round(0.05·n)))(≤ n) 종목을
  `default_rng([20261004, 88, D])` 로 코드 정렬 목록에서 비복원 추출 · 호출 순서 `[20261004, 92, D]` · 단건 호출.
  🔑 `round` = 파이썬 내장(은행가 반올림) 그대로.
- 입력 = 본체와 같은 종목 블록(A.2 · `=== 1/1` · 머리 둘째 줄 생략) · 시스템 A.1(규칙 2 → A.5) · 스키마 A.6 · 명령 A.7.
- 재시도 1회(하루 ≤ 30호출) · 한도 오류 ⇒ 검색 팔 중단 · 모델 검사 = modelUsage 중 출력 토큰 최다 키.
- (ㄱ) 수집 누락 추정 = D+3(거래일)에 판정 · (ㄷ) excluded_after_D 건수 · date > D 인데 sources 에 든 건수 → `search_daily_agg`.
  (ㄴ) 점수 차 분포는 여기서 계산하지 않는다(개봉-1 스크립트 몫).
- 🔒 봉인: `search.output_json`·`batch.raw_result` 외 어디에도 출력·sources 원문을 남기지 않는다(집계 건수만).
"""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Any, Callable, Dict, Iterable, List, Optional, Set, Tuple

from backtest.concept_axes.candidate_ledger.dart_events import dart_tags as DT

from . import cli as C
from . import inputs as I
from . import prompt_v1 as P
from . import schedule as SC
from . import settings as S
from . import state as ST

FAMILY = "S1"
ST_NOT_CALLED = "not_called"


# ── 표본 ─────────────────────────────────────────────────────────────────────────
def sample_k(n: int) -> int:
    return min(n, min(S.SEARCH_K_MAX, max(S.SEARCH_K_MIN, round(S.SEARCH_FRAC * n))))


def sample_codes(codes: Iterable[str], D: date) -> List[str]:
    """반환 = 호출 순서대로의 표본(비복원 [88] → 순서 [92])."""
    order = sorted(set(codes))
    k = sample_k(len(order))
    if k == 0:
        return []
    picked = sorted(order[i] for i in SC.rng_of(S.SEED_SEARCH_SAMPLE, D).permutation(len(order))[:k])
    return [picked[j] for j in SC.rng_of(S.SEED_SEARCH_ORDER, D).permutation(k)]


# ── (ㄱ) 정규화 · 매칭 ───────────────────────────────────────────────────────────
_WS = re.compile(r"\s+")
# 가운뎃점 6종(① dart_tags.MIDDOTS) — NFKC 가 먼저라 `ㆍ`(U+318D)는 `ᆞ`(U+119E)로 바뀐다 ⇒ 6종의 NFKC 상도 함께 잡는다.
_DOT_SET = sorted(set(DT.MIDDOTS) | {unicodedata.normalize("NFKC", m) for m in DT.MIDDOTS})
_DOTS = re.compile("[" + "".join(_DOT_SET) + "]")
_LEAD = re.compile(r"^\[[^\]]*\]")
_STRIP = re.compile(r"[\"'“”‘’`´「」『』«»()\[\]{}<>〈〉《》【】…,.!?:;~\-]")
_RCPNO = re.compile(r"rcpNo=(\d{14})", re.I)
_DISC_SRC = re.compile(r"(?i)dart|전자공시|kind")


def normalize_title(t: str) -> str:
    """NFKC → 공백 제거 → 가운뎃점 6종 → `·` → 앞머리 `[…]` 반복 제거 → 따옴표·괄호·…,.!?:;~- 제거 → 영문 소문자."""
    s = unicodedata.normalize("NFKC", t or "")
    s = _WS.sub("", s)
    s = _DOTS.sub(DT.DOT, s)
    while True:
        m = _LEAD.match(s)
        if not m:
            break
        s = s[m.end():]
    s = _STRIP.sub("", s)
    return s.lower()


def rcpno_of(url: Optional[str]) -> Optional[str]:
    m = _RCPNO.search(url or "")
    return m.group(1) if m else None


def is_disclosure(src: Dict[str, Any]) -> bool:
    url = str(src.get("url") or "")
    return bool(rcpno_of(url)) or "dart.fss.or.kr" in url or "kind.krx.co.kr" in url \
        or bool(_DISC_SRC.search(str(src.get("source") or "")))


def _date(s: str) -> Optional[date]:
    try:
        return date.fromisoformat(str(s))
    except ValueError:
        return None


@dataclass
class Lookup:
    """DB 조회 결과(순수 매칭 입력). rcpno → 연결 종목 집합 · 종목 → [(rcept_dt, 정규화 report_nm)] · 기사 행."""
    rcp_stocks: Dict[str, Set[str]]
    disc_by_stock: Dict[str, List[Tuple[date, str]]]
    press: List[Tuple[date, str, Set[str]]]          # (published_at 날짜, 정규화 제목, 연결 종목)


def match_disclosure(src: Dict[str, Any], code: str, lk: Lookup) -> str:
    """'found' | 'unlinked' | 'missing'."""
    rc = rcpno_of(src.get("url"))
    if rc and rc in lk.rcp_stocks:
        return "found" if code in lk.rcp_stocks[rc] else "unlinked"
    d, nt = _date(src.get("date")), normalize_title(src.get("title"))
    for rdt, nr in lk.disc_by_stock.get(code, []):
        if d and abs((rdt - d).days) <= 1 and nr == nt:
            return "found"
    return "missing"


def _title_hit(a: str, b: str) -> bool:
    if not a or not b:
        return False
    if a == b:
        return True
    short, long_ = (a, b) if len(a) <= len(b) else (b, a)
    return len(short) >= 15 and short in long_


def match_press(src: Dict[str, Any], code: str, lk: Lookup) -> str:
    d, nt = _date(src.get("date")), normalize_title(src.get("title"))
    hit_other = False
    for pd, ntitle, linked in lk.press:
        if d and abs((pd - d).days) <= 1 and _title_hit(nt, ntitle):
            if code in linked:
                return "found"
            hit_other = True
    return "unlinked" if hit_other else "missing"


def aggregate(rows: List[Dict[str, Any]], D: date, lk: Lookup) -> Dict[str, int]:
    """(ㄱ)(ㄷ) — rows = 그날 S1 search 행(ok 만 집계)."""
    out = dict(n_rows=len(rows), n_ok=0, n_sources_le_d=0, n_disc_sources=0, n_press_sources=0, n_missing_disc=0,
               n_missing_press=0, n_db_unlinked=0, n_excluded_after_d=0, n_rule_violation=0)
    for r in rows:
        if r.get("status") != S.ST_OK or not isinstance(r.get("output_json"), dict):
            continue
        out["n_ok"] += 1
        o = r["output_json"]
        out["n_excluded_after_d"] += len(o.get("excluded_after_D") or [])
        for src in o.get("sources") or []:
            d = _date(src.get("date"))
            if d is None:
                continue
            if d > D:
                out["n_rule_violation"] += 1
                continue
            out["n_sources_le_d"] += 1
            if is_disclosure(src):
                out["n_disc_sources"] += 1
                m = match_disclosure(src, r["stock_code"], lk)
                out["n_missing_disc"] += m == "missing"
            else:
                out["n_press_sources"] += 1
                m = match_press(src, r["stock_code"], lk)
                out["n_missing_press"] += m == "missing"
            out["n_db_unlinked"] += m == "unlinked"
    return out


def build_lookup(conn, rows: List[Dict[str, Any]], D: date) -> Lookup:
    """(ㄱ) 에 필요한 DB 조회(SELECT 만)."""
    srcs = [(r["stock_code"], s) for r in rows if r.get("status") == S.ST_OK and isinstance(r.get("output_json"), dict)
            for s in (r["output_json"].get("sources") or [])]
    srcs = [(c, s) for c, s in srcs if _date(s.get("date")) and _date(s.get("date")) <= D]

    def q(sql: str, params: tuple) -> List[tuple]:
        with conn.cursor() as cur:
            cur.execute(sql, params)
            return cur.fetchall()
    rcp = sorted({rc for _, s in srcs if (rc := rcpno_of(s.get("url")))})
    rcp_stocks: Dict[str, Set[str]] = {}
    if rcp:
        for rc, sc in q("SELECT rcept_no, stock_code FROM dart_disclosures WHERE rcept_no = ANY(%s)", (rcp,)):
            rcp_stocks.setdefault(rc, set()).update({sc} if sc else set())
        for url, sc in q("SELECT n.url, ns.stock_code FROM news n LEFT JOIN news_stock ns ON ns.news_id = n.id "
                         "WHERE n.source = 'dart' AND n.url LIKE ANY(%s)", ([f"%rcpNo={x}%" for x in rcp],)):
            rc = rcpno_of(url)
            if rc:
                rcp_stocks.setdefault(rc, set()).update({sc} if sc else set())
    codes = sorted({c for c, _ in srcs})
    dates = sorted({_date(s.get("date")) for _, s in srcs})
    disc_by_stock: Dict[str, List[Tuple[date, str]]] = {}
    press: List[Tuple[date, str, Set[str]]] = []
    if codes and dates:
        for sc, rdt, nm in q("SELECT stock_code, rcept_dt, report_nm FROM dart_disclosures WHERE stock_code = ANY(%s) "
                             "AND rcept_dt BETWEEN %s AND %s", (codes, dates[0] - timedelta(days=1),
                                                                dates[-1] + timedelta(days=1))):
            disc_by_stock.setdefault(sc, []).append((rdt, normalize_title(nm)))
        agg: Dict[int, Tuple[date, str, Set[str]]] = {}
        for d in dates:
            for nid, pub, title, sc in q(
                    "SELECT n.id, n.published_at, n.title, ns.stock_code FROM news n LEFT JOIN news_stock ns "
                    "ON ns.news_id = n.id WHERE n.source <> 'dart' AND n.published_at >= %s AND n.published_at < %s",
                    (datetime.combine(d - timedelta(days=1), datetime.min.time()),
                     datetime.combine(d + timedelta(days=2), datetime.min.time()))):
                e = agg.setdefault(int(nid), (pub.date(), normalize_title(title), set()))
                if sc:
                    e[2].add(sc)
        press = list(agg.values())
    return Lookup(rcp_stocks, disc_by_stock, press)


# ── 호출 ─────────────────────────────────────────────────────────────────────────
@dataclass
class SearchCtx:
    store: Any
    caller: ST.Caller
    exe: str
    code_sha: str
    exe_sha256: str
    cli_version: str
    timeout_s: float
    deadline: datetime
    now: Callable[[], datetime] = datetime.now
    sleep: Callable[[float], None] = lambda s: None
    log: Callable[[str], None] = print
    stop_reason: Optional[str] = None
    calls: int = 0
    alerts: Optional[List[str]] = None

    @property
    def model(self) -> str:
        return S.FAMILIES[FAMILY]["model"]


def _left(sc: SearchCtx) -> float:
    return (sc.deadline - sc.now()).total_seconds()


def _one(sc: SearchCtx, D: date, code: str, text: str, stdin: str, bid: str, kind: str) -> Tuple[str, C.CallResult]:
    argv = P.argv_search(sc.exe, sc.model)
    tmo = min(sc.timeout_s, _left(sc))
    if tmo < 5 or sc.calls >= S.SEARCH_MAX_CALLS:
        return ST_NOT_CALLED, C.CallResult(ST_NOT_CALLED, error_text="deadline" if tmo < 5 else "call cap")
    res = sc.caller(argv, stdin, tmo, sc.model, True)
    sc.calls += 1
    if res.status == C.ST_OVERLOAD:
        sc.store.insert_many([("batch", [_brow(sc, D, bid, kind, stdin, argv, res, {code: C.ST_OVERLOAD})])])
        sc.sleep(S.OVERLOAD_SLEEP_S)
        tmo = min(sc.timeout_s, _left(sc))
        if tmo < 5:
            return ST_NOT_CALLED, C.CallResult(ST_NOT_CALLED, error_text="deadline")
        bid, kind = bid + ":o", "overload_retry"
        res = sc.caller(argv, stdin, tmo, sc.model, True)
        sc.calls += 1
    st, item, err = (C.validate_search(res.structured, code) if res.status == S.ST_OK
                     else ((S.ST_CLI if res.status == C.ST_OVERLOAD else res.status), None, res.error_text))
    res.structured = item
    if err and res.status == S.ST_OK:
        res.error_text = err
    sc.store.insert_many([("batch", [_brow(sc, D, bid, kind, stdin, argv, res, {code: st})])])
    if res.status == S.ST_LIMIT:
        sc.stop_reason = "limit_error"
    elif res.status == S.ST_MODEL:
        sc.stop_reason = "model_mismatch"
    return st, res


def _brow(sc: SearchCtx, D: date, bid: str, kind: str, stdin: str, argv: List[str], res: C.CallResult,
          cell_status: Dict[str, str]) -> Dict[str, Any]:
    ctx = ST.Ctx(store=sc.store, inputs=None, family=FAMILY, caller=sc.caller, exe=sc.exe, code_sha=sc.code_sha,
                 exe_sha256=sc.exe_sha256, cli_version=sc.cli_version)
    return ST._batch_row(ctx, D, bid, kind, stdin, argv, res, cell_status, 1, P.PROMPT_SHA256_SEARCH)


def run_search(sc: SearchCtx, D: date, T: date, codes: List[str], blocks: Dict[str, str], main_family: str
               ) -> Dict[str, Any]:
    """codes = 호출 순서 표본 · blocks = code → `=== 1/1` 블록. 이미 있는 행(PK)은 다시 부르지 않는다."""
    have = {r["stock_code"] for r in sc.store.select("search", {"family": FAMILY, "scan_date": D}, ["stock_code"])}
    todo = [c for c in codes if c not in have]
    final: Dict[str, Tuple[str, C.CallResult, int]] = {}
    failed: List[str] = []
    for c in todo:
        if sc.stop_reason:
            final[c] = (ST_NOT_CALLED, C.CallResult(ST_NOT_CALLED, error_text=sc.stop_reason), 0)
            continue
        stdin = P.render_user(D.isoformat(), T.isoformat(), [blocks[c]], search=True)
        st, res = _one(sc, D, c, blocks[c], stdin, f"{FAMILY}:{D.isoformat()}:{c}", "search")
        final[c] = (st, res, 1)
        if st in S.RETRYABLE:
            failed.append(c)
    for c in failed:                                    # 재시도 1회
        if sc.stop_reason:
            break
        stdin = P.render_user(D.isoformat(), T.isoformat(), [blocks[c]], search=True)
        st, res = _one(sc, D, c, blocks[c], stdin, f"{FAMILY}:{D.isoformat()}:{c}:r", "search_retry")
        if st != ST_NOT_CALLED:
            final[c] = (st, res, 2)
    rows = []
    for order, c in enumerate(codes, 1):
        if c not in final:
            continue
        st, res, attempt = final[c]
        text = blocks[c]
        o = res.structured if st == S.ST_OK else None
        rows.append(dict(
            family=FAMILY, scan_date=D, stock_code=c, main_family=main_family, sample_order=order, attempt=attempt,
            status=st, input_text=text, input_sha256=P.sha256_text(text),
            block_sha256=P.sha256_text(P.block_body(text)), output_json=o,
            n_sources=len(o.get("sources") or []) if o else None,
            n_excluded=len(o.get("excluded_after_D") or []) if o else None,
            web_search_requests=res.web_search_requests, web_fetch_requests=res.web_fetch_requests,
            permission_denials=res.permission_denials, helper_models=res.helper_models,
            model=res.model, cli_version=sc.cli_version,
            exe_sha256=sc.exe_sha256, code_sha=sc.code_sha,
            argv_sha256=P.argv_sha256(P.argv_search(sc.exe, sc.model)), prompt_version=S.PROMPT_VERSION,
            prompt_sha256=P.PROMPT_SHA256_SEARCH, latency_ms=res.latency_ms, cost_usd=res.cost_usd,
            error_text=res.error_text))
    sc.store.insert_many([("search", rows)])
    summ: Dict[str, Any] = {"calls": sc.calls, "sampled": len(codes)}
    for r in rows:
        summ[r["status"]] = summ.get(r["status"], 0) + 1
    return summ


def agg_targets(store: Any, cal: I.Calendar, D: date) -> List[date]:
    """(ㄱ) 판정일 = D+3 거래일 도달 · 아직 집계 행 없음 · 최근 10거래일."""
    done = {r["scan_date"] for r in store.select("search_daily_agg", {"family": FAMILY}, ["scan_date"])}
    lo = cal.back(D, 10)
    have = {r["scan_date"] for r in store.select("search", {"family": FAMILY}, ["scan_date"])}
    return sorted(d for d in have if d not in done and cal.has(d) and lo <= d
                  and cal.idx(D) - cal.idx(d) >= S.SEARCH_AGG_LAG_TD)


def write_agg(store: Any, conn, Dx: date, judged_on: date, code_sha: str) -> Dict[str, int]:
    rows = store.select("search", {"family": FAMILY, "scan_date": Dx}, ["stock_code", "status", "output_json"])
    lk = build_lookup(conn, rows, Dx) if conn is not None else Lookup({}, {}, [])
    a = aggregate(rows, Dx, lk)
    store.insert_many([("search_daily_agg", [dict(family=FAMILY, scan_date=Dx, judged_on=judged_on,
                                                  code_sha=code_sha, **a)])])
    return a
