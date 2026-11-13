# -*- coding: utf-8 -*-
"""페이퍼 vs 실전 daytrading 대조 — 11-13 CI 분석 스크립트 (사전등록 §8·§9).

정본: docs/prereg_2026-10-18_paper_vs_real_daytrading_compare.md (동결 21e9702).
계층: ci_data.py(적재 · SELECT/파일 읽기만) → ci_stats.py(순수 통계) → 이 파일(CLI · 실행 가드).

실행 방식(셋 중 하나만):
  --synthetic-demo                          합성 자료로 전체 요약 1장(실데이터 접근 0)
  --dry-run                                 실데이터 행 수·쌍 수·거래일 수·지표별 n·최소 n 충족 여부만 (지표 값·CI 계산 0)
  --i-understand-this-is-the-single-run     실데이터 CI 계산 «단 1회» (§8) · --cost-source {allocated,strict} 필수

단일 실행 가드(순서대로 · 하나라도 걸리면 값 계산 전에 거부):
  1. --start 2026-10-19 · --end 2026-11-13 고정 · --cost-source 필수(기본값 없음)
  2. 평일 09:00~16:30 거부(§9 장중 실행 금지)
  3. 코드 식별 — git HEAD · 작업트리 dirty 여부 · ci_stats/ci_data/compare_ci sha256. dirty 면 거부(커밋된 코드만)
  4. 표식(results/SINGLE_RUN.marker) — 있으면 거부. 예외는 아래 «실패 뒤 재시도» 1회뿐
  5. 적재 뒤 거래일 수 == 20 이고 11-13 이 거래일 목록에 있어야 함(아니면 표식 쓰기 전에 중단)
  6. 표식에 시도 기록 → 단계(적재 완료 → 계산 완료 → 저장 완료 + 결과 경로)를 차례로 덧붙임 = 어디서 죽었는지 남김

실행 도중 실패 규칙(어느 쪽을 쓸지는 사장님이 고름 · 코드는 둘 다 지원):
  - 기본 = 재시도 없음. 표식이 남은 뒤 실패해도 다시 돌리지 않는다(그 시도가 «1회»).
  - --retry-after-failed-run --retry-reason "<사유>" = 직전 시도에 결과 경로가 없고 results 폴더에 요약 파일이 없으며
    앞선 재시도가 없을 때만 1회 허용. 표식에 재시도 사실·사유를 덧붙인다.
"""
import argparse
import hashlib
import json
import os
import subprocess
import sys
from datetime import date, datetime
from pathlib import Path

PKG_DIR = Path(__file__).resolve().parent
if str(PKG_DIR) not in sys.path:
    sys.path.insert(0, str(PKG_DIR))

import ci_stats  # noqa: E402

DEFAULT_START = date(2026, 10, 19)
DEFAULT_END = date(2026, 11, 13)
EXPECTED_TRADING_DAYS = 20
SINGLE_RUN_FLAG = "--i-understand-this-is-the-single-run"
MARKER_NAME = "SINGLE_RUN.marker"
CODE_FILES = ("ci_stats.py", "ci_data.py", "compare_ci.py")
RC = {"no_mode": 2, "market_hours": 3, "marker": 4, "args": 5, "dirty": 6, "days": 7}


def _parse_date(s: str) -> date:
    return datetime.strptime(s, "%Y-%m-%d").date()


def market_hours_block(now: datetime) -> bool:
    """평일 09:00 ≤ now < 16:30 이면 True(실데이터 실행 거부)."""
    if now.weekday() >= 5:
        return False
    hm = now.hour * 60 + now.minute
    return 9 * 60 <= hm < 16 * 60 + 30


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(description="페이퍼 vs 실전 daytrading 대조 CI (사전등록 2026-10-18)")
    mode = ap.add_mutually_exclusive_group()
    mode.add_argument("--dry-run", action="store_true", help="행·쌍·거래일·지표별 n·최소 n 만 (값·CI 계산 0)")
    mode.add_argument(SINGLE_RUN_FLAG, dest="single_run", action="store_true", help="실데이터 CI 계산 단 1회")
    mode.add_argument("--synthetic-demo", action="store_true", help="합성 자료로 요약 1장")
    ap.add_argument("--cost-source", choices=ci_stats.COST_SOURCES, default=None,
                    help="지표4 비용 출처: allocated(하루 합계 배분) | strict(건별 없음 → 미측정). 단일 실행엔 필수")
    ap.add_argument("--retry-after-failed-run", action="store_true",
                    help="직전 단일 실행이 결과 저장 전에 죽었을 때만 1회 허용")
    ap.add_argument("--retry-reason", default="", help="재시도 사유(표식에 기록)")
    ap.add_argument("--start", type=_parse_date, default=DEFAULT_START)
    ap.add_argument("--end", type=_parse_date, default=DEFAULT_END)
    ap.add_argument("--out", type=Path, default=PKG_DIR / "results")
    ap.add_argument("--log-root", type=Path, default=None)
    ap.add_argument("--cost-daily", type=Path, default=None)
    ap.add_argument("--cost-pairs", type=Path, default=None)
    return ap


def _load_real(args):
    import ci_data
    return ci_data.load_dataset(args.start, args.end,
                                log_root=args.log_root or ci_data.DEFAULT_LOG_ROOT,
                                cost_daily=args.cost_daily or ci_data.DEFAULT_COST_DAILY,
                                cost_pairs=args.cost_pairs or ci_data.DEFAULT_COST_PAIRS)


def code_identity() -> dict:
    """실행 코드 식별: git HEAD · dirty 여부(results/ 제외) · 세 파일 sha256."""
    def git(*a):
        return subprocess.run(["git", "-C", str(PKG_DIR), *a], capture_output=True, text=True, timeout=30)
    head = git("rev-parse", "HEAD").stdout.strip() or "?"
    st = git("status", "--porcelain", "--untracked-files=all")
    lines = [ln for ln in st.stdout.splitlines() if "paper_vs_real_compare/results/" not in ln.replace("\\", "/")]
    sha = {f: hashlib.sha256((PKG_DIR / f).read_bytes()).hexdigest() for f in CODE_FILES}
    return {"git_head": head, "dirty": bool(lines) or st.returncode != 0, "dirty_paths": lines[:20], "sha256": sha}


def _read_marker(p: Path) -> dict:
    return json.loads(p.read_text(encoding="utf-8"))


def _write_marker(p: Path, data: dict) -> None:
    tmp = p.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(tmp, p)


def _stage(p: Path, data: dict, stage: str, now_fn, **extra) -> None:
    att = data["attempts"][-1]
    att["stages"].append(dict({"stage": stage, "at": now_fn().isoformat(timespec="seconds")}, **extra))
    att.update(extra)
    _write_marker(p, data)


def _refuse(msg: str, rc: int) -> int:
    print(f"거부: {msg}", file=sys.stderr)
    return rc


def main(argv=None, loader=None, now=None, code_id=None, now_fn=None) -> int:
    args = build_parser().parse_args(argv)
    now = now or datetime.now()
    now_fn = now_fn or datetime.now
    if not (args.dry_run or args.single_run or args.synthetic_demo):
        return _refuse(f"실행 방식을 고르시오 — --dry-run | {SINGLE_RUN_FLAG} | --synthetic-demo. "
                       "실데이터 CI 계산은 사전등록상 단 1회(§8)이며 명시 플래그 없이는 하지 않는다.", RC["no_mode"])
    if args.retry_after_failed_run and not args.single_run:
        return _refuse("--retry-after-failed-run 은 단일 실행에만 붙는다.", RC["args"])

    if args.synthetic_demo:
        import synthetic
        res = ci_stats.build_summary(synthetic.full_synthetic(), cost_source=args.cost_source or "allocated")
        print(ci_stats.render_markdown(res, title_suffix=" — 🧪 합성 자료 데모(실데이터 아님)"))
        return 0

    if args.single_run:
        if (args.start, args.end) != (DEFAULT_START, DEFAULT_END):
            return _refuse(f"단일 실행 기간은 {DEFAULT_START}~{DEFAULT_END} 고정.", RC["args"])
        if args.cost_source is None:
            return _refuse("단일 실행엔 --cost-source allocated|strict 필수(기본값 없음).", RC["args"])
        if args.retry_after_failed_run and not args.retry_reason.strip():
            return _refuse("--retry-reason 필수.", RC["args"])

    if market_hours_block(now):
        return _refuse("평일 09:00~16:30 실데이터 실행 금지(§9 장중 실행 금지).", RC["market_hours"])

    load = loader or _load_real
    if args.dry_run:
        ds = load(args)
        counts = ci_stats.build_counts(ds)
        counts["checks"] = ds.meta.get("checks", {})
        print("# --dry-run (지표 값·CI 계산 0)")
        print(json.dumps(counts, ensure_ascii=False, indent=2, default=str))
        return 0

    # ---- 단일 실행 ----
    cid = code_id if code_id is not None else code_identity()
    if cid["dirty"]:
        return _refuse(f"작업트리 dirty — 커밋된 코드만 단일 실행(HEAD {cid['git_head']} · {cid['dirty_paths'][:5]}).",
                       RC["dirty"])
    marker = args.out / MARKER_NAME
    prev = None
    if marker.exists():
        if not args.retry_after_failed_run:
            return _refuse(f"단일 실행 표식이 이미 있음({marker}). 사전등록상 실데이터 CI 계산은 1회뿐.", RC["marker"])
        prev = _read_marker(marker)
        last = prev["attempts"][-1]
        if last.get("result_path"):
            return _refuse("직전 시도가 결과를 저장했음 — 재시도 불가.", RC["marker"])
        if list(args.out.glob("summary_*.md")):
            return _refuse("results 폴더에 요약 파일이 있음 — 재시도 불가.", RC["marker"])
        if any(a.get("retry") for a in prev["attempts"]):
            return _refuse("재시도는 1회뿐 — 이미 재시도한 기록이 있음.", RC["marker"])
    elif args.retry_after_failed_run:
        return _refuse("재시도할 직전 시도(표식)가 없음.", RC["marker"])

    ds = load(args)
    if len(ds.trading_days) != EXPECTED_TRADING_DAYS or DEFAULT_END not in ds.trading_days:
        return _refuse(f"거래일 점검 실패 — {len(ds.trading_days)}일(기대 {EXPECTED_TRADING_DAYS}) · "
                       f"{DEFAULT_END} 포함={DEFAULT_END in ds.trading_days}. 값 계산 전 중단(표식 안 씀).", RC["days"])

    args.out.mkdir(parents=True, exist_ok=True)
    attempt = {"started_kst": now.isoformat(timespec="seconds"), "argv": list(argv if argv is not None else sys.argv[1:]),
               "start": str(args.start), "end": str(args.end), "cost_source": args.cost_source,
               "code": cid, "stages": []}
    if prev is not None:
        attempt.update(retry=True, retry_reason=args.retry_reason.strip())
        data = prev
        data["attempts"].append(attempt)
    else:
        data = {"prereg": "docs/prereg_2026-10-18_paper_vs_real_daytrading_compare.md (21e9702)", "attempts": [attempt]}
    _write_marker(marker, data)
    _stage(marker, data, "적재 완료", now_fn, trading_days=len(ds.trading_days))
    res = ci_stats.build_summary(ds, cost_source=args.cost_source)
    md = ci_stats.render_markdown(res, title_suffix=f" — {args.start:%m-%d}~{args.end:%m-%d} 단일 실행")
    _stage(marker, data, "계산 완료", now_fn)
    outp = args.out / f"summary_{args.end:%Y%m%d}.md"
    outp.write_text(md, encoding="utf-8")
    _stage(marker, data, "저장 완료", now_fn, result_path=str(outp))
    print(md)
    print(f"\n산출: {outp}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
