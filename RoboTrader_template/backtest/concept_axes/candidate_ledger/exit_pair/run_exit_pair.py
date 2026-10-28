"""청산 브래킷 짝 비교 — 사전등록 `docs/prereg_2026-09-26_exit_bracket_pair_comparison.md`(🔒 동결 dbea62a) 그대로.

    cd <worktree>/RoboTrader_template
    $PY -m backtest.concept_axes.candidate_ledger.exit_pair.run_exit_pair --pilot   # ③ 1개월 파일럿(시간·재현 가드만 · d 미열람)
    $PY -m backtest.concept_axes.candidate_ledger.exit_pair.run_exit_pair           # ④ 본 실행 → RESULTS_exit_pair.md

순서(문서 §8): 재현 가드 → 자기 표본 가짜 게이트(CR1) → 탈락 전략만 대체 도구 게이트 → 판정(E → C) → 꼬리표·병기.
🔴 관측 · shadow 재료 · 라이브 룰 변경 근거 인용 금지(§10-6) · DB SELECT 만(`bootstrap` = 읽기 전용 세션) · 재사용 모듈 수정 0줄.
재사용(🔒 §2 재구현 금지): 경로 = `run.make_window_fn`·`run.build_path` · 청산 = `exitsim8.simulate_lot` + `sellprobe8.SellProbe` ·
tp/sl = `sellprobe8.resolve_live_tp_sl`(원 값) · 에피소드 = `run_calib.episodes` · Holm = `run_random_entry.holm` ·
입력 md5 = `run_exit_diag.check_inputs` · 제외 방식 = 청산 진단 §1(`run.any_in` · 폭포식).
"""
from __future__ import annotations

from backtest.concept_axes.minervini.cap_skip_ledger import bootstrap  # noqa: F401  안전 설정 먼저

import argparse                                                        # noqa: E402
import dataclasses                                                     # noqa: E402
import hashlib                                                         # noqa: E402
import json                                                            # noqa: E402
import math                                                            # noqa: E402
import sys                                                             # noqa: E402
import time                                                            # noqa: E402
import warnings                                                        # noqa: E402
from collections import Counter, OrderedDict                           # noqa: E402
from datetime import date, datetime                                    # noqa: E402
from pathlib import Path                                               # noqa: E402
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple  # noqa: E402

import numpy as np                                                     # noqa: E402
import pandas as pd                                                    # noqa: E402
from scipy import stats as sst                                         # noqa: E402

from backtest.concept_axes.candidate_ledger import run as R            # noqa: E402
from backtest.concept_axes.candidate_ledger.exit_diag import run_exit_diag as D  # noqa: E402
from backtest.concept_axes.candidate_ledger.exit_diag import run_random_entry as RE  # noqa: E402
from backtest.concept_axes.candidate_ledger.tool_calibration import run_calib as RC  # noqa: E402
from backtest.concept_axes.ledger8 import exitsim8 as X                # noqa: E402
from backtest.concept_axes.ledger8 import sellprobe8 as SP             # noqa: E402
from backtest.concept_axes.ledger8 import sources8 as SRC8             # noqa: E402
from backtest.concept_axes.ledger8.livesignal8 import load8            # noqa: E402
from backtest.concept_axes.replayer import flags as FL                 # noqa: E402
from backtest.concept_axes.replayer import loader as LD                # noqa: E402

warnings.filterwarnings("ignore", message="pandas only supports SQLAlchemy")

BASE = Path(__file__).resolve().parent
LEDGER_DIR = D.LEDGER_DIR
PREREG = "docs/prereg_2026-09-26_exit_bracket_pair_comparison.md"
PREREG_SHA = "dbea62a"
STRATS = list(D.EXPECT_L)                          # ma20 → minervini → daytrading (s = 0, 1, 2 · 시드 순서)
SHORT = D.SHORT
S_IDX = {f: i for i, f in enumerate(STRATS)}

# ── §1 입력 🔒 ──────────────────────────────────────────────────────────────
FP_PREFIX = "59c14921"                             # loader.db_fingerprint sha256 — 원장·진단 실행과 같아야 한다
A51 = "a51c631"                                    # 원장 실행 코드 — 아래 8파일 blob 기준
GUARD8 = ["backtest/concept_axes/ledger8/exitsim8.py", "backtest/concept_axes/ledger8/sellprobe8.py",
          "backtest/concept_axes/ledger8/sources8.py", "backtest/concept_axes/minervini/cap_skip_ledger/sim.py",
          "backtest/concept_axes/replayer/loader.py", "backtest/concept_axes/replayer/flags.py",
          "utils/korean_holidays.py", "core/trading_decision_engine.py"]
HORIZON_MAX = date(2026, 9, 23)                    # ① 수평선 끝 상한
WIN = OrderedDict([("E", ("2024-03-13", "2025-06-30")), ("C", ("2025-07-01", "2026-09-23"))])
W_IDX = {"E": 0, "C": 1}
EXPECT_TAB = {  # §1 구조 계수(작성 중 실측 · ②③④ 적용 «전») — 대조 인쇄용
    "book_pullback_ma20": dict(L_E=9733, L_C=8283, ex1=1294, post1_E=9733, post1_C=6989, first_E=8447,
                               first_C=6180, codes_E=1664, codes_C=1573, per_day_E=26.9),
    "minervini_volume_dryup": dict(L_E=3495, L_C=5011, ex1=72, post1_E=3495, post1_C=4939, first_E=1019,
                                   first_C=1596, codes_E=313, codes_C=451, per_day_E=3.5),
    "daytrading_3methods_breakout": dict(L_E=7629, L_C=7371, ex1=121, post1_E=7629, post1_C=7250, first_E=6760,
                                         first_C=6375, codes_E=1794, codes_C=1759, per_day_E=21.5),
}

# ── §2 변형 🔒 (모문서 §4 표 글자 그대로 · (tp, sl)) ─────────────────────────────
VNAMES = ["V1", "V2", "V3", "V4"]
VDESC = {"V1": "손절 좁힘", "V2": "손절 넓힘", "V3": "익절 좁힘", "V4": "익절 넓힘"}
VARIANTS: Dict[str, Dict[str, Tuple[float, float]]] = {
    "book_pullback_ma20": {"V1": (0.10, 0.06), "V2": (0.10, 0.10), "V3": (0.08, 0.08), "V4": (0.12, 0.08)},
    "minervini_volume_dryup": {"V1": (0.12, 0.06), "V2": (0.12, 0.10), "V3": (0.10, 0.08), "V4": (0.14, 0.08)},
    "daytrading_3methods_breakout": {"V1": (0.10, 0.08), "V2": (0.10, 0.12), "V3": (0.08, 0.10), "V4": (0.12, 0.10)},
}
BRACKETS = ["orig"] + VNAMES
GUARD_TOL = 0.001                                  # 재현 불일치 > 0.1% ⇒ 전체 중단
PX_TOL = 1e-6                                      # exit_price·ret_pct |차| 허용
SAMPLE_MAX = 0.01                                  # ④ > 1% ⇒ 판별 보류(표본)

# ── §3~§6 🔒 ────────────────────────────────────────────────────────────────
THETA = 0.25                                       # %p
ALPHA = 0.05
M_E = 12
MDE_K = 3.71                                       # (2.87 + 0.84) — 문서 값 그대로
N_FAKE = 100
SEED0 = 20261003
FAKE_P, FAKE_MAX = 0.10, 0.16
BLOCK, SHIFT, BLOCK40 = 20, 10, 40
FTYPES = OrderedDict([("F-종목", 1), ("F-블록", 2), ("F-블록′", 3), ("F-블록40", 4)])   # 값 = 시드 t
GATE_TYPES = ["F-종목", "F-블록"]                     # CR1 게이트
ALT_TYPE = "F-블록′"                                 # 대체 도구 게이트
VOL_N, VOL_MIN = 20, 15                            # §7 층 변수 v · 봉 < 15 ⇒ 층 결측
VOL_Q = (33.3, 66.7)
BUDGET_S = 3600.0
PILOT_MONTH = "2024-03"

LAB_UP, LAB_DOWN, LAB_NONE, LAB_HOLD = "변형이 낫다", "원이 낫다", "차이 없음", "판별 보류"
SUB_TOOL, SUB_SAMPLE, SUB_CONF, SUB_POWER = "(도구)", "(표본)", "(확인 실패)", "(검정력)"
TAG_VOL, TAG_TOUCH = "변동성 의존", "동시 터치 의존"

_LOG: List[str] = []
_LOG_PATH: List[Path] = []


def log(msg: str = "") -> None:
    line = f"{datetime.now():%H:%M:%S} {msg}"
    _LOG.append(line)
    print(line, file=sys.stderr, flush=True)
    if _LOG_PATH:
        with open(_LOG_PATH[0], "a", encoding="utf-8") as fh:
            fh.write(line + "\n")


def md5_file(p: Path) -> str:
    return hashlib.md5(p.read_bytes()).hexdigest()


# ════════════════════════════════════════════════════════════════════════════
# 1. 가드
# ════════════════════════════════════════════════════════════════════════════
def guard_blobs8(git: Callable[..., str] = R._git) -> Dict[str, str]:
    """§2 실행 전 가드 — 8파일 blob = 원장 실행 코드 a51c631(바이트 그대로 · 해석 기록 H1)."""
    out: Dict[str, str] = {}
    bad: List[str] = []
    for rel in GUARD8 + [PREREG]:
        ref = PREREG_SHA if rel == PREREG else A51
        want = git("rev-parse", f"{ref}:./{rel}")
        have = git("hash-object", "--no-filters", rel)
        out[rel] = have
        if want != have:
            bad.append(f"{rel} ({ref}={want[:10]} · 현재={have[:10]})")
    if bad:
        raise SystemExit("🔴 가드: blob 불일치 — 중단\n  " + "\n  ".join(bad))
    return out


def variant_rules(base: X.ExitRules, tp: float, sl: float) -> X.ExitRules:
    """🔒 §2 — `ExitRules` 에서 tp·sl 두 값만 바꾼다(max_hold·source 원 값 · 엔진 미경유)."""
    return dataclasses.replace(base, tp=float(tp), sl=float(sl))


def guard_variants(folder: str, base: X.ExitRules) -> None:
    tp0, sl0 = R.STRATS[folder]["tp"], R.STRATS[folder]["sl"]
    v = VARIANTS[folder]
    want = {"V1": (tp0, sl0 - 0.02), "V2": (tp0, sl0 + 0.02), "V3": (tp0 - 0.02, sl0), "V4": (tp0 + 0.02, sl0)}
    for k in VNAMES:
        if tuple(round(x, 9) for x in v[k]) != tuple(round(x, 9) for x in want[k]):
            raise SystemExit(f"🔴 변형 값 불일치 {folder} {k}: {v[k]} ≠ 한 칸 {want[k]} — 중단")
    if (round(base.tp, 9), round(base.sl, 9)) != (tp0, sl0):
        raise SystemExit(f"🔴 원 브래킷 {folder} ({base.tp}, {base.sl}) ≠ PREREG §6 — 중단")


# ════════════════════════════════════════════════════════════════════════════
# 2. 제외 ①~③ (결과 열을 읽지 않는다) · 창 · 블록 · v
# ════════════════════════════════════════════════════════════════════════════
def horizon_end(cal: Sequence[date], cal_idx: Dict[date, int], entry: date, max_hold: int) -> Optional[date]:
    """수평선 끝 = entry_date + max_hold 거래일(KOSPI 달력) · 달력(≤ 2026-09-23) 밖이면 None."""
    j = cal_idx[entry] + int(max_hold)
    return cal[j] if j < len(cal) else None


def exclusions_123(lots: pd.DataFrame, max_hold: Dict[str, int], cal: Sequence[date], cal_idx: Dict[date, int],
                   corp_dates: Dict[str, np.ndarray], imp_dates: Dict[str, np.ndarray]) -> pd.DataFrame:
    """§1 ①→②→③ 폭포식 — 입력 열은 strategy·stock_code·entry_date 뿐(결과 무관). 반환 = (hend, excl)."""
    hend: List[str] = []
    excl: List[str] = []
    for f, code, en in zip(lots["strategy"].tolist(), lots["stock_code"].tolist(), lots["entry_date"].tolist()):
        d1 = date.fromisoformat(en)
        he = horizon_end(cal, cal_idx, d1, max_hold[f])
        if he is None or he > HORIZON_MAX:
            hend.append("")
            excl.append("①horizon")
            continue
        hend.append(he.isoformat())
        if R.any_in(corp_dates.get(code), d1, he):
            excl.append("②corp_event")
        elif R.any_in(imp_dates.get(code), d1, he):
            excl.append("③impossible_bar")
        else:
            excl.append("")
    return pd.DataFrame({"hend": hend, "excl": excl}, index=lots.index)


def window_of(scan_date: str) -> str:
    return "E" if scan_date <= WIN["E"][1] else "C"


def block_ids(ci: np.ndarray, ci0: int, size: int = BLOCK, shift: int = 0) -> np.ndarray:
    """창 첫 거래일(ci0)부터 연속 size 거래일 블록 번호 · shift = 경계를 민 거리(F-블록′ = 10 · 해석 기록 H6)."""
    return (np.asarray(ci, dtype=np.int64) - int(ci0) + int(shift)) // int(size)


def n_blocks(n_days: int, size: int, shift: int = 0) -> int:
    return (n_days - 1 + shift) // size + 1


def vol_v(dates64: np.ndarray, highs: np.ndarray, lows: np.ndarray, oncal: np.ndarray, lo64: np.datetime64,
          d64: np.datetime64) -> Tuple[float, int]:
    """§7 v = 창 [lo, D](KOSPI 달력 20거래일 · D 포함) 안 달력 봉의 평균 ln(high/low) · 봉 < 15 ⇒ NaN."""
    a = int(np.searchsorted(dates64, lo64, side="left"))
    b = int(np.searchsorted(dates64, d64, side="right"))
    h, lo, m = highs[a:b], lows[a:b], oncal[a:b] & (highs[a:b] > 0) & (lows[a:b] > 0)
    n = int(m.sum())
    if n < VOL_MIN:
        return float("nan"), n
    return float(np.mean(np.log(h[m] / lo[m]))), n


def layer_of(v: np.ndarray, b1: float, b2: float) -> np.ndarray:
    """1: v ≤ b1 · 2: b1 < v ≤ b2 · 3: v > b2 · 0: 결측."""
    out = np.where(v <= b1, 1, np.where(v <= b2, 2, 3))
    return np.where(np.isfinite(v), out, 0)


# ════════════════════════════════════════════════════════════════════════════
# 3. 청산 — 원장 경로 그대로(재구현 금지)
# ════════════════════════════════════════════════════════════════════════════
def sim_lot(env: R.Env, probe: Any, rules: X.ExitRules, code: str, d1: date, qty: int) -> X.ExitOut:
    """원장 `run.lot_row` 의 청산 호출 그대로 — D+1 시가 진입 · `build_path` · `simulate_lot`."""
    bars = env.bars(code)
    px_open = float(bars[d1].open)
    pos = X.Pos(code, d1, SRC8.aware(datetime.combine(d1, R.ENTRY_TIME)), px_open, int(qty), X.BASIS_D_OPEN)
    return X.simulate_lot(pos, rules, R.build_path(env.cal, env.cal_idx, bars, d1, rules.max_hold_days), probe)


def run_bracket(env: R.Env, probe: Any, rules: X.ExitRules, sub: pd.DataFrame) -> Dict[str, list]:
    out: Dict[str, list] = {k: [] for k in ("reason", "exit_date", "price", "ret", "hold", "flags", "status")}
    for code, en, q in zip(sub["stock_code"].tolist(), sub["entry_date"].tolist(), sub["qty"].tolist()):
        try:
            ex = sim_lot(env, probe, rules, code, date.fromisoformat(en), int(q))
            vals = (ex.reason, ex.exit_date.isoformat() if ex.exit_date else "", ex.price, ex.ret_pct, ex.hold_days,
                    ";".join(ex.flags), ex.status)
        except Exception as exc:  # noqa: BLE001 — 로트 단위 격리(④ sim_error)
            vals = ("sim_error", "", None, None, None, f"sim_error:{type(exc).__name__}", "sim_error")
        for k, v in zip(out, vals):
            out[k].append(v)
    return out


def guard_mismatch(reason: Sequence[str], xdate: Sequence[str], price: Sequence[Any], ret: Sequence[Any],
                   led: pd.DataFrame) -> np.ndarray:
    """재현 가드 — exit_reason·exit_date 완전 일치 · exit_price·ret_pct |차| ≤ 1e−6. 반환 = 로트별 불일치."""
    bad = np.zeros(len(led), dtype=bool)
    for i, (a, b, c, e, wa, wb, wc, we) in enumerate(zip(reason, xdate, price, ret, led["exit_reason"].tolist(),
                                                         led["exit_date"].tolist(), led["exit_price"].tolist(),
                                                         led["ret_pct"].tolist())):
        ok = a == wa and b == wb and c is not None and e is not None
        ok = ok and abs(float(c) - float(wc)) <= PX_TOL and abs(float(e) - float(we)) <= PX_TOL
        bad[i] = not ok
    return bad


# ════════════════════════════════════════════════════════════════════════════
# 4. 검정 — P2 첫 행 · CR1(K=1) · 2원 클러스터(CGM) · Holm
# ════════════════════════════════════════════════════════════════════════════
def _cl_var(e: np.ndarray, lab: np.ndarray, n: int) -> Tuple[float, int]:
    u, inv = np.unique(lab, return_inverse=True)
    G = len(u)
    if G < 2:
        return float("nan"), G
    s = np.bincount(inv, weights=e, minlength=G)
    return G / (G - 1) * float((s ** 2).sum()) / (n * n), G


def cr1(d: np.ndarray, g: np.ndarray) -> Dict[str, float]:
    """§4 🔒 `SE² = G/(G−1) · Σ_g(Σ_{i∈g}(d_i − d̄))² / N²` (절편만 · K=1)."""
    d = np.asarray(d, dtype=float)
    n = len(d)
    if n < 2:
        return dict(mean=float("nan"), se=float("nan"), G=0, n=n)
    m = float(d.mean())
    v, G = _cl_var(d - m, np.asarray(g), n)
    return dict(mean=m, se=math.sqrt(v) if v == v and v > 0 else float("nan"), G=G, n=n)


def cgm2(d: np.ndarray, g: np.ndarray, b: np.ndarray) -> Dict[str, float]:
    """§4 병기 · §6 대체 도구 — `V_종목 + V_블록 − V_종목×블록`(각 G/(G−1)) · V ≤ 0 ⇒ max(V_종목, V_블록)(해석 기록 H8)."""
    d = np.asarray(d, dtype=float)
    n = len(d)
    if n < 2:
        return dict(mean=float("nan"), se=float("nan"), Gs=0, Gb=0, Gsb=0, neg=False)
    m = float(d.mean())
    e = d - m
    g, b = np.asarray(g, dtype=np.int64), np.asarray(b, dtype=np.int64)
    vs, gs = _cl_var(e, g, n)
    vb, gb = _cl_var(e, b, n)
    vsb, gsb = _cl_var(e, g * (int(b.max()) + 1) + b, n)
    v = vs + vb - (vsb if vsb == vsb else 0.0)
    neg = not (v > 0)
    if neg:
        v = max(x for x in (vs, vb) if x == x) if (vs == vs or vb == vb) else float("nan")
    return dict(mean=m, se=math.sqrt(v) if v == v and v > 0 else float("nan"), Gs=gs, Gb=gb, Gsb=gsb, neg=neg,
                Vs=vs, Vb=vb, Vsb=vsb)


def p_norm(m: float, se: float) -> Tuple[float, float, float]:
    """(양측 p, p_up, p_down) · p_up = 변형이 낫다(d̄ > 0) 쪽 한쪽 p."""
    if not (se == se and se > 0 and m == m):
        return 1.0, 1.0, 1.0
    z = m / se
    up, down = 0.5 * math.erfc(z / math.sqrt(2)), 0.5 * math.erfc(-z / math.sqrt(2))
    return min(1.0, 2 * min(up, down)), up, down


def p_t(m: float, se: float, df: int) -> Tuple[float, float, float]:
    if not (se == se and se > 0 and m == m and df >= 1):
        return 1.0, 1.0, 1.0
    z = m / se
    up, down = float(sst.t.sf(z, df)), float(sst.t.cdf(z, df))
    return min(1.0, 2 * min(up, down)), up, down


def fake_rng(t: int, w: int, s: int, v: int, j: int) -> np.random.Generator:
    """§6 🔒 `default_rng([20261003, t, w, s, v, j])`."""
    return np.random.default_rng([SEED0, t, w, s, v, j])


def fake_signs(t: int, w: int, s: int, v: int, j: int, n: int) -> np.ndarray:
    return fake_rng(t, w, s, v, j).choice([-1, 1], n)


def centered(d: np.ndarray) -> np.ndarray:
    """§6 🔒 가짜의 재료 `d − d̄_셀`(셀 = 에피소드 첫 행)."""
    d = np.asarray(d, dtype=float)
    return d - d.mean()


def holm(ps: Dict[Any, float]) -> Dict[Any, bool]:
    return RE.holm(ps, ALPHA)


# ════════════════════════════════════════════════════════════════════════════
# 5. 셀 통계 · 라벨
# ════════════════════════════════════════════════════════════════════════════
def cell_stats(d: np.ndarray, g: np.ndarray, b: np.ndarray) -> Dict[str, Any]:
    c = cr1(d, g)
    w2 = cgm2(d, g, b)
    pn = p_norm(c["mean"], c["se"])
    pt = p_t(c["mean"], w2["se"], int(w2["Gb"]) - 1)
    se_max = max(x for x in (c["se"], w2["se"]) if x == x) if (c["se"] == c["se"] or w2["se"] == w2["se"]) \
        else float("nan")
    return dict(mean=c["mean"], n=c["n"], G=c["G"], se=c["se"], p=pn[0], p_up=pn[1], p_down=pn[2],
                se2=w2["se"], Gb=w2["Gb"], neg2=w2["neg"], p2=pt[0], p2_up=pt[1], p2_down=pt[2],
                mde=MDE_K * c["se"], mde2=MDE_K * w2["se"], mde_lab=MDE_K * se_max)


def tool_p(st: Dict[str, Any], tool: str) -> Tuple[float, float, float]:
    """창·전략 도구에 따른 (양측, up, down) — fail ⇒ p = 1(가족에 남김)."""
    if tool == "CR1":
        return st["p"], st["p_up"], st["p_down"]
    if tool == "2원":
        return st["p2"], st["p2_up"], st["p2_down"]
    return 1.0, 1.0, 1.0


def decide(cells: Dict[Tuple[str, str], Dict[str, Dict[str, Any]]], tool: Dict[str, Dict[str, str]],
           sample_hold: Dict[str, bool], theta: float = THETA) -> Dict[Tuple[str, str], Dict[str, Any]]:
    """§5 🔒 E(Holm m=12) → C(Holm m_C · E 방향 한쪽 p) · 라벨 적용 순서 = (도구)·(표본) → 방향 → 차이 없음 → 보류."""
    pE = {k: tool_p(c["E"], tool["E"][k[0]])[0] for k, c in cells.items()}
    if len(pE) != M_E:
        raise SystemExit(f"🔴 E 가족 크기 {len(pE)} ≠ {M_E}")
    passE = holm(pE)
    cand: Dict[Tuple[str, str], int] = {}
    for k, c in cells.items():
        if passE[k] and c["E"]["mean"] >= theta:
            cand[k] = 1
        elif passE[k] and c["E"]["mean"] <= -theta:
            cand[k] = -1
    pC = {k: tool_p(cells[k]["C"], tool["C"][k[0]])[1 if s > 0 else 2] for k, s in cand.items()}
    passC = holm(pC) if pC else {}
    out: Dict[Tuple[str, str], Dict[str, Any]] = {}
    for k, c in cells.items():
        f = k[0]
        E, C = c["E"], c["C"]
        subs: List[str] = []
        dirn = cand.get(k, 0)
        conf = bool(passC.get(k, False)) and (C["mean"] >= theta if dirn > 0 else C["mean"] <= -theta)
        if tool["E"][f] == "fail" or tool["C"][f] == "fail":
            lab, subs = LAB_HOLD, [SUB_TOOL]
        elif sample_hold.get(f):
            lab, subs = LAB_HOLD, [SUB_SAMPLE]
        elif dirn and conf:
            lab = LAB_UP if dirn > 0 else LAB_DOWN
        elif (abs(E["mean"]) < theta and E["mde_lab"] <= theta and abs(C["mean"]) < theta
              and C["mde_lab"] <= theta):
            lab = LAB_NONE
        else:
            lab = LAB_HOLD
            if dirn:
                subs.append(SUB_CONF)
            if not (E["mde_lab"] <= theta) or not (C["mde_lab"] <= theta):
                subs.append(SUB_POWER)
            if not subs:
                subs.append("(그 밖 — |d̄| ≥ θ 이나 E 방향 후보 아님)")
        out[k] = dict(label=lab, subs=subs, pE=pE[k], passE=passE[k], dir=dirn, pC=pC.get(k), passC=passC.get(k),
                      m_C=len(pC))
    return out


# ════════════════════════════════════════════════════════════════════════════
# 6. main
# ════════════════════════════════════════════════════════════════════════════
def _code_md5() -> str:
    return md5_file(Path(__file__))


def _sim_md5() -> str:
    """체크포인트 식별 — 시뮬 결과를 정하는 코드만(분석·출력 코드 수정이 시뮬 재실행을 부르지 않게)."""
    import inspect
    src = "".join(inspect.getsource(fn) for fn in (sim_lot, run_bracket, variant_rules, horizon_end, exclusions_123,
                                                   _run_strategy))
    return hashlib.md5((src + repr(VARIANTS) + repr(BRACKETS)).encode("utf-8")).hexdigest()


def _part_paths(out: Path, f: str) -> Tuple[Path, Path]:
    b = out / "parts" / SHORT[f]
    return b.with_suffix(".csv"), b.with_suffix(".done")


def _run_strategy(env, probe, rules0, f, Lf: pd.DataFrame, keep: np.ndarray, out: Path, ident: Dict[str, str]
                  ) -> Tuple[pd.DataFrame, Dict[str, float]]:
    """전략 1개 — 원 브래킷은 L 전체(재현 가드) · 변형 4개는 ①~③ 통과 로트만. 체크포인트 = 전략 단위."""
    p_csv, p_done = _part_paths(out, f)
    if p_done.exists():
        meta = json.loads(p_done.read_text(encoding="utf-8"))
        if all(meta.get(k) == v for k, v in ident.items()) and meta.get("n_lots") == len(Lf):
            log(f"[{SHORT[f]}] 체크포인트 재사용 ({p_csv.name})")
            return pd.read_csv(p_csv, dtype=str, keep_default_na=False), meta["secs"]
        raise SystemExit(f"🔴 체크포인트 불일치 {p_done} — 지우고 다시 돌릴 것")
    res = pd.DataFrame({"key": Lf["key"].to_numpy()})
    secs: Dict[str, float] = {}
    for b in BRACKETS:
        rules = rules0 if b == "orig" else variant_rules(rules0, *VARIANTS[f][b])
        sub = Lf if b == "orig" else Lf[keep]
        t = time.perf_counter()
        r = run_bracket(env, probe, rules, sub)
        secs[b] = time.perf_counter() - t
        for k, v in r.items():
            col = pd.Series([""] * len(Lf), index=Lf.index, dtype=object)
            col.loc[sub.index] = [R._fmt(x) for x in v]
            res[f"{b}_{k}"] = col.to_numpy()
        log(f"[{SHORT[f]}] {b} (tp {rules.tp:g} · sl {rules.sl:g} · mh {rules.max_hold_days}) 로트 {len(sub):,} · "
            f"{secs[b]:.1f}s")
    R.write_csv(p_csv, list(res.columns), res.to_dict("records"))
    R._atomic_write(p_done, json.dumps(dict(ident, n_lots=len(Lf), secs=secs), ensure_ascii=False, indent=1))
    return res.astype(str), secs


def main(argv: Optional[Sequence[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="청산 브래킷 짝 비교 (사전등록 동결 dbea62a)")
    ap.add_argument("--pilot", action="store_true", help=f"scan_date {PILOT_MONTH} · 시간·재현 가드만(d 미열람)")
    ap.add_argument("--out", default=None)
    a = ap.parse_args(argv)
    out_dir = Path(a.out) if a.out else (BASE / "pilot" if a.pilot else BASE)
    out_dir.mkdir(parents=True, exist_ok=True)
    _LOG_PATH[:] = [out_dir / "run_log.txt"]
    _LOG_PATH[0].write_text("", encoding="utf-8")
    started = datetime.now().isoformat(timespec="seconds")
    T0 = time.perf_counter()
    tm: Dict[str, float] = {}

    # ── 가드 ────────────────────────────────────────────────────────────────
    md5s = D.check_inputs()
    blobs11 = R.guard_blobs()
    blobs8 = guard_blobs8()
    sha = R.git_sha()
    strategies = {f: load8(f) for f in STRATS}
    adapters = {f: getattr(__import__(R.STRATS[f]["module"], fromlist=["x"]), R.STRATS[f]["cls"])() for f in STRATS}
    rules = {f: SP.resolve_live_tp_sl(f, strategies[f]) for f in STRATS}
    for f in STRATS:
        R.guard_rules(f, rules[f], strategies[f], adapters[f])
        guard_variants(f, rules[f])
    led_meta = json.loads((LEDGER_DIR / "run_meta.json").read_text(encoding="utf-8"))
    fp_want = led_meta["db_fingerprint"]["sha256"]
    log(f"[가드] md5 6항목 ✓ · 전략 11파일 blob = {R.BASE_SHA} ✓ · 8파일 blob = {A51} ✓ · 문서 blob = {PREREG_SHA} ✓ · "
        f"tp/sl/max_hold·밴드 = PREREG ✓ · V1~V4 = 모문서 §4 ✓ · sha {sha[:10]} · 코드 md5 {_code_md5()[:10]}")

    # ── L ──────────────────────────────────────────────────────────────────
    led = pd.read_csv(LEDGER_DIR / "ledger.csv", dtype=str, keep_default_na=False)
    L = led[(led["band_ok"] == "True") & (led["exit_reason"] != X.EXIT_OPEN) & (led["exit_reason"] != "")
            & (led["entry_price"] != "")].copy()
    L["_s"] = L["strategy"].map(S_IDX)                 # 전략 순서 = STRATS(시드 s 순서 · 결과 이어 붙이기 순서)
    L = L.sort_values(["_s", "scan_date", "stock_code"], kind="mergesort").reset_index(drop=True)
    L["key"] = L["strategy"].map(SHORT) + "|" + L["scan_date"] + "|" + L["stock_code"]
    if L["key"].duplicated().any():
        raise SystemExit("🔴 L 키 중복 — 중단")
    n_L = {f: int((L["strategy"] == f).sum()) for f in STRATS}
    log(f"[L] {len(L):,} · " + " · ".join(f"{SHORT[f]} {n_L[f]:,}" for f in STRATS))

    # ── DB 로드 ─────────────────────────────────────────────────────────────
    t = time.perf_counter()
    conn = R._connect()
    cal = [pd.Timestamp(x).date() for x in LD.load_trading_calendar(conn, R.PX_START, R.W_END)]
    fp = LD.db_fingerprint(conn, R.PX_START, R.W_END)
    if fp["sha256"] != fp_want or not fp["sha256"].startswith(FP_PREFIX):
        conn.close()
        raise SystemExit(f"🔴 DB 지문 {fp['sha256'][:12]} ≠ 원장 {fp_want[:12]} — 중단")
    px = LD.load_prices(conn, R.PX_START, R.W_END)
    corp_dates = R._date_index(LD.load_corp_events(conn).keys())
    conn.close()
    if cal[-1] != HORIZON_MAX:
        raise SystemExit(f"🔴 달력 끝 {cal[-1]} ≠ {HORIZON_MAX}")
    cal_idx = {x: i for i, x in enumerate(cal)}
    fl = FL.compute_bar_flags(px)
    m_imp = fl["flag_padding"] | fl["flag_locked_limit"] | fl["flag_cliff"]
    imp_dates = R._date_index(zip(px.loc[m_imp, "stock_code"], px.loc[m_imp, "date"]))
    book = R.build_book(px)
    env = R.Env(cal=cal, book=book, uni={}, excl={}, imp_dates=imp_dates, corp_dates=corp_dates, bad_open=set(),
                minute_fn=lambda p: set())
    probes = {f: SP.SellProbe(f, strategies[f], R.make_window_fn(book)) for f in STRATS}
    tm["load"] = time.perf_counter() - t
    log(f"[로드] 달력 {len(cal)}일({cal[0]}~{cal[-1]}) · DB 지문 {fp['sha256'][:12]} = 원장 ✓ · px {len(px):,}행 · "
        f"종목 {fp['n_stocks']:,} · 행 {fp['n_rows']:,} · 불가능봉 {int(m_imp.sum()):,} · {tm['load']:.0f}s")

    # ── ①~③ 제외(결과 무관) ──────────────────────────────────────────────────
    mh = {f: int(rules[f].max_hold_days) for f in STRATS}
    ex = exclusions_123(L[["strategy", "stock_code", "entry_date"]], mh, cal, cal_idx, corp_dates, imp_dates)
    L["hend"], L["excl"] = ex["hend"], ex["excl"]
    L["window"] = L["scan_date"].map(window_of)
    for f in STRATS:
        m = L["strategy"] == f
        c = Counter(L.loc[m, "excl"])
        log(f"[제외 ①~③] {SHORT[f]} ① {c['①horizon']:,} · ② {c['②corp_event']:,} · ③ {c['③impossible_bar']:,} · "
            f"남음 {c['']:,}")
    n_keep_all = {f: int(((L["strategy"] == f) & (L["excl"] == "")).sum()) for f in STRATS}
    if a.pilot:
        L = L[L["scan_date"].str.startswith(PILOT_MONTH)].reset_index(drop=True)
        log(f"[파일럿] scan_date {PILOT_MONTH} → 로트 {len(L):,}")

    # ── 청산 시뮬(전략 단위 체크포인트) ─────────────────────────────────────────
    ident = dict(git_sha=sha, db_fingerprint=fp["sha256"], sim_md5=_sim_md5(), pilot=bool(a.pilot))
    sims: Dict[str, pd.DataFrame] = {}
    secs_sim: Dict[str, Dict[str, float]] = {}
    for f in STRATS:
        Lf = L[L["strategy"] == f]
        keep = (Lf["excl"] == "").to_numpy()
        sims[f], secs_sim[f] = _run_strategy(env, probes[f], rules[f], f, Lf, keep, out_dir, ident)
        el = time.perf_counter() - T0
        if not a.pilot and el > BUDGET_S:
            raise SystemExit(f"🔴 비용 상한 1시간 초과({el:.0f}s) — {SHORT[f]} 까지 체크포인트 · 중단·보고")
    tm["sim"] = sum(sum(v.values()) for v in secs_sim.values())

    # ── 재현 가드 ───────────────────────────────────────────────────────────
    S = pd.concat([sims[f] for f in STRATS], ignore_index=True)
    if not (S["key"].to_numpy() == L["key"].to_numpy()).all():
        raise SystemExit("🔴 시뮬 결과 순서 ≠ L — 중단")
    bad = guard_mismatch(S["orig_reason"].tolist(), S["orig_exit_date"].tolist(),
                         [x if x != "" else None for x in S["orig_price"].tolist()],
                         [x if x != "" else None for x in S["orig_ret"].tolist()], L)
    guard: Dict[str, Dict[str, Any]] = {}
    for f in STRATS:
        m = (L["strategy"] == f).to_numpy()
        n, k = int(m.sum()), int(bad[m].sum())
        guard[f] = dict(n=n, mismatch=k, rate=k / max(1, n), agree=1 - k / max(1, n))
        log(f"[재현 가드] {SHORT[f]} L {n:,} · 불일치 {k} ({k / max(1, n):.4%}) · 대조율 {1 - k / max(1, n):.4%}")
    stop = [f for f in STRATS if guard[f]["rate"] > GUARD_TOL]

    if a.pilot:
        n_runs_p = sum(int((L["strategy"] == f).sum()) + 4 * int(((L["strategy"] == f) & (L["excl"] == "")).sum())
                       for f in STRATS)
        per_run = tm["sim"] / max(1, n_runs_p)
        n_runs_full = sum(n_L.values()) + 4 * sum(n_keep_all.values())
        est = tm["load"] + per_run * n_runs_full
        pilot = dict(started=started, month=PILOT_MONTH, n_lots=len(L), n_runs=n_runs_p, secs_sim=secs_sim,
                     secs_load=round(tm["load"], 1), per_run_ms=round(per_run * 1000, 3), n_runs_full=n_runs_full,
                     est_full_secs=round(est, 1), guard=guard, git_sha=sha, code_md5=_code_md5(),
                     over_budget=est > BUDGET_S)
        R._atomic_write(out_dir / "pilot_timing.json", json.dumps(pilot, ensure_ascii=False, indent=1))
        log(f"[파일럿] 로트 {len(L):,} · 시뮬 {n_runs_p:,}회 {tm['sim']:.1f}s ({per_run * 1000:.2f}ms/회) · 전체 "
            f"{n_runs_full:,}회 외삽 ≈ {est:.0f}s ({est / 3600:.2f}시간) · 1시간 초과 {'예 🔴' if est > BUDGET_S else '아니오'}"
            f" · d 는 계산·인쇄하지 않음")
        return 0
    if stop:
        raise SystemExit("🔴 재현 불일치 > 0.1% — 전체 중단: " + ", ".join(SHORT[f] for f in stop))
    return analyze(L, S, bad, cal, cal_idx, book, rules, guard, dict(
        md5s=md5s, blobs11=blobs11, blobs8=blobs8, sha=sha, fp=fp, started=started, T0=T0, tm=tm,
        secs_sim=secs_sim, n_L=n_L, led=led), out_dir)



# ════════════════════════════════════════════════════════════════════════════
# 7. 분석(④ · 에피소드 · v · 가짜 게이트 → 판정 → 꼬리표 · 병기)
# ════════════════════════════════════════════════════════════════════════════
def _num(s: pd.Series) -> np.ndarray:
    return pd.to_numeric(s.replace("", np.nan), errors="coerce").to_numpy(dtype=float)


def _vol_all(L: pd.DataFrame, cal: List[date], cal_idx: Dict[date, int], book: R.Book) -> Tuple[np.ndarray, np.ndarray]:
    cal64 = pd.to_datetime(pd.Series(cal)).to_numpy(dtype="datetime64[ns]")
    arrs: Dict[str, Tuple[np.ndarray, ...]] = {}
    v = np.full(len(L), np.nan)
    n = np.zeros(len(L), dtype=np.int64)
    for i, (code, sd) in enumerate(zip(L["stock_code"].tolist(), L["scan_date"].tolist())):
        if code not in arrs:
            g = book[code][1]
            dts = g["date"].to_numpy(dtype="datetime64[ns]")
            arrs[code] = (dts, g["high"].to_numpy(dtype=float), g["low"].to_numpy(dtype=float), np.isin(dts, cal64))
        k = cal_idx[date.fromisoformat(sd)]
        v[i], n[i] = vol_v(*arrs[code], cal64[k - VOL_N + 1], cal64[k])
    return v, n


def _episodes(A: pd.DataFrame, mask: np.ndarray) -> Tuple[np.ndarray, np.ndarray]:
    """(전략, 창)마다 표본 `mask` 안에서 에피소드 재계산 → (첫 행 여부, 에피소드 id) · 표본 밖 = False/−1."""
    first = np.zeros(len(A), dtype=bool)
    eid = np.full(len(A), -1, dtype=np.int64)
    base = 0
    for f in STRATS:
        for w in WIN:
            m = mask & (A["strategy"] == f).to_numpy() & (A["window"] == w).to_numpy()
            idx = np.flatnonzero(m)
            if not len(idx):
                continue
            _u, g = np.unique(A["stock_code"].to_numpy()[idx], return_inverse=True)
            e, fr = RC.episodes(np.zeros(len(idx), dtype=np.int64), g.astype(np.int64),
                                A["ci"].to_numpy()[idx].astype(np.int64))
            first[idx] = fr
            eid[idx] = e + base
            base += int(e.max()) + 1
    return first, eid


def _rt(k: int, n: int) -> str:
    return f"{k / n:.3f} ({k}/{n})" if n else "—"


def _layer_stats(d: np.ndarray, g: np.ndarray, lv: np.ndarray) -> Dict[int, Dict[str, float]]:
    out: Dict[int, Dict[str, float]] = {}
    for ly in (1, 2, 3):
        m = lv == ly
        if m.sum() >= 2:
            out[ly] = cr1(d[m], g[m])
        else:
            out[ly] = dict(mean=float(d[m].mean()) if m.any() else float("nan"), se=float("nan"), G=int(m.sum()),
                           n=int(m.sum()))
    return out


def analyze(L: pd.DataFrame, S: pd.DataFrame, bad: np.ndarray, cal: List[date], cal_idx: Dict[date, int],
            book: R.Book, rules: Dict[str, X.ExitRules], guard: Dict[str, Dict[str, Any]], ctx: Dict[str, Any],
            out_dir: Path) -> int:
    T0, tm = ctx["T0"], ctx["tm"]
    t = time.perf_counter()
    A = L.copy()
    for c in S.columns:
        if c != "key":
            A[c] = S[c].to_numpy()
    # ── ④ 잔여 ─────────────────────────────────────────────────────────────
    ex4: List[str] = []
    for i in range(len(A)):
        if A["excl"].iat[i]:
            ex4.append(A["excl"].iat[i])
            continue
        why = ["repro"] if bad[i] else []
        why += [f"{b}:{A[f'{b}_status'].iat[i]}" for b in BRACKETS if A[f"{b}_status"].iat[i] != "closed"]
        ex4.append("④" + ",".join(why) if why else "")
    A["excl"] = ex4
    A["repro_ok"] = ~bad
    n123 = {f: int(((A["strategy"] == f) & ~A["excl"].str.match("^[①②③]")).sum()) for f in STRATS}
    n4 = {f: int(((A["strategy"] == f) & A["excl"].str.startswith("④")).sum()) for f in STRATS}
    sample_hold = {f: n4[f] / max(1, n123[f]) > SAMPLE_MAX for f in STRATS}
    for f in STRATS:
        log(f"[④] {SHORT[f]} ①~③ 뒤 {n123[f]:,} · ④ {n4[f]} ({n4[f] / max(1, n123[f]):.3%}) · "
            f"판별 보류(표본) {'예 🔴' if sample_hold[f] else '아니오'}")
    keep = (A["excl"] == "").to_numpy()

    # ── 창 · 블록 · 에피소드 · v ──────────────────────────────────────────────
    A["ci"] = [cal_idx[date.fromisoformat(x)] for x in A["scan_date"]]
    ci0 = {w: next(i for i, x in enumerate(cal) if x.isoformat() >= WIN[w][0]) for w in WIN}
    ndays = {w: sum(1 for x in cal if WIN[w][0] <= x.isoformat() <= WIN[w][1]) for w in WIN}
    c0 = A["window"].map(ci0).to_numpy(dtype=np.int64)
    ci = A["ci"].to_numpy(dtype=np.int64)
    A["block20"] = block_ids(ci - c0, 0, BLOCK)
    A["block20s"] = block_ids(ci - c0, 0, BLOCK, SHIFT)
    A["block40"] = block_ids(ci - c0, 0, BLOCK40)
    first, eid = _episodes(A, keep)
    A["ep_first"], A["ep_id"] = first, eid
    post1 = ~A["excl"].str.startswith("①").to_numpy()
    first1, _ = _episodes(A, post1)
    v, vn = _vol_all(A, cal, cal_idx, book)
    A["v"], A["v_n"] = v, vn
    bounds: Dict[str, Tuple[float, float]] = {}
    for f in STRATS:
        mE = keep & (A["strategy"] == f).to_numpy() & (A["window"] == "E").to_numpy() & np.isfinite(v)
        q1, q2 = np.percentile(v[mE], VOL_Q)
        bounds[f] = (float(q1), float(q2))
    lay_arr = np.zeros(len(A), dtype=np.int64)
    for f in STRATS:
        ms_ = (A["strategy"] == f).to_numpy()
        lay_arr[ms_] = layer_of(v[ms_], *bounds[f])
    A["layer"] = lay_arr
    ret = {b: _num(A[f"{b}_ret"]) for b in BRACKETS}
    hold = {b: _num(A[f"{b}_hold"]) for b in BRACKETS}
    price = {b: _num(A[f"{b}_price"]) for b in BRACKETS}
    dV = {b: np.where(keep, ret[b] - ret["orig"], np.nan) for b in VNAMES}
    for b in VNAMES:
        A[f"d_{b}"] = dV[b]
    tm["prep"] = time.perf_counter() - t

    # 표본 계수(§1 대조)
    counts: Dict[str, Dict[str, Any]] = {}
    for f in STRATS:
        ms = (A["strategy"] == f).to_numpy()
        row: Dict[str, Any] = {}
        for w in WIN:
            mw = ms & (A["window"] == w).to_numpy()
            row[f"L_{w}"] = int(mw.sum())
            row[f"post1_{w}"] = int((mw & post1).sum())
            row[f"first1_{w}"] = int((mw & first1).sum())
            row[f"codes1_{w}"] = int(A.loc[mw & post1, "stock_code"].nunique())
            row[f"final_{w}"] = int((mw & keep).sum())
            row[f"first_{w}"] = int((mw & first).sum())
            row[f"codes_{w}"] = int(A.loc[mw & keep, "stock_code"].nunique())
            row[f"days_first_{w}"] = int(A.loc[mw & first, "scan_date"].nunique())
            row[f"days_first1_{w}"] = int(A.loc[mw & first1, "scan_date"].nunique())
            for col, m_, bc_ in (("filled", first, "block20"), ("filled1", first1, "block20"),
                                 ("filleds", first, "block20s"), ("filled40", first, "block40")):
                bc = Counter(A.loc[mw & m_, bc_].tolist())
                row[f"{col}_{w}"] = (len(bc), min(bc.values()) if bc else 0)
            row[f"vmiss_{w}"] = int((mw & keep & ~np.isfinite(v)).sum())
            row[f"layer_n_{w}"] = [int((mw & keep & (A["layer"].to_numpy() == ly)).sum()) for ly in (1, 2, 3)]
        c = Counter(A.loc[ms, "excl"].map(lambda s: s[:1] if s else ""))
        row.update(ex1=c["①"], ex2=c["②"], ex3=c["③"], ex4=c["④"])
        for w in WIN:
            mw = ms & (A["window"] == w).to_numpy()
            c2 = Counter(A.loc[mw, "excl"].map(lambda s: s[:1] if s else ""))
            row.update({f"ex1_{w}": c2["①"], f"ex2_{w}": c2["②"], f"ex3_{w}": c2["③"], f"ex4_{w}": c2["④"]})
        counts[f] = row
        log(f"[표본] {SHORT[f]} " + " · ".join(
            f"{w}: L {row[f'L_{w}']:,} → 최종 {row[f'final_{w}']:,} · 첫 행 {row[f'first_{w}']:,} · 종목 "
            f"{row[f'codes_{w}']:,} · 블록 {row[f'filled_{w}'][0]}(최소 {row[f'filled_{w}'][1]})" for w in WIN))

    # 셀 표본(에피소드 첫 행)
    samp: Dict[Tuple[str, str], Dict[str, Any]] = {}
    for f in STRATS:
        for w in WIN:
            idx = np.flatnonzero(first & (A["strategy"] == f).to_numpy() & (A["window"] == w).to_numpy())
            codes, g = np.unique(A["stock_code"].to_numpy()[idx], return_inverse=True)
            samp[(f, w)] = dict(idx=idx, g=g.astype(np.int64), G=len(codes),
                                b20=A["block20"].to_numpy()[idx].astype(np.int64),
                                b20s=A["block20s"].to_numpy()[idx].astype(np.int64),
                                b40=A["block40"].to_numpy()[idx].astype(np.int64),
                                lv=A["layer"].to_numpy()[idx])

    # ── §6 자기 표본 가짜 시험 → 게이트 확정(진짜 p 계산 «전») ─────────────────────
    t = time.perf_counter()
    fk: Dict[str, Any] = {w: {ty: {SHORT[f]: {} for f in STRATS} for ty in FTYPES} for w in WIN}
    for w in WIN:
        for f in STRATS:
            sm = samp[(f, w)]
            nb = {"F-종목": sm["G"], "F-블록": n_blocks(ndays[w], BLOCK), "F-블록′": n_blocks(ndays[w], BLOCK, SHIFT),
                  "F-블록40": n_blocks(ndays[w], BLOCK40)}
            clu = {"F-종목": sm["g"], "F-블록": sm["b20"], "F-블록′": sm["b20s"], "F-블록40": sm["b40"]}
            for vi, vn_ in enumerate(VNAMES, start=1):
                e = centered(dV[vn_][sm["idx"]])
                for ty, tcode in FTYPES.items():
                    pc: List[float] = []
                    p2: List[float] = []
                    for j in range(1, N_FAKE + 1):
                        ds = fake_signs(tcode, W_IDX[w], S_IDX[f], vi, j, nb[ty])[clu[ty]] * e
                        c = cr1(ds, sm["g"])
                        pc.append(p_norm(c["mean"], c["se"])[0])
                        w2 = cgm2(ds, sm["g"], sm["b20"])
                        p2.append(p_t(w2["mean"], w2["se"], int(w2["Gb"]) - 1)[0])
                    fk[w][ty][SHORT[f]][vn_] = {"CR1": pc, "2원": p2}
    tm["fake"] = time.perf_counter() - t

    def rate(w: str, ty: str, f: str, tool_: str, a: float = FAKE_P, v_: Optional[str] = None) -> Tuple[int, int]:
        ps = [p for vn_ in (VNAMES if v_ is None else [v_]) for p in fk[w][ty][SHORT[f]][vn_][tool_]]
        return sum(1 for p in ps if p < a), len(ps)

    tool: Dict[str, Dict[str, str]] = {w: {} for w in WIN}
    gate: Dict[str, Dict[str, Any]] = {w: {} for w in WIN}
    for w in WIN:
        for f in STRATS:
            r = {ty: rate(w, ty, f, "CR1") for ty in GATE_TYPES}
            ok = all(k / n <= FAKE_MAX for k, n in r.values())
            ra = rate(w, ALT_TYPE, f, "2원")
            alt_ok = ra[0] / ra[1] <= FAKE_MAX
            tool[w][f] = "CR1" if ok else ("2원" if alt_ok else "fail")
            gate[w][SHORT[f]] = dict(cr1={ty: list(x) for ty, x in r.items()}, cr1_pass=ok, alt=list(ra),
                                     alt_pass=alt_ok, alt_applied=not ok, tool=tool[w][f])
            log(f"[가짜 게이트] {w} {SHORT[f]} CR1 F-종목 {_rt(*r['F-종목'])} · F-블록 {_rt(*r['F-블록'])} ⇒ "
                + ("통과" if ok else f"탈락 → 대체 도구 F-블록′ {_rt(*ra)} ⇒ "
                   + ("통과(2원)" if alt_ok else "탈락 ⇒ 판별 보류(도구)")))
    fake_doc = dict(prereg=f"{PREREG} ({PREREG_SHA})", seed="default_rng([20261003, t, w, s, v, j])",
                    t=dict(FTYPES), w=W_IDX, s={SHORT[f]: S_IDX[f] for f in STRATS},
                    v={k: i for i, k in enumerate(VNAMES, 1)}, j="1..100", gate=gate,
                    note="p = 양측 · CR1 = P2 첫 행·종목 CR1·정규 · 2원 = 종목×20일 블록 CGM·t(G_블록−1) · "
                         "F-블록40 시드 t=4 = 해석 기록 H7", p=fk)
    R._atomic_write(out_dir / "fake.json", json.dumps(fake_doc, ensure_ascii=False))
    log("[게이트 확정] 도구 = " + " · ".join(f"{w}: " + ", ".join(f"{SHORT[f]} {tool[w][f]}" for f in STRATS)
                                        for w in WIN) + " · fake.json 기록 — 이 줄 «뒤»에 진짜 p·라벨을 계산·인쇄한다")

    # ── 판정(E → C) ────────────────────────────────────────────────────────
    t = time.perf_counter()
    cells: Dict[Tuple[str, str], Dict[str, Dict[str, Any]]] = {}
    for f in STRATS:
        for b in VNAMES:
            cells[(f, b)] = {w: cell_stats(dV[b][samp[(f, w)]["idx"]], samp[(f, w)]["g"], samp[(f, w)]["b20"])
                             for w in WIN}
    dec = decide(cells, tool, sample_hold)
    for (f, b), dd in dec.items():
        E, C = cells[(f, b)]["E"], cells[(f, b)]["C"]
        log(f"[판정] {SHORT[f]} {b} E d̄ {E['mean']:+.4f} p {dd['pE']:.4g} Holm {'✓' if dd['passE'] else '✗'} · "
            f"C d̄ {C['mean']:+.4f}" + (f" p {dd['pC']:.4g} Holm {'✓' if dd['passC'] else '✗'}"
                                       if dd["pC"] is not None else "") + f" ⇒ {dd['label']}{''.join(dd['subs'])}")

    # ── §7 꼬리표 ───────────────────────────────────────────────────────────
    lay = {(f, b, w): _layer_stats(dV[b][samp[(f, w)]["idx"]], samp[(f, w)]["g"], samp[(f, w)]["lv"])
           for f in STRATS for b in VNAMES for w in WIN}
    tp_of = {(f, b): (rules[f].tp if b == "orig" else VARIANTS[f][b][0]) for f in STRATS for b in BRACKETS}
    same = {b: A[f"{b}_flags"].map(lambda s: X.FLAG_SL_TP_BOTH in (s or "").split(";")).to_numpy() for b in BRACKETS}
    touch: Dict[Tuple[str, str], Dict[str, Any]] = {}
    pE_all = {k: dd["pE"] for k, dd in dec.items()}
    pC_all = {k: dd["pC"] for k, dd in dec.items() if dd["pC"] is not None}
    for (f, b), dd in dec.items():
        per: Dict[str, Any] = {}
        for w in WIN:
            sm = samp[(f, w)]
            ro = np.where(same["orig"], tp_of[(f, "orig")] * 100.0, ret["orig"])[sm["idx"]]
            rv = np.where(same[b], tp_of[(f, b)] * 100.0, ret[b])[sm["idx"]]
            st = cell_stats(rv - ro, sm["g"], sm["b20"])
            st.update(n_same_o=int(same["orig"][sm["idx"]].sum()), n_same_v=int(same[b][sm["idx"]].sum()),
                      p_tool=tool_p(st, tool[w][f]))
            per[w] = st
        tags: List[str] = []
        if dd["label"] in (LAB_UP, LAB_DOWN):
            sgn = 1 if dd["label"] == LAB_UP else -1
            if any(lay[(f, b, w)][ly]["n"] > 0 and lay[(f, b, w)][ly]["mean"] * sgn < 0 for w in WIN
                   for ly in (1, 2, 3)):
                tags.append(TAG_VOL)
            pe = dict(pE_all)
            pe[(f, b)] = per["E"]["p_tool"][0]
            okE = holm(pe)[(f, b)] and per["E"]["mean"] * sgn >= THETA
            pc = dict(pC_all)
            pc[(f, b)] = per["C"]["p_tool"][1 if sgn > 0 else 2]
            okC = holm(pc)[(f, b)] and per["C"]["mean"] * sgn >= THETA
            if not (okE and okC):
                tags.append(TAG_TOUCH)
            per["okE"], per["okC"] = okE, okC
        dd["tags"] = tags
        touch[(f, b)] = per

    # ── 병기(인쇄만) ────────────────────────────────────────────────────────
    extra: Dict[Tuple[str, str, str], Dict[str, Any]] = {}
    qty = _num(A["qty"])
    flag_sets = {b: A[f"{b}_flags"].map(lambda s: set((s or "").split(";"))) for b in BRACKETS}
    for f in STRATS:
        for b in VNAMES:
            for w in WIN:
                m = keep & (A["strategy"] == f).to_numpy() & (A["window"] == w).to_numpy()
                dm = dV[b][m]
                ep = pd.Series(dm).groupby(eid[m]).mean()
                dh = hold[b][m] - hold["orig"][m]
                fm = m & first
                flg = {bb: dict(same=int(flag_sets[bb][m].map(lambda xs: X.FLAG_SL_TP_BOTH in xs).sum()),
                                gap_tp=int(flag_sets[bb][m].map(lambda xs: X.FLAG_GAP_TP in xs).sum()),
                                gap_sl=int(flag_sets[bb][m].map(lambda xs: X.FLAG_SL_GAP_0905 in xs).sum()))
                       for bb in ("orig", b)}
                tr = Counter(zip(A.loc[m, "orig_reason"], A.loc[m, f"{b}_reason"]))
                extra[(f, b, w)] = dict(
                    n=int(m.sum()), lot_mean=float(dm.mean()), ep_mean=float(ep.mean()), n_ep=int(len(ep)),
                    won=int(round(float(np.nansum(qty[m] * (price[b][m] - price["orig"][m]))))),
                    zero=float((dm == 0).mean()), flags=flg, trans={(a, c): k for (a, c), k in sorted(tr.items())},
                    dh_mean=float(dh.mean()), dh_q=[float(x) for x in np.percentile(dh, [10, 50, 90])],
                    dh_first=float((hold[b][fm] - hold["orig"][fm]).mean()),
                    std=float(np.nanmean([lay[(f, b, w)][ly]["mean"] for ly in (1, 2, 3)])))
    # §11 ma20 밴드 결합(인쇄만) — 원장 열(ref_close·entry_price·band_ok)만
    led = ctx["led"]
    m20 = (led["strategy"] == "book_pullback_ma20").to_numpy()
    ref, ent = _num(led["ref_close"])[m20], _num(led["entry_price"])[m20]
    er = led["exit_reason"].to_numpy()[m20]
    closed = (er != "open") & (er != "") & np.isfinite(ent)
    bok = led["band_ok"].to_numpy()[m20]
    band = dict(drop_v1=int((closed & (bok == "True") & (ent < ref * (1 - 0.06))).sum()),
                add_v2=int((closed & (bok == "False") & (ent >= ref * (1 - 0.10)) & (ent <= ref * 1.01)).sum()))
    tm["stats"] = time.perf_counter() - t

    # ── 출력 ────────────────────────────────────────────────────────────────
    ren = {"reason": "exit_reason", "exit_date": "exit_date", "price": "exit_price", "ret": "ret_pct",
           "hold": "hold_days", "flags": "flags"}
    cols = ["strategy", "scan_date", "stock_code", "entry_date", "entry_price", "qty", "window", "block20", "block20s",
            "block40", "hend", "excl", "repro_ok", "ep_first", "v", "v_n", "layer"]
    outA = A[cols].copy()
    for b in BRACKETS:
        for k, nm in ren.items():
            outA[f"{b}_{nm}"] = A[f"{b}_{k}"].to_numpy()
    for b in VNAMES:
        outA[f"d_{b}"] = A[f"d_{b}"].to_numpy()
    R.write_csv(out_dir / "pair_lots.csv", list(outA.columns),
                [{k: R._fmt(v_) for k, v_ in r.items()} for r in outA.to_dict("records")])
    finished = datetime.now().isoformat(timespec="seconds")
    secs_total = time.perf_counter() - T0
    res = dict(cells=cells, dec=dec, lay=lay, touch=touch, extra=extra, counts=counts, bounds=bounds, gate=gate,
               tool=tool, rate=rate, n123=n123, n4=n4, sample_hold=sample_hold, band=band, ndays=ndays, guard=guard,
               ex4_detail=Counter(x for x in A["excl"] if x.startswith("④")))
    meta = dict(prereg=f"{PREREG} ({PREREG_SHA})", git_sha=ctx["sha"], code_md5=_code_md5(), sim_md5=_sim_md5(),
                started=ctx["started"],
                finished=finished, secs_total=round(secs_total, 1), secs={k: round(v_, 1) for k, v_ in tm.items()},
                secs_sim={SHORT[f]: {b: round(x, 1) for b, x in ctx["secs_sim"][f].items()} for f in STRATS},
                input_md5=ctx["md5s"],
                db_fingerprint={k: ctx["fp"][k] for k in ("sha256", "md5", "n_stocks", "n_rows", "window")},
                blobs_strategy_2274895=ctx["blobs11"], blobs_a51c631_and_prereg_dbea62a=ctx["blobs8"],
                seeds="default_rng([20261003, t, w, s, v, j]) · t 1 F-종목 · 2 F-블록 · 3 F-블록′ · 4 F-블록40(해석 H7)",
                repro_guard={SHORT[f]: guard[f] for f in STRATS}, n_L=ctx["n_L"],
                exclusions={SHORT[f]: dict(ex1=counts[f]["ex1"], ex2=counts[f]["ex2"], ex3=counts[f]["ex3"],
                                           ex4=counts[f]["ex4"], ex4_rate=n4[f] / max(1, n123[f])) for f in STRATS},
                ex4_detail=dict(res["ex4_detail"]), vol_bounds={SHORT[f]: bounds[f] for f in STRATS},
                gate={w: {SHORT[f]: tool[w][f] for f in STRATS} for w in WIN}, band_coupling_ma20=band,
                labels={f"{SHORT[f]}|{b}": dict(label=dd["label"], subs=dd["subs"], tags=dd["tags"])
                        for (f, b), dd in dec.items()},
                outputs=["run_exit_pair.py", "RESULTS_exit_pair.md", "pair_lots.csv", "fake.json", "run_meta.json",
                         "run_log.txt"])
    R._atomic_write(out_dir / "run_meta.json", json.dumps(meta, ensure_ascii=False, indent=1, default=str))
    R._atomic_write(out_dir / "RESULTS_exit_pair.md", render(res, meta))
    log(f"[끝] {secs_total:.0f}s → {out_dir}")
    return 0


# ════════════════════════════════════════════════════════════════════════════
# 8. 결과 문서
# ════════════════════════════════════════════════════════════════════════════
INTERP = [
    "**H1 blob 가드** — 8파일(`exitsim8`·`sellprobe8`·`sources8`·`sim.py`·`loader`·`flags`·`korean_holidays`·"
    "`trading_decision_engine`)과 문서는 `git hash-object --no-filters`(작업 트리 바이트 그대로)로 `a51c631`·`dbea62a` "
    "blob 과 대조했다. `core/trading_decision_engine.py` 는 저장소에 CRLF 로 들어 있어 필터(autocrlf=input)를 거친 해시는 "
    "blob 과 다르다(내용 변경 아님 · `git diff` 0). 전략 11파일은 원장 `run.guard_blobs` 그대로.",
    "**H2 ① 수평선** — 수평선 끝 = 달력(KOSPI 행)에서 `entry_date` 뒤 `ExitRules.max_hold_days`(50·20·10) 번째 거래일. "
    "달력(끝 2026-09-23) 밖이면 제외. 입력 열 = strategy·stock_code·entry_date 뿐(`exclusions_123` · 테스트 고정).",
    "**H3 ②③** — 청산 진단 H4 방식(폭포식 ①→②→③ · `run.any_in` 양끝 포함) · 구간 `[entry_date, 수평선 끝]` · "
    "impossible_bar = `compute_bar_flags` 의 padding ∨ locked_limit ∨ cliff(가격 창 2023-01-02~ 전체).",
    "**H4 시뮬 범위** — 원 브래킷 재시뮬 = L 전체(재현 가드) · 변형 V1~V4 = ①~③ 통과 로트만(①~③ 제외 로트는 어차피 "
    "빠진다 · 결과 무관 규칙이므로 동일). 진입가 = 원장 `lot_row` 와 같은 `bars[entry_date].open` · qty = 원장 값.",
    "**H5 ④ 비율** — 분모 = 전략별 ①~③ 뒤 로트 · > 1% ⇒ 그 전략 8셀(4 변형 × E·C) 「판별 보류(표본)」. 문서가 p = 1 "
    "을 명시한 것은 §6 게이트 탈락뿐이므로 (표본) 셀의 p 는 계산값 그대로 가족에 둔다.",
    "**H6 블록** — scan_date 의 달력 순번 − 창 첫 거래일 순번(E 2024-03-13 · C 2025-07-01)을 20 으로 나눈 몫. "
    "F-블록′ = 순번 + 10 을 20 으로 나눈 몫(격자 전체를 10거래일 민 것 · 앞 10일이 짧은 첫 블록). 40일 = 40 으로 나눈 몫. "
    "부호 벡터 길이 n = 창의 달력 블록 수(20일 E 16·C 16 · F-블록′ E 17·C 16 · 40일 E 8·C 8)를 블록 순번으로 · "
    "F-종목 n = 셀 첫 행 표본의 종목 수(코드 오름차순).",
    "**H7 40일 F-블록 시드** — 문서에 시드가 없어 `default_rng([20261003, 4, w, s, v, j])`(t=4 · 다른 가짜와 겹치지 "
    "않음). 인쇄만.",
    "**H8 CGM** — 각 차원 `G/(G−1)` 보정 · G = 첫 행 표본의 비어 있지 않은 클러스터 수 · `V_종목 + V_블록 − V_종목×블록` "
    "≤ 0 이면 `max(V_종목, V_블록)`(보수적 · 건수 인쇄).",
    "**H9 대체 도구 p** — z = d̄/SE_2원 · `t(G_블록 − 1)`(G_블록 = 그 셀 첫 행 표본의 채워진 20일 블록 수) · "
    "p_up = sf(z) · p_down = cdf(z) · 양측 = 2·min.",
    "**H10 MDE** — 곱수 3.71 은 문서 값 그대로(Φ⁻¹(1−0.05/24)+Φ⁻¹(0.8) = 3.707). 「차이 없음」 조건의 MDE = "
    "3.71 × max(SE_CR1, SE_2원)(창별) · 표의 MDE_CR1 = 3.71 × SE_CR1(§4 인쇄) 따로.",
    "**H11 E 방향 후보·m_C** — E Holm(12) 통과 ∧ |d̄_E| ≥ θ 인 셀 = 「E 통과 셀」 · C 는 그 셀들만 E 방향 한쪽 p "
    "(C 도구) 로 Holm(m_C).",
    "**H12 v** — scan_date 의 달력 순번 i 에서 KOSPI 달력 20거래일 `[cal[i−19], cal[i]]`(D 포함) 안의 그 종목 «달력 날짜» "
    "봉(고가·저가 > 0)의 평균 ln(high/low) · 봉 < 15 ⇒ 결측. 경계 = `np.percentile(v_E, [33.3, 66.7])`(선형 보간 · "
    "전략별 E 최종 표본 전 로트) · 층 1: v ≤ b1 · 2: b1 < v ≤ b2 · 3: v > b2.",
    "**H13 층별 d̄** — 에피소드는 셀 전체 표본에서 정하고, 첫 행의 v 층으로 나눴다(층 안에서 에피소드 재계산 안 함).",
    "**H14 동시 터치 꼬리표** — 첫 행에서 원·변형 각자의 `sl_tp_same_bar(손절 우선)` 로트 ret 을 그 브래킷 tp×100 으로 "
    "바꾼 d′ · 셀 도구 그대로 p′ · E 가족에서 이 셀 p 만 p′ 로 바꿔 Holm 재적용 ∧ d̄′_E 방향 ≥ θ · C 가족(같은 구성원)에서 "
    "이 셀 p 만 p′_C 로 바꿔 Holm ∧ d̄′_C 방향 ≥ θ — 하나라도 깨지면 꼬리표.",
    "**H15 병기 표본** — Δhold·전이표·원 단위 합·d=0 비율·플래그 건수 = 셀의 최종 표본 «전 로트» · Δhold 는 첫 행 평균도 "
    "병기 · 에피소드 평균 = 에피소드별 d 평균의 평균.",
    "**H16 재현 가드 대조** — 원장 CSV 문자열과 exit_reason·exit_date 완전 일치 · exit_price·ret_pct 는 float 로 |차| ≤ 1e−6.",
    "**H17 「변동성 의존」** — 층 d̄ 가 라벨과 «엄격히» 반대 부호(0 은 반대 아님) · 층 표본 0 은 건너뜀.",
    "**H18 게이트 경계** — `p < 0.10` 엄격 · 거부율 > 0.16 엄격(64/400 = 0.16 은 통과).",
    "**H19 C 게이트 탈락** — 문서 §6 「C 탈락 = 방향 라벨·차이 없음 모두」 ⇒ 그 전략 4셀 「판별 보류(도구)」 · E p 는 E 가족에 "
    "그대로 · C 가족에서는 p = 1.",
]
LIMITS_11 = [
    "🔒 **결과 전 검정력 인정**: minervini 는 어떤 도구로도 MDE > θ ⇒ 「차이 없음」 불가. ma20·daytrading 은 d 의 같은 날 "
    "상관(ICC)이 ≈0.002~0.003 만 넘어도 F-블록 게이트(>0.16)에 걸린다. **사전 최빈 결과 = 12셀 판별 보류.** 방향 라벨은 "
    "|δ| ≳ 0.4%p 일 때만 가능.",
    "🔒 두 창 모두 d̄ ≥ θ 를 요구하므로 참 효과 δ = θ 이면 검출 확률 ≤ 25%(창마다 ≤ 50% · 산술).",
    "**10번 밖의 상호작용**: ma20 V3·V4 는 trail_ma 가 숨은 셋째 장벽이다(익절 ↔ trail 전환) · daytrading V2·V4 는 "
    "max_hold 전환(원장 max_hold 4,057/15,000 = 27%)이 커서 효과 일부가 보유기간 효과다 · 로트당 d 는 자리·자본 점유를 "
    "무시한다(넓힘은 보유일↑ ⇒ 자리 10/10 잠긴 전략에서 진입 수↓) ⇒ §3 전이표·Δhold 로 드러낸다.",
    "**일봉 근사** — 봉 안 순서 미지 · 같은 봉 손절 우선(좁힘에 불리 · §7 꼬리표로만 다룸) · 갭 손절 체결가 = 시가(라이브는 "
    "09:05 이후) · 분봉 재분류 안 함.",
    "**ma20 진입 밴드 결합 미측정** — 라이브 ma20 밴드 하한 = `ref × (1 − sl)`(`book_pullback_ma20/strategy.py:92`) ⇒ "
    "V1·V2 를 라이브에 넣으면 진입 집합도 바뀐다. 이 문서는 L 을 고정하고 «청산만» 바꾼다 · 밴드가 바뀌었다면 L 에서 빠지거나 "
    "들어올 로트 수만 인쇄.",
    "E 끝 로트의 경로가 C 로 넘어가 두 창이 완전 독립은 아니다 · ③ `[entry, entry+max_hold]` 의 locked_limit 제외는 "
    "상·하한가 경로를 뺀다(급등락 로트의 브래킷 효과는 안 잰다).",
    "생존자 유니버스 · 빈티지(M4) 미보정 · `corp_event` 는 2026-07 이전 거의 안 걸림(원장 PREREG §8) · 정적 휴장 목록으로 "
    "max_hold 가 하루 이른 로트(원장 README §5-1 · 202행)는 원·변형 같은 규약이라 짝 안에서 상쇄되지만 절대 수준은 어긋난다 · "
    "① 로 C 의 최근 구간이 빠진다(ma20 은 «2026-07 중순까지»의 확인).",
    "비용 = 고정 산술 규약 · 세금·호가 미끄러짐 미반영 · 가짜 두 종류는 종목·시기 상관의 일부만 대표한다(합격 = 필요조건).",
]


def _f(x: Any, nd: int = 3, sign: bool = True) -> str:
    if x is None or not (isinstance(x, (int, float, np.floating, np.integer)) and math.isfinite(float(x))):
        return "—"
    return f"{float(x):+.{nd}f}" if sign else f"{float(x):.{nd}f}"


def _p(x: Any) -> str:
    if x is None or not math.isfinite(float(x)):
        return "—"
    return f"{float(x):.4f}" if float(x) >= 1e-4 else f"{float(x):.1e}"


def render(res: Dict[str, Any], meta: Dict[str, Any]) -> str:
    cells, dec, lay, touch, extra = res["cells"], res["dec"], res["lay"], res["touch"], res["extra"]
    counts, tool, rate, guard = res["counts"], res["tool"], res["rate"], res["guard"]
    L: List[str] = [
        "# 청산 브래킷 짝 비교 — 결과 (V1~V4 · 3전략 · 같은 로트 짝 차 d)", "",
        f"> 🔒 규범 = `{PREREG}`(동결 `{PREREG_SHA}` · §12 0~4 사장님 확인 ✓) · 모문서 `docs/prereg_2026-09-24_exit_path_"
        "diagnosis.md`(`0bfbe92`) §4 · 🔴 **shadow 재료 · 라이브 룰 변경 근거 인용 금지**(§9·§10-6 · ~2026-10-16 3전략 룰 "
        "변경 0건) · 무작위 진입 대조군 결과는 설계·판정에 쓰지 않았다(실행자 미열람).",
        "",
        f"- 실행 git `{meta['git_sha'][:10]}`(브랜치 `research/candidate-ledger` · 코드 미추적 md5 `{meta['code_md5'][:12]}`) · "
        f"시작 {meta['started']} · 끝 {meta['finished']} · 총 {meta['secs_total']:.0f}s "
        f"({' · '.join(f'{k} {v:.0f}s' for k, v in meta['secs'].items())})",
        f"- 입력 md5: ledger `{meta['input_md5']['ledger_worktree']}` · scan_diag `{meta['input_md5']['scan_diag_worktree']}` "
        "— 동결값·보관소 MD5SUMS·보관소 파일 6항목 일치 ✓",
        f"- DB 지문 sha256 `{meta['db_fingerprint']['sha256'][:16]}…` · 종목 {meta['db_fingerprint']['n_stocks']:,} · 행 "
        f"{meta['db_fingerprint']['n_rows']:,} = 원장 실행 지문 ✓ · blob: 전략 11파일 = `2274895` ✓ · 8파일 = `a51c631` ✓ · "
        f"문서 = `{PREREG_SHA}` ✓",
        f"- 시드 {meta['seeds']} · θ {THETA}%p · Holm α {ALPHA} · m_E {M_E} · MDE 곱수 {MDE_K} · 가짜 {N_FAKE}회 × 4 변형",
        "",
        "## 1. 입력 · 모집단 · 재현 가드", "",
        "### 1-1. 제외 (문서 §1 표 대조 · 폭포식 ① → ② → ③ → ④)", "",
        "| 전략 | L E / C (문서) | ① 수평선 (문서) · E/C | ② corp_event E/C | ③ impossible_bar E/C | ④ 잔여 (율) | 최종 E / C |",
        "|---|---|---|---|---|---|---|"]
    for f in STRATS:
        c, e = counts[f], EXPECT_TAB[f]
        L.append(f"| {SHORT[f]} | {c['L_E']:,} / {c['L_C']:,} ({e['L_E']:,} / {e['L_C']:,}) | {c['ex1']:,} ({e['ex1']:,}) · "
                 f"{c['ex1_E']}/{c['ex1_C']} | {c['ex2_E']}/{c['ex2_C']} | {c['ex3_E']}/{c['ex3_C']} | {c['ex4']} "
                 f"({res['n4'][f] / max(1, res['n123'][f]):.3%}) | {c['final_E']:,} / {c['final_C']:,} |")
    L += ["", "- ④ 사유: " + (" · ".join(f"`{k}` {v}" for k, v in sorted(res["ex4_detail"].items())) or "없음")
          + " · > 1% ⇒ 판별 보류(표본): " + ", ".join(f"{SHORT[f]} {'예' if res['sample_hold'][f] else '아니오'}"
                                                   for f in STRATS), "",
          "### 1-2. 에피소드 첫 행 · 종목 · 블록 (① 뒤 = 문서 구조 계수와 같은 기준 · 최종 = ①~④ 뒤 판정 표본)", "",
          "| 전략 | ① 뒤 E / C (문서) | ① 뒤 첫 행 E / C (문서) | ① 뒤 종목 E / C (문서) | ① 뒤 하루 첫 행 수 E (문서) | "
          "최종 첫 행 E / C | 최종 종목 E / C | 채워진 20일 블록 E / C (최소 크기) · ① 뒤 | 최종 |",
          "|---|---|---|---|---|---|---|---|---|"]
    for f in STRATS:
        c, e = counts[f], EXPECT_TAB[f]
        dpf = c["first1_E"] / max(1, c["days_first1_E"])
        L.append(f"| {SHORT[f]} | {c['post1_E']:,} / {c['post1_C']:,} ({e['post1_E']:,} / {e['post1_C']:,}) | "
                 f"{c['first1_E']:,} / {c['first1_C']:,} ({e['first_E']:,} / {e['first_C']:,}) | {c['codes1_E']:,} / "
                 f"{c['codes1_C']:,} ({e['codes_E']:,} / {e['codes_C']:,}) | {dpf:.1f} ({e['per_day_E']}) | "
                 f"{c['first_E']:,} / {c['first_C']:,} | {c['codes_E']:,} / {c['codes_C']:,} | "
                 f"{c['filled1_E'][0]}({c['filled1_E'][1]}) / {c['filled1_C'][0]}({c['filled1_C'][1]}) | "
                 f"{c['filled_E'][0]}({c['filled_E'][1]}) / {c['filled_C'][0]}({c['filled_C'][1]}) |")
    L += ["", "- 인쇄만: 최종 표본 F-블록′ 채워진 블록 " + " · ".join(
        f"{SHORT[f]} E {counts[f]['filleds_E'][0]}({counts[f]['filleds_E'][1]}) / C {counts[f]['filleds_C'][0]}"
        f"({counts[f]['filleds_C'][1]})" for f in STRATS) + " · 40일 블록 " + " · ".join(
        f"{SHORT[f]} E {counts[f]['filled40_E'][0]}({counts[f]['filled40_E'][1]}) / C {counts[f]['filled40_C'][0]}"
        f"({counts[f]['filled40_C'][1]})" for f in STRATS) + f" · 창 거래일 E {res['ndays']['E']} · C {res['ndays']['C']}",
        "", "### 1-3. 재현 가드 (원 브래킷 재시뮬 × L 전체 vs 원장)", "",
        "| 전략 | L | 불일치 | 불일치율 | 대조율 | 문턱 0.1% |", "|---|---|---|---|---|---|"]
    for f in STRATS:
        g_ = guard[f]
        L.append(f"| {SHORT[f]} | {g_['n']:,} | {g_['mismatch']} | {g_['rate']:.4%} | {g_['agree']:.4%} | "
                 f"{'통과' if g_['rate'] <= GUARD_TOL else '🔴 초과'} |")
    b_ = res["band"]
    L += ["", f"- §11 ma20 밴드 결합(인쇄만 · 원장 ref_close·entry_price 로만): V1(sl 6% ⇒ 하한 ref×0.94)이면 L 에서 빠질 "
          f"로트 **{b_['drop_v1']:,}** · V2(sl 10% ⇒ 하한 ref×0.90)이면 밴드 밖(청산 완료)에서 들어올 로트 **{b_['add_v2']:,}** "
          "— 이 비교는 L 을 고정했으므로 반영하지 않았다.",
          "- 변동성 층 경계 v(창 E 최종 표본 · 33.3/66.7 백분위 · ln(high/low) 평균): " + " · ".join(
              f"{SHORT[f]} {res['bounds'][f][0]:.4f} / {res['bounds'][f][1]:.4f}" for f in STRATS)
          + " · 층 결측(봉 < 15): " + " · ".join(f"{SHORT[f]} E {counts[f]['vmiss_E']} / C {counts[f]['vmiss_C']}"
                                                 for f in STRATS)
          + " · 층 크기(최종 로트 L1/L2/L3): " + " · ".join(
              f"{SHORT[f]} E {'/'.join(map(str, counts[f]['layer_n_E']))} · C {'/'.join(map(str, counts[f]['layer_n_C']))}"
              for f in STRATS), ""]

    # ── 2. 가짜 게이트 ────────────────────────────────────────────────────
    L += ["## 2. 자기 표본 가짜 게이트 (§6 · 판정 «전» 확정 — `run_log.txt` 의 `[게이트 확정]` 줄이 `[판정]` 줄보다 앞)", "",
          "거부율 = `p < 0.10` 비율 · 4 변형 × 100 = 400 검정 · 게이트 > 0.16 ⇒ 탈락.", "",
          "| 창 | 전략 | F-종목 (CR1) | F-블록 (CR1) | CR1 게이트 | 대체 도구 F-블록′ (2원 · t) | 대체 도구 적용 | 최종 도구 |",
          "|---|---|---|---|---|---|---|---|"]
    for w in WIN:
        for f in STRATS:
            gg = res["gate"][w][SHORT[f]]
            L.append(f"| {w} | {SHORT[f]} | {_rt(*gg['cr1']['F-종목'])} | {_rt(*gg['cr1']['F-블록'])} | "
                     f"{'통과' if gg['cr1_pass'] else '**탈락**'} | {_rt(*gg['alt'])}"
                     f"{'' if gg['alt_applied'] else ' (인쇄만)'} | {'예' if gg['alt_applied'] else '아니오'} | "
                     f"**{ {'CR1': 'CR1', '2원': '대체(2원)', 'fail': '둘 다 탈락 ⇒ 보류(도구)'}[gg['tool']] }** |")
    L += ["", "인쇄만(판정 0):", "",
          "| 창 | 전략 | CR1 `p<0.05` F-종목 / F-블록 | CR1 F-블록40 `p<0.10` | 2원 `p<0.10` F-종목 / F-블록 / F-블록40 | "
          "셀별 CR1 `p<0.10` F-종목 (V1·V2·V3·V4 /100) | 셀별 CR1 F-블록 |", "|---|---|---|---|---|---|---|"]
    for w in WIN:
        for f in STRATS:
            L.append(f"| {w} | {SHORT[f]} | {_rt(*rate(w, 'F-종목', f, 'CR1', 0.05))} / "
                     f"{_rt(*rate(w, 'F-블록', f, 'CR1', 0.05))} | {_rt(*rate(w, 'F-블록40', f, 'CR1'))} | "
                     f"{_rt(*rate(w, 'F-종목', f, '2원'))} / {_rt(*rate(w, 'F-블록', f, '2원'))} / "
                     f"{_rt(*rate(w, 'F-블록40', f, '2원'))} | "
                     + " · ".join(str(rate(w, "F-종목", f, "CR1", v_=b)[0]) for b in VNAMES) + " | "
                     + " · ".join(str(rate(w, "F-블록", f, "CR1", v_=b)[0]) for b in VNAMES) + " |")
    L.append("")

    # ── 3. 12셀 판정표 ────────────────────────────────────────────────────
    tname = {"CR1": "CR1", "2원": "2원·t", "fail": "p=1"}
    L += ["## 3. 12셀 판정표 (§5 · d = ret(변형) − ret(원) %p · + = 변형이 낫다 · 표본 = 에피소드 첫 행)", "",
          "| 전략 | 변형 | E n / 종목 | E d̄ | E SE_CR1 | E p (도구) | E Holm(12) | E MDE_CR1 | E MDE_라벨 | C n / 종목 | "
          "C d̄ | C SE_CR1 | C p 한쪽 (도구) | C Holm(m_C) | C MDE_CR1 | C MDE_라벨 | **라벨** | 하위 표기 | 꼬리표 |",
          "|" + "---|" * 19]
    for (f, b), dd in dec.items():
        E, C = cells[(f, b)]["E"], cells[(f, b)]["C"]
        L.append(f"| {SHORT[f]} | {b} {VDESC[b]} {VARIANTS[f][b][1] * 100:.0f}/{VARIANTS[f][b][0] * 100:.0f} | "
                 f"{E['n']:,} / {E['G']:,} | {_f(E['mean'])} | {_f(E['se'], 3, False)} | {_p(dd['pE'])} "
                 f"({tname[tool['E'][f]]}) | {'✓' if dd['passE'] else '✗'} | {_f(E['mde'], 3, False)} | "
                 f"{_f(E['mde_lab'], 3, False)} | {C['n']:,} / {C['G']:,} | {_f(C['mean'])} | {_f(C['se'], 3, False)} | "
                 + (f"{_p(dd['pC'])} ({tname[tool['C'][f]]})" if dd["pC"] is not None else "— (E 후보 아님)")
                 + f" | {'—' if dd['passC'] is None else ('✓' if dd['passC'] else '✗')} | {_f(C['mde'], 3, False)} | "
                 f"{_f(C['mde_lab'], 3, False)} | **{dd['label']}** | {' '.join(dd['subs']) or '—'} | "
                 f"{' · '.join(dd['tags']) or '—'} |")
    mC = next(iter(dec.values()))["m_C"]
    order = sorted(dec, key=lambda k: dec[k]["pE"])
    L += ["", f"- 변형 열 = sl/tp(%) · E 가족 m = {M_E}(탈락 셀 p = 1 포함) · E 방향 후보(= C 가족) m_C = {mC} · "
          "Holm 1단계 문턱 α/12 = 0.00417.",
          "- E Holm 순서(p 오름차순 · 문턱 α/(m−i)): " + " · ".join(
              f"{SHORT[k[0]]} {k[1]} {_p(dec[k]['pE'])} ≤ {ALPHA / (M_E - i):.5f} {'✓' if dec[k]['passE'] else '✗'}"
              for i, k in enumerate(order)), "",
          "병기(인쇄만 · 판정 0) — 2원 클러스터(종목 × 20일 블록 · CGM) · 로트 평균 · 에피소드 평균 · 원 단위 합 · d = 0 비율 · "
          "플래그(원 → 변형 · 최종 전 로트):", "",
          "| 전략 | 변형 | 창 | SE_2원 (G_블록 · V≤0) | p_2원 양측 | 로트 n | 로트 평균 d | 에피소드 n · 평균 d | "
          "원 단위 합 Σqty×Δexit_price | d = 0 비율 | 동시 터치 원→변형 | 갭 익절 원→변형 | 갭 손절 원→변형 |",
          "|" + "---|" * 13]
    for (f, b) in dec:
        for w in WIN:
            st, ex = cells[(f, b)][w], extra[(f, b, w)]
            fo, fv = ex["flags"]["orig"], ex["flags"][b]
            L.append(f"| {SHORT[f]} | {b} | {w} | {_f(st['se2'], 3, False)} ({st['Gb']} · {'예' if st['neg2'] else '아니오'}) "
                     f"| {_p(st['p2'])} | {ex['n']:,} | {_f(ex['lot_mean'])} | {ex['n_ep']:,} · {_f(ex['ep_mean'])} | "
                     f"{ex['won']:,} | {ex['zero']:.3f} | {fo['same']}→{fv['same']} | {fo['gap_tp']}→{fv['gap_tp']} | "
                     f"{fo['gap_sl']}→{fv['gap_sl']} |")
    L.append("")

    # ── 4. Δhold · 전이표 ───────────────────────────────────────────────
    L += ["## 4. Δhold_days · exit_reason 전이표 (§3 🔒 병기 · 셀 최종 전 로트)", "",
          "Δhold = hold(변형) − hold(원) 거래일 · 🔒 방향 라벨은 반드시 Δhold 와 함께 인용(§9 · §10-5).", "",
          "| 전략 | 변형 | 창 | Δhold 평균 | p10 / p50 / p90 | 첫 행 평균 | 전이(원 → 변형 : 로트 수 · 같은 사유 포함) |",
          "|---|---|---|---|---|---|---|"]
    for (f, b) in dec:
        for w in WIN:
            ex = extra[(f, b, w)]
            tr = " · ".join(f"{a}→{c} {k:,}" for (a, c), k in sorted(ex["trans"].items(), key=lambda t_: -t_[1]))
            L.append(f"| {SHORT[f]} | {b} | {w} | {_f(ex['dh_mean'], 2)} | {ex['dh_q'][0]:+.0f} / {ex['dh_q'][1]:+.0f} / "
                     f"{ex['dh_q'][2]:+.0f} | {_f(ex['dh_first'], 2)} | {tr} |")
    L.append("")

    # ── 5. 꼬리표 ─────────────────────────────────────────────────────────
    L += ["## 5. 꼬리표 (§7 · 라벨을 바꾸지 않음)", "",
          "### 5-1. 변동성 층별 d̄ (에피소드 첫 행 · CR1 SE · 인쇄 · Holm 가족 밖 · 라벨 없음)", "",
          "| 전략 | 변형 | 창 | L1 d̄ (SE · n) | L2 d̄ (SE · n) | L3 d̄ (SE · n) | 등가중 평균(C = E 구성 표준화 d̄) | 비층화 d̄ |",
          "|---|---|---|---|---|---|---|---|"]
    for (f, b) in dec:
        for w in WIN:
            ly = lay[(f, b, w)]
            L.append(f"| {SHORT[f]} | {b} | {w} | " + " | ".join(
                f"{_f(ly[k]['mean'])} ({_f(ly[k]['se'], 3, False)} · {ly[k]['n']:,})" for k in (1, 2, 3))
                + f" | {_f(extra[(f, b, w)]['std'])} | {_f(cells[(f, b)][w]['mean'])} |")
    L += ["", "### 5-2. 동시 터치 「익절 우선」 상한 (첫 행 · 재시뮬 없음)", "",
          "| 전략 | 변형 | 창 | 동시 터치 첫 행 원 / 변형 | d̄′ | p′ 양측 (셀 도구) | 라벨 조건 유지(방향 라벨 셀만) |",
          "|---|---|---|---|---|---|---|"]
    for (f, b), dd in dec.items():
        for w in WIN:
            tt = touch[(f, b)][w]
            keep_ = "—" if dd["label"] not in (LAB_UP, LAB_DOWN) else ("유지" if touch[(f, b)].get(f"ok{w}") else "깨짐")
            L.append(f"| {SHORT[f]} | {b} | {w} | {tt['n_same_o']} / {tt['n_same_v']} | {_f(tt['mean'])} | "
                     f"{_p(tt['p_tool'][0])} | {keep_} |")
    n_dir = sum(1 for dd in dec.values() if dd["label"] in (LAB_UP, LAB_DOWN))
    L += ["", f"- 방향 라벨 셀 {n_dir}개 · 꼬리표는 방향 라벨 셀에만 붙인다(「변동성 의존」 = 층 없이 일반화하지 말 것 · "
          "「그 층에만 쓰자」가 아님).", ""]

    # ── 6~9 ──────────────────────────────────────────────────────────────
    L += ["## 6. 해석 기록 (문서가 정하지 않은 구현 선택 · 결과를 보기 «전»에 코드에 고정)", ""]
    L += [f"{i}. {s}" for i, s in enumerate(INTERP, 1)]
    L += ["", "## 7. 문서와 다르게 한 것", "",
          "- 🔒 항목: 없음(V1~V4 값 · 수평선·제외 규칙 · θ · p 부품 · Holm m=12·탈락 셀 p=1 · m_C · E→C · 게이트 0.16 · "
          "대체 도구 · 변동성 3층·꼬리표 · 동시 터치 상한 · 시드 · 라벨 · MDE · 비용 상한 = 문서 그대로).",
          "- 산출물 추가: `pilot/`(③ 파일럿 `run_log.txt`·`pilot_timing.json`·`parts/`) · `parts/`(전략 단위 체크포인트 · "
          "§8 비용 상한 절의 체크포인트).", "",
          "## 8. 한계 (문서 §11 인용)", ""]
    L += [f"> - {s}" for s in LIMITS_11]
    L += ["", "## 9. §10 금지 준수", "",
          "- 결과를 본 뒤 바꾼 것 0 · 격자·조합 0 · 층별·창별·사유별 결과로 브래킷 선택 0 · 판정 p = §4 P2·CR1 / §6 대체 도구뿐 · "
          "전략을 섞은 평균 0 · 「판별 보류」를 「차이 없음」으로 쓰지 않음 · Δhold 병기 · 라이브 0줄 · DB SELECT 만 · "
          "무작위 대조군 결과 미사용 · 원장 값 수정 0.", ""]
    return "\n".join(L) + "\n"


if __name__ == "__main__":
    sys.exit(main())
