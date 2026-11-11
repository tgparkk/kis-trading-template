"""1분 원장 실행기 — 층 A(ledger.csv) · 층 B(스냅샷) → 진입일 분봉 1회 적재 → `lots_rule.csv` + `run_meta.json`.

규범 = `docs/prereg_2026-11-11_minute_rules.md`(🔒 동결 e2945ee) §2·§3·§5-1·§8·§9. 문서와 어긋나면 코드가 틀린 것이다.

    python -X utf8 -m backtest.concept_axes.minute_rules.run --window E               # 탐색 창(효과 계산 없음 · 로트만)
    python -X utf8 -m backtest.concept_axes.minute_rules.run --window C2 --plumbing   # 배관 확인(적재·건수·체크섬만)

🔴 관측 — 판정 근거 아님. 이 파일은 로트(arm 별 ret)만 쓴다 · 평균·비교·p 는 `analyze.py`(별도 단계 · §8 순서).
🔴 DB SELECT 만(`data.connect` = PGOPTIONS read-only + `set_session(readonly=True)`) · 직접 import 하는 운영 모듈 0
   (`backtest/__init__.py` 가 끌어오는 전이 import 는 1단계부터 있던 것 · 동작 영향 없음 · 수정 1 문서 N7).
   `_atomic_write`·`git_sha`·`_fmt`·`build_path` = `candidate_ledger/run.py:104-121·142-148·303-313` 의 «동작 같은»
   사본(차이: `_fmt` 가 np.bool_ 를 받고 날짜를 isoformat 으로 · `build_path` 에 `end` 인자 — 층 A 는 end = 원본 끝).
🔒 수정 1(2026-11-11 · `docs/prereg_2026-11-11_minute_rules_amendment1.md`):
   실창(E·C·C2·U · `--plumbing` 제외) 실행은 레포 작업 트리가 깨끗할 때만(B2 · run_meta 에 코드·의존 파일 sha256 표) ·
   C·C2·U 는 «커밋된» `RESULTS_explore.md` 뒤에만(A6) · U 출력은 레포 밖 봉인 폴더(`--sealed-dir` 또는 env
   `KIS_MINUTE_SEALED_DIR` · 기본 `D:/tmp/kis-minute-sealed`) + `--i-understand-sealed`(B1) · 레포엔 해시만
   (`results/U/public_meta.json`) · G8·G5 지문이 어긋나면 결과 csv 를 쓰지 않는다(A4).
🔒 수정 1 §7(재리뷰 NB1·D3): E·C·C2 의 로트 단위 csv(`lots_rule.csv`·`fake_timing.csv`)도 레포 밖 비공개 폴더
   (`--private-dir` > env `KIS_MINUTE_PRIVATE_DIR` > 기본 `D:/tmp/kis-minute-private`)/<창>/ 에만 쓴다 — E 의 가짜 시점
   u=10 은 봉인 대상 H2_HIST 와 같고, 로트 표로 «≤09:10/>09:10» 봉인 칸을 다시 낼 수 있어서다. 레포 `results/<창>/` 엔
   run_meta(해시·행 수)만. 봉인·비공개 폴더는 «어떤 git 작업 트리 안»이어도 거부(`ensure_outside_git`).

창(§5-1) · arm
  E  = 층 A 진입일 2025-04-17~2025-12-31 · C = 층 A 2026-01-01~2026-09-23 · C2 = 층 B 2026-10-06~(asof 기준 보유기한
  max_hold 거래일 이전 진입일까지) · U(미관측) = 층 A 2025-04-17~2026-09-23(2026-06-01~ = `print_only`).
  E·C·C2 = 기준 2 + 주 가족 6(8 arm) · U = R0 + 독립 가족 2(3 arm) — 독립 가족 결과는 봉인(§4-2·§8)이라 주 가족 창
  파일에 섞지 않고, 주 가족 규칙도 U 파일에 넣지 않는다(«≤09:10/>09:10» 두 칸 표 봉인).
  C·C2 는 `RESULTS_explore.md` sha256 확인 뒤에만 로트를 만든다(§8 순서 · `--plumbing` 은 예외).
로트(§3)
  체결 모델 a = 그 분 종가(round_to_tick) · b = 다음 분 시가(밴드 밖 = 결측 · 청산은 그 분부터) · c = 밴드 경계값.
  모델마다 k=0 탐침 1회(`engine.k0_probe`) → 진입 다음 분부터 분 단위 청산 → 미청산이면 `engine.continue_daily`
  (`exitsim8.simulate_lot` · k=0 재판정 없음 · A1). 안 삼 = 현금(ret 0).
  거르기 R4·R5 = R0_0905 결과를 로트당 1번 만들고 라벨만 붙인다(두 군 모두 R0_0905 진입 · 리뷰 M1).
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import os
import subprocess
import sys
import tempfile
import time
from bisect import bisect_left
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, List, Optional, Sequence, Set, Tuple

import numpy as np

from backtest.concept_axes.ledger8 import exitsim8 as X

from . import data as D
from . import engine as E
from . import rules as R

BASE = Path(__file__).resolve().parent
ROOT = BASE.parents[2]                                           # …/RoboTrader_template
RESULTS = BASE / "results"
LEDGER = ROOT / "backtest" / "concept_axes" / "candidate_ledger" / "results" / "ledger.csv"
LEDGER_META = LEDGER.with_name("run_meta.json")
PREREG = ROOT / "docs" / "prereg_2026-11-11_minute_rules.md"
GAP_CACHE = RESULTS / "cache" / "market_gap_rows.json"
EXPLORE_DOC = RESULTS / "RESULTS_explore.md"
AMENDMENT = ROOT / "docs" / "prereg_2026-11-11_minute_rules_amendment1.md"
REPO = ROOT.parent                                               # git 루트
SEALED_ENV = "KIS_MINUTE_SEALED_DIR"
SEALED_DEFAULT = Path("D:/tmp/kis-minute-sealed")               # 레포·연구 보관소 밖(수정 1 결정 4-나)
PRIVATE_ENV = "KIS_MINUTE_PRIVATE_DIR"
PRIVATE_DEFAULT = Path("D:/tmp/kis-minute-private")             # E·C·C2 로트 csv(수정 1 §7 NB1 · 레포 밖)
DEP_MODULES = ["backtest.concept_axes.ledger8.exitsim8", "backtest.concept_axes.ledger8.sizing",
               "backtest.concept_axes.minervini.cap_skip_ledger.sim", "backtest.concept_axes.replayer.loader",
               "utils.price_utils", "config.constants"]
FAKES_REQUIRED = 100                                             # §5-3 가짜 시점 규칙 100(R2 · E 필수)
CLEAN_IGNORE = "RoboTrader_template/backtest/concept_axes/minute_rules/results/"   # 깨끗함 검사에서 뺄 경로
CODE_DEPS = ["backtest/concept_axes/ledger8/exitsim8.py", "backtest/concept_axes/ledger8/sizing.py",
             "backtest/concept_axes/ledger8/fidelity8.py", "backtest/concept_axes/minervini/cap_skip_ledger/sim.py",
             "backtest/concept_axes/minervini/cap_skip_ledger/bootstrap.py",
             "backtest/concept_axes/minervini/cap_skip_ledger/classify.py",
             "backtest/concept_axes/replayer/loader.py", "utils/price_utils.py", "config/constants.py"]
KOSPI = "KOSPI"
KOSPI20_LAG = 20                                                 # [W2]:26 KOSPI20 = 직전 거래일 ÷ 20거래일 전 − 1

# ── §2·§5-1 창 🔒 ─────────────────────────────────────────────────────────
A_START, A_END = date(2025, 4, 17), date(2026, 9, 23)          # 층 A 진입일 · A_END = ledger W_END(보유 경로 끝)
B_START = date(2026, 10, 6)                                      # 층 B D+1 ≥ 10-06
U_PRINT_ONLY_FROM = date(2026, 6, 1)                             # 미관측 창 06-01~09-23 = 인쇄만
VINTAGE_CUT = date(2026, 7, 3)                                   # G10 vintage_m4 = scan_date < 07-03([L]:150)
# 분봉 수집 시대(EXPERT_SYSTEM Q1·모른다 · fadd037 top300 = 06-23) · 그 뒤 snap100
ERA_CUTS = ((date(2026, 6, 23), "m533"), (B_START, "top300"))

MAIN_ARMS = ["R0", "R0_0905", "R1", "R3", "R7", "R6", "R4", "R5"]
INDEP_ARMS = ["R0", "H2_HIST", "H_PLUS2"]


@dataclass(frozen=True)
class Win:
    layer: str
    start: date
    end: Optional[date]                  # None = asof 기준 보유기한 이전(C2)
    arms: Tuple[str, ...]
    sealed_after_explore: bool


WINDOWS: Dict[str, Win] = {
    "E": Win("A", A_START, date(2025, 12, 31), tuple(MAIN_ARMS), False),
    "C": Win("A", date(2026, 1, 1), A_END, tuple(MAIN_ARMS), True),
    "C2": Win("B", B_START, None, tuple(MAIN_ARMS), True),
    "U": Win("A", A_START, A_END, tuple(INDEP_ARMS), True),      # 수정 1 결정 4-나 — E 결과 해시 커밋 뒤
}

# candidate_ledger/run.py:67-79 STATS 값(🔒 PREREG 585b651) 사본 — ledger run_meta.json exit_rules 로 대조(guard_spec)
STRATS: Dict[str, Dict[str, Any]] = {
    "daytrading_3methods_breakout": dict(short="daytrading", tp=0.10, sl=0.10, max_hold=10, band=(None, 0.03)),
    "minervini_volume_dryup": dict(short="minervini", tp=0.12, sl=0.08, max_hold=20, band=(None, 0.03)),
}
UNSUPPORTED = {"book_pullback_ma20": "데이터 청산 trail_ma(진입가 의존) 탐침에 strategies import 필요 — 실행기 밖"}
NO_DATA_EXIT = {"tp", "sl", "max_hold", "open", ""}              # ledger exit_reason 이 이 안이면 데이터 청산 없음
CORP_TYPES = ("split", "bonus_issue", "rights_issue")            # §4-1 P2 분할·병합·권리락(replayer 와 같은 3종)
TV_BUCKETS = ((300, "le300"), (600, "301_600"), (1000, "601_1000"))
VI_GAP_MIN, VI_JUMP = 2, 0.03                                    # 설계 10-08 §3-6 vi_suspect

SEED = 20261111
W_FAKE = 4
FAKE_TIMING_R0 = 100                                             # 가짜 시점 규칙 k 의 시드 r = 100 + k
FAKE_U_LO, FAKE_U_HI = 2, 60                                     # 09:02~10:00 분(행 번호 · 양끝 포함)

LOT_COLS = [
    "lot_id", "window", "layer", "era", "print_only", "strategy", "scan_date", "entry_date", "stock_code", "market",
    "rank",
    "ref_close", "band_lo", "band_hi", "band_ok_open", "tv_rank_d", "tv_bucket_d", "tv_rank_d1", "tv_bucket_d1",
    "month", "kospi20", "kospi_day_ret",
    "arm", "family", "kind", "label", "entered", "skip_reason", "undetermined_minutes",
    "entry_time", "px_raw", "px_tick", "qty", "exit_date", "exit_time", "exit_reason", "exit_phase", "hold_days",
    "exit_px", "ret", "close_ret", "k0_flags", "exit_flags", "sl_tp_same_minute", "gap_tp_overridden",
    "b_time", "b_px", "b_missing", "b_on_empty", "b_ret", "c_time", "c_px", "c_ret",
    "main_excl", "excl_reason", "daily_fallback", "market_gap_day", "long_gap", "long_gap_minutes", "filled_minutes",
    "zero_volume_minutes", "n_minute_rows", "has_1530", "open_gap_flag", "open_gap_pct", "vi_suspect", "vintage_m4",
    "corp_event", "adj_null_prev", "adj_null_entry", "prev_day_volume", "ledger_flags",
]
FAKE_COLS = ["lot_id", "fake_k", "u_idx", "entered", "entry_time", "ret"]


def log(msg: str = "") -> None:
    print(msg, file=sys.stderr, flush=True)


# ── candidate_ledger/run.py 사본(같은 본문) ─────────────────────────────────
def _fmt(x: Any) -> str:
    if x is None:
        return ""
    if isinstance(x, (bool, np.bool_)):
        return "True" if x else "False"
    if isinstance(x, (float, np.floating)):
        return "" if x != x else format(float(x), ".15g")
    if isinstance(x, date):
        return x.isoformat()
    return str(x)


def _atomic_write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=path.stem + ".", suffix=".tmp", dir=str(path.parent))
    with os.fdopen(fd, "w", encoding="utf-8", newline="") as fh:
        fh.write(text)
    os.replace(tmp, path)


def git_sha() -> str:
    return subprocess.run(["git", "rev-parse", "HEAD"], cwd=str(ROOT), capture_output=True, text=True,
                          check=True).stdout.strip()


def build_path(cal: Sequence[date], cal_idx: Dict[date, int], bars: Dict[date, X.Bar], entry: date, max_hold: int,
               end: date) -> List[Tuple[int, date, Optional[X.Bar]]]:
    """[(k, 날짜, 봉|None)] · path[0] = 진입일 · k ≥ max_hold 인 첫 «봉 있는» 날에서 자른다 · `end` 뒤는 없음."""
    out: List[Tuple[int, date, Optional[X.Bar]]] = []
    for k, d in enumerate(cal[cal_idx[entry]:]):
        if d > end:
            break
        b = bars.get(d)
        out.append((k, d, b))
        if b is not None and k >= max_hold:
            break
    return out


def sha256_file(p: Path) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def csv_text(cols: Sequence[str], rows: Iterable[Dict[str, Any]]) -> str:
    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=list(cols), extrasaction="ignore", lineterminator="\n")
    w.writeheader()
    for r in rows:
        w.writerow({k: _fmt(r.get(k)) for k in cols})
    return buf.getvalue()


# ── 로트 ──────────────────────────────────────────────────────────────────
@dataclass
class Lot:
    layer: str
    strategy: str
    scan_date: date
    entry_date: date
    code: str
    rank: str
    ref_close: float
    band_lo: Optional[float]
    band_hi: Optional[float]
    band_ok_open: Optional[bool] = None
    ledger_flags: str = ""
    corp_event: bool = False
    tv_rank_d: Optional[float] = None    # 신호일 D 순위(주 · 수정 1 결정 2)
    tv_rank_d1: Optional[float] = None   # 진입일 D+1 순위(참고 · 패널 q_bias 기준)
    kospi20: Optional[float] = None      # %(국면 칸 · [W2]:26)
    kospi_day_ret: Optional[float] = None   # 진입일 KOSPI 등락 %(±3% 분할 인쇄)

    @property
    def key(self) -> Tuple[str, date]:
        return (self.code, self.entry_date)

    @property
    def lot_id(self) -> str:
        return f"{self.strategy}|{self.scan_date.isoformat()}|{self.code}"


def _opt_float(s: str) -> Optional[float]:
    return float(s) if s not in ("", None) else None


def guard_spec(folders: Sequence[str], ledger_meta: Dict[str, Any]) -> None:
    """ledger run_meta exit_rules ↔ STRATS(tp·sl·max_hold) · ma20 등 미지원 전략 거부."""
    bad = [f"{f}: {UNSUPPORTED[f]}" for f in folders if f in UNSUPPORTED]
    bad += [f"모르는 전략 {f}" for f in folders if f not in STRATS and f not in UNSUPPORTED]
    for f in folders:
        if f in STRATS:
            got = ledger_meta.get("exit_rules", {}).get(f, {})
            want = (STRATS[f]["tp"], STRATS[f]["sl"], STRATS[f]["max_hold"])
            if (got.get("tp"), got.get("sl"), got.get("max_hold_days")) != want:
                bad.append(f"{f}: ledger exit_rules {got} ≠ {want}")
    if bad:
        raise SystemExit("🔴 가드: " + " · ".join(bad))


def band_for(folder: str, ref: float) -> Tuple[Optional[float], Optional[float]]:
    """라이브 `BaseStrategy._entry_band` 식(lo = ref×(1−down) · hi = ref×(1+up) · None 쪽 열림) — 층 B 용."""
    down, up = STRATS[folder]["band"]
    return (ref * (1.0 - down) if down is not None else None, ref * (1.0 + up) if up is not None else None)


def lots_from_ledger(rows: Iterable[Dict[str, str]], folders: Sequence[str], start: date, end: date) -> List[Lot]:
    """층 A — ledger.csv 행 중 진입일 ∈ [start, end] · 데이터 청산 사유가 보이면 중단 · 밴드 식 대조."""
    out: List[Lot] = []
    for r in rows:
        f = r["strategy"]
        if f not in folders or not r.get("entry_date"):
            continue
        d1 = date.fromisoformat(r["entry_date"])
        if not start <= d1 <= end:
            continue
        if r.get("exit_reason", "") not in NO_DATA_EXIT:
            raise SystemExit(f"🔴 가드: {f} 에 데이터 청산 사유 {r['exit_reason']!r} — 탐침 없이 재현 불가")
        ref = float(r["ref_close"])
        lo, hi = _opt_float(r["band_lo"]), _opt_float(r["band_hi"])
        want = band_for(f, ref)
        if any((a is None) != (b is None) or (a is not None and abs(a - b) > 1e-6 * ref)
               for a, b in zip((lo, hi), want)):
            raise SystemExit(f"🔴 가드: 밴드 식 불일치 {f} {r['scan_date']} {r['stock_code']} ({lo},{hi}) ≠ {want}")
        ok = r.get("band_ok", "")
        out.append(Lot("A", f, date.fromisoformat(r["scan_date"]), d1, r["stock_code"], r["rank"], ref, lo, hi,
                       None if ok == "" else ok == "True", r.get("flags", "")))
    return out


def lots_from_snapshots(snap: Iterable[Tuple[str, date, str, Any]], folders: Sequence[str], cal: Sequence[date],
                        daily: Dict[str, Dict[date, X.Bar]], start: date, end_of: Dict[str, date]
                        ) -> Tuple[List[Lot], Dict[str, int]]:
    """층 B — (strategy, scan_date, code, rank) → D+1 = 달력 다음 거래일 · start ≤ D+1 ≤ end_of[전략] ·
    ref = D 일봉 종가 · 밴드 = 층 A 와 같은 식. 같은 (전략, D, 종목) 중복은 첫 순위만(건수 인쇄)."""
    counts = {"dup": 0, "no_ref_close": 0, "out_of_window": 0}
    seen: Set[Tuple[str, date, str]] = set()
    out: List[Lot] = []
    for f, sd, code, rank in sorted(snap, key=lambda t: (t[0], t[1], int(t[3]) if t[3] is not None else 10**9, t[2])):
        if f not in folders:
            continue
        k = (f, sd, str(code))
        if k in seen:
            counts["dup"] += 1
            continue
        seen.add(k)
        i = bisect_left(cal, sd)
        j = i + 1 if i < len(cal) and cal[i] == sd else i
        d1 = cal[j] if j < len(cal) else None
        if d1 is None or not start <= d1 <= end_of[f]:
            counts["out_of_window"] += 1
            continue
        b0 = daily.get(str(code), {}).get(sd)
        if b0 is None or not b0.close > 0:
            counts["no_ref_close"] += 1
            continue
        lo, hi = band_for(f, float(b0.close))
        b1 = daily.get(str(code), {}).get(d1)
        ok = None if b1 is None else bool((lo is None or b1.open >= lo) and (hi is None or b1.open <= hi))
        out.append(Lot("B", f, sd, d1, str(code), str(rank), float(b0.close), lo, hi, ok, ""))
    return out, counts


def era_of(d1: date) -> str:
    for cut, name in ERA_CUTS:
        if d1 < cut:
            return name
    return "snap100"


def tv_bucket(rank: Optional[float]) -> str:
    if rank is None or rank != rank:
        return ""
    for hi, name in TV_BUCKETS:
        if rank <= hi:
            return name
    return "gt1000"


def corp_flags(lots: Sequence[Lot], events: Dict[str, List[date]]) -> None:
    """R5 corp_event(🔒 §4-1 P2) = `corp_events` event_date ∈ [D, D+1] · 분할·병합·권리락."""
    for lot in lots:
        ds = events.get(lot.code, [])
        i = bisect_left(ds, lot.scan_date)
        lot.corp_event = i < len(ds) and ds[i] <= lot.entry_date


def vi_suspect(bars: np.ndarray, observed: np.ndarray) -> bool:
    """설계 10-08 §3-6 — 거래 분 사이 빈 분 ≥2 뒤 첫 거래 분 시가가 직전 거래 분 종가 대비 ±3% 이상(표시만)."""
    idx = np.flatnonzero(observed[: E.N_CONT])
    for a, b in zip(idx[:-1], idx[1:]):
        if b - a - 1 >= VI_GAP_MIN:
            c, o = float(bars[a, E.F_CLOSE]), float(bars[b, E.F_OPEN])
            if c > 0 and abs(o / c - 1.0) >= VI_JUMP:
                return True
    return False


# ── 체결 모델 · 청산 ────────────────────────────────────────────────────────
def never_probe(_pos: X.Pos, _day: date) -> Optional[str]:
    """dt·minervini — 데이터 청산 없음(ledger exit_reason ⊂ {tp, sl, max_hold, open} 가드 · lots_from_ledger)."""
    return None


def finish(bars: np.ndarray, ctx: E.DayCtx, fill_idx: int, px: float, scan_after: int, rules: X.ExitRules,
           path: Sequence[Tuple[int, date, Optional[X.Bar]]], probe: X.Probe,
           day_exit: Optional[E.DayExit] = None) -> Dict[str, Any]:
    """체결 1건 → k=0 탐침 1회 → 분 단위 청산(scan_after+1 분부터) → 미청산이면 continue_daily."""
    pos = E.make_pos(ctx, fill_idx, px)
    r = E.k0_probe(pos, probe)
    if r:
        return dict(exit_reason=r, exit_date=ctx.day, exit_time=E.idx_to_time(fill_idx), exit_px=px, ret=0.0,
                    exit_phase=X.PHASE_ENTRY, hold_days=0, k0_flags=[X.FLAG_K0_DATA], exit_flags=[])
    dx = day_exit if day_exit is not None else E.simulate_day_exit(bars, scan_after, px, rules.tp, rules.sl)
    if dx.closed:
        return dict(exit_reason=dx.reason, exit_date=ctx.day, exit_time=dx.time, exit_px=dx.px, ret=dx.ret_pct,
                    exit_phase="k0_minute", hold_days=0, k0_flags=list(dx.flags), exit_flags=[])
    ex = E.continue_daily(pos, rules, path, probe)
    return dict(exit_reason=ex.reason, exit_date=ex.exit_date, exit_time="", exit_px=ex.price, ret=ex.ret_pct,
                exit_phase=ex.phase, hold_days=ex.hold_days, k0_flags=list(dx.flags), exit_flags=list(ex.flags))


def arm_result(bars: np.ndarray, ctx: E.DayCtx, rule: R.Rule, rules: X.ExitRules,
               path: Sequence[Tuple[int, date, Optional[X.Bar]]], probe: X.Probe,
               d0_close: Optional[float]) -> Dict[str, Any]:
    """시점·기준 arm 1개(거르기는 R0_0905 결과 재사용 · simulate_arms) — 모델 a·b·c."""
    res = E.run_day(bars, ctx, rule.pred, rules.tp, rules.sl, base=rule.base)
    out: Dict[str, Any] = dict(entered=res.entered, skip_reason=res.skip_reason,
                               undetermined_minutes=res.undetermined_minutes, ret=0.0, b_ret=0.0, c_ret=0.0)
    if res.entered:
        f = res.entry
        out.update(entry_time=f.time, px_raw=f.px_raw, px_tick=f.px, qty=E.arm_b_qty(f.px).qty)
        out.update(finish(bars, ctx, f.idx, f.px, f.idx, rules, path, probe, day_exit=res.exit))
        out["close_ret"] = (d0_close / f.px - 1.0) * 100.0 if d0_close else None
        flags = out["k0_flags"]
        out["sl_tp_same_minute"] = E.FLAG_SL_TP_SAME in flags
        out["gap_tp_overridden"] = E.FLAG_GAP_TP_OVERRIDDEN in flags
        if f.px_next_open is None:
            out.update(b_missing=True, b_ret=None)
        else:
            b = finish(bars, ctx, f.idx + 1, f.px_next_open, f.idx, rules, path, probe)
            out.update(b_missing=False, b_time=E.idx_to_time(f.idx + 1), b_px=f.px_next_open, b_ret=b["ret"],
                       b_on_empty=not float(bars[f.idx + 1, E.F_VOL]) > 0)   # 거래 없는 분(평평 채움) 시가 체결
    else:
        out["b_missing"] = False
    if res.band_edge is not None:
        g = res.band_edge
        c = finish(bars, ctx, g.idx, g.px, g.idx, rules, path, probe)
        out.update(c_time=g.time, c_px=g.px, c_ret=c["ret"])
    out["k0_flags"] = ";".join(out.get("k0_flags", []))
    out["exit_flags"] = ";".join(out.get("exit_flags", []))
    return out


def simulate_arms(bars: np.ndarray, ctx: E.DayCtx, arms: Sequence[str], rules: X.ExitRules,
                  path: Sequence[Tuple[int, date, Optional[X.Bar]]], probe: X.Probe,
                  d0_close: Optional[float]) -> Dict[str, Dict[str, Any]]:
    """로트 1개 × arm 들. 거르기(R4·R5) = R0_0905 결과 1벌 + 라벨(재계산 없음 · rules.run_rule 의 run 판)."""
    out: Dict[str, Dict[str, Any]] = {}
    r0905: Optional[Dict[str, Any]] = None
    for arm in arms:
        rule = R.REGISTRY[arm]
        if rule.kind == "filter":
            if r0905 is None:
                r0905 = arm_result(bars, ctx, R.BASELINE_0905, rules, path, probe, d0_close)
            res = dict(r0905)
            res["label"] = E.label_day(bars, ctx, rule.label)
        else:
            res = arm_result(bars, ctx, rule, rules, path, probe, d0_close)
            if arm == E.BASE_R0_0905:
                r0905 = dict(res)
        out[arm] = res
    return out


def band_minutes(bars: np.ndarray, ctx: E.DayCtx) -> np.ndarray:
    """R0 와 같은 순서(종가 → round_to_tick → 밴드)로 밴드 안인 분(09:02~15:19) 행 번호 — 가짜 시점 규칙 빠른 길."""
    out = [t for t in range(E.IDX_ENTRY_START, E.IDX_ENTRY_END + 1)
           if np.isfinite(bars[t, E.F_CLOSE]) and bars[t, E.F_CLOSE] > 0
           and E.in_band(E.round_to_tick(float(bars[t, E.F_CLOSE])), ctx)]
    return np.asarray(out, dtype=np.int64)


def fake_timing_rets(bars: np.ndarray, ctx: E.DayCtx, u_idx: int, rules: X.ExitRules,
                     path: Sequence[Tuple[int, date, Optional[X.Bar]]], probe: X.Probe,
                     inband: Optional[np.ndarray] = None) -> Dict[str, Any]:
    """§5-3 가짜 시점 규칙 ② — u 분 이전 진입 금지(기준 R0 · 모델 a 만) = 밴드 안 분 중 ≥ u 인 첫 분.

    `run_day(pred = t ≥ u)` 와 같은 결과(테스트로 고정) — 가짜 100개 × 로트마다 분 단위 view 를 다시 만들지 않는다."""
    inb = band_minutes(bars, ctx) if inband is None else inband
    j = int(np.searchsorted(inb, u_idx, side="left"))
    if j >= len(inb):
        return dict(entered=False, ret=0.0)
    t = int(inb[j])
    px = E.round_to_tick(float(bars[t, E.F_CLOSE]))
    fin = finish(bars, ctx, t, px, t, rules, path, probe)
    return dict(entered=True, entry_time=E.idx_to_time(t), ret=fin["ret"])


# ── DB(SELECT 만) ─────────────────────────────────────────────────────────
def load_daily(conn, codes: Sequence[str], start: date, end: date, info: Optional[Dict[str, Any]] = None
               ) -> Dict[str, Dict[date, X.Bar]]:
    """일봉 → `replayer.loader.normalize_prices`(ledger 와 같은 위생) → {code: {날짜: Bar}} · `info` 에 원행 digest·
    normalize 건수(N6)."""
    import pandas as pd

    from backtest.concept_axes.replayer import loader as LD
    rows = D._fetch(conn, "SELECT stock_code, date, open, high, low, close, volume FROM daily_prices "
                          "WHERE stock_code = ANY(%s) AND date BETWEEN %s AND %s",
                    (sorted(set(codes)), start.isoformat(), end.isoformat()))
    df = LD.normalize_prices(pd.DataFrame(rows, columns=["stock_code", "date", "open", "high", "low", "close",
                                                         "volume"]))
    if info is not None:
        info.update(daily_rows=len(rows), daily_rows_sha256=digest_rows(rows),
                    normalize_counts=df.attrs.get("normalize_counts"))
    out: Dict[str, Dict[date, X.Bar]] = {}
    for c, t, o, h, lo, cl in zip(df["stock_code"], df["date"], df["open"], df["high"], df["low"], df["close"]):
        d = t.date()
        out.setdefault(str(c), {})[d] = X.Bar(d, float(o), float(h), float(lo), float(cl))
    return out


def load_tv_rank(conn, days: Sequence[date]) -> Dict[Tuple[str, date], float]:
    """그날 전 `daily_prices` 행의 `trading_value` 내림차순 순위(평균 동순위) — 패널 q_bias.py:14-15 와 같은 식.
    주 = 신호일 D · 참고 = 진입일 D+1(수정 1 결정 2) — 호출자가 날짜를 골라 두 번 부른다."""
    import pandas as pd
    rows = D._fetch(conn, "SELECT stock_code, date, trading_value FROM daily_prices WHERE date = ANY(%s)",
                    (sorted({d.isoformat() for d in days}),))
    df = pd.DataFrame(rows, columns=["stock_code", "date", "tv"])
    df["tv"] = pd.to_numeric(df["tv"], errors="coerce")
    df["rk"] = df.groupby("date")["tv"].rank(ascending=False)
    return {(str(c), date.fromisoformat(str(d)[:10])): float(r)
            for c, d, r in zip(df["stock_code"], df["date"], df["rk"]) if r == r}


def load_corp_events(conn, start: date, end: date, info: Optional[Dict[str, Any]] = None) -> Dict[str, List[date]]:
    rows = D._fetch(conn, "SELECT stock_code, event_date FROM corp_events WHERE event_type = ANY(%s) "
                          "AND event_date BETWEEN %s AND %s", (list(CORP_TYPES), start, end))
    if info is not None:
        info.update(corp_events_rows=len(rows), corp_events_sha256=digest_rows(rows))
    out: Dict[str, List[date]] = {}
    for c, d in rows:
        out.setdefault(str(c), []).append(d if isinstance(d, date) else date.fromisoformat(str(d)[:10]))
    return {c: sorted(v) for c, v in out.items()}


def load_kospi(conn, start: date, end: date) -> Dict[date, float]:
    rows = D._fetch(conn, "SELECT date, close FROM daily_prices WHERE stock_code = %s AND date BETWEEN %s AND %s",
                    (KOSPI, start.isoformat(), end.isoformat()))
    return {date.fromisoformat(str(d)[:10]): float(c) for d, c in rows if c is not None and float(c) > 0}


def regime_cols(lots: Sequence[Lot], cal: Sequence[date], kospi: Dict[date, float]) -> None:
    """KOSPI20 = 진입일 직전 거래일 종가 ÷ 그 20거래일 전 종가 − 1([W2]:26 · 매수일 = 진입일) · 진입일 등락(%)."""
    for x in lots:
        i = bisect_left(cal, x.entry_date)
        if i < 1 or i >= len(cal) or cal[i] != x.entry_date:
            continue
        p = kospi.get(cal[i - 1])
        p20 = kospi.get(cal[i - 1 - KOSPI20_LAG]) if i - 1 - KOSPI20_LAG >= 0 else None
        x.kospi20 = (p / p20 - 1.0) * 100.0 if p and p20 else None
        c = kospi.get(cal[i])
        x.kospi_day_ret = (c / p - 1.0) * 100.0 if c and p else None


def load_snapshots(conn, folders: Sequence[str], start: date, end: date) -> List[Tuple[str, date, str, Any]]:
    rows = D._fetch(conn, "SELECT strategy, scan_date, stock_code, rank_in_snapshot FROM screener_snapshots "
                          "WHERE strategy = ANY(%s) AND scan_date BETWEEN %s AND %s", (list(folders), start, end))
    return [(str(f), sd if isinstance(sd, date) else date.fromisoformat(str(sd)[:10]), str(c), rk)
            for f, sd, c, rk in rows]


class GapCache:
    """G5 분모(그날 `minute_candles` 전 종목의 20분+ 빈 구간)를 날짜별로 캐시 — 시장 구분과 무관한 원행만 담는다.

    파일 = {"version": 2, "days": {"YYYYMMDD": {"fp": [행수, 종목 수], "rows": [[code, [[lo, hi], …] | null], …]}}} ·
    날짜 묶음(20일)마다 원자적 저장 · 버전이 다르면 통째로 무시(다시 조회) · `verify()` = 끝에 지문 재조회 대조(A2)."""

    VERSION = 2
    FP_SQL = ("SELECT trade_date, count(*), count(DISTINCT stock_code) FROM minute_candles WHERE trade_date = ANY(%s) "
              "GROUP BY 1")

    def __init__(self, conn, path: Path):
        self.conn, self.path = conn, path
        self.days: Dict[str, Dict[str, Any]] = {}
        if path.exists():
            doc = json.loads(path.read_text(encoding="utf-8"))
            if doc.get("version") == self.VERSION:
                self.days = doc.get("days", {})
        self.hits = self.misses = 0
        self.fetch_secs = 0.0
        self.used: List[str] = []

    def _save(self) -> None:
        _atomic_write(self.path, json.dumps({"version": self.VERSION,
                                             "days": {k: self.days[k] for k in sorted(self.days)}},
                                            ensure_ascii=False, separators=(",", ":")))

    def fingerprints(self, keys: Sequence[str]) -> Dict[str, List[int]]:
        got = {str(td): [int(n), int(c)] for td, n, c in D._fetch(self.conn, self.FP_SQL, (list(keys),))}
        return {k: got.get(k, [0, 0]) for k in keys}

    def rows(self, days: Iterable[date]) -> List[Tuple[Any, Any, Any]]:
        want = sorted({d.strftime("%Y%m%d") for d in days})
        self.used = sorted(set(self.used) | set(want))
        miss = [k for k in want if k not in self.days]
        self.hits += len(want) - len(miss)
        self.misses += len(miss)
        for i in range(0, len(miss), D.GAP_DAYS_BATCH):
            part = miss[i: i + D.GAP_DAYS_BATCH]
            t0 = time.perf_counter()
            fps = self.fingerprints(part)
            got = D.fetch_market_gap_rows(self.conn, [date(int(k[:4]), int(k[4:6]), int(k[6:])) for k in part])
            self.fetch_secs += time.perf_counter() - t0
            new: Dict[str, List[List[Any]]] = {k: [] for k in part}
            for td, code, gaps in got:
                new[str(td)].append([str(code), [[int(a), int(b)] for a, b in gaps] if gaps else None])
            for k, v in new.items():
                self.days[k] = {"fp": fps[k], "rows": sorted(v, key=lambda x: x[0])}
            self._save()
            log(f"  [G5 캐시] {part[0]}~{part[-1]} {len(part)}일 · {time.perf_counter() - t0:.0f}s "
                f"(남은 {len(miss) - i - len(part)}일)")
        return [(k, c, g) for k in want for c, g in self.days[k]["rows"]]

    def verify(self) -> List[str]:
        """이번 실행이 쓴 날짜의 지문(행수·종목 수)을 DB 에 다시 물어 캐시와 다른 날짜 목록(빈 목록 = 낡지 않음)."""
        now = self.fingerprints(self.used) if self.used else {}
        return [k for k in self.used if now.get(k) != self.days[k]["fp"]]


def rows_digest(rows: Sequence[Tuple[Any, Any, Any]]) -> str:
    return hashlib.sha256(json.dumps(sorted([str(a), str(b), g] for a, b, g in rows),
                                     separators=(",", ":")).encode()).hexdigest()


def digest_rows(rows: Iterable[Sequence[Any]]) -> str:
    """입력 행 집합의 정렬 digest(N6) — 값은 `_fmt` 문자열로 맞춘다(순서 무관)."""
    lines = sorted("|".join(_fmt(v) for v in r) for r in rows)
    return hashlib.sha256("\n".join(lines).encode("utf-8")).hexdigest()


# ── 행 조립 ──────────────────────────────────────────────────────────────
def lot_base_row(window: str, lot: Lot, market: str, print_only: bool) -> Dict[str, Any]:
    return dict(lot_id=lot.lot_id, window=window, layer=lot.layer, era=era_of(lot.entry_date), print_only=print_only,
                strategy=lot.strategy, scan_date=lot.scan_date, entry_date=lot.entry_date, stock_code=lot.code,
                market=market, rank=lot.rank, ref_close=lot.ref_close, band_lo=lot.band_lo, band_hi=lot.band_hi,
                band_ok_open=lot.band_ok_open, tv_rank_d=lot.tv_rank_d, tv_bucket_d=tv_bucket(lot.tv_rank_d),
                tv_rank_d1=lot.tv_rank_d1, tv_bucket_d1=tv_bucket(lot.tv_rank_d1), kospi20=lot.kospi20,
                kospi_day_ret=lot.kospi_day_ret, month=lot.entry_date.strftime("%Y-%m"),
                vintage_m4=lot.scan_date < VINTAGE_CUT,
                corp_event=lot.corp_event, ledger_flags=lot.ledger_flags)


def meta_cols(m: D.DayMeta) -> Dict[str, Any]:
    return dict(market_gap_day=m.market_gap_day, long_gap=m.long_gap, long_gap_minutes=m.long_gap_minutes,
                filled_minutes=m.filled_minutes, zero_volume_minutes=m.zero_volume_minutes, n_minute_rows=m.n_rows,
                has_1530=m.has_1530, open_gap_flag=m.open_gap_flag, open_gap_pct=m.open_gap_pct,
                adj_null_prev=m.adj_null_prev, adj_null_entry=m.adj_null_entry, prev_day_volume=m.prev_day_volume)


def build_rows(window: str, win: Win, lots: Sequence[Lot], bundle: D.MinuteBundle, daily: Dict[str, Dict[date, X.Bar]],
               cal: Sequence[date], path_end: Dict[str, date], market_of: Dict[str, str],
               probe: X.Probe = never_probe, fakes: int = 0, simulate: bool = True
               ) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]], Dict[str, int]]:
    """로트 × arm 행 + 가짜 시점 규칙 행(E) + 로트 단위 플래그 건수(효과 아님). `simulate=False` = 건수만(배관)."""
    cal_idx = {d: i for i, d in enumerate(cal)}
    rows: List[Dict[str, Any]] = []
    fake_rows: List[Dict[str, Any]] = []
    cnt: Dict[str, int] = {}

    def inc(k: str, v: bool = True) -> None:
        cnt[k] = cnt.get(k, 0) + int(bool(v))

    lots = sorted(lots, key=lambda x: (x.scan_date, x.strategy, x.code))
    sim_lots: List[Tuple[Lot, np.ndarray, E.DayCtx, X.ExitRules, list]] = []
    for lot in lots:
        inc("lots")
        spec = STRATS[lot.strategy]
        rules = X.ExitRules(spec["tp"], spec["sl"], spec["max_hold"], "minute_rules STRATS")
        print_only = window == "U" and lot.entry_date >= U_PRINT_ONLY_FROM
        base = lot_base_row(window, lot, market_of.get(lot.code, D.MARKET_UNKNOWN), print_only)
        inc("vintage_m4", base["vintage_m4"])
        inc("corp_event", lot.corp_event)
        inc("print_only", print_only)
        toks = set(lot.ledger_flags.split(";")) if lot.ledger_flags else set()
        for tok in ("impossible_bar", "survivor_universe"):       # G10 건수(N5)
            inc(tok, tok in toks)
        try:
            i = bundle.index(lot.key)
        except KeyError:
            why = bundle.excluded.get(lot.key, D.EXCL_NO_MINUTE)
            inc(f"excl_{why}")
            base.update(excl_reason=why, daily_fallback=why == D.EXCL_NO_MINUTE, main_excl=why)
            rows += [dict(base, arm=a, family=R.REGISTRY[a].family, kind=R.REGISTRY[a].kind) for a in win.arms]
            continue
        m = bundle.meta[i]
        bars = np.asarray(bundle.bars[i], dtype=np.float64)
        base.update(meta_cols(m), daily_fallback=False, vi_suspect=vi_suspect(bars, bundle.observed[i]))
        excl = [k for k, on in (("market_gap_day", m.market_gap_day), ("open_gap", m.open_gap_flag)) if on]
        base["main_excl"] = ";".join(excl)
        for k in ("market_gap_day", "long_gap", "open_gap_flag", "adj_null_prev", "adj_null_entry", "has_1530",
                  "vi_suspect"):
            inc(k, base[k])
        inc("minute_lots")
        inc("n_rows_lt300", m.n_rows < 300)
        inc("band_ok_open_minute", lot.band_ok_open is True)
        if not simulate:
            continue
        ctx = E.DayCtx(lot.code, lot.entry_date, band_lo=lot.band_lo, band_hi=lot.band_hi, prev_close=lot.ref_close,
                       prev_day_volume=m.prev_day_volume, corp_event=lot.corp_event)
        bars_d = daily.get(lot.code, {})
        path = build_path(cal, cal_idx, bars_d, lot.entry_date, rules.max_hold_days, path_end[lot.layer])
        d0 = bars_d.get(lot.entry_date)
        res = simulate_arms(bars, ctx, win.arms, rules, path, probe, d0.close if d0 is not None else None)
        for a in win.arms:
            rule = R.REGISTRY[a]
            rows.append(dict(base, arm=a, family=rule.family, kind=rule.kind, **res[a]))
        sim_lots.append((lot, bars, ctx, rules, path))
    inbands = [band_minutes(bars, ctx) for _, bars, ctx, _, _ in sim_lots] if fakes else []
    for k in range(fakes):
        rng = np.random.default_rng([SEED, W_FAKE, FAKE_TIMING_R0 + k])
        us = rng.integers(FAKE_U_LO, FAKE_U_HI + 1, size=len(sim_lots))
        for (lot, bars, ctx, rules, path), u, inb in zip(sim_lots, us, inbands):
            fr = fake_timing_rets(bars, ctx, int(u), rules, path, probe, inb)
            fake_rows.append(dict(lot_id=lot.lot_id, fake_k=k, u_idx=int(u), **fr))
    return rows, fake_rows, cnt


# ── main ─────────────────────────────────────────────────────────────────
def _resolve_folders(arg: str) -> List[str]:
    short = {v["short"]: k for k, v in STRATS.items()}
    short["ma20"] = "book_pullback_ma20"
    return [short.get(s.strip(), s.strip()) for s in arg.split(",") if s.strip()]


def _git_run(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["git", *args], cwd=str(REPO), capture_output=True, text=True)


def check_explore(sha: Optional[str], git: Callable[..., subprocess.CompletedProcess] = _git_run,
                  doc: Optional[Path] = None, code_now: Optional[Dict[str, str]] = None,
                  results_dir: Optional[Path] = None) -> Dict[str, str]:
    """§8 순서 관문(A6) — `RESULTS_explore.md` 가 ① git 추적 ② HEAD 와 같음(미커밋 변경 없음) ③ sha256 = 인자.
    반환 = {sha256, commit(그 파일을 마지막으로 바꾼 커밋)}."""
    doc = EXPLORE_DOC if doc is None else doc
    got = check_committed(doc, git)
    if not sha or sha.lower() != got["sha256"]:
        raise SystemExit(f"🔴 §8 순서: --explore-sha256 ≠ {doc.name} sha256 {got['sha256']}")
    from .analyze import verify_prior                              # G1 — 관문 거친 E 문서 · 같은 코드 · B
    meta_e = (results_dir or RESULTS) / "E" / "run_meta.json"
    verify_prior(doc.with_suffix(".json"), doc, git, code_now=code_hashes() if code_now is None else code_now,
                 run_meta_expect={"E": meta_e})
    return got


def check_committed(doc: Path, git: Callable[..., subprocess.CompletedProcess] = _git_run) -> Dict[str, str]:
    """앞 단계 산출 문서 관문 — 파일 있음 ∧ git 추적 ∧ HEAD 와 같음 → {sha256, commit}(A6 · NB2)."""
    if not doc.exists():
        raise SystemExit(f"🔴 §8 순서: {doc.name} 가 없다 — 앞 단계 결과 커밋 뒤에만")
    rel = doc.resolve().relative_to(REPO.resolve()).as_posix()
    if git("ls-files", "--error-unmatch", rel).returncode != 0:
        raise SystemExit(f"🔴 §8 순서: {rel} 가 git 에 추적되지 않는다(커밋 필요)")
    if git("diff", "--quiet", "HEAD", "--", rel).returncode != 0:
        raise SystemExit(f"🔴 §8 순서: {rel} 에 커밋 안 된 변경이 있다")
    return {"sha256": sha256_file(doc), "commit": git("log", "-1", "--format=%H", "--", rel).stdout.strip()}


def dirty_paths(porcelain: str, ignore_prefix: str = CLEAN_IGNORE) -> List[str]:
    """`git status --porcelain` 출력 → 결과 폴더(results·cache)를 뺀 변경·미추적 경로(B2)."""
    out = []
    for line in porcelain.splitlines():
        p = line[3:].strip()
        if " -> " in p:
            p = p.split(" -> ", 1)[1]
        p = p.strip('"')
        if p and not p.startswith(ignore_prefix):
            out.append(p)
    return sorted(out)


def require_clean_tree(git: Callable[..., subprocess.CompletedProcess] = _git_run) -> None:
    bad = dirty_paths(git("status", "--porcelain", "--untracked-files=all").stdout)
    if bad:
        raise SystemExit("🔴 B2: 커밋 안 된 코드로 실창을 돌리지 않는다(run_meta git SHA = 실행 코드) — "
                         + " · ".join(bad[:8]) + (" …" if len(bad) > 8 else ""))


def code_hashes() -> Dict[str, str]:
    """minute_rules/*.py + 의존 파일 sha256 표(B2 · 결과를 낸 코드를 묶는다)."""
    files = sorted(BASE.glob("*.py")) + [ROOT / d for d in CODE_DEPS]
    return {p.relative_to(ROOT).as_posix(): sha256_file(p) for p in files}


def ensure_outside_git(p: Path, what: str,
                       runner: Optional[Callable[[Sequence[str]], subprocess.CompletedProcess]] = None) -> Path:
    """레포 밖 폴더 검사(D3) — 경로(없으면 가장 가까운 있는 부모)가 «어떤» git 작업 트리 안이면 거부.

    경로 목록을 박지 않고 `git -C <부모> rev-parse --show-toplevel` 성공 여부로 판정한다(이 워크트리 · 라이브 트리 ·
    태쏘 워크트리 · 다른 `D:/tmp/kis-wt-*` 모두) · «밖» = rc 128 ∧ «not a git repository» 일 때만(W5)."""
    runner = runner or _git_cmd
    p = Path(p).resolve()
    anc = p
    while not anc.exists() and anc != anc.parent:
        anc = anc.parent
    r = runner(["git", "-C", str(anc), "rev-parse", "--show-toplevel"])
    if r.returncode == 0:
        raise SystemExit(f"🔴 {what}: git 작업 트리 안이다({r.stdout.strip()}) — {p}")
    if not (r.returncode == 128 and "not a git repository" in (r.stderr or "")):   # W5 — 다른 실패는 «밖» 아님
        raise SystemExit(f"🔴 {what}: git 판정 실패(rc {r.returncode} · {(r.stderr or '').strip()[:80]}) — {p}")
    return p


def _git_cmd(cmd: Sequence[str]) -> subprocess.CompletedProcess:
    env = {k: v for k, v in os.environ.items() if k not in ("GIT_DIR", "GIT_WORK_TREE")}
    return subprocess.run(list(cmd), capture_output=True, text=True, env=env)


SEAL_README = "README_봉인등급.txt"
SEAL_NOTE = ("봉인 등급 — 이 폴더의 로트 단위 csv(lots_rule.csv · fake_timing.csv)는 그림자 ② 판정(짝 ≥40 · "
             "매수일 ≥15) 전 열람·인용 금지(사전등록 §4-2·§8 · 수정 1 §7 W1). "
             "E 의 가짜 시점 u=10 = H②-hist · 로트 표로 "
             "«≤09:10/>09:10» 봉인 칸을 다시 낼 수 있다. 보관소 사본도 같은 등급.\n")


def sealed_dir(arg: Optional[str]) -> Path:
    """독립 가족(U) 봉인 폴더 — 인자 > env `KIS_MINUTE_SEALED_DIR` > 기본 · git 작업 트리 안이면 거부(B1·D3)."""
    return ensure_outside_git(Path(arg or os.environ.get(SEALED_ENV) or SEALED_DEFAULT), "B1 봉인 폴더")


def private_dir(arg: Optional[str]) -> Path:
    """E·C·C2 로트 csv 비공개 폴더 — 인자 > env `KIS_MINUTE_PRIVATE_DIR` > 기본 · git 작업 트리 안이면 거부(NB1·D3)."""
    return ensure_outside_git(Path(arg or os.environ.get(PRIVATE_ENV) or PRIVATE_DEFAULT), "NB1 비공개 폴더")


def attach_ranks(lots: Sequence[Lot], tv_d: Dict[Tuple[str, date], float],
                 tv_d1: Dict[Tuple[str, date], float]) -> int:
    """순위 붙이기(결정 2 · R1) — D = (code, scan_date) · D+1 = (code, entry_date). 반환 = D 순위 없는 로트 수(R6)."""
    for x in lots:
        x.tv_rank_d, x.tv_rank_d1 = tv_d.get((x.code, x.scan_date)), tv_d1.get(x.key)
    return sum(1 for x in lots if x.tv_rank_d is None)


def dep_module_files() -> Dict[str, Optional[str]]:
    """실제로 import 된 의존 모듈의 파일 경로(R6 · PYTHONPATH 바꿔치기 흔적)."""
    return {m: (Path(sys.modules[m].__file__).resolve().as_posix() if m in sys.modules
                and getattr(sys.modules[m], "__file__", None) else None) for m in DEP_MODULES}


def window_dates(cal: Sequence[date], today: date, asof_arg: Optional[str], folders: Sequence[str]
                 ) -> Tuple[date, List[date], Dict[str, date], Dict[str, date]]:
    """(asof, asof 까지 달력, 경로 끝 {층: 날짜}, C2 끝 {전략: 날짜}) — 순수 함수(A9).

    asof = 인자 또는 «오늘 전» 마지막 KOSPI 거래일(오늘 행은 장중 미완성일 수 있음) · 층 A 경로 끝 = A_END ·
    층 B = asof · C2 끝 = asof 에서 전략 max_hold 거래일 앞(그 날 진입이면 asof 에 k = max_hold 가 닫힌다)."""
    asof = date.fromisoformat(asof_arg) if asof_arg else max(d for d in cal if d < today)
    cal2 = [d for d in cal if d <= asof]
    if not cal2 or cal2[-1] != asof:
        raise SystemExit(f"🔴 asof {asof} 는 KOSPI 거래일이 아니다")
    ai = len(cal2) - 1
    c2_end = {f: cal2[ai - STRATS[f]["max_hold"]] for f in folders}
    return asof, cal2, {"A": A_END, "B": asof}, c2_end


def main(argv: Optional[Sequence[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="1분 원장 실행기(사전등록 2026-11-11 동결 e2945ee + 수정 1)")
    ap.add_argument("--window", required=True, choices=sorted(WINDOWS))
    ap.add_argument("--strategies", default="daytrading", help="daytrading,minervini (ma20 = 미지원 · 수정 1 4-다)")
    ap.add_argument("--asof", default=None, help="층 B 경로 끝·C2 끝 기준 거래일(기본 = 오늘 전 마지막 KOSPI 거래일)")
    ap.add_argument("--out", default=None)
    ap.add_argument("--plumbing", action="store_true", help="적재·건수·체크섬만(로트 시뮬레이션·csv 없음)")
    ap.add_argument("--fakes", type=int, default=None, help="가짜 시점 규칙 수(E 기본 100 · 다른 창 0)")
    ap.add_argument("--explore-sha256", default=None, help="C·C2·U: 커밋된 RESULTS_explore.md 의 sha256")
    ap.add_argument("--sealed-dir", default=None, help=f"U 봉인 폴더(기본 env {SEALED_ENV} 또는 {SEALED_DEFAULT})")
    ap.add_argument("--i-understand-sealed", action="store_true", help="U: 독립 가족 결과는 봉인(§4-2·§8)임을 확인")
    ap.add_argument("--private-dir", default=None,
                    help=f"E·C·C2 로트 csv 폴더(기본 env {PRIVATE_ENV} 또는 {PRIVATE_DEFAULT} · git 작업 트리 밖)")
    ap.add_argument("--gap-cache", default=str(GAP_CACHE))
    a = ap.parse_args(argv)
    win = WINDOWS[a.window]
    folders = _resolve_folders(a.strategies)
    ledger_meta = json.loads(LEDGER_META.read_text(encoding="utf-8"))
    guard_spec(folders, ledger_meta)
    fakes = (100 if a.window == "E" else 0) if a.fakes is None else a.fakes
    if fakes and a.window != "E":
        raise SystemExit("🔴 가짜 규칙 보정은 E 창에서만(§5-3)")
    if a.window == "E" and not a.plumbing and fakes != FAKES_REQUIRED:
        raise SystemExit(f"🔴 R2: E 실창은 가짜 시점 규칙 {FAKES_REQUIRED}개 필수(§5-3) — --fakes {fakes}")
    sealed = a.window == "U" and not a.plumbing
    if sealed and not a.i_understand_sealed:
        raise SystemExit("🔴 B1: U 창은 --i-understand-sealed 가 필요하다(결과는 레포 밖 봉인 폴더에만)")
    if not a.plumbing:
        require_clean_tree()
    explore = check_explore(a.explore_sha256) if win.sealed_after_explore and not a.plumbing else None
    out = sealed_dir(a.sealed_dir) / "U" if sealed else (Path(a.out) if a.out else RESULTS / a.window)
    csv_dir = out if sealed else (private_dir(a.private_dir) / a.window if not a.plumbing else None)
    from .analyze import SPEC_SHA256
    T: Dict[str, float] = {}
    t_all = time.perf_counter()
    started = datetime.now().isoformat(timespec="seconds")
    info: Dict[str, Any] = {}

    conn = D.connect()
    try:
        t = time.perf_counter()
        cal_all = D.load_calendar(conn, A_START - timedelta(days=60), date.today() + timedelta(days=1))
        asof, cal, path_end, c2_all = window_dates(cal_all, date.today(), a.asof, folders)
        market_of = D.load_market_of(conn)
        info["stock_market_sha256"] = digest_rows(sorted(market_of.items()))
        T["calendar_market"] = time.perf_counter() - t

        t = time.perf_counter()
        counts_b: Dict[str, int] = {}
        c2_end: Dict[str, date] = {}
        if win.layer == "A":
            with open(LEDGER, encoding="utf-8", newline="") as fh:
                lots = lots_from_ledger(csv.DictReader(fh), folders, win.start, win.end or A_END)
            daily = load_daily(conn, sorted({x.code for x in lots}), min(x.scan_date for x in lots), A_END, info)
        else:
            c2_end = c2_all
            snap = load_snapshots(conn, folders, win.start - timedelta(days=15), max(c2_end.values()))
            info.update(snapshot_rows=len(snap), snapshot_sha256=digest_rows(snap))
            daily = load_daily(conn, sorted({c for _, _, c, _ in snap}), win.start - timedelta(days=15), asof, info)
            lots, counts_b = lots_from_snapshots(snap, folders, cal, daily, win.start, c2_end)
        if not lots:
            raise SystemExit("로트 0 — 창·전략 확인")
        corp_flags(lots, load_corp_events(conn, min(x.scan_date for x in lots), max(x.entry_date for x in lots), info))
        tv_d = load_tv_rank(conn, sorted({x.scan_date for x in lots}))
        tv_d1 = load_tv_rank(conn, sorted({x.entry_date for x in lots}))
        info["no_rank_d_lots"] = attach_ranks(lots, tv_d, tv_d1)
        info["tv_rank_sha256"] = digest_rows((x.lot_id, x.tv_rank_d, x.tv_rank_d1) for x in lots)
        kospi = load_kospi(conn, cal[0], asof)
        info["kospi_sha256"] = digest_rows(sorted(kospi.items()))
        regime_cols(lots, cal, kospi)
        T["lots_daily"] = time.perf_counter() - t

        cache = GapCache(conn, Path(a.gap_cache))
        used_gap: List[Tuple[Any, Any, Any]] = []

        def gap_rows(days: Iterable[date]) -> List[Tuple[Any, Any, Any]]:
            got = cache.rows(days)
            used_gap.extend(got)
            return got

        t = time.perf_counter()
        bundle = D.load_minute_days(conn, [x.key for x in lots], market_of, calendar=cal, gap_rows=gap_rows)
        T["minute_load_total"] = time.perf_counter() - t
        T["market_gap_fetch"] = cache.fetch_secs
        before = D.checksum_digest(bundle.checksums)

        t = time.perf_counter()
        rows, fake_rows, cnt = build_rows(a.window, win, lots, bundle, daily, cal, path_end, market_of,
                                          fakes=0 if a.plumbing else fakes, simulate=not a.plumbing)
        T["simulate"] = time.perf_counter() - t

        t = time.perf_counter()
        after_raw = D.fetch_minute_rows(conn, bundle.keys)
        after = D.checksum_digest({k: D.raw_checksum(after_raw[k]) for k in bundle.keys})
        n_diff = sum(1 for k in bundle.keys if D.raw_checksum(after_raw[k]) != bundle.checksums[k])
        g5_stale = cache.verify()
        T["checksum_after"] = time.perf_counter() - t
    finally:
        conn.close()

    ok = before == after and n_diff == 0 and not g5_stale
    files: Dict[str, Dict[str, Any]] = {}
    if not a.plumbing and ok:                                      # A4 — 검사 통과 뒤에만 결과 확정
        _atomic_write(csv_dir / SEAL_README, SEAL_NOTE)             # W1 — 폴더에 봉인 등급 안내
        text = csv_text(LOT_COLS, rows)
        _atomic_write(csv_dir / "lots_rule.csv", text)
        files["lots_rule.csv"] = dict(rows=len(rows), sha256=hashlib.sha256(text.encode("utf-8")).hexdigest())
        if fakes:
            ftext = csv_text(FAKE_COLS, fake_rows)
            _atomic_write(csv_dir / "fake_timing.csv", ftext)
            files["fake_timing.csv"] = dict(rows=len(fake_rows), sha256=hashlib.sha256(ftext.encode()).hexdigest())
    excl_counts: Dict[str, int] = {}
    for why in bundle.excluded.values():
        excl_counts[why] = excl_counts.get(why, 0) + 1
    meta = dict(
        banner="관측 — 판정 근거 아님(사전등록 §8) · 효과·p 없음(로트만)",
        prereg=dict(path=PREREG.relative_to(ROOT).as_posix(), sha256=sha256_file(PREREG)),
        amendment=dict(path=AMENDMENT.relative_to(ROOT).as_posix(),
                       sha256=sha256_file(AMENDMENT) if AMENDMENT.exists() else None),
        git_sha=git_sha(), code_sha256=code_hashes(), analysis_spec_sha256=SPEC_SHA256, rules_draft_flag=R.DRAFT,
        window=a.window, layer=win.layer, start=win.start, end=win.end, c2_end=c2_end, asof=asof,
        path_end=path_end, arms=list(win.arms), strategies=folders, plumbing=bool(a.plumbing), fakes=fakes,
        explore=explore, sealed=sealed, csv_dir=str(csv_dir) if csv_dir is not None else None,
        dep_module_files=dep_module_files(),
        inputs=dict(ledger_csv=sha256_file(LEDGER), ledger_run_meta=sha256_file(LEDGER_META),
                    gap_rows_used_sha256=rows_digest(used_gap), gap_rows_used=len(used_gap), **info),
        n_lots=len(lots), n_code_days=len({x.key for x in lots}), n_buy_days=len({x.entry_date for x in lots}),
        n_codes=len({x.code for x in lots}), n_minute_code_days=len(bundle.keys),
        excluded=dict(sorted(excl_counts.items())), unknown_market_codes=bundle.unknown_market_codes,
        layer_b=counts_b, lot_flag_counts=dict(sorted(cnt.items())),
        g8=dict(before=before, after=after, n_diff=n_diff, ok=before == after and n_diff == 0),
        g5_cache=dict(version=GapCache.VERSION, stale_days=g5_stale, ok=not g5_stale),
        ok=ok, outputs=files)
    meta_text = json.dumps(meta, ensure_ascii=False, indent=1, default=_fmt) + "\n"
    _atomic_write(out / "run_meta.json", meta_text)
    if csv_dir is not None and not sealed:                          # 비공개 폴더에도 같은 메타(csv 와 짝)
        _atomic_write(csv_dir / "run_meta.json", meta_text)
    if sealed:                                                      # B1 — 레포에는 해시만
        public = dict(banner="봉인 — 내용은 레포 밖(그림자 ② 판정 전 열람·인용 금지 · §4-2·§8)", window="U",
                      git_sha=meta["git_sha"], analysis_spec_sha256=SPEC_SHA256, ok=ok,
                      outputs={k: dict(rows=v["rows"], sha256=v["sha256"]) for k, v in files.items()},
                      run_meta_sha256=hashlib.sha256(meta_text.encode("utf-8")).hexdigest())
        _atomic_write(RESULTS / "U" / "public_meta.json", json.dumps(public, ensure_ascii=False, indent=1) + "\n")
    timing = dict(started=started, finished=datetime.now().isoformat(timespec="seconds"),
                  secs={k: round(v, 1) for k, v in T.items()}, secs_total=round(time.perf_counter() - t_all, 1),
                  gap_cache=dict(hits=cache.hits, misses=cache.misses, path=str(cache.path)))
    _atomic_write(out / "run_timing.json", json.dumps(timing, ensure_ascii=False, indent=1) + "\n")
    g5_txt = "✓" if not g5_stale else f"🔴 낡음 {len(g5_stale)}일"
    log(f"[{a.window}] 로트 {len(lots):,} · code-day {meta['n_code_days']:,} · 분봉 {len(bundle.keys):,} · "
        f"제외 {excl_counts} · G8 {'✓' if meta['g8']['ok'] else '🔴 불일치'} · G5 캐시 {g5_txt} · "
        f"{timing['secs_total']}s → {'(봉인 폴더)' if sealed else out}")
    for k, v in files.items():
        if sealed:
            print(f"{k} sha256 {v['sha256']}")
    return 0 if ok else 2


if __name__ == "__main__":
    sys.exit(main())
