"""청산 경로 진단(관측) — 사전등록 `docs/prereg_2026-09-24_exit_path_diagnosis.md`(🔒 동결 0bfbe92) §2~3 그대로.

    cd <worktree>/RoboTrader_template
    $PY -m backtest.concept_axes.candidate_ledger.exit_diag.run_exit_diag --pilot   # 1개월 파일럿(시간·건수만 · 짝 값 미인쇄)
    $PY -m backtest.concept_axes.candidate_ledger.exit_diag.run_exit_diag           # 본 실행 → RESULTS_exit_diag.md

범위 = §2 관측 정의 + §3 비대칭 판정만. 🔴 §4 짝 비교 변형은 실행 금지(문서 §4 · §7-2) · §5 무작위 진입 대조군은
이 파일에 없다(도구 교정 합격 뒤 별도 `run_random_entry.py`).
🔴 관측 · p 없음 · 라이브 룰 변경 근거 인용 금지(§7-6) · DB SELECT 만(`bootstrap` = 읽기 전용 세션) · 재사용 모듈 수정 0줄.
재사용: 원장 `../results/ledger.csv` · 달력(KOSPI 행)·가격(원시 OHLC · adj 미적용)·corp_event·DB 지문 = `replayer/loader` ·
impossible_bar = `replayer/flags.compute_bar_flags` 의 padding ∨ locked_limit ∨ cliff(원장 `run.py:781-782` 와 같은 합성) ·
플래그 어휘 = `ledger8/exitsim8` · 장벽 도달 비교식 = `cap_skip_ledger/sim.simulate_exit` 의 수익률 비교(라이브 position_monitor 식).
"""
from __future__ import annotations

from backtest.concept_axes.minervini.cap_skip_ledger import bootstrap  # noqa: F401  안전 설정 먼저

import argparse                                                        # noqa: E402
import hashlib                                                         # noqa: E402
import json                                                            # noqa: E402
import math                                                            # noqa: E402
import sys                                                             # noqa: E402
import time                                                            # noqa: E402
import warnings                                                        # noqa: E402
from collections import Counter, OrderedDict                           # noqa: E402
from datetime import date, datetime                                    # noqa: E402
from pathlib import Path                                               # noqa: E402
from typing import Any, Dict, List, Optional, Sequence, Tuple          # noqa: E402

import numpy as np                                                     # noqa: E402
import pandas as pd                                                    # noqa: E402

from backtest.concept_axes.candidate_ledger import run as R            # noqa: E402
from backtest.concept_axes.ledger8 import exitsim8 as X                # noqa: E402
from backtest.concept_axes.replayer import flags as FL                 # noqa: E402
from backtest.concept_axes.replayer import loader as LD                # noqa: E402

warnings.filterwarnings("ignore", message="pandas only supports SQLAlchemy")

BASE = Path(__file__).resolve().parent
LEDGER_DIR = BASE.parent / "results"
ARCHIVE = Path("D:/research-archive/candidate_ledger_20260924")
PREREG = "docs/prereg_2026-09-24_exit_path_diagnosis.md"
PREREG_SHA = "0bfbe92"

# ── §1 입력 🔒 ──────────────────────────────────────────────────────────────
LEDGER_MD5 = "980e58492a7ac2ed11d25526f4488dbc"
SCAN_DIAG_MD5 = "c14fb12854845d34e25e0912addfd4d6"
EXPECT_L: "OrderedDict[str, int]" = OrderedDict([("book_pullback_ma20", 18016), ("minervini_volume_dryup", 8506),
                                                ("daytrading_3methods_breakout", 15000)])
SHORT = {f: R.STRATS[f]["short"] for f in EXPECT_L}

# ── §2 관측 정의 🔒 ─────────────────────────────────────────────────────────
W = 10                                   # 청산 뒤 창 (exit_date, exit_date + W] · KOSPI 거래일
WIN_END_MAX = date(2026, 9, 23)          # 창 끝 > 이 날이면 제외
MINUTE_FROM = date(2025, 2, 24)          # 분봉 범위 시작
SESSION = ("090000", "153000")           # (a) 분봉 재분류에 쓰는 정규장(해석 기록 H5)
COST_PCT = 0.25                          # (e)(f) 비용 %

# ── §3 판정 🔒 ──────────────────────────────────────────────────────────────
X_PP = 2.0
N_BOOT = 2000
SEED_ROOT, SEED_STREAM = 20261002, 1     # default_rng([20261002, 1, s]) · s = 전략 인덱스(해석 기록 H1)
STRAT_IDX = {f: i for i, f in enumerate(EXPECT_L)}
MIN_DEN = 200

PILOT_MONTH = "2025-03"                  # 파일럿 = scan_date 1개월(분봉 있는 첫 온전한 달)

EXCL_WIN, EXCL_CORP, EXCL_IMP = "window_end_gt_2026-09-23", "corp_event", "impossible_bar"
MIN_SL_FIRST, MIN_TP_FIRST = "손절 먼저", "익절 먼저"
MIN_BOTH, MIN_NONE = "한 분봉 안 동시(미해결)", "분봉 미도달(미해결)"
MIN_CATS = (MIN_SL_FIRST, MIN_TP_FIRST, MIN_BOTH, MIN_NONE)

LAB_ASYM = "비대칭 → 짝 비교 사전등록으로 넘어감"
LAB_NONE = "청산 층 정보 없음(일봉 해상도 · W=10)"
LAB_NA = "판정 불가"

LOT_COLS = ["strategy", "scan_date", "stock_code", "entry_date", "entry_price", "exit_date", "exit_reason",
            "exit_price", "tp_barrier", "sl_barrier", "window_end", "excl", "corp_in_win", "imp_in_win",
            "n_bars_win", "max_high_win", "min_low_win", "hit", "logval"]
MIN_COLS = ["strategy", "scan_date", "stock_code", "entry_price", "exit_date", "hold_days", "tp_barrier",
            "sl_barrier", "n_minute_rows", "n_session_bars", "category", "first_touch_time", "ret_before", "ret_after"]


def log(msg: str = "") -> None:
    print(msg, file=sys.stderr, flush=True)


def md5_file(p: Path) -> str:
    h = hashlib.md5()
    with open(p, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


# ────────────────────────────────────────────────────────────────────────────
# 순수 함수 — 창 · 장벽 · 짝 값 · 분봉 재분류 · 부트스트랩 · 라벨
# ────────────────────────────────────────────────────────────────────────────
def barriers(E: float, tp: float, sl: float) -> Tuple[float, float]:
    """🔒 기준가 = 장벽 가격(체결가 아님) — (익절 장벽 E×(1+tp), 손절 장벽 E×(1−sl))."""
    return E * (1.0 + tp), E * (1.0 - sl)


def touches_tp(E: float, px: Any, tp: float) -> Any:
    """`px ≥ E×(1+tp)` — 원장·라이브와 같은 수익률 비교식 `(px−E)/E ≥ tp`(부동소수 경계 방어 · 해석 기록 H3)."""
    return (np.asarray(px, dtype=float) - E) / E >= tp


def touches_sl(E: float, px: Any, sl: float) -> Any:
    """`px ≤ E×(1−sl)` — 같은 비교식 `(px−E)/E ≤ −sl`."""
    return (np.asarray(px, dtype=float) - E) / E <= -sl


def window_end(cal: Sequence[date], cal_idx: Dict[date, int], exit_date: date, w: int = W) -> Optional[date]:
    """🔒 청산 뒤 창 `(exit_date, exit_date + w]` 의 끝 = 달력에서 exit_date 뒤 w 번째 거래일.
    달력(≤ 2026-09-23) 밖이면 None — 창 끝이 2026-09-23 을 넘는다는 뜻(제외)."""
    i = cal_idx[exit_date]
    j = i + w
    return cal[j] if j < len(cal) else None


def window_bounds(dates: np.ndarray, exit_date: date, wend: date) -> Tuple[int, int]:
    """정렬된 봉 날짜에서 `exit_date < d ≤ wend` 인 구간 [lo, hi) — exit_date 봉은 «제외», wend 봉은 «포함»."""
    lo = int(np.searchsorted(dates, pd.Timestamp(exit_date).to_datetime64(), side="right"))
    hi = int(np.searchsorted(dates, pd.Timestamp(wend).to_datetime64(), side="right"))
    return lo, max(lo, hi)


def pair_metric(reason: str, E: float, tp: float, sl: float, highs: np.ndarray,
                lows: np.ndarray) -> Tuple[bool, float]:
    """(도달 여부, 로그 폭) — 창 안 봉(highs·lows)만 받는다.

    sl 로트 → ((b) 익절 장벽 도달 = high ≥ E×(1+tp) 인 봉 있음, (c′) = −ln(min low / (E×(1−sl))))
    tp 로트 → ((b′) 손절 장벽 도달 = low ≤ E×(1−sl) 인 봉 있음, (c) = ln(max high / (E×(1+tp))))
    창 안 봉 0개면 (False, nan) — 도달 없음 · 로그 폭 정의 불가(해석 기록 H6).
    """
    tp_px, sl_px = barriers(E, tp, sl)
    if reason == X.EXIT_SL:
        if not len(lows):
            return False, float("nan")
        return bool(np.any(touches_tp(E, highs, tp))), -math.log(float(np.min(lows)) / sl_px)
    if reason == X.EXIT_TP:
        if not len(highs):
            return False, float("nan")
        return bool(np.any(touches_sl(E, lows, sl))), math.log(float(np.max(highs)) / tp_px)
    raise ValueError(f"짝 지표는 sl·tp 로트만: {reason}")


def reclassify_minutes(E: float, tp: float, sl: float,
                       bars: Sequence[Tuple[str, float, float]]) -> Tuple[str, Optional[str]]:
    """(a) 같은 봉 동시 터치 로트의 분봉 재분류 — bars = [(HHMMSS, high, low)] 시간 오름차순 · 정규장만.

    첫 번째로 장벽에 닿은 분봉으로 가른다: 손절만 → 손절 먼저 · 익절만 → 익절 먼저 · 한 분봉에 둘 다 → 동시(미해결) ·
    어느 분봉도 안 닿음 → 분봉 미도달(미해결 · 일봉과 분봉 불일치). 반환 = (분류, 첫 도달 분봉 시각).
    """
    for t, h, lo in bars:
        s = bool(touches_sl(E, lo, sl))
        p = bool(touches_tp(E, h, tp))
        if s and p:
            return MIN_BOTH, t
        if s:
            return MIN_SL_FIRST, t
        if p:
            return MIN_TP_FIRST, t
    return MIN_NONE, None


AGG_KEYS = ("b_num", "b_den", "bp_num", "bp_den", "c_sum", "c_den", "cp_sum", "cp_den")


def aggregate(df: pd.DataFrame) -> Tuple[np.ndarray, Dict[str, np.ndarray]]:
    """진단 로트(열 stock_code · exit_reason ∈ {sl,tp} · hit · logval) → 종목(오름차순)별 합.

    b = sl 로트 중 익절 장벽 도달 · bp = tp 로트 중 손절 장벽 도달 · c = tp 로트 로그 폭 · cp = sl 로트 로그 폭.
    """
    codes = np.array(sorted(df["stock_code"].unique()), dtype=object)
    pos = {c: i for i, c in enumerate(codes)}
    gi = df["stock_code"].map(pos).to_numpy(dtype=np.int64)
    is_sl = (df["exit_reason"] == X.EXIT_SL).to_numpy()
    is_tp = (df["exit_reason"] == X.EXIT_TP).to_numpy()
    hit = df["hit"].to_numpy(dtype=bool)
    val = df["logval"].to_numpy(dtype=float)
    fin = np.isfinite(val)
    G = len(codes)

    def s(mask: np.ndarray, x: Optional[np.ndarray] = None) -> np.ndarray:
        return np.bincount(gi[mask], weights=None if x is None else x[mask], minlength=G).astype(float)

    agg = dict(b_num=s(is_sl & hit), b_den=s(is_sl), bp_num=s(is_tp & hit), bp_den=s(is_tp),
               c_sum=s(is_tp & fin, val), c_den=s(is_tp & fin), cp_sum=s(is_sl & fin, val), cp_den=s(is_sl & fin))
    return codes, agg


def pair_stats(agg: Dict[str, np.ndarray], w: Optional[np.ndarray] = None) -> Dict[str, float]:
    """(b)(b′) = 비율 · (c)(c′) = 로그 폭 평균(원값 · ×100 하면 %p). w = 종목 재표집 가중치(None = 원표본)."""
    def dot(k: str) -> float:
        return float(agg[k].sum()) if w is None else float(w @ agg[k])

    def ratio(n: str, d: str) -> float:
        dd = dot(d)
        return dot(n) / dd if dd > 0 else float("nan")

    return dict(b=ratio("b_num", "b_den"), bp=ratio("bp_num", "bp_den"),
                c=ratio("c_sum", "c_den"), cp=ratio("cp_sum", "cp_den"))


def bootstrap_diffs(agg: Dict[str, np.ndarray], rng: np.random.Generator,
                    n_boot: int = N_BOOT) -> Tuple[np.ndarray, np.ndarray]:
    """🔒 종목 클러스터 부트스트랩 — 반복마다 종목 G 개를 복원추출(`rng.integers(0, G, G)`)하고
    «한 재표집 안에서» 짝 두 값을 같이 계산 → ((b)−(b′), (c)−(c′)) 차(%p) 배열."""
    G = len(agg["b_den"])
    d_b = np.empty(n_boot)
    d_c = np.empty(n_boot)
    for r in range(n_boot):
        w = np.bincount(rng.integers(0, G, size=G), minlength=G).astype(float)
        st = pair_stats(agg, w)
        d_b[r] = (st["b"] - st["bp"]) * 100.0
        d_c[r] = (st["c"] - st["cp"]) * 100.0
    return d_b, d_c


def ci95(d: np.ndarray) -> Tuple[float, float]:
    lo, hi = np.nanpercentile(d, [2.5, 97.5])
    return float(lo), float(hi)


def pair_verdict(diff_pp: float, lo: float, hi: float, den1: int, den2: int) -> str:
    """🔒 §3 — 분모 < 200 ⇒ 판정 불가 · |차| ≥ 2.0%p ∧ CI 가 0 배제 ⇒ 비대칭 · 그 밖 = 기준 미달."""
    if min(den1, den2) < MIN_DEN:
        return "판정 불가(분모<200)"
    if abs(diff_pp) >= X_PP and (lo > 0 or hi < 0):
        return "비대칭"
    return "기준 미달"


def strategy_label(v_b: str, v_c: str) -> str:
    """두 짝 중 하나라도 비대칭 ⇒ 넘어감 · 아니면 판정 불가 짝이 있으면 판정 불가 · 둘 다 기준 미달 ⇒ 정보 없음."""
    if "비대칭" in (v_b, v_c):
        return LAB_ASYM
    if v_b.startswith("판정 불가") or v_c.startswith("판정 불가"):
        return LAB_NA
    return LAB_NONE


def breakeven(tp: float, sl: float) -> Tuple[float, float]:
    """(e) 손익분기 승률 `sl/(tp+sl)` · 비용 반영 `(sl+0.25)/(tp+sl)`(%단위 · trail·max_hold 무시 근사)."""
    tpp, slp = tp * 100.0, sl * 100.0
    return slp / (tpp + slp) * 100.0, (slp + COST_PCT) / (tpp + slp) * 100.0


def has_flag(flags: str, f: str) -> bool:
    return f in (flags or "").split(";")


# ────────────────────────────────────────────────────────────────────────────
# 입력 검증 · DB 로드(SELECT 전용)
# ────────────────────────────────────────────────────────────────────────────
def check_inputs() -> Dict[str, Any]:
    """🔒 §1 — 원장·scan_diag md5 가 동결값·보관소 MD5SUMS·보관소 파일과 다르면 중단."""
    sums: Dict[str, str] = {}
    for line in (ARCHIVE / "MD5SUMS.txt").read_text(encoding="utf-8").splitlines():
        parts = line.strip().split()
        if len(parts) == 2:
            sums[parts[1].lstrip("*")] = parts[0].lower()
    got = dict(ledger_worktree=md5_file(LEDGER_DIR / "ledger.csv"),
               scan_diag_worktree=md5_file(LEDGER_DIR / "scan_diag.csv"),
               ledger_archive_file=md5_file(ARCHIVE / "ledger.csv"),
               scan_diag_archive_file=md5_file(ARCHIVE / "scan_diag.csv"),
               ledger_archive_md5sums=sums.get("ledger.csv", ""),
               scan_diag_archive_md5sums=sums.get("scan_diag.csv", ""))
    bad = [k for k, v in got.items() if v != (LEDGER_MD5 if k.startswith("ledger") else SCAN_DIAG_MD5)]
    if bad:
        raise SystemExit("🔴 입력 md5 불일치 — 중단: " + " · ".join(f"{k}={got[k]}" for k in bad))
    return got


def check_prereg_frozen() -> str:
    """사전등록 문서 blob 이 동결 커밋과 같아야 한다(바뀌었으면 중단)."""
    want = R._git("rev-parse", f"{PREREG_SHA}:./{PREREG}")
    have = R._git("hash-object", PREREG)
    if want != have:
        raise SystemExit(f"🔴 사전등록 문서가 동결 {PREREG_SHA} 와 다르다({want[:10]} ≠ {have[:10]}) — 중단")
    return have


def load_minutes(conn, pairs: Sequence[Tuple[str, str]]) -> Dict[Tuple[str, str], List[Tuple[str, float, float]]]:
    """(stock_code, trade_date=YYYYMMDD) → [(time, high, low)] 시간 오름차순 · 행 전부(정규장 거르기는 호출부). PK 경유."""
    pairs = sorted(set(pairs))
    out: Dict[Tuple[str, str], List[Tuple[str, float, float]]] = {}
    if not pairs:
        return out
    with conn.cursor() as cur:
        cur.execute("SELECT m.stock_code, m.trade_date, m.time, m.high, m.low FROM minute_candles m "
                    "JOIN unnest(%s::text[], %s::text[]) AS p(c, d) ON m.stock_code = p.c AND m.trade_date = p.d "
                    "ORDER BY m.stock_code, m.trade_date, m.time, m.idx",
                    ([c for c, _ in pairs], [d for _, d in pairs]))
        for c, d, t, h, lo in cur.fetchall():
            out.setdefault((str(c), str(d)), []).append((str(t) if t is not None else "", float(h), float(lo)))
    return out


# ────────────────────────────────────────────────────────────────────────────
# 요약 보조
# ────────────────────────────────────────────────────────────────────────────
def q(x: Sequence[float], ps: Sequence[float] = (10, 25, 50, 75, 90)) -> List[float]:
    a = np.asarray(x, dtype=float)
    a = a[np.isfinite(a)]
    return [float(np.percentile(a, p)) for p in ps] if len(a) else [float("nan")] * len(ps)


def f2(x: float, nd: int = 2) -> str:
    return "–" if x is None or (isinstance(x, float) and not math.isfinite(x)) else f"{x:.{nd}f}"


def won(x: float) -> str:
    return f"{int(round(x)):,}"


# ────────────────────────────────────────────────────────────────────────────
# 본 계산
# ────────────────────────────────────────────────────────────────────────────
def diagnose_lots(Ls: pd.DataFrame, tp: float, sl: float, cal: Sequence[date], cal_idx: Dict[date, int],
                  book: Dict[str, Tuple[np.ndarray, np.ndarray, np.ndarray]], corp_dates: Dict[str, np.ndarray],
                  imp_dates: Dict[str, np.ndarray]) -> List[Dict[str, Any]]:
    """sl·tp 로트마다 창 끝 → 제외 재판정(창 → corp_event → impossible_bar 순) → 짝 값."""
    rows: List[Dict[str, Any]] = []
    sub = Ls[Ls["exit_reason"].isin([X.EXIT_SL, X.EXIT_TP])]
    for r in sub.itertuples(index=False):
        code = r.stock_code
        E = float(r.entry_price)
        en = date.fromisoformat(r.entry_date)
        ex = date.fromisoformat(r.exit_date)
        tp_px, sl_px = barriers(E, tp, sl)
        wend = window_end(cal, cal_idx, ex)
        out: Dict[str, Any] = dict(strategy=r.strategy, scan_date=r.scan_date, stock_code=code, entry_date=r.entry_date,
                                   entry_price=E, exit_date=r.exit_date, exit_reason=r.exit_reason,
                                   exit_price=r.exit_price, tp_barrier=tp_px, sl_barrier=sl_px,
                                   window_end=wend.isoformat() if wend else "", excl="", corp_in_win="",
                                   imp_in_win="", n_bars_win="", max_high_win="", min_low_win="", hit="", logval="")
        if wend is None or wend > WIN_END_MAX:
            out["excl"] = EXCL_WIN
            rows.append(out)
            continue
        corp = R.any_in(corp_dates.get(code), en, wend)
        imp = R.any_in(imp_dates.get(code), en, wend)
        out.update(corp_in_win=corp, imp_in_win=imp)
        if corp:
            out["excl"] = EXCL_CORP
        elif imp:
            out["excl"] = EXCL_IMP
        if out["excl"]:
            rows.append(out)
            continue
        ent = book.get(code)
        if ent is None:
            highs = lows = np.empty(0)
        else:
            dates, hi_a, lo_a = ent
            a, b = window_bounds(dates, ex, wend)
            highs, lows = hi_a[a:b], lo_a[a:b]
        hit, val = pair_metric(r.exit_reason, E, tp, sl, highs, lows)
        out.update(n_bars_win=len(highs), max_high_win=float(highs.max()) if len(highs) else "",
                   min_low_win=float(lows.min()) if len(lows) else "", hit=hit, logval=val)
        rows.append(out)
    return rows


def same_bar_rows(Ls: pd.DataFrame, tp: float, sl: float,
                  minutes: Dict[Tuple[str, str], List[Tuple[str, float, float]]]) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    sub = Ls[Ls["flags"].map(lambda s: has_flag(s, X.FLAG_SL_TP_BOTH))]
    for r in sub.itertuples(index=False):
        E = float(r.entry_price)
        tp_px, sl_px = barriers(E, tp, sl)
        ex = date.fromisoformat(r.exit_date)
        key = (r.stock_code, ex.strftime("%Y%m%d"))
        allrows = minutes.get(key, []) if ex >= MINUTE_FROM else []
        sess = [b for b in allrows if SESSION[0] <= b[0] <= SESSION[1]]
        cat, t = (reclassify_minutes(E, tp, sl, sess) if allrows else ("분봉 없음", None))
        ret_before = float(r.ret_pct)
        ret_after = (tp_px - E) / E * 100.0 if cat == MIN_TP_FIRST else ret_before
        out.append(dict(strategy=r.strategy, scan_date=r.scan_date, stock_code=r.stock_code, entry_price=E,
                        exit_date=r.exit_date, hold_days=r.hold_days, tp_barrier=tp_px, sl_barrier=sl_px,
                        n_minute_rows=len(allrows), n_session_bars=len(sess), category=cat,
                        first_touch_time=t or "", ret_before=ret_before, ret_after=ret_after))
    return out


def main(argv: Optional[Sequence[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="청산 경로 진단 §2~3 (사전등록 동결 0bfbe92)")
    ap.add_argument("--pilot", action="store_true", help=f"scan_date {PILOT_MONTH} 로트만 · 시간·건수만 인쇄")
    ap.add_argument("--out", default=None)
    a = ap.parse_args(argv)
    out_dir = Path(a.out) if a.out else (BASE / "pilot" if a.pilot else BASE)
    started = datetime.now().isoformat(timespec="seconds")
    T0 = time.perf_counter()

    # ── 가드 ──
    md5s = check_inputs()
    prereg_blob = check_prereg_frozen()
    sha = R.git_sha()
    ledger_meta = json.loads((LEDGER_DIR / "run_meta.json").read_text(encoding="utf-8"))
    brackets: Dict[str, Tuple[float, float]] = {}
    for f in EXPECT_L:
        spec, er = R.STRATS[f], ledger_meta["exit_rules"][f]
        if (round(er["tp"], 9), round(er["sl"], 9)) != (spec["tp"], spec["sl"]):
            raise SystemExit(f"🔴 브래킷 불일치 {f}: 원장 run_meta {er} ≠ PREREG §6 ({spec['tp']}, {spec['sl']}) — 중단")
        brackets[f] = (spec["tp"], spec["sl"])
    log(f"[가드] md5 6항목 ✓ · 사전등록 blob = {PREREG_SHA} ✓ · 브래킷 = 원장 PREREG §6 ✓ · sha {sha[:10]}")

    # ── 모집단 L ──
    led = pd.read_csv(LEDGER_DIR / "ledger.csv", dtype=str, keep_default_na=False)
    L = led[(led["band_ok"] == "True") & (led["exit_reason"] != X.EXIT_OPEN) & (led["exit_reason"] != "")
            & (led["entry_price"] != "")].copy()
    n_L = {f: int((L["strategy"] == f).sum()) for f in EXPECT_L}
    log(f"[L] 원장 {len(led):,}행 → L {len(L):,} · " + " · ".join(
        f"{SHORT[f]} {n_L[f]:,}(기대 {EXPECT_L[f]:,}{' ✓' if n_L[f] == EXPECT_L[f] else ' ≠'})" for f in EXPECT_L))
    if a.pilot:
        L = L[L["scan_date"].str.startswith(PILOT_MONTH)].copy()
        log(f"[파일럿] scan_date {PILOT_MONTH} → {len(L):,} 로트")

    # ── DB 로드 ──
    t = time.perf_counter()
    conn = R._connect()
    cal = [pd.Timestamp(d).date() for d in LD.load_trading_calendar(conn, R.PX_START, R.W_END)]
    cal_idx = {d: i for i, d in enumerate(cal)}
    fp = LD.db_fingerprint(conn, R.PX_START, R.W_END)
    fp_ledger = ledger_meta.get("db_fingerprint", {})
    fp_same = fp["sha256"] == fp_ledger.get("sha256")
    n_fp_diff = sum(1 for c, h in fp["per_stock"].items() if fp_ledger.get("per_stock", {}).get(c) != h) + \
        sum(1 for c in fp_ledger.get("per_stock", {}) if c not in fp["per_stock"])
    fp_note = "= 원장 실행 지문 ✓" if fp_same else f"≠ 원장 지문 {str(fp_ledger.get('sha256'))[:12]} · 종목 {n_fp_diff}"
    log(f"[로드] 달력 {len(cal)}일({cal[0]}~{cal[-1]}) · DB 지문 {fp['sha256'][:12]} ({fp_note})")
    px = LD.load_prices(conn, R.PX_START, R.W_END)
    fl = FL.compute_bar_flags(px)
    m_imp = fl["flag_padding"] | fl["flag_locked_limit"] | fl["flag_cliff"]
    imp_dates = R._date_index(zip(px.loc[m_imp, "stock_code"], px.loc[m_imp, "date"]))
    corp_dates = R._date_index(LD.load_corp_events(conn).keys())
    codes_L = set(L["stock_code"])
    cal_set = set(pd.Timestamp(d) for d in cal)
    sub = px[px["stock_code"].isin(codes_L)]
    on_cal = sub["date"].isin(cal_set)
    n_offcal = int((~on_cal).sum())
    sub = sub[on_cal]
    book = {str(c): (g["date"].to_numpy(dtype="datetime64[ns]"), g["high"].to_numpy(dtype=float),
                     g["low"].to_numpy(dtype=float)) for c, g in sub.groupby("stock_code", sort=False)}
    secs_load = time.perf_counter() - t
    log(f"[로드] px {len(px):,}행 · 불가능봉 {int(m_imp.sum()):,} · corp_event 종목 {len(corp_dates):,} · "
        f"L 종목 {len(codes_L):,} · 달력 밖 봉 {n_offcal}(창에서 제외) · {secs_load:.0f}s")

    # ── 전략별 §2 ──
    t = time.perf_counter()
    lots: List[Dict[str, Any]] = []
    for f in EXPECT_L:
        tp, sl = brackets[f]
        rows = diagnose_lots(L[L["strategy"] == f], tp, sl, cal, cal_idx, book, corp_dates, imp_dates)
        lots += rows
        log(f"[{SHORT[f]}] 짝 대상 sl·tp 로트 {len(rows):,} · 제외 {sum(1 for x in rows if x['excl']):,}")
    secs_lots = time.perf_counter() - t

    # ── (a) 분봉 재분류 ──
    t = time.perf_counter()
    sb = L[L["flags"].map(lambda s: has_flag(s, X.FLAG_SL_TP_BOTH))]
    pairs = [(c, date.fromisoformat(d).strftime("%Y%m%d")) for c, d in zip(sb["stock_code"], sb["exit_date"])
             if date.fromisoformat(d) >= MINUTE_FROM]
    minutes = load_minutes(conn, pairs)
    conn.close()
    sbrows: List[Dict[str, Any]] = []
    for f in EXPECT_L:
        tp, sl = brackets[f]
        sbrows += same_bar_rows(L[L["strategy"] == f], tp, sl, minutes)
    n_min_rows = sum(len(v) for v in minutes.values())
    n_min_off = sum(1 for v in minutes.values() for b in v if not (SESSION[0] <= b[0] <= SESSION[1]))
    secs_min = time.perf_counter() - t
    log(f"[a] 같은 봉 동시 {len(sb):,} · 분봉 조회 쌍 {len(set(pairs)):,} · 행 있음 {len(minutes):,} · "
        f"분봉 {n_min_rows:,}행(정규장 밖 {n_min_off}) · {secs_min:.1f}s")

    # ── §3 부트스트랩 ──
    t = time.perf_counter()
    ldf = pd.DataFrame(lots, columns=LOT_COLS)
    diag = ldf[ldf["excl"] == ""].copy()
    res: Dict[str, Dict[str, Any]] = {}
    for f in EXPECT_L:
        d = diag[diag["strategy"] == f]
        codes, agg = aggregate(d)
        st = pair_stats(agg)
        rng = np.random.default_rng([SEED_ROOT, SEED_STREAM, STRAT_IDX[f]])
        d_b, d_c = bootstrap_diffs(agg, rng, N_BOOT)
        res[f] = dict(n_codes=len(codes), st=st, d_b=d_b, d_c=d_c, agg={k: float(v.sum()) for k, v in agg.items()})
    secs_boot = time.perf_counter() - t
    secs_total = time.perf_counter() - T0

    if a.pilot:
        n_all = sum(EXPECT_L.values())
        per_lot = (secs_lots + secs_min + secs_boot) / max(1, len(L))
        est = secs_load + per_lot * n_all
        pilot = dict(started=started, pilot_month=PILOT_MONTH, n_lots=len(L), n_pair_lots=len(lots),
                     n_same_bar=len(sb), secs_load=round(secs_load, 1), secs_lots=round(secs_lots, 2),
                     secs_minute=round(secs_min, 2), secs_boot=round(secs_boot, 2), secs_total=round(secs_total, 1),
                     est_full_secs=round(est, 1), db_fingerprint_same_as_ledger=fp_same, git_sha=sha)
        R._atomic_write(out_dir / "pilot_timing.json", json.dumps(pilot, ensure_ascii=False, indent=1))
        log(f"[파일럿] 로트 {len(L):,} · 로드 {secs_load:.0f}s · 로트 {secs_lots:.1f}s · 분봉 {secs_min:.1f}s · "
            f"부트 {secs_boot:.1f}s · 전체 추정 ≈ {est:.0f}s ({est / 3600:.2f}시간) · 짝 값은 인쇄하지 않음")
        return 0

    # ── 출력 ──
    out_dir.mkdir(parents=True, exist_ok=True)
    R.write_csv(out_dir / "exit_diag_lots.csv", LOT_COLS, [{k: R._fmt(v) for k, v in x.items()} for x in lots])
    R.write_csv(out_dir / "same_bar_minute.csv", MIN_COLS, [{k: R._fmt(v) for k, v in x.items()} for x in sbrows])
    md, summary = render(L, ldf, sbrows, res, brackets, n_L, md5s, fp, fp_same, n_fp_diff, n_offcal,
                         dict(n_pairs=len(set(pairs)), n_with=len(minutes), n_rows=n_min_rows, n_off=n_min_off),
                         sha, started)
    finished = datetime.now().isoformat(timespec="seconds")
    meta = dict(prereg=f"{PREREG} ({PREREG_SHA})", prereg_blob=prereg_blob, git_sha=sha, started=started,
                finished=finished, secs_total=round(time.perf_counter() - T0, 1), secs_load=round(secs_load, 1),
                secs_lots=round(secs_lots, 2), secs_minute=round(secs_min, 2), secs_boot=round(secs_boot, 2),
                input_md5=md5s, db_fingerprint=dict((k, fp[k]) for k in ("sha256", "md5", "n_stocks", "n_rows",
                                                                          "window", "cols")),
                db_fingerprint_same_as_ledger_run=fp_same, db_fingerprint_n_stock_diff=n_fp_diff,
                ledger_run_git_sha=ledger_meta.get("git_sha"), W=W, X_pp=X_PP, n_boot=N_BOOT, min_den=MIN_DEN,
                seeds={SHORT[f]: [SEED_ROOT, SEED_STREAM, STRAT_IDX[f]] for f in EXPECT_L},
                seed_s_meaning="s = 전략 인덱스(ma20=0, minervini=1, daytrading=2) · 해석 기록 H1",
                brackets={SHORT[f]: dict(tp=brackets[f][0], sl=brackets[f][1]) for f in EXPECT_L},
                n_L=n_L, n_L_expected=dict(EXPECT_L), calendar=[cal[0].isoformat(), cal[-1].isoformat(), len(cal)],
                n_offcal_bars_dropped=n_offcal, summary=summary,
                outputs=["RESULTS_exit_diag.md", "exit_diag_lots.csv", "same_bar_minute.csv", "run_meta.json"])
    R._atomic_write(out_dir / "run_meta.json", json.dumps(meta, ensure_ascii=False, indent=1, default=str))
    R._atomic_write(out_dir / "RESULTS_exit_diag.md", md)
    log(f"[끝] {time.perf_counter() - T0:.0f}s → {out_dir}")
    for f in EXPECT_L:
        log(f"  {SHORT[f]}: {summary[SHORT[f]]['label']}")
    return 0


# ────────────────────────────────────────────────────────────────────────────
# 결과 문서
# ────────────────────────────────────────────────────────────────────────────
def render(L: pd.DataFrame, ldf: pd.DataFrame, sbrows: List[Dict[str, Any]], res: Dict[str, Dict[str, Any]],
           brackets: Dict[str, Tuple[float, float]], n_L: Dict[str, int], md5s: Dict[str, str], fp: Dict[str, Any],
           fp_same: bool, n_fp_diff: int, n_offcal: int, mininfo: Dict[str, int], sha: str,
           started: str) -> Tuple[str, Dict[str, Any]]:
    S: List[str] = []
    summary: Dict[str, Any] = {}
    A = S.append
    A("# 청산 경로 진단(관측) — 결과 · §2~3")
    A("")
    A(f"> 🔒 규범 = `{PREREG}`(동결 `{PREREG_SHA}`) §2~3 · 🔴 관측 · p 없음 · **라이브 룰 변경 근거 인용 금지**(§7-6 · "
      "~2026-10-16 3전략 룰 변경 0건) · §4 짝 비교 변형 **미실행**(§7-2) · §5 무작위 진입 대조군 **미작성·미실행**(교정 합격 뒤).")
    A("")
    A(f"- 실행 git `{sha[:10]}`(브랜치 `research/candidate-ledger`) · 시작 {started} · 코드 `exit_diag/run_exit_diag.py`")
    A(f"- 입력 md5: ledger `{md5s['ledger_worktree']}` · scan_diag `{md5s['scan_diag_worktree']}` — 동결값·보관소 "
      "MD5SUMS·보관소 파일 6항목 전부 일치 ✓")
    A(f"- DB 지문(`loader.db_fingerprint` · 2023-01-02..2026-09-23) sha256 `{fp['sha256'][:16]}…` · 종목 {fp['n_stocks']:,} "
      f"· 행 {fp['n_rows']:,} · 원장 실행 지문과 {'**같음** ✓' if fp_same else f'**다름** 🔴(종목 {n_fp_diff})'}")
    A(f"- W = {W} 거래일(KOSPI 달력) · X = {X_PP}%p · 부트스트랩 {N_BOOT:,}회 · 시드 `default_rng([{SEED_ROOT}, "
      f"{SEED_STREAM}, s])` s = 전략 인덱스(ma20 0 · minervini 1 · daytrading 2) · 분모 < {MIN_DEN} ⇒ 판정 불가")
    A("")

    # ── 1. 모집단 ──
    A("## 1. 주 모집단 L · 제외 재판정")
    A("")
    A("| 전략 | L 로트(실측) | 기대(패널 ①-5) | sl | tp | 그 밖(trail_ma·max_hold) |")
    A("|---|---|---|---|---|---|")
    for f in EXPECT_L:
        r = L[L["strategy"] == f]
        vc = r["exit_reason"].value_counts()
        other = " · ".join(f"{k} {v:,}" for k, v in vc.items() if k not in (X.EXIT_SL, X.EXIT_TP)) or "0"
        A(f"| {SHORT[f]} | {n_L[f]:,} | {EXPECT_L[f]:,} {'✓' if n_L[f] == EXPECT_L[f] else '≠'} | "
          f"{int(vc.get(X.EXIT_SL, 0)):,} | {int(vc.get(X.EXIT_TP, 0)):,} | {other} |")
    A(f"| 합 | {sum(n_L.values()):,} | {sum(EXPECT_L.values()):,} | | | |")
    A("")
    A("제외(짝 지표 (b)~(c′) 대상 = sl·tp 로트 · 순서 적용: ① 창 끝 > 2026-09-23 → ② corp_event → ③ impossible_bar · "
      "②③ 은 `[entry_date, exit_date + W]` 재판정):")
    A("")
    A("| 전략 | 청산 | 로트 | ① 창 끝 초과 | ② corp_event | ③ impossible_bar | 진단 로트 | 참고: ②∧③ 겹침 | 창 안 봉 0개 | 창 안 봉 < W |")
    A("|---|---|---|---|---|---|---|---|---|---|")
    for f in EXPECT_L:
        for rsn in (X.EXIT_SL, X.EXIT_TP):
            d = ldf[(ldf["strategy"] == f) & (ldf["exit_reason"] == rsn)]
            ok = d[d["excl"] == ""]
            both = int(((d["corp_in_win"] == True) & (d["imp_in_win"] == True)).sum())  # noqa: E712
            nb = pd.to_numeric(ok["n_bars_win"], errors="coerce")
            A(f"| {SHORT[f]} | {rsn} | {len(d):,} | {int((d['excl'] == EXCL_WIN).sum()):,} | "
              f"{int((d['excl'] == EXCL_CORP).sum()):,} | {int((d['excl'] == EXCL_IMP).sum()):,} | {len(ok):,} | "
              f"{both} | {int((nb == 0).sum())} | {int((nb < W).sum())} |")
    A("")
    A(f"- 달력(KOSPI 행)에 없는 날짜의 종목 봉 {n_offcal}행은 창에서 뺐다(원장 청산 시뮬도 달력 날짜 봉만 쓴다 · 해석 기록 H7).")
    A("")

    # ── 2. 짝 ──
    A("## 2. 로그 대칭 짝 · §3 판정")
    A("")
    A("장벽 사이 로그 거리 `ln((1+tp)/(1−sl))`: " + " · ".join(
        f"{SHORT[f]} {math.log((1 + brackets[f][0]) / (1 - brackets[f][1])):.3f}" for f in EXPECT_L) + "(산술 재확인)")
    A("")
    A("| 전략 | 짝 | 값 1 (분모) | 값 2 (분모) | 차 값1−값2 (%p) | 95% CI (%p) | 짝 판정 | 방향(인쇄만) |")
    A("|---|---|---|---|---|---|---|---|")
    for f in EXPECT_L:
        rr = res[f]
        st, ag = rr["st"], rr["agg"]
        db = (st["b"] - st["bp"]) * 100.0
        dc = (st["c"] - st["cp"]) * 100.0
        lo_b, hi_b = ci95(rr["d_b"])
        lo_c, hi_c = ci95(rr["d_c"])
        vb = pair_verdict(db, lo_b, hi_b, int(ag["b_den"]), int(ag["bp_den"]))
        vc = pair_verdict(dc, lo_c, hi_c, int(ag["c_den"]), int(ag["cp_den"]))
        lab = strategy_label(vb, vc)
        A(f"| {SHORT[f]} | (b) 손절 뒤 익절가 도달률 vs (b′) 익절 뒤 손절가 도달률 | {st['b'] * 100:.2f}% "
          f"({int(ag['b_den']):,}) | {st['bp'] * 100:.2f}% ({int(ag['bp_den']):,}) | {db:+.2f} | "
          f"[{lo_b:+.2f}, {hi_b:+.2f}] | {vb} | {'(b) > (b′)' if db > 0 else '(b) < (b′)' if db < 0 else '같음'} |")
        A(f"| {SHORT[f]} | (c) 익절 뒤 추가 상승폭 vs (c′) 손절 뒤 추가 하락폭 | {st['c'] * 100:.2f}%p "
          f"({int(ag['c_den']):,}) | {st['cp'] * 100:.2f}%p ({int(ag['cp_den']):,}) | {dc:+.2f} | "
          f"[{lo_c:+.2f}, {hi_c:+.2f}] | {vc} | {'(c) > (c′)' if dc > 0 else '(c) < (c′)' if dc < 0 else '같음'} |")
        summary[SHORT[f]] = dict(label=lab, b=st["b"] * 100, bp=st["bp"] * 100, c=st["c"] * 100, cp=st["cp"] * 100,
                                 diff_b=db, ci_b=[lo_b, hi_b], verdict_b=vb, diff_c=dc, ci_c=[lo_c, hi_c],
                                 verdict_c=vc, n_codes=rr["n_codes"], den={k: int(v) for k, v in ag.items()
                                                                          if k.endswith("den")})
    A("")
    A("**전략별 라벨(§3)**")
    A("")
    for f in EXPECT_L:
        A(f"- **{SHORT[f]}** — 「{summary[SHORT[f]]['label']}」 (종목 클러스터 {res[f]['n_codes']:,}개)")
    A("")
    A("(c)·(c′) 분포(로트 단위 로그 폭 ×100 = %p · 음수 = 창 안에서 장벽까지 다시 못 감):")
    A("")
    A("| 전략 | 지표 | n | 평균 | p10 | p25 | p50 | p75 | p90 | > 0 비율 |")
    A("|---|---|---|---|---|---|---|---|---|---|")
    diag = ldf[ldf["excl"] == ""]
    for f in EXPECT_L:
        for rsn, nm in ((X.EXIT_TP, "(c) 익절 뒤 ln(max high / 익절 장벽)"), (X.EXIT_SL, "(c′) 손절 뒤 −ln(min low / 손절 장벽)")):
            v = pd.to_numeric(diag[(diag["strategy"] == f) & (diag["exit_reason"] == rsn)]["logval"],
                              errors="coerce").dropna().to_numpy() * 100.0
            qs = q(v)
            A(f"| {SHORT[f]} | {nm} | {len(v):,} | {f2(float(v.mean()) if len(v) else float('nan'))} | "
              + " | ".join(f2(x) for x in qs) + f" | {f2(float((v > 0).mean()) * 100 if len(v) else float('nan'), 1)}% |")
    A("")

    # ── 3. 보조 ──
    A("## 3. 보조 인쇄(판정 없음)")
    A("")
    A("### (a) 같은 봉 동시 터치 — 측정 문제로만 다룬다(🔒 짝 비교·브래킷 변경 근거 아님 · §7-3)")
    A("")
    sbd = pd.DataFrame(sbrows, columns=MIN_COLS)
    A("| 전략 | sl 로트 | 동시 터치(손절 우선) | ÷ sl | 봉 날짜 ≥ 2025-02-24 | 그중 분봉 행 있음 | 손절 먼저 | 익절 먼저 | "
      "한 분봉 안 동시(미해결) | 분봉 미도달(미해결) |")
    A("|---|---|---|---|---|---|---|---|---|---|")
    for f in EXPECT_L:
        r = L[L["strategy"] == f]
        n_sl = int((r["exit_reason"] == X.EXIT_SL).sum())
        s = sbd[sbd["strategy"] == f]
        post = s[pd.to_datetime(s["exit_date"]) >= pd.Timestamp(MINUTE_FROM)]
        withm = s[s["n_minute_rows"] > 0]
        cc = Counter(withm["category"])
        A(f"| {SHORT[f]} | {n_sl:,} | {len(s):,} | {len(s) / n_sl * 100 if n_sl else float('nan'):.2f}% | {len(post):,} | "
          f"{len(withm):,} | " + " | ".join(str(cc.get(k, 0)) for k in MIN_CATS) + " |")
    A("")
    A(f"- 분봉 조회 (종목, 봉 날짜) 쌍 {mininfo['n_pairs']:,} · 행 있음 {mininfo['n_with']:,} · 분봉 {mininfo['n_rows']:,}행 · "
      f"정규장({SESSION[0][:2]}:{SESSION[0][2:4]}~{SESSION[1][:2]}:{SESSION[1][2:4]}) 밖 {mininfo['n_off']}행(재분류에서 뺌).")
    A("")
    A("재분류 뒤 승률·평균 `ret_pct`(「익절 먼저」 로트만 ret = 익절 장벽 수익으로 바꿈 · 나머지 그대로 · 경로 뒤 재시뮬 없음 — "
      "그 봉에서 어느 쪽이든 청산이므로):")
    A("")
    A("| 전략 | 범위 | n | 승률 전 | 승률 뒤 | 평균 ret_pct 전 | 평균 ret_pct 뒤 |")
    A("|---|---|---|---|---|---|---|")
    for f in EXPECT_L:
        s = sbd[(sbd["strategy"] == f) & (sbd["n_minute_rows"] > 0)]
        rb, ra = s["ret_before"].astype(float), s["ret_after"].astype(float)
        A(f"| {SHORT[f]} | 동시 터치 ∧ 분봉 있음 | {len(s):,} | {f2((rb > 0).mean() * 100 if len(s) else float('nan'))}% | "
          f"{f2((ra > 0).mean() * 100 if len(s) else float('nan'))}% | {f2(rb.mean() if len(s) else float('nan'))} | "
          f"{f2(ra.mean() if len(s) else float('nan'))} |")
        r = L[L["strategy"] == f]
        ret = pd.to_numeric(r["ret_pct"], errors="coerce").to_numpy()
        adj = ret.copy()
        key = {(a, b, c): v for a, b, c, v in zip(s["scan_date"], s["stock_code"], s["exit_date"], ra)}
        for i, (a, b, c) in enumerate(zip(r["scan_date"], r["stock_code"], r["exit_date"])):
            if (a, b, c) in key:
                adj[i] = key[(a, b, c)]
        A(f"| {SHORT[f]} | L 전체 | {len(r):,} | {f2((ret > 0).mean() * 100)}% | {f2((adj > 0).mean() * 100)}% | "
          f"{f2(float(ret.mean()), 3)} | {f2(float(adj.mean()), 3)} |")
    A("")

    A("### (d) 갭 청산")
    A("")
    A("| 전략 | 갭 손절 `sl_gap_open` | ÷ sl | 갭 익절 `gap_tp_open` | ÷ tp | 갭 손절 미끄러짐 `exit_price/(E×(1−sl))−1` 평균 | p10 | p50 | p90 |")
    A("|---|---|---|---|---|---|---|---|---|")
    for f in EXPECT_L:
        tp, sl = brackets[f]
        r = L[L["strategy"] == f]
        s_ = r[r["exit_reason"] == X.EXIT_SL]
        t_ = r[r["exit_reason"] == X.EXIT_TP]
        g = s_[s_["flags"].map(lambda z: has_flag(z, X.FLAG_SL_GAP_0905))]
        gt = int(t_["flags"].map(lambda z: has_flag(z, X.FLAG_GAP_TP)).sum())
        slip = (g["exit_price"].astype(float) / (g["entry_price"].astype(float) * (1 - sl)) - 1.0).to_numpy() * 100.0
        qs = q(slip, (10, 50, 90))
        A(f"| {SHORT[f]} | {len(g):,} | {len(g) / max(1, len(s_)) * 100:.2f}% | {gt:,} | {gt / max(1, len(t_)) * 100:.2f}% | "
          f"{f2(float(slip.mean()) if len(slip) else float('nan'))}% | " + " | ".join(f"{f2(x)}%" for x in qs) + " |")
    A("")

    A("### (e) 보유일 · 승률 vs 손익분기")
    A("")
    A("| 전략 | exit_reason | n | hold_days 평균 | p10 | p50 | p90 | 최대 |")
    A("|---|---|---|---|---|---|---|---|")
    for f in EXPECT_L:
        r = L[L["strategy"] == f]
        for rsn, g in r.groupby("exit_reason"):
            h = pd.to_numeric(g["hold_days"], errors="coerce").dropna().to_numpy()
            qs = q(h, (10, 50, 90))
            A(f"| {SHORT[f]} | {rsn} | {len(g):,} | {f2(float(h.mean()), 1)} | " + " | ".join(f2(x, 0) for x in qs)
              + f" | {int(h.max())} |")
    A("")
    A("| 전략 | 실제 승률(ret_pct > 0) | 손익분기 sl/(tp+sl) | 비용 반영 (sl+0.25)/(tp+sl) | 승률 − 비용 반영 분기 (%p) |")
    A("|---|---|---|---|---|")
    for f in EXPECT_L:
        tp, sl = brackets[f]
        r = L[L["strategy"] == f]
        wr = float((pd.to_numeric(r["ret_pct"], errors="coerce") > 0).mean() * 100.0)
        be, bec = breakeven(tp, sl)
        summary[SHORT[f]].update(win_rate=wr, breakeven=be, breakeven_cost=bec)
        A(f"| {SHORT[f]} | {wr:.2f}% | {be:.2f}% | {bec:.2f}% | {wr - bec:+.2f} |")
    A("")
    A("- 손익분기는 문서 §2 (e) 대로 trail·max_hold 를 무시한 근사다(ma20 trail_ma · daytrading max_hold 비중이 크면 어긋난다).")
    A("")

    A("### (f) 비용 차감 손익(로트당 비용 = notional × 0.25% · 원 단위 정수)")
    A("")
    A("| 전략 | 로트 | gross 합(원) | 비용 합(원) | net 합(원) | 로트당 net 평균(원) | `ret_pct − 0.25` 평균(%) |")
    A("|---|---|---|---|---|---|---|")
    for f in EXPECT_L:
        r = L[L["strategy"] == f]
        gross = pd.to_numeric(r["pnl_won"], errors="coerce").fillna(0).to_numpy()
        cost = pd.to_numeric(r["notional"], errors="coerce").fillna(0).to_numpy() * COST_PCT / 100.0
        net = gross - cost
        rp = pd.to_numeric(r["ret_pct"], errors="coerce").to_numpy() - COST_PCT
        summary[SHORT[f]].update(gross=int(round(gross.sum())), cost=int(round(cost.sum())), net=int(round(net.sum())),
                                 net_per_lot=int(round(net.mean())), ret_net_mean=float(np.nanmean(rp)))
        A(f"| {SHORT[f]} | {len(r):,} | {won(gross.sum())} | {won(cost.sum())} | {won(net.sum())} | {won(net.mean())} | "
          f"{np.nanmean(rp):+.3f} |")
    A("")
    A("- 전략별로만 읽는다 — 전략을 섞은 합·평균은 판정에 쓰지 않는다(§7-4). gross 원장에 비용을 산술로만 얹었다(§8).")
    A("")

    # ── 4. 손계산용 ──
    A("## 4. 손계산용 예시(verifier · 전략별 진단 로트 중 scan_date·종목 오름차순 첫 sl·tp 로트)")
    A("")
    A("| 전략 | 청산 | scan_date | 종목 | E | exit_date | 창 끝 | 익절 장벽 | 손절 장벽 | 창 max high | 창 min low | 도달 | 로그 폭 ×100 |")
    A("|---|---|---|---|---|---|---|---|---|---|---|---|---|")
    for f in EXPECT_L:
        for rsn in (X.EXIT_SL, X.EXIT_TP):
            d = diag[(diag["strategy"] == f) & (diag["exit_reason"] == rsn)].sort_values(["scan_date", "stock_code"])
            if not len(d):
                continue
            x = d.iloc[0]
            A(f"| {SHORT[f]} | {rsn} | {x['scan_date']} | {x['stock_code']} | {x['entry_price']:g} | {x['exit_date']} | "
              f"{x['window_end']} | {x['tp_barrier']:.4f} | {x['sl_barrier']:.4f} | {x['max_high_win']} | "
              f"{x['min_low_win']} | {x['hit']} | {float(x['logval']) * 100:.4f} |")
    A("")
    A("- 로트 전체 = `exit_diag_lots.csv`(제외 사유·창 끝·창 안 봉 수·max high·min low·도달·로그 폭) · "
      "분봉 재분류 = `same_bar_minute.csv`.")
    A("")

    # ── 5. 해석 기록 ──
    A("## 5. 해석 기록(문언이 애매한 곳 → 가장 문자 그대로의 해석)")
    A("")
    for line in INTERP:
        A(line)
    A("")
    A("## 6. 한계(문서 §8 인용)")
    A("")
    A("> - 일봉 근사(봉 안 순서 · 장중 청산 · 09:05 규약) — 분봉 재분류는 2025-02-24 이후 봉만 · 시가 밴드 근사 · gross 원장에 "
      "비용 0.25% 를 산술로만 얹음(세금·호가 미끄러짐 미반영).")
    A("> - W=10 은 전략 max_hold(10/20/50)와 다르다 — 「보유를 더 했으면」이 아니라 «청산 직후 가격 경로의 대칭성»만 잰다.")
    A("> - 무작위 대조는 «같은 유니버스·같은 날·같은 밴드» 조건부다 — 유니버스 필터 자체의 가치는 재지 않는다. 원장은 생존자 "
      "유니버스 · 빈티지 보정 없음(원장 PREREG §8 승계).")
    A("")
    A("## 7. §7 금지 준수")
    A("")
    A("- W·X·장벽 기준가·시드·반복 수 = 문서 값 그대로 · 브래킷 격자 탐색 0 · §4 변형 실행 0 · §5 코드 0줄 · "
      "(a) 는 측정 문제로만 인쇄 · 판정은 전략별(섞은 평균 0) · 라이브 0줄 · DB SELECT 만.")
    return "\n".join(S) + "\n", summary


INTERP = [
    "- **H1 시드 `s`** — §3 `default_rng([20261002, 1, s])` 의 `s` 는 정의가 없다. §5 가 반복 인덱스를 `r`·`j` 로 따로 쓰므로 "
    "여기 `s` 는 **전략 인덱스**(ma20=0 · minervini=1 · daytrading=2 · 문서 §1·§2 표 순서)로 읽었다. 반복마다 "
    "`rng.integers(0, G, G)`(G = 그 전략 진단 로트의 종목 수 · 종목코드 오름차순)로 종목을 복원추출한다.",
    "- **H2 CI** — 부트스트랩 차 2,000개의 백분위 2.5·97.5(`numpy.nanpercentile` 선형 보간). 「0 배제」 = 하한 > 0 또는 상한 < 0. "
    "점추정(표의 값·차)은 원표본 값이다.",
    "- **H3 장벽 비교식** — 문서 `high ≥ E×(1+tp)` · `low ≤ E×(1−sl)` 를 원장·라이브와 같은 수익률 비교 "
    "`(px−E)/E ≥ tp` · `≤ −sl` 로 구현했다(수학적으로 같음). 가격 곱셈 비교는 부동소수 오차로 경계가 어긋난다"
    "(예: E=10,000 · tp 0.12 → E×1.12 = 11200.000000000002 라 고가 11,200 이 「미도달」이 된다 · 정수 가격 격자에서 "
    "익절 쪽만 생기고 손절 쪽은 안 생겨 (b)·(b′) 에 «비대칭» 오차를 만든다 · 수익률 비교식은 정수 장벽 125,958건 전수에서 "
    "누락 0 · 테스트로 고정).",
    "- **H4 제외 적용 범위** — 창 끝 초과·corp_event·impossible_bar 제외는 문서대로 짝 지표 (b)~(c′) 에만 적용했다. "
    "보조 (a)(d)(e)(f) 는 창이 필요 없으므로 L 전체(해당 청산 사유) 기준이다. 제외 사유별 건수는 폭포식(① → ② → ③ 순서 · "
    "앞 사유에 걸리면 뒤는 세지 않음)이고, ②∧③ 겹침은 참고 열로 따로 인쇄했다. impossible_bar = "
    "`compute_bar_flags` 의 padding ∨ locked_limit ∨ cliff(원장 `run.py:781-782` 와 같은 합성 · 원장과 같은 가격 창 "
    "2023-01-02~ 전체로 계산). corp_event = `loader.load_corp_events`(bonus_issue·split·rights_issue event_date). "
    "구간 `[entry_date, 창 끝]` 은 양끝 포함.",
    "- **H5 (a) 분봉 재분류** — 봉 날짜 = 원장 `exit_date`(동시 터치 봉 = 청산 봉). `minute_candles` 는 `(stock_code, trade_date)`"
    "(PK)로 묶고 `time` 오름차순. 정규장 09:00:00~15:30:00 분봉만 쓴다. 첫 번째로 장벽에 닿은 분봉이 손절만 → 「손절 먼저」 · "
    "익절만 → 「익절 먼저」 · 둘 다 → 「한 분봉 안 동시(미해결)」 · 어느 분봉도 안 닿음 → 「분봉 미도달(미해결)」(일봉·분봉 "
    "불일치 · 문서의 3분류 밖이라 따로 인쇄). 라이브 손절 09:05 규약은 재분류에 넣지 않았다(문서가 요구하지 않음 · 한계 §8). "
    "재분류 뒤 값은 「익절 먼저」 로트의 ret 만 익절 장벽 수익으로 바꾼 것이다.",
    "- **H6 창 안 봉 0개** — (b)(b′) 는 문서 문언(「sl 로트 중 … 봉이 있는 비율」)대로 분모에 넣고 미도달로 센다 · "
    "(c)(c′) 는 max/min 이 정의되지 않아 그 로트만 뺀다(건수는 §1 표 「창 안 봉 0개」 열). 창 안 봉이 W 개보다 적은 로트(결측)는 "
    "있는 봉만 쓴다.",
    "- **H7 창의 봉** — 창은 KOSPI 달력 거래일로 정의되므로 달력에 없는 날짜의 종목 행(예: 2026-01-11 일요일 가짜 행)은 창에서 "
    "뺐다(원장 청산 시뮬도 달력 날짜 봉만 본다). impossible_bar 재판정은 원장과 같게 가격 행 전체로 했다.",
    "- **H8 (c)(c′) 부호** — 문서 식을 그대로 쓰고 자르지 않았다: 창 안에서 장벽까지 다시 가지 못하면 (c)·(c′) 값은 음수다"
    "(「추가 상승·하락폭」이 0 아래 = 되돌림). 분포 표에 > 0 비율을 같이 인쇄했다.",
    "- **H9 짝 판정 → 전략 라벨** — 한 짝이라도 「비대칭」 ⇒ 「비대칭 → 짝 비교 사전등록으로 넘어감」. 아니고 분모 < 200 짝이 "
    "하나라도 있으면 「판정 불가」. 두 짝 모두 기준 미달 ⇒ 「청산 층 정보 없음」. (b)/(b′) 짝의 분모 = sl·tp 진단 로트 수 · "
    "(c)/(c′) 짝의 분모 = 로그 폭이 정의된 로트 수.",
    "- **H10 L 필터** — `band_ok == 'True'` ∧ `exit_reason ∉ {open, ''}` ∧ `entry_price ≠ ''`(원장 CSV 문자열 그대로).",
]


if __name__ == "__main__":
    sys.exit(main())
