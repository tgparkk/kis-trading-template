"""과거 재스캔 후보 원장 — 규범 = `PREREG.md`(🔒 동결 `585b651`). 문서와 어긋나면 코드가 틀린 것이다.

    python -m backtest.concept_axes.candidate_ledger.run --pilot --verify
    python -m backtest.concept_axes.candidate_ledger.run --verify            # 본 실행(617거래일)

🔴 관측 원장 · 판정 근거 아님 · 룰 변경 근거 인용 금지(§0 · §8-7).
🔴 DB SELECT 전용(`bootstrap` = PGOPTIONS read-only) · 라이브 코드는 import 만 · 재사용 모듈 수정 0줄.
재사용: 스캔 = `replayer/{loader,scan,flags}` + 라이브 어댑터 3개 · 사이징 = `ledger8/sizing.arm_b_qty` ·
청산 = `ledger8/exitsim8.simulate_lot` + `sellprobe8.{resolve_live_tp_sl, SellProbe}`(`arms.run_lots` 미사용 · §12).
"""
from __future__ import annotations

from backtest.concept_axes.minervini.cap_skip_ledger import bootstrap  # noqa: F401  안전 설정 먼저

import argparse                                                        # noqa: E402
import csv                                                             # noqa: E402
import importlib                                                       # noqa: E402
import json                                                            # noqa: E402
import os                                                              # noqa: E402
import random                                                          # noqa: E402
import statistics                                                      # noqa: E402
import subprocess                                                      # noqa: E402
import sys                                                             # noqa: E402
import tempfile                                                        # noqa: E402
import time                                                            # noqa: E402
import warnings                                                        # noqa: E402
from collections import Counter, OrderedDict                           # noqa: E402
from dataclasses import dataclass, field                               # noqa: E402
from datetime import date, datetime                                    # noqa: E402
from datetime import time as dtime                                     # noqa: E402
from pathlib import Path                                               # noqa: E402
from typing import Any, Callable, Dict, List, Optional, Sequence, Set, Tuple  # noqa: E402

import numpy as np                                                     # noqa: E402
import pandas as pd                                                    # noqa: E402

from backtest.concept_axes.ledger8 import exitsim8 as X                # noqa: E402
from backtest.concept_axes.ledger8 import sellprobe8 as SP             # noqa: E402
from backtest.concept_axes.ledger8 import sizing as Z                  # noqa: E402
from backtest.concept_axes.ledger8 import sources8 as SRC8             # noqa: E402
from backtest.concept_axes.ledger8.livesignal8 import load8            # noqa: E402
from backtest.concept_axes.replayer import flags as FL                 # noqa: E402
from backtest.concept_axes.replayer import loader as LD                # noqa: E402
from backtest.concept_axes.replayer import scan as SC                  # noqa: E402
from backtest.concept_axes.replayer.run import params_hash             # noqa: E402
from config.constants import OHLCV_LOOKBACK_DAYS                       # noqa: E402
from strategies.base import BaseStrategy                               # noqa: E402

warnings.filterwarnings("ignore", message="pandas only supports SQLAlchemy")

BASE = Path(__file__).resolve().parent
ROOT = BASE.parents[2]                               # …/RoboTrader_template

# ── §2 창 · 달력 🔒 ──────────────────────────────────────────────────────────
W_START, W_END = "2024-03-13", "2026-09-23"          # scan_date 창 · W_END = 보유 경로 끝
PX_START = "2023-01-02"                              # 워밍업(minervini 260봉)
PILOT = ("2024-03-13", "2024-03-31")                 # §11 1개월 파일럿(scan_date 2024-03)
FULL_DAYS = 617
HOUR_CAP = 4.0
BASE_SHA = "2274895"                                 # §7 실행 전 가드 기준 커밋
SEED = 20260924                                      # §10 V5
V1_WIN = ("2026-06-05", "2026-09-22")
V1_TOP = 10
ENTRY_TIME = dtime(9, 0)                             # §4 체결 시각 = D+1 09:00

# ── §3 · §4 · §6 동결 값 — 코드는 라이브에서 얻고, 이 표는 «대조»에만 쓴다 ──────────
STRATS: "OrderedDict[str, Dict[str, Any]]" = OrderedDict([
    ("book_pullback_ma20", dict(short="ma20", module="strategies.book_pullback_ma20.screener",
                                cls="BookPullbackMa20ScreenerAdapter", lookback=90, sanity=None,
                                two_pass=False, tp=0.10, sl=0.08, max_hold=50, band=(0.08, 0.01))),
    ("minervini_volume_dryup", dict(short="minervini", module="strategies.minervini_volume_dryup.screener",
                                    cls="MinerviniVolumeDryupScreenerAdapter", lookback=260, sanity=90,
                                    two_pass=True, tp=0.12, sl=0.08, max_hold=20, band=(None, 0.03))),
    ("daytrading_3methods_breakout", dict(short="daytrading",
                                          module="strategies.daytrading_3methods_breakout.screener",
                                          cls="Daytrading3MethodsBreakoutScreenerAdapter", lookback=60,
                                          sanity=None, two_pass=False, tp=0.10, sl=0.10, max_hold=10,
                                          band=(None, 0.03))),
])
GUARD_FILES = ([f"strategies/{f}/{n}" for f in STRATS for n in ("screener.py", "strategy.py", "config.yaml")]
               + ["strategies/base.py", "strategies/_rule_screener_base.py"])

# ── §7 출력 열(순서 동결) ────────────────────────────────────────────────────
LEDGER_COLS = ["strategy", "scan_date", "stock_code", "rank", "score", "n_passed", "reason", "n_bars",
               "ref_close", "market_cap", "trading_value", "d_volume", "rs_value", "excl_class",
               "entry_date", "entry_price", "band_lo", "band_hi", "band_ok", "qty", "qty_basis", "notional",
               "exit_date", "exit_price", "exit_reason", "exit_phase", "hold_days", "ret_pct", "pnl_won",
               "flags"]
DIAG_COLS = ["strategy", "scan_date", "universe_eff_date", "n_universe", "n_eligible", "n_evaluated",
             "n_impossible", "n_no_bar_at_d", "n_matched", "secs", "n_errors"]   # n_errors = 예외 격리 카운트(추가 열)
EXCL_KEYS = (("excl_pref", "pref"), ("excl_foreign", "foreign"), ("excl_reit", "reit"),
             ("excl_spac", "spac"), ("excl_etf", "etf"))

F_BAND_OUT, F_NO_OPEN, F_NO_NEXT = "band_out", "no_open", "no_next_day"
F_IMPOSSIBLE, F_VINTAGE, F_CORP = "impossible_bar", "vintage_m4", "corp_event"
F_MINUTE, F_SURVIVOR = "minute_avail", "survivor_universe"


def log(msg: str = "") -> None:
    print(msg, file=sys.stderr, flush=True)


def _fmt(x: Any) -> str:
    if x is None:
        return ""
    if isinstance(x, bool):
        return "True" if x else "False"
    if isinstance(x, (float, np.floating)):
        return "" if x != x else format(float(x), ".15g")
    if isinstance(x, (date, pd.Timestamp)):
        return pd.Timestamp(x).strftime("%Y-%m-%d")
    return str(x)


def _atomic_write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=path.stem + ".", suffix=".tmp", dir=str(path.parent))
    with os.fdopen(fd, "w", encoding="utf-8", newline="") as fh:
        fh.write(text)
    os.replace(tmp, path)


def write_csv(path: Path, cols: Sequence[str], rows: Sequence[Dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=path.stem + ".", suffix=".tmp", dir=str(path.parent))
    with os.fdopen(fd, "w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(cols), extrasaction="ignore", lineterminator="\n")
        w.writeheader()
        w.writerows(rows)
    os.replace(tmp, path)


def read_csv(path: Path) -> List[Dict[str, str]]:
    with open(path, encoding="utf-8", newline="") as fh:
        return list(csv.DictReader(fh))


# ────────────────────────────────────────────────────────────────────────────
# 가드 (§7 blob · §6 tp/sl)
# ────────────────────────────────────────────────────────────────────────────
def _git(*args: str) -> str:
    return subprocess.run(["git", *args], cwd=str(ROOT), capture_output=True, text=True,
                          check=True).stdout.strip()


def git_sha() -> str:
    return _git("rev-parse", "HEAD")


def guard_blobs(git: Callable[..., str] = _git) -> Dict[str, str]:
    """전략·어댑터 파일 blob 해시가 `2274895` 와 다르면 중단."""
    out: Dict[str, str] = {}
    bad: List[str] = []
    for rel in GUARD_FILES:
        want = git("rev-parse", f"{BASE_SHA}:./{rel}")
        have = git("hash-object", rel)
        out[rel] = have
        if want != have:
            bad.append(f"{rel} ({BASE_SHA}={want[:10]} · 현재={have[:10]})")
    if bad:
        raise SystemExit("🔴 가드: 전략/어댑터 파일이 기준 커밋과 다르다 — 중단\n  " + "\n  ".join(bad))
    return out


def guard_rules(folder: str, rules: X.ExitRules, strategy: Any = None, adapter: Any = None) -> None:
    """`resolve_live_tp_sl` 값·밴드·lookback 이 PREREG §3·§4·§6 표와 다르면 중단."""
    spec = STRATS[folder]
    bad: List[str] = []
    if (round(rules.tp, 9), round(rules.sl, 9), int(rules.max_hold_days)) != (spec["tp"], spec["sl"],
                                                                              spec["max_hold"]):
        bad.append(f"tp/sl/max_hold = ({rules.tp}, {rules.sl}, {rules.max_hold_days}) ≠ PREREG §6 "
                   f"({spec['tp']}, {spec['sl']}, {spec['max_hold']})")
    if strategy is not None:
        band = (getattr(strategy, "_entry_band_down_pct", "?"), getattr(strategy, "_entry_band_up_pct", "?"))
        if band != spec["band"]:
            bad.append(f"밴드(down, up) = {band} ≠ PREREG §4 {spec['band']}")
    if adapter is not None:
        got = (int(adapter.lookback_days), adapter.sanity_window, bool(adapter.wants_context))
        if got != (spec["lookback"], spec["sanity"], spec["two_pass"]):
            bad.append(f"어댑터(lookback, sanity_window, 2패스) = {got} ≠ PREREG §3")
    if bad:
        raise SystemExit(f"🔴 가드({folder}): " + " · ".join(bad) + " — 중단")


# ────────────────────────────────────────────────────────────────────────────
# 순수 함수 — 밴드 · 순위 · 창
# ────────────────────────────────────────────────────────────────────────────
def entry_band(ref: float, down: Optional[float], up: Optional[float]) -> Tuple[Optional[float], Optional[float]]:
    """§4 — 라이브 `BaseStrategy._entry_band` 를 «그대로» 부른다(self 미사용)."""
    return BaseStrategy._entry_band(None, float(ref), down_pct=down, up_pct=up)


def band_ok(price: float, lo: Optional[float], hi: Optional[float]) -> bool:
    """경계 포함 · None 쪽 열림."""
    return (lo is None or price >= lo) and (hi is None or price <= hi)


def rank_day(matched: Sequence[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """§3-6 — `rank_and_truncate(max_candidates=None, count_boundary_tie=False)` = 전수 · rank/n_passed 부여."""
    ordered = SC.rank_and_truncate([(m["stock_code"], m["score"]) for m in matched], max_candidates=None,
                                   count_boundary_tie=False)
    by = {m["stock_code"]: m for m in matched}
    return [dict(by[c], rank=i + 1, n_passed=len(ordered)) for i, (c, _) in enumerate(ordered)]


Book = Dict[str, Tuple[np.ndarray, pd.DataFrame]]


def build_book(px: pd.DataFrame) -> Book:
    return {str(c): (g["date"].to_numpy(), g) for c, g in px.groupby("stock_code", sort=False)}


def _ts64(d: Any) -> np.datetime64:
    return pd.Timestamp(d).to_datetime64()


def make_window_fn(book: Book, days: int = OHLCV_LOOKBACK_DAYS) -> Callable[[str, date], Tuple[Any, Dict]]:
    """§6 🔒 `window_fn(code, day)` = 벌크 px 중 `date < day`(마지막 봉 = day−1)인 봉 — 당일 봉 포함 금지.

    시작 = day − `OHLCV_LOOKBACK_DAYS`(120 달력일) — 라이브 `live_daily_window`(PriceRepository days=120 ·
    `date ≥ now−120일` · 오늘 봉 드롭)와 같은 창.
    """
    def fn(code: str, day: date) -> Tuple[Optional[pd.DataFrame], Dict]:
        ent = book.get(code)
        if ent is None:
            return None, {}
        dates, g = ent
        t = pd.Timestamp(day)
        j = int(np.searchsorted(dates, t.to_datetime64(), side="left"))
        s = int(np.searchsorted(dates, (t - pd.Timedelta(days=days)).to_datetime64(), side="left"))
        data = g.iloc[s:j][["date", "open", "high", "low", "close", "volume"]].reset_index(drop=True)
        return data, {"n": len(data), "last_bar": _fmt(data["date"].iloc[-1]) if len(data) else ""}
    return fn


def scan_two_pass(adapter: Any, params: Dict[str, Any], book: Book, elig: Set[str], d: pd.Timestamp,
                  lookback: int, sanity_window: Optional[int]) -> Tuple[List[Dict[str, Any]], Dict[str, int]]:
    """§3-4 minervini 2패스(라이브 `_rule_screener_base.py:113-127`).

    ① frames = 적격 ∧ `date ≤ D` 봉 ≥1 ∧ 가드(`win.iloc[-sanity_window:]`) 통과 — D 봉 없는 종목도 포함
    ② `adapter.build_context(frames, D)` ③ D 봉 있는 종목만 `match(win, params, ctx.get(code) or {})`.
    """
    t = _ts64(d)
    frames: Dict[str, pd.DataFrame] = {}
    has_d: List[str] = []
    n_imp = n_err = 0
    for code in sorted(elig):
        ent = book.get(code)
        if ent is None:
            continue
        dates, g = ent
        i = int(np.searchsorted(dates, t, side="right")) - 1
        if i < 0:
            continue
        win = SC.window_slice(g, i, lookback)
        view = win if sanity_window is None else win.iloc[-sanity_window:]
        if SC.is_impossible(view):
            n_imp += 1
            continue
        frames[code] = win
        if dates[i] == t:
            has_d.append(code)
    ctxs = adapter.build_context(frames, pd.Timestamp(d).date()) or {}
    matched: List[Dict[str, Any]] = []
    for code in has_d:
        win = frames[code]
        ctx = ctxs.get(code) or {}
        try:
            verdict = adapter.match(win, params, ctx)
        except Exception:  # noqa: BLE001 — 종목-일 단위 격리
            n_err += 1
            continue
        if verdict is None or not (float(win["close"].iloc[-1]) > 0):
            continue
        score, reason = verdict
        matched.append(dict(scan_date=pd.Timestamp(d), stock_code=code, score=float(score), reason=reason,
                            n_bars=int(len(win)), rs_value=ctx.get("rs_value")))
    n_eval = len(has_d)
    diag = dict(n_eligible=len(elig), n_impossible=n_imp, n_evaluated=n_eval, n_matched=len(matched),
                n_no_bar_at_d=max(0, len(elig) - n_imp - n_eval), n_errors=n_err, n_frames=len(frames))
    return matched, diag


class GuardedAdapter:
    """`scan_strategy` 에 넘기는 얇은 감싸개 — `match` 예외를 종목-일 단위로 격리·계수(판정 경로 불변)."""

    def __init__(self, adapter: Any):
        self.adapter = adapter
        self.errors: Counter = Counter()

    def base_filter(self, universe):
        return self.adapter.base_filter(universe)

    def match(self, win, params):
        try:
            return self.adapter.match(win, params)
        except Exception:  # noqa: BLE001
            self.errors[pd.Timestamp(win["date"].iloc[-1])] += 1
            return None


def build_path(cal: Sequence[date], cal_idx: Dict[date, int], bars: Dict[date, X.Bar], entry: date,
               max_hold: int) -> List[Tuple[int, date, Optional[X.Bar]]]:
    """[(k, 날짜, 봉|None)] — path[0] = 진입일. k ≥ max_hold 인 첫 «봉 있는» 날에서 자른다
    (그 봉에서 `open_phase` 가 반드시 닫으므로 결과 불변 · 결측 중 도달이면 다음 봉까지 간다)."""
    out: List[Tuple[int, date, Optional[X.Bar]]] = []
    for k, d in enumerate(cal[cal_idx[entry]:]):
        b = bars.get(d)
        out.append((k, d, b))
        if b is not None and k >= max_hold:
            break
    return out


def any_in(sorted_dates: Optional[np.ndarray], a: Any, b: Any) -> bool:
    if sorted_dates is None or not len(sorted_dates):
        return False
    i = int(np.searchsorted(sorted_dates, _ts64(a), side="left"))
    return i < len(sorted_dates) and sorted_dates[i] <= _ts64(b)


# ────────────────────────────────────────────────────────────────────────────
# 환경(벌크 로드) · 로트 행
# ────────────────────────────────────────────────────────────────────────────
@dataclass
class Env:
    cal: List[date]
    book: Book
    uni: Dict[pd.Timestamp, Dict[str, Tuple[float, float]]]
    excl: Dict[str, str]
    imp_dates: Dict[str, np.ndarray]
    corp_dates: Dict[str, np.ndarray]
    bad_open: Set[Tuple[str, date]]
    minute_fn: Callable[[Sequence[Tuple[str, str]]], Set[Tuple[str, str]]]
    path_end: date = date.fromisoformat(W_END)
    cal_idx: Dict[date, int] = field(default_factory=dict)
    _bars: Dict[str, Dict[date, X.Bar]] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.cal_idx = {d: i for i, d in enumerate(self.cal)}

    def bars(self, code: str) -> Dict[date, X.Bar]:
        if code not in self._bars:
            ent = self.book.get(code)
            out: Dict[date, X.Bar] = {}
            if ent is not None:
                g = ent[1]
                for t, o, h, lo, c in zip(g["date"], g["open"], g["high"], g["low"], g["close"]):
                    dd = pd.Timestamp(t).date()
                    out[dd] = X.Bar(dd, float(o), float(h), float(lo), float(c))
            self._bars[code] = out
        return self._bars[code]

    def next_day(self, d: date) -> Optional[date]:
        i = self.cal_idx.get(d)
        return self.cal[i + 1] if i is not None and i + 1 < len(self.cal) else None


def lot_row(env: Env, folder: str, m: Dict[str, Any], strategy: Any, rules: X.ExitRules, probe: Any,
            eff_date: Optional[pd.Timestamp], minute: Set[Tuple[str, str]]) -> Tuple[Dict[str, str], bool]:
    """스캔 통과 1행 → 원장 1행(§4~§7). 반환 = (행, 예외 여부)."""
    code, d = m["stock_code"], pd.Timestamp(m["scan_date"]).date()
    bars = env.bars(code)
    dbar = bars.get(d)
    ref = float(dbar.close)
    dates, g = env.book[code]
    j = int(np.searchsorted(dates, _ts64(d), side="left"))
    d_volume = float(g["volume"].iloc[j])
    mc_tv = env.uni.get(eff_date, {}).get(code, (None, None)) if eff_date is not None else (None, None)
    lo, hi = entry_band(ref, strategy._entry_band_down_pct, strategy._entry_band_up_pct)
    row: Dict[str, Any] = dict(
        strategy=folder, scan_date=d, stock_code=code, rank=m["rank"], score=m["score"], n_passed=m["n_passed"],
        reason=m["reason"], n_bars=m["n_bars"], ref_close=ref, market_cap=mc_tv[0], trading_value=mc_tv[1],
        d_volume=d_volume, rs_value=m.get("rs_value"), excl_class=env.excl.get(code, ""),
        band_lo=lo, band_hi=hi)
    flags: List[str] = []
    err = False
    ex: Optional[X.ExitOut] = None
    d1 = env.next_day(d)
    b1 = bars.get(d1) if d1 is not None else None
    end_for_flags = env.path_end
    if d1 is None:
        flags.append(F_NO_NEXT)
    elif b1 is None or (code, d1) in env.bad_open or not (b1.open > 0):
        row["entry_date"] = d1
        flags.append(F_NO_OPEN)
    else:
        px_open = float(b1.open)
        ok = band_ok(px_open, lo, hi)
        q = Z.arm_b_qty(px_open)
        row.update(entry_date=d1, entry_price=px_open, band_ok=ok, qty=q.qty, qty_basis=q.basis,
                   notional=q.notional)
        if not ok:
            flags.append(F_BAND_OUT)
        try:
            pos = X.Pos(code, d1, SRC8.aware(datetime.combine(d1, ENTRY_TIME)), px_open, q.qty, X.BASIS_D_OPEN)
            ex = X.simulate_lot(pos, rules, build_path(env.cal, env.cal_idx, bars, d1, rules.max_hold_days), probe)
        except Exception:  # noqa: BLE001 — 로트 단위 격리(scan_diag n_errors)
            ex, err = None, True
        if ex is not None:
            row.update(exit_date=ex.exit_date, exit_price=ex.price, exit_reason=ex.reason, exit_phase=ex.phase,
                       hold_days=ex.hold_days, ret_pct=ex.ret_pct,
                       pnl_won=(int(round(q.qty * (ex.price - px_open))) if ex.price is not None else None))
            if any_in(env.imp_dates.get(code), d1, ex.exit_date or env.path_end):
                flags.append(F_IMPOSSIBLE)
            if ex.closed and ex.exit_date is not None:
                end_for_flags = ex.exit_date
    if d < date.fromisoformat(LD.OVERTIME_MIN_DATE):
        flags.append(F_VINTAGE)
    if any_in(env.corp_dates.get(code), d, end_for_flags):
        flags.append(F_CORP)
    if d1 is not None and (code, d1.strftime("%Y%m%d")) in minute:
        flags.append(F_MINUTE)
    flags.append(F_SURVIVOR)
    if ex is not None:
        flags.extend(ex.flags)
    row["flags"] = ";".join(flags)
    return {k: _fmt(row.get(k)) for k in LEDGER_COLS}, err


# ────────────────────────────────────────────────────────────────────────────
# 체크포인트 파트(전략 × scan_date 월)
# ────────────────────────────────────────────────────────────────────────────
def part_paths(out: Path, folder: str, ym: str) -> Tuple[Path, Path, Path]:
    base = out / "parts" / f"{folder}_{ym}"
    return base.with_suffix(".csv"), Path(str(base) + "_diag.csv"), base.with_suffix(".done")


def load_done_part(out: Path, folder: str, ym: str, sha: str, fp: str):
    """`.done` 이 있으면 sha·지문 대조 후 (rows, diag, meta) · 없으면 None · 불일치면 중단."""
    p_csv, p_diag, p_done = part_paths(out, folder, ym)
    if not p_done.exists():
        return None
    meta = json.loads(p_done.read_text(encoding="utf-8"))
    if meta.get("git_sha") != sha or meta.get("db_fingerprint") != fp:
        raise SystemExit(f"🔴 체크포인트 불일치 {p_done.name}: git {meta.get('git_sha', '')[:10]}/{sha[:10]} · "
                         f"지문 {str(meta.get('db_fingerprint'))[:12]}/{fp[:12]} — 중단(파트를 지우고 다시 돌릴 것)")
    return read_csv(p_csv), read_csv(p_diag), meta


def save_part(out: Path, folder: str, ym: str, rows, diag, meta: Dict[str, Any]) -> None:
    p_csv, p_diag, p_done = part_paths(out, folder, ym)
    write_csv(p_csv, LEDGER_COLS, rows)
    write_csv(p_diag, DIAG_COLS, diag)
    _atomic_write(p_done, json.dumps(meta, ensure_ascii=False, indent=1))


def run_part(env: Env, folder: str, days: List[pd.Timestamp], adapter: Any, params: Dict[str, Any],
             elig: Dict[pd.Timestamp, Set[str]], info: Dict[pd.Timestamp, Dict[str, Any]], strategy: Any,
             rules: X.ExitRules, probe: Any, px: pd.DataFrame):
    spec = STRATS[folder]
    t0 = time.perf_counter()
    matched_by_day: Dict[pd.Timestamp, List[Dict[str, Any]]] = {d: [] for d in days}
    diag_by_day: Dict[pd.Timestamp, Dict[str, Any]] = {}
    secs_by_day: Dict[pd.Timestamp, float] = {}
    if spec["two_pass"]:
        for d in days:
            t1 = time.perf_counter()
            ms, dg = scan_two_pass(adapter, params, env.book, elig.get(d, set()), d, spec["lookback"],
                                   spec["sanity"])
            matched_by_day[d] = ms
            diag_by_day[d] = dg
            secs_by_day[d] = time.perf_counter() - t1
    else:
        ga = GuardedAdapter(adapter)
        ms, dgs, _imp = SC.scan_strategy(px, {d: elig.get(d, set()) for d in days}, ga, params, spec["lookback"],
                                         scan_dates=days, max_candidates=None, progress_every=0)
        for m in ms:
            matched_by_day[pd.Timestamp(m["scan_date"])].append(m)
        per = (time.perf_counter() - t0) / max(1, len(days))     # 월 단위 1회 스캔 ⇒ 일평균 배분
        for d in days:
            dg = dict(dgs.get(d, {"n_eligible": len(elig.get(d, ())), "n_impossible": 0, "n_evaluated": 0,
                                  "n_matched": 0, "n_no_bar_at_d": 0}))
            dg["n_errors"] = int(ga.errors.get(d, 0))
            diag_by_day[d] = dg
            secs_by_day[d] = per
    scan_secs = time.perf_counter() - t0

    t2 = time.perf_counter()
    ranked = {d: rank_day(matched_by_day[d]) for d in days}
    pairs = [(m["stock_code"], nd.strftime("%Y%m%d")) for d in days for m in ranked[d]
             for nd in [env.next_day(pd.Timestamp(d).date())] if nd is not None]
    minute = env.minute_fn(pairs)
    rows: List[Dict[str, str]] = []
    diag_rows: List[Dict[str, str]] = []
    for d in days:
        n_err = 0
        eff = info.get(d, {}).get("eff_date")
        for m in ranked[d]:
            try:
                r, e = lot_row(env, folder, m, strategy, rules, probe, eff, minute)
            except Exception as exc:  # noqa: BLE001 — 종목-일 단위 격리
                log(f"      ⚠️ {folder} {d:%Y-%m-%d} {m['stock_code']}: {type(exc).__name__}: {exc}")
                n_err += 1
                continue
            n_err += int(e)
            rows.append(r)
        dg = diag_by_day[d]
        ui = info.get(d, {})
        diag_rows.append({k: _fmt(v) for k, v in dict(
            strategy=folder, scan_date=d, universe_eff_date=ui.get("eff_date"), n_universe=ui.get("n_universe"),
            n_eligible=dg.get("n_eligible"), n_evaluated=dg.get("n_evaluated"), n_impossible=dg.get("n_impossible"),
            n_no_bar_at_d=dg.get("n_no_bar_at_d"), n_matched=dg.get("n_matched"), secs=round(secs_by_day[d], 3),
            n_errors=int(dg.get("n_errors", 0)) + n_err).items()})
    exit_secs = time.perf_counter() - t2
    return rows, diag_rows, scan_secs, exit_secs


# ────────────────────────────────────────────────────────────────────────────
# DB 로드(SELECT 전용)
# ────────────────────────────────────────────────────────────────────────────
def load_bad_open(conn, start: str, end: str) -> Set[Tuple[str, date]]:
    """§4 `no_open` — 원본 시가 결측/≤0(로더 `normalize_prices` 가 종가로 메우기 «전» 값)."""
    df = pd.read_sql("SELECT stock_code, date FROM daily_prices WHERE {} AND date BETWEEN %s AND %s "
                     "AND (open IS NULL OR open <= 0)".format(LD.STOCK_ONLY), conn, params=(start, end))
    return {(str(c), date.fromisoformat(str(d)[:10])) for c, d in zip(df["stock_code"], df["date"])}


def make_minute_fn(conn) -> Callable[[Sequence[Tuple[str, str]]], Set[Tuple[str, str]]]:
    """§7 `minute_avail` — (stock_code, trade_date=YYYYMMDD) 존재 여부(PK 인덱스 경유)."""
    def fn(pairs: Sequence[Tuple[str, str]]) -> Set[Tuple[str, str]]:
        pairs = sorted(set(pairs))
        if not pairs:
            return set()
        with conn.cursor() as cur:
            cur.execute("SELECT p.c, p.d FROM unnest(%s::text[], %s::text[]) AS p(c, d) WHERE EXISTS "
                        "(SELECT 1 FROM minute_candles m WHERE m.stock_code = p.c AND m.trade_date = p.d)",
                        ([c for c, _ in pairs], [d for _, d in pairs]))
            return {(str(c), str(d)) for c, d in cur.fetchall()}
    return fn


def _date_index(pairs) -> Dict[str, np.ndarray]:
    tmp: Dict[str, List[np.datetime64]] = {}
    for c, t in pairs:
        tmp.setdefault(str(c), []).append(_ts64(t))
    return {c: np.array(sorted(v), dtype="datetime64[ns]") for c, v in tmp.items()}


def excl_class_map(codes: Sequence[str], names: Dict[str, str]) -> Dict[str, str]:
    cls = LD.classify_exclusions(codes, names)
    return {c: ";".join(lab for k, lab in EXCL_KEYS if rec[k]) for c, rec in cls.items()}


# ────────────────────────────────────────────────────────────────────────────
# summary · 검증
# ────────────────────────────────────────────────────────────────────────────
def _num(s: pd.Series) -> pd.Series:
    return pd.to_numeric(s.replace("", np.nan), errors="coerce")


def _has(flags: pd.Series, f: str) -> pd.Series:
    return flags.fillna("").str.split(";").apply(lambda xs: f in xs)


def verify(led: pd.DataFrame, diag: pd.DataFrame, conn, scan_days: Sequence[pd.Timestamp],
           folders: Sequence[str]) -> List[str]:
    L: List[str] = ["## §10 검증 (V1~V5 · 값만 · 판정은 verifier)", ""]
    # V1
    L += ["### V1 스냅샷 일치율 (재스캔 rank≤10 ∩ 라이브 rank_in_snapshot≤10 ÷ 라이브 rank≤10 행수)", ""]
    v1_days = [d for d in scan_days if V1_WIN[0] <= d.strftime("%Y-%m-%d") <= V1_WIN[1]]
    if not v1_days:
        L += [f"- 스캔 창에 V1 창({V1_WIN[0]}~{V1_WIN[1]})이 없다 — 해당 없음", ""]
    else:
        snap = pd.read_sql("SELECT strategy, scan_date, stock_code, rank_in_snapshot, params_hash "
                           "FROM screener_snapshots WHERE strategy = ANY(%s) AND scan_date BETWEEN %s AND %s",
                           conn, params=(list(folders), V1_WIN[0], V1_WIN[1]))
        snap["scan_date"] = pd.to_datetime(snap["scan_date"])
        L += ["| 전략 | params_hash | 구간 | 일수 | 평균 | 최소 | 중앙 | 최대 | 대표 |", "|---|---|---|---|---|---|---|---|---|"]
        for f in folders:
            s = snap[snap["strategy"] == f]
            r = led[(led["strategy"] == f) & (_num(led["rank"]) <= V1_TOP)]
            rep = {d: set(g["stock_code"]) for d, g in r.groupby(pd.to_datetime(r["scan_date"]))}
            per: List[Tuple[str, pd.Timestamp, float]] = []
            for d, g in s.groupby("scan_date"):
                if d not in v1_days:
                    continue
                live = set(g.loc[g["rank_in_snapshot"] <= V1_TOP, "stock_code"].astype(str))
                if live:
                    per.append((str(g["params_hash"].iloc[0]), d, len(live & rep.get(d, set())) / len(live)))
            segs: "OrderedDict[str, List[Tuple[pd.Timestamp, float]]]" = OrderedDict()
            for h, d, v in sorted(per, key=lambda t: t[1]):
                segs.setdefault(h, []).append((d, v))
            last = next(reversed(segs)) if segs else None
            for h, xs in segs.items():
                vals = [v for _, v in xs]
                L.append(f"| {f} | {h} | {xs[0][0]:%Y-%m-%d}~{xs[-1][0]:%Y-%m-%d} | {len(vals)} | "
                         f"{statistics.mean(vals):.3f} | {min(vals):.3f} | {statistics.median(vals):.3f} | "
                         f"{max(vals):.3f} | {'현행 ✓' if h == last else ''} |")
            miss = sorted(set(v1_days) - set(s["scan_date"]))
            L.append(f"| {f} | 스냅샷 없는 날 {len(miss)}일 | {', '.join(d.strftime('%Y-%m-%d') for d in miss)} "
                     f"| | | | | | |")
        L.append("")
    # V2
    L += ["### V2 행수 = Σ n_passed · 날짜별 n_passed = scan_diag.n_matched", ""]
    for f in folders:
        r, dg = led[led["strategy"] == f], diag[diag["strategy"] == f]
        per_day = r.groupby("scan_date")["n_passed"].first().map(int) if len(r) else pd.Series(dtype=int)
        cnt = r.groupby("scan_date").size() if len(r) else pd.Series(dtype=int)
        dm = dict(zip(dg["scan_date"], _num(dg["n_matched"]).astype(int)))
        bad = sum(1 for d in set(dm) | set(per_day.index)
                  if int(per_day.get(d, 0)) != dm.get(d, 0) or int(cnt.get(d, 0)) != int(per_day.get(d, 0)))
        L.append(f"- {f}: 행 {len(r):,} · Σn_passed {int(per_day.sum()):,} · Σn_matched {sum(dm.values()):,} · "
                 f"불일치 날짜 {bad}")
    L.append("")
    # V3
    ep = _num(led["entry_price"])
    has = ep.notna()
    q, no = _num(led["qty"]), _num(led["notional"])
    v3a = int(((q * ep - no).abs() > 1)[has].sum())
    lo, hi = _num(led["band_lo"]), _num(led["band_hi"])
    re_ok = ((lo.isna() | (ep >= lo)) & (hi.isna() | (ep <= hi)))
    v3b = int((re_ok[has].map(str) != led.loc[has, "band_ok"]).sum())
    L += ["### V3 사이징·밴드 항등", "", f"- 시가 있는 행 {int(has.sum()):,} · |qty×entry−notional|>1원 {v3a} · "
          f"band_ok 재계산 불일치 {v3b}", ""]
    # V4
    closed = led["exit_reason"].ne("open") & led["exit_date"].ne("")
    dfr = _has(led["flags"], X.FLAG_MAXHOLD_DEFERRED)
    mh = led["strategy"].map({f: STRATS[f]["max_hold"] for f in STRATS})
    bad_d = int((closed & (pd.to_datetime(led["exit_date"], errors="coerce")
                           < pd.to_datetime(led["entry_date"], errors="coerce"))).sum())
    over = _num(led["hold_days"]) > mh
    L += ["### V4 청산 행 날짜·보유일", "", f"- 청산 행 {int(closed.sum()):,} · exit_date<entry_date {bad_d} · "
          f"hold_days>max_hold(비유예) {int((closed & over & ~dfr).sum())} · max_hold_deferred 행 "
          f"{int((closed & dfr).sum())}(그중 초과 {int((closed & over & dfr).sum())})", ""]
    # V5
    rng = random.Random(SEED)
    ent = led[has]
    picks: List[Tuple[str, Optional[pd.Series]]] = []
    for f in folders:
        sub = ent[ent["strategy"] == f].sort_values(["scan_date", "rank"])
        picks.append((f, sub.iloc[rng.randrange(len(sub))] if len(sub) else None))
    for lab, m in (("trail_ma", ent["exit_reason"] == "trail_ma"), ("band_out", _has(ent["flags"], F_BAND_OUT))):
        sub = ent[m].sort_values(["strategy", "scan_date", "rank"])
        picks.append((lab, sub.iloc[rng.randrange(len(sub))] if len(sub) else None))
    L += [f"### V5 층화 5행(시드 {SEED}) — 손계산 대조는 verifier", "",
          "| 층 | strategy | scan_date | code | ref_close | band_lo | band_hi | entry_date | entry_price | band_ok | qty "
          "| exit_date | exit_price | exit_reason | pnl_won |", "|" + "---|" * 15]
    for lab, r in picks:
        if r is None:
            L.append(f"| {lab} | (해당 행 없음) |" + " |" * 13)
            continue
        L.append("| " + " | ".join([lab] + [str(r[c]) for c in (
            "strategy", "scan_date", "stock_code", "ref_close", "band_lo", "band_hi", "entry_date", "entry_price",
            "band_ok", "qty", "exit_date", "exit_price", "exit_reason", "pnl_won")]) + " |")
    L.append("")
    return L


def summary_md(led: pd.DataFrame, diag: pd.DataFrame, meta: Dict[str, Any], folders: Sequence[str],
               extra: Sequence[str]) -> str:
    L = ["# candidate_ledger — summary", "",
         "> 🔴 관측 원장 · 판정 근거 아님 · 룰 변경 근거 인용 금지(PREREG §0·§8-7). 순위 구간별 수익 비교표 없음(§9).", "",
         f"- git sha `{meta['git_sha']}` · 창 {meta['window'][0]}~{meta['window'][1]} · 스캔 거래일 "
         f"{meta['n_scan_days']} · DB 지문 sha256 `{meta['db_fingerprint']['sha256'][:16]}…`",
         f"- 실행 {meta['secs_total']:.0f}s (로드 {meta['secs_load']:.0f}s · 스캔 {meta['secs_scan']:.0f}s · 청산 "
         f"{meta['secs_exit']:.0f}s) · 시작 {meta['started']} · 끝 {meta['finished']}", ""]
    L += ["## 전략별", "", "| 전략 | 행 | 시가 있음(로트) | band_ok=True | band_ok 비율 | no_open | no_next_day | band_out "
          "| n_passed 최소/중앙/최대 | n_impossible 합 | n_errors 합 |", "|" + "---|" * 11]
    for f in folders:
        r, dg = led[led["strategy"] == f], diag[diag["strategy"] == f]
        n = len(r)
        has = _num(r["entry_price"]).notna()
        ok = int((r["band_ok"] == "True").sum())
        npd = _num(dg["n_matched"])
        rate = f"{ok / int(has.sum()):.3f}" if int(has.sum()) else "-"
        L.append(f"| {f} | {n:,} | {int(has.sum()):,} ({(has.mean() if n else 0):.3f}) | {ok:,} | {rate} | "
                 f"{int(_has(r['flags'], F_NO_OPEN).sum())} | {int(_has(r['flags'], F_NO_NEXT).sum())} | "
                 f"{int(_has(r['flags'], F_BAND_OUT).sum())} | "
                 f"{int(npd.min()) if len(npd) else 0}/{npd.median() if len(npd) else 0:g}/"
                 f"{int(npd.max()) if len(npd) else 0} | {int(_num(dg['n_impossible']).sum())} | "
                 f"{int(_num(dg['n_errors']).sum())} |")
    L += ["", "## exit_reason 분포(시가 있는 로트 전부 · band_out 가상 로트 포함 · 라이브 근사는 band_ok=True 로 거를 것)", ""]
    for f in folders:
        r = led[(led["strategy"] == f) & (led["exit_reason"] != "")]
        vc = r["exit_reason"].value_counts()
        L.append(f"- {f}: " + (" · ".join(f"{k} {v:,}" for k, v in vc.items()) or "(없음)"))
    L += [""] + list(extra)
    return "\n".join(L) + "\n"


# ────────────────────────────────────────────────────────────────────────────
# main
# ────────────────────────────────────────────────────────────────────────────
def _resolve_folders(arg: Optional[str]) -> List[str]:
    if not arg:
        return list(STRATS)
    short = {v["short"]: k for k, v in STRATS.items()}
    out = []
    for s in (x.strip() for x in arg.split(",") if x.strip()):
        f = short.get(s, s)
        if f not in STRATS:
            raise SystemExit(f"모르는 전략: {s} (허용: {', '.join(list(short) + list(STRATS))})")
        out.append(f)
    return out


def main(argv: Optional[Sequence[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="과거 재스캔 후보 원장(PREREG 동결 585b651)")
    ap.add_argument("--start", default=W_START)
    ap.add_argument("--end", default=W_END)
    ap.add_argument("--strategies", default=None, help="ma20,minervini,daytrading (기본 3개)")
    ap.add_argument("--pilot", action="store_true", help="--start 2024-03-13 --end 2024-03-31 + 시간 추정")
    ap.add_argument("--out", default=None)
    ap.add_argument("--verify", action="store_true", help="summary 에 V1~V5 인쇄")
    a = ap.parse_args(argv)
    if a.pilot:
        a.start, a.end = PILOT
    if not (W_START <= a.start <= a.end <= W_END):
        raise SystemExit(f"창은 PREREG §2 {W_START}~{W_END} 안이어야 한다: {a.start}~{a.end}")
    out = Path(a.out) if a.out else BASE / "results" / ("pilot" if a.pilot else "")
    folders = _resolve_folders(a.strategies)
    started = datetime.now().isoformat(timespec="seconds")
    T0 = time.perf_counter()

    blobs = guard_blobs()
    sha = git_sha()
    strategies = {f: load8(f) for f in folders}
    adapters = {f: getattr(importlib.import_module(STRATS[f]["module"]), STRATS[f]["cls"])() for f in folders}
    rules = {f: SP.resolve_live_tp_sl(f, strategies[f]) for f in folders}
    for f in folders:
        guard_rules(f, rules[f], strategies[f], adapters[f])
    log(f"[가드] blob {len(blobs)}파일 = {BASE_SHA} ✓ · tp/sl/max_hold·밴드·lookback = PREREG ✓ · sha {sha[:10]}")

    import psycopg2
    conn = psycopg2.connect(**LD.dsn())
    conn.set_session(readonly=True)
    t = time.perf_counter()
    cal = [pd.Timestamp(d).date() for d in LD.load_trading_calendar(conn, PX_START, W_END)]
    scan_days = [pd.Timestamp(d) for d in cal if a.start <= d.isoformat() <= a.end]
    fp = LD.db_fingerprint(conn, PX_START, W_END)
    log(f"[로드] 달력 {len(cal)}일 · 스캔일 {len(scan_days)} · 지문 {fp['sha256'][:12]} ({time.perf_counter() - t:.0f}s)")
    px = LD.load_prices(conn, PX_START, W_END)
    uni = LD.build_universe(px)
    book = build_book(px)
    fl = FL.compute_bar_flags(px)
    m_imp = fl["flag_padding"] | fl["flag_locked_limit"] | fl["flag_cliff"]
    env = Env(cal=cal, book=book, uni=uni,
              excl=excl_class_map(sorted(book), LD.load_stock_names(conn)),
              imp_dates=_date_index(zip(px.loc[m_imp, "stock_code"], px.loc[m_imp, "date"])),
              corp_dates=_date_index(LD.load_corp_events(conn).keys()),
              bad_open=load_bad_open(conn, PX_START, W_END), minute_fn=make_minute_fn(conn))
    probes = {f: SP.SellProbe(f, strategies[f], make_window_fn(book)) for f in folders}
    secs_load = time.perf_counter() - T0
    log(f"[로드] px {len(px):,}행 · {len(book):,}종목 · 불가능봉 {int(m_imp.sum()):,} · 로드 합계 {secs_load:.0f}s")

    all_rows: List[Dict[str, str]] = []
    all_diag: List[Dict[str, str]] = []
    secs_scan = secs_exit = 0.0
    per_strat: Dict[str, Dict[str, float]] = {}
    for f in folders:
        adapter, params = adapters[f], adapters[f].default_params()
        elig, info = SC.eligible_for_dates(uni, adapter, scan_days)
        months: "OrderedDict[str, List[pd.Timestamp]]" = OrderedDict()
        for d in scan_days:
            months.setdefault(d.strftime("%Y-%m"), []).append(d)
        ps = per_strat.setdefault(f, {"scan": 0.0, "exit": 0.0, "rows": 0})
        for ym, days in months.items():
            got = load_done_part(out, f, ym, sha, fp["sha256"])
            if got is not None:
                rows, drows, meta = got
                log(f"[{STRATS[f]['short']}] {ym} 체크포인트 재사용 · 행 {len(rows):,}")
            else:
                rows, drows, s_scan, s_exit = run_part(env, f, days, adapter, params, elig, info, strategies[f],
                                                       rules[f], probes[f], px)
                meta = dict(git_sha=sha, db_fingerprint=fp["sha256"], strategy=f, month=ym, n_days=len(days),
                            n_rows=len(rows), scan_secs=round(s_scan, 2), exit_secs=round(s_exit, 2),
                            probe_calls=probes[f].calls)
                save_part(out, f, ym, rows, drows, meta)
                log(f"[{STRATS[f]['short']}] {ym} 스캔일 {len(days)} · 행 {len(rows):,} · 스캔 {s_scan:.1f}s · "
                    f"청산 {s_exit:.1f}s · 오류 {sum(int(r['n_errors']) for r in drows)}")
            secs_scan += float(meta.get("scan_secs", 0))
            secs_exit += float(meta.get("exit_secs", 0))
            ps["scan"] += float(meta.get("scan_secs", 0))
            ps["exit"] += float(meta.get("exit_secs", 0))
            ps["rows"] += len(rows)
            all_rows += rows
            all_diag += drows

    all_rows.sort(key=lambda r: (r["strategy"], r["scan_date"], int(r["rank"])))
    all_diag.sort(key=lambda r: (r["strategy"], r["scan_date"]))
    write_csv(out / "ledger.csv", LEDGER_COLS, all_rows)
    write_csv(out / "scan_diag.csv", DIAG_COLS, all_diag)
    led = pd.DataFrame(all_rows, columns=LEDGER_COLS).fillna("")
    diag = pd.DataFrame(all_diag, columns=DIAG_COLS).fillna("")

    n_days = max(1, len(scan_days))
    est = secs_load + (secs_scan + secs_exit) / n_days * FULL_DAYS
    timing = ["## 실행시간 · 전체 추정", "",
              f"- 스캔 1일 평균(전략 합) {secs_scan / n_days:.2f}s · 청산 시뮬 1일 평균 {secs_exit / n_days:.2f}s · "
              f"고정 로드 {secs_load:.0f}s",
              *[f"  - {f}: 스캔 {v['scan'] / n_days:.2f}s/일 · 청산 {v['exit'] / n_days:.2f}s/일 · 행 {int(v['rows']):,}"
                for f, v in per_strat.items()],
              f"- 전체 {FULL_DAYS}일 예상 ≈ {est / 3600:.2f}시간 · {HOUR_CAP:.0f}시간 초과: "
              f"{'예 🔴 본 실행 전 중단·보고(§11)' if est > HOUR_CAP * 3600 else '아니오'}", ""]
    extra = timing + (verify(led, diag, conn, scan_days, folders) if a.verify else [])
    conn.close()

    finished = datetime.now().isoformat(timespec="seconds")
    meta = dict(git_sha=sha, window=[a.start, a.end], pilot=bool(a.pilot), px_window=[PX_START, W_END],
                n_calendar_days=len(cal), n_scan_days=len(scan_days), strategies=folders,
                params_hash={f: params_hash(adapters[f].default_params()) for f in folders},
                exit_rules={f: dict(tp=rules[f].tp, sl=rules[f].sl, max_hold_days=rules[f].max_hold_days,
                                    source=rules[f].source) for f in folders},
                rows={f: int(per_strat[f]["rows"]) for f in folders}, guard_blobs=blobs, base_sha=BASE_SHA,
                started=started, finished=finished, secs_total=round(time.perf_counter() - T0, 1),
                secs_load=round(secs_load, 1), secs_scan=round(secs_scan, 1), secs_exit=round(secs_exit, 1),
                est_full_hours=round(est / 3600, 2), normalize_counts=px.attrs.get("normalize_counts"),
                db_fingerprint=fp)
    _atomic_write(out / "run_meta.json", json.dumps(meta, ensure_ascii=False, indent=1, default=str))
    _atomic_write(out / "summary.md", summary_md(led, diag, meta, folders, extra))
    print("\n".join(timing))
    print(f"출력 → {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
