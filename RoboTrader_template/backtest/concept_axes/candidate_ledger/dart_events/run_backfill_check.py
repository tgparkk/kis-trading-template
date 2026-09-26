"""DART 공시 백필 완결성 점검 — 커버리지만(수익 조인 0) · `candidate_ledger/dart_events`.

`scripts/dart_disclosure_backfill.py` 산출물(progress.json · raw/*.json · call_log.jsonl)과
DB(`dart_disclosures`, SELECT 만)를 대조해 완결·절단·중복·정합성을 점검한다.

DB 쓰기 0 · DELETE/UPDATE 0 · 다른 테이블 접근 0 · 새 백필 호출 0(순수 읽기 점검기).

점검 항목:
  ① (type, day) 창 수 · done 수 · 미완결/미시작 목록
  ② raw 응답 total_count 합 vs 받은 행 수 vs DB 행 수(유형별) — 페이지 절단 의심 창 목록
  ③ 교차유형(B·I) 중복 rcept_no 수(raw 원자료 기준 — DB 는 PK 라 충돌분이 가려짐)
  ④ 종목코드 유무 · corp_cls 분포
  ⑤ 정정 접두 행 중 같은 (corp_code, 정규화 제목)의 원공시가 «먼저»(rcept_dt·rcept_no 순) 있는 비율
  ⑥ rcept_no 앞 8자리 ≠ rcept_dt 건수(유형별)
  ⑦ 총 호출 수 · 중복 URL 호출 수(call_log 에서 같은 URL 2회 이상) · status 분포
  ⑧ 월별 원공시(정정 제외) 행 수(유형별)

usage (워크트리 RoboTrader_template 에서):
  python -m backtest.concept_axes.candidate_ledger.dart_events.run_backfill_check --partial
  python -m backtest.concept_axes.candidate_ledger.dart_events.run_backfill_check \
      --backfill-dir scratchpad/dart_backfill_20260926

--partial: 백필이 아직 도는 중일 때 형식만 확인하는 용도 — 보고서 머리에 「진행 중 스냅샷」
경고만 붙이고 계산 로직은 동일하다(완결 판정은 항상 실측대로 인쇄한다).
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter, defaultdict
from datetime import date, datetime, timedelta
from pathlib import Path

import psycopg2

BASE = Path(__file__).resolve().parent
ROOT = BASE.parents[3]  # …/RoboTrader_template
RESULTS_DIR = BASE / "results"

# 백필 창 기본값 — scripts/dart_disclosure_backfill.py 의 DEFAULT_BGN/END/TYPES 와 동일한
# 값을 여기 독립적으로 하드코딩한다(점검기가 생산 스크립트 import 에 결합되지 않도록).
BGN = date(2024, 3, 13)
END = date(2026, 9, 23)
TYPES = ("B", "I")
DB = dict(host="127.0.0.1", port=5433, user="robotrader", password="1234", dbname="kis_template")
RAW_NAME_RE = re.compile(r"^(\d{8})_([A-Z])_p(\d+)\.json$")
BRACKET_RE = re.compile(r"[\[(][^\])]*[\])]")
WS_RE = re.compile(r"\s+")


def db_readonly():
    conn = psycopg2.connect(**DB)
    conn.set_session(readonly=True, autocommit=True)
    return conn


def daterange(bgn: date, end: date):
    d = bgn
    one = timedelta(days=1)
    while d <= end:
        yield d
        d += one


def normalize_title(report_nm: str) -> str:
    """대괄호·괄호 접두(예 [기재정정]·(정정)) 전부 제거 + 공백 제거.

    원공시-정정 매칭 키로 쓴다. `is_correction()` 은 "정정" 부분일치만 보지만
    여기서는 모든 대괄호/괄호 그룹을 지운다 — 정정이 아닌 다른 태그(예 "(자율공시)")도
    같은 공시의 다른 표기 변형일 수 있어 매칭 폭을 넓힌다.
    """
    if not report_nm:
        return ""
    t = BRACKET_RE.sub("", report_nm)
    return WS_RE.sub("", t)


def load_progress(backfill_dir: Path) -> dict:
    path = backfill_dir / "progress.json"
    if not path.exists():
        return {}
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def check_windows(progress: dict) -> dict:
    """① 전체 창 수 대비 attempted·done·미완결·미시작."""
    all_keys = [f"{ty}:{d.strftime('%Y%m%d')}" for d in daterange(BGN, END) for ty in TYPES]
    all_set = set(all_keys)
    attempted = len(progress)
    done = sum(1 for v in progress.values() if v.get("done"))
    incomplete_attempted = sorted(k for k, v in progress.items() if not v.get("done"))
    not_started = sorted(all_set - set(progress.keys()))
    return {
        "total_windows": len(all_set),
        "attempted": attempted,
        "done": done,
        "incomplete_attempted": incomplete_attempted,
        "not_started_count": len(not_started),
        "not_started_sample": not_started[:20],
    }


def scan_raw(backfill_dir: Path) -> dict:
    """② ③ raw/*.json 전수 스캔 — (type,day)별 p1 total_count/total_page·받은 행수,
    유형별 rcept_no 집합(교차유형 중복 판정용)."""
    raw_dir = backfill_dir / "raw"
    per_day: dict = {}
    rcept_by_type: dict = defaultdict(set)
    files = sorted(raw_dir.glob("*.json")) if raw_dir.exists() else []
    for fp in files:
        m = RAW_NAME_RE.match(fp.name)
        if not m:
            continue
        day, ty, page = m.group(1), m.group(2), int(m.group(3))
        with open(fp, encoding="utf-8") as f:
            data = json.load(f)
        key = (ty, day)
        entry = per_day.setdefault(key, {"pages_seen": set(), "rows": 0})
        items = data.get("list") or []
        entry["pages_seen"].add(page)
        entry["rows"] += len(items)
        if page == 1:
            entry["total_count"] = int(data.get("total_count") or 0)
            entry["total_page"] = int(data.get("total_page") or 1)
            entry["p1_status"] = data.get("status")
        for it in items:
            rn = (it.get("rcept_no") or "").strip()
            if rn:
                rcept_by_type[ty].add(rn)
    return {"per_day": per_day, "rcept_by_type": rcept_by_type, "n_files": len(files)}


def check_truncation(progress: dict, raw_scan: dict) -> dict:
    """② 유형별 total_count 합 vs 받은 행수 합 vs DB 행수 + 절단 의심 창 목록."""
    per_day = raw_scan["per_day"]
    by_type_total_count = Counter()
    by_type_rows_raw = Counter()
    suspects = []
    for (ty, day), entry in per_day.items():
        tc = entry.get("total_count", 0)
        rows = entry["rows"]
        by_type_total_count[ty] += tc
        by_type_rows_raw[ty] += rows
        prog = progress.get(f"{ty}:{day}", {})
        done = bool(prog.get("done"))
        if not done:
            suspects.append({"key": f"{ty}:{day}", "reason": "done=False(미완결)",
                              "total_count": tc, "rows_raw": rows,
                              "pages_seen": len(entry["pages_seen"]), "total_page": entry.get("total_page")})
        elif rows != tc:
            suspects.append({"key": f"{ty}:{day}", "reason": "rows≠total_count(개수 불일치)",
                              "total_count": tc, "rows_raw": rows,
                              "pages_seen": len(entry["pages_seen"]), "total_page": entry.get("total_page")})
    return {
        "by_type_total_count": dict(by_type_total_count),
        "by_type_rows_raw": dict(by_type_rows_raw),
        "suspects": suspects,
    }


def check_cross_type_duplicates(raw_scan: dict) -> dict:
    """③ raw 원자료 기준 B∩I rcept_no 교차유형 중복(DB 는 PK 라 이미 가려짐)."""
    sets_by_type = raw_scan["rcept_by_type"]
    if len(sets_by_type) < 2:
        return {"n_duplicates": 0, "sample": []}
    keys = list(sets_by_type.keys())
    inter = sets_by_type[keys[0]]
    for k in keys[1:]:
        inter = inter & sets_by_type[k]
    return {"n_duplicates": len(inter), "sample": sorted(inter)[:10]}


def fetch_all_rows(conn):
    with conn.cursor() as cur:
        cur.execute(
            "SELECT rcept_no, corp_code, stock_code, corp_cls, report_nm, rcept_dt, "
            "pblntf_ty, is_correction FROM dart_disclosures")
        cols = [c.name for c in cur.description]
        return [dict(zip(cols, row)) for row in cur.fetchall()]


def check_stock_and_cls(rows: list) -> dict:
    """④ 종목코드 유무 · corp_cls 분포(전체 + 유형별)."""
    has_code = Counter()
    cls_dist = Counter()
    cls_dist_by_type = defaultdict(Counter)
    for r in rows:
        has_code["有" if r["stock_code"] else "無"] += 1
        cls_dist[r["corp_cls"] or "?"] += 1
        cls_dist_by_type[r["pblntf_ty"]][r["corp_cls"] or "?"] += 1
    return {
        "has_stock_code": dict(has_code),
        "corp_cls": dict(cls_dist.most_common()),
        "corp_cls_by_type": {k: dict(v.most_common()) for k, v in cls_dist_by_type.items()},
    }


def check_correction_has_prior_original(rows: list) -> dict:
    """⑤ 정정 행 중 같은 (corp_code, 정규화 제목) 원공시가 «먼저»(rcept_dt·rcept_no 순) 있는 비율."""
    originals = defaultdict(list)  # (corp_code, norm_title) -> [(rcept_dt, rcept_no), ...]
    corrections = []
    for r in rows:
        norm = normalize_title(r["report_nm"] or "")
        key = (r["corp_code"], norm)
        if r["is_correction"]:
            corrections.append((key, r["rcept_dt"], r["rcept_no"]))
        else:
            originals[key].append((r["rcept_dt"], r["rcept_no"]))
    for v in originals.values():
        v.sort()
    n_with_prior = 0
    for key, rcept_dt, rcept_no in corrections:
        cand = originals.get(key)
        if not cand:
            continue
        if any((od, on_) < (rcept_dt, rcept_no) for od, on_ in cand):
            n_with_prior += 1
    total = len(corrections)
    pct = round(100.0 * n_with_prior / total, 1) if total else 0.0
    return {"total_corrections": total, "with_prior_original": n_with_prior, "pct": pct}


def check_rcept_no_date_mismatch(rows: list) -> dict:
    """⑥ rcept_no 앞 8자리 ≠ rcept_dt 건수(유형별)."""
    mismatch = Counter()
    for r in rows:
        rn = r["rcept_no"] or ""
        dt = r["rcept_dt"]
        expect = dt.strftime("%Y%m%d") if dt else None
        if rn[:8] != expect:
            mismatch[r["pblntf_ty"]] += 1
    return dict(mismatch)


def check_call_log(backfill_dir: Path) -> dict:
    """⑦ 총 호출 수 · 중복 URL 호출 수 · status 분포."""
    path = backfill_dir / "call_log.jsonl"
    total = 0
    status_dist = Counter()
    url_count = Counter()
    if path.exists():
        with open(path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    rec = json.loads(line)
                except json.JSONDecodeError:
                    continue
                total += 1
                status_dist[str(rec.get("status"))] += 1
                url_count[rec.get("url", "")] += 1
    dup_urls = {u: c for u, c in url_count.items() if c >= 2}
    extra_calls = sum(c - 1 for c in dup_urls.values())
    return {
        "total_calls_logged": total,
        "status_dist": dict(status_dist.most_common()),
        "n_duplicate_urls": len(dup_urls),
        "n_extra_calls_from_duplicates": extra_calls,
        "duplicate_url_sample": list(dup_urls.items())[:5],
    }


def check_monthly_originals(rows: list) -> dict:
    """⑧ 월별 원공시(정정 제외) 행 수(유형별)."""
    monthly = defaultdict(Counter)  # month -> {ty: count}
    for r in rows:
        if r["is_correction"]:
            continue
        dt = r["rcept_dt"]
        if not dt:
            continue
        month = dt.strftime("%Y-%m")
        monthly[month][r["pblntf_ty"]] += 1
    return {m: dict(c) for m, c in sorted(monthly.items())}


def render_report(partial: bool, backfill_dir: Path, windows: dict, trunc: dict, dup: dict,
                   stock_cls: dict, corr: dict, mismatch: dict, calls: dict, monthly: dict,
                   db_totals: dict, n_raw_files: int) -> str:
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    complete = (windows["attempted"] == windows["total_windows"]
                and windows["done"] == windows["total_windows"]
                and windows["not_started_count"] == 0)
    lines = []
    lines.append(f"# DART 백필 완결성 점검 — {backfill_dir.name}")
    lines.append("")
    lines.append(f"- 생성 {ts} · 점검 대상 `{backfill_dir}` · raw 파일 {n_raw_files}개")
    if partial:
        lines.append("- ⚠️ **`--partial` — 백필 진행 중 스냅샷(형식 확인용), 최종 결과 아님**")
    lines.append(f"- **완결 여부: {'COMPLETE' if complete else 'INCOMPLETE'}**"
                 f" (전체 {windows['total_windows']}창 · attempted {windows['attempted']} ·"
                 f" done {windows['done']} · 미시작 {windows['not_started_count']})")
    lines.append("")
    lines.append("## ① 창 완결")
    lines.append(f"- 전체 창(type×day) = {windows['total_windows']} · attempted = {windows['attempted']}"
                 f" · done = {windows['done']}")
    lines.append(f"- 미완결(attempted 이지만 done=False) = {len(windows['incomplete_attempted'])}건"
                 + (f" → {windows['incomplete_attempted'][:20]}" if windows['incomplete_attempted'] else ""))
    lines.append(f"- 미시작 = {windows['not_started_count']}건"
                 + (f" (표본 {windows['not_started_sample']})" if windows['not_started_sample'] else ""))
    lines.append("")
    lines.append("## ② total_count 합 vs raw 수집 행수 vs DB 행수(유형별)")
    for ty in TYPES:
        lines.append(f"- {ty}: total_count 합 = {trunc['by_type_total_count'].get(ty, 0)}"
                     f" · raw 수집 = {trunc['by_type_rows_raw'].get(ty, 0)}"
                     f" · DB = {db_totals.get(ty, 0)}")
    lines.append(f"- 절단/불일치 의심 창 {len(trunc['suspects'])}건"
                 + (f" (표본 {trunc['suspects'][:10]})" if trunc['suspects'] else " — 없음"))
    lines.append("")
    lines.append("## ③ 교차유형(B∩I) 중복 rcept_no (raw 원자료 기준)")
    lines.append(f"- {dup['n_duplicates']}건" + (f" (표본 {dup['sample']})" if dup['sample'] else ""))
    lines.append("")
    lines.append("## ④ 종목코드 유무 · corp_cls 분포")
    lines.append(f"- 종목코드 유무: {stock_cls['has_stock_code']}")
    lines.append(f"- corp_cls 전체: {stock_cls['corp_cls']}")
    lines.append(f"- corp_cls 유형별: {stock_cls['corp_cls_by_type']}")
    lines.append("")
    lines.append("## ⑤ 정정 행의 원공시 선행 비율 (corp_code + 정규화 제목 매칭)")
    lines.append(f"- 정정 {corr['total_corrections']}건 중 원공시가 먼저 있는 것 "
                 f"{corr['with_prior_original']}건 ({corr['pct']}%)")
    lines.append("")
    lines.append("## ⑥ rcept_no 앞 8자리 ≠ rcept_dt (유형별)")
    lines.append(f"- {mismatch if mismatch else '없음(전부 일치)'}")
    lines.append("")
    lines.append("## ⑦ 호출 로그")
    lines.append(f"- call_log 총 기록 {calls['total_calls_logged']}회 · status 분포 {calls['status_dist']}")
    lines.append(f"- 중복 URL(2회 이상) {calls['n_duplicate_urls']}개 · 중복으로 인한 여분 호출 "
                 f"{calls['n_extra_calls_from_duplicates']}회"
                 + (f" (표본 {calls['duplicate_url_sample']})" if calls['duplicate_url_sample'] else ""))
    lines.append("")
    lines.append("## ⑧ 월별 원공시(정정 제외) 행 수 (유형별)")
    for month, d in monthly.items():
        lines.append(f"- {month}: {d}")
    lines.append("")
    return "\n".join(lines)


def parse_args(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--backfill-dir", default=str(ROOT / "scratchpad" / "dart_backfill_20260926"))
    ap.add_argument("--partial", action="store_true",
                     help="백필이 아직 도는 중일 때 형식 확인용 — 보고서에 진행 중 경고만 붙는다")
    ap.add_argument("--out-dir", default=str(RESULTS_DIR))
    return ap.parse_args(argv)


def run(args) -> str:
    backfill_dir = Path(args.backfill_dir)
    progress = load_progress(backfill_dir)
    windows = check_windows(progress)
    raw_scan = scan_raw(backfill_dir)
    trunc = check_truncation(progress, raw_scan)
    dup = check_cross_type_duplicates(raw_scan)
    calls = check_call_log(backfill_dir)

    conn = db_readonly()
    try:
        rows = fetch_all_rows(conn)
        with conn.cursor() as cur:
            cur.execute("SELECT pblntf_ty, count(*) FROM dart_disclosures GROUP BY 1")
            db_totals = dict(cur.fetchall())
    finally:
        conn.close()

    stock_cls = check_stock_and_cls(rows)
    corr = check_correction_has_prior_original(rows)
    mismatch = check_rcept_no_date_mismatch(rows)
    monthly = check_monthly_originals(rows)

    report = render_report(args.partial, backfill_dir, windows, trunc, dup, stock_cls, corr,
                            mismatch, calls, monthly, db_totals, raw_scan["n_files"])

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_path = out_dir / f"backfill_check_{ts}.md"
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(report)
    print(report)
    print(f"\n[written] {out_path}")
    return report


if __name__ == "__main__":
    # Windows 콘솔 기본 코드페이지(cp949)로는 ①~⑧·em dash 등 인쇄 불가 — utf-8 강제.
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except AttributeError:
        pass
    run(parse_args())
