"""무작위 진입 대조군 — 사전등록 `docs/prereg_2026-09-24_exit_path_diagnosis.md`(🔒 동결 0bfbe92) §5~§8 그대로.

    cd <worktree>/RoboTrader_template
    $PY -m backtest.concept_axes.candidate_ledger.exit_diag.run_random_entry --guard-only   # 로드 · n_eligible · 재현 가드만
    $PY -m backtest.concept_axes.candidate_ledger.exit_diag.run_random_entry                # 본 실행 → RESULTS_random_entry.md

순서(문서 §6-2): ④ 대조군 코드 + 테스트 → ⑤ 가짜 룰 거부율 → ⑥ §5 판정. 가짜 룰 거부율이 0.16 을 넘으면 판정 단계는 건너뛴다.
p = 도구 교정 합격 주 도구 K2 의 귀무/SE 부품 = P2(에피소드 첫 행 · 종목 클러스터 CR1 · 정규 근사) 를 이진 비교에 적용.
🔴 관측 · 라이브 룰 변경 근거 인용 금지(§7-6) · DB SELECT 만(`bootstrap` = 읽기 전용 세션) · 재사용 모듈 수정 0줄.
재사용: 유니버스 = `replayer/scan.eligible_for_dates`(원장 `run.py:798` 과 같은 호출) · 밴드 = `run.entry_band`/`band_ok` 식 ·
청산 = `ledger8/exitsim8` 규칙(벡터화 재구현 → L 전체 재현 가드 · 불일치 > 0.1% 면 원 코드 `simulate_lot` + `SellProbe`) ·
에피소드 = `tool_calibration/run_calib.episodes`.
"""
from __future__ import annotations

from backtest.concept_axes.minervini.cap_skip_ledger import bootstrap  # noqa: F401  안전 설정 먼저

import argparse                                                        # noqa: E402
import csv                                                             # noqa: E402
import importlib                                                       # noqa: E402
import json                                                            # noqa: E402
import math                                                            # noqa: E402
import sys                                                             # noqa: E402
import time                                                            # noqa: E402
import warnings                                                        # noqa: E402
from collections import OrderedDict                                    # noqa: E402
from dataclasses import dataclass                                      # noqa: E402
from datetime import date, datetime, timedelta                         # noqa: E402
from pathlib import Path                                               # noqa: E402
from statistics import NormalDist                                      # noqa: E402
from typing import Any, Dict, List, Optional, Sequence, Tuple          # noqa: E402

import numpy as np                                                     # noqa: E402
import pandas as pd                                                    # noqa: E402

from backtest.concept_axes.candidate_ledger import run as R            # noqa: E402
from backtest.concept_axes.candidate_ledger.exit_diag import run_exit_diag as D  # noqa: E402
from backtest.concept_axes.candidate_ledger.tool_calibration import run_calib as RC  # noqa: E402
from backtest.concept_axes.ledger8 import exitsim8 as X                # noqa: E402
from backtest.concept_axes.ledger8 import sellprobe8 as SP             # noqa: E402
from backtest.concept_axes.ledger8 import sources8 as SRC8             # noqa: E402
from backtest.concept_axes.ledger8 import sizing as Z                  # noqa: E402
from backtest.concept_axes.ledger8.livesignal8 import load8            # noqa: E402
from backtest.concept_axes.replayer import loader as LD                # noqa: E402
from backtest.concept_axes.replayer import scan as SC                  # noqa: E402
from config.constants import OHLCV_LOOKBACK_DAYS                       # noqa: E402
from utils.korean_holidays import is_holiday                           # noqa: E402

warnings.filterwarnings("ignore", message="pandas only supports SQLAlchemy")

BASE = Path(__file__).resolve().parent
LEDGER_DIR = D.LEDGER_DIR
STRATS = list(D.EXPECT_L)                          # ma20 → minervini → daytrading (고정 순서 · 난수 소비 순서)
SHORT = D.SHORT
EXIT_META = BASE / "run_meta.json"                 # ③ 진단 실행 지문(DB 지문 대조용)

# ── §5 🔒 ──────────────────────────────────────────────────────────────────
N_REP = 200
SEED_REP = (20261002, 2)                           # default_rng([20261002, 2, r]) · r = 0..199
N_FAKE = 100
SEED_FAKE = (20261002, 3)                          # default_rng([20261002, 3, j]) · j = 0..99
COST = 0.25                                        # %(비용 1회분)
T_MIN = 0.25                                       # %p 라벨 문턱
HOLM_M, ALPHA = 6, 0.05
FAKE_P, FAKE_MAX = 0.10, 0.16
GUARD_TOL = 0.001                                  # 재현 가드 불일치 허용 0.1%
RET_TOL = 1e-9                                     # ret_pct 대조 여유(%) — 원장 15자리 인쇄
Z_POWER = NormalDist().inv_cdf(0.80)
Z_HOLM1 = NormalDist().inv_cdf(1 - ALPHA / HOLM_M)  # 한쪽 · Holm m=6 1단계 문턱
MDE_K = Z_HOLM1 + Z_POWER                          # 해석 기록 I7

# ── 비용 상한(문서 §6-3) ────────────────────────────────────────────────────
SECS_STEP3 = 31.2                                  # ③ 진단 실행 시간(exit_diag/run_meta.json secs_total)
BUDGET_S = 3600.0 - SECS_STEP3
PILOT_MONTH = "2025-03"                            # 1개월 파일럿(③ 과 같은 달)
SAMPLE_N = 3000                                    # 인쇄 전용 — 무작위 로트 표본 원 코드 대조
SEED_SAMPLE = (20261002, 9, 0)                     # 인쇄 전용 대조의 표본 추출 시드(판정 무관)

BOARDS = OrderedDict([("main", "주판(종목 단위 대응)"), ("fake", "가짜 룰"),
                      ("b1", "병기판 ① L 밖 대조"), ("b2", "병기판 ② 날짜 독립")])

RSN = ["open", "tp", "sl", "max_hold", "trail_ma"]  # 청산 사유 코드(그 밖 데이터 청산 코드는 뒤에 붙인다)
LAB_UP, LAB_DOWN, LAB_NONE, LAB_HOLD = "룰 > 무작위", "룰 < 무작위", "차이 없음", "판별 보류"
LAB_HOLD_FAKE = "판별 보류(도구가 이 비교에서 낙관적)"
LAB_HOLD_TIME = "판별 보류(1개월 파일럿 예상 1시간 초과 · 부분 실행 판정 없음)"


def log(msg: str = "") -> None:
    print(msg, file=sys.stderr, flush=True)


# ════════════════════════════════════════════════════════════════════════════
# 1. 시장 배열(달력 정렬) · 유니버스 · 밴드
# ════════════════════════════════════════════════════════════════════════════
@dataclass
class Market:
    cal: List[date]
    cal64: np.ndarray
    codes: np.ndarray                  # 정렬된 종목 코드
    O: np.ndarray                      # (n_cal, n_stock) 달력 정렬 시가 · 결측 NaN
    H: np.ndarray
    Lo: np.ndarray
    C: np.ndarray
    HAS: np.ndarray                    # 달력 날짜 봉 존재
    BAD: np.ndarray                    # 원본 시가 결측/≤0 (run.load_bad_open)
    px_date: np.ndarray                # px 전 행(달력 밖 행 포함 · window_fn 과 같은 원천)
    px_close: np.ndarray
    bounds: np.ndarray                 # 종목 k 의 px 행 = [bounds[k], bounds[k+1])

    @property
    def n_cal(self) -> int:
        return len(self.cal)

    @property
    def n_stock(self) -> int:
        return len(self.codes)


def build_market(px: pd.DataFrame, cal: List[date], bad_open: set) -> Market:
    cal64 = pd.to_datetime(pd.Series(cal)).to_numpy(dtype="datetime64[ns]")
    codes = np.array(sorted(px["stock_code"].astype(str).unique()))
    sc = px["stock_code"].astype(str).to_numpy()
    si = np.searchsorted(codes, sc)
    dt = px["date"].to_numpy(dtype="datetime64[ns]")
    ci = np.searchsorted(cal64, dt)
    on = (ci < len(cal64)) & (cal64[np.minimum(ci, len(cal64) - 1)] == dt)
    shape = (len(cal64), len(codes))
    mats = {}
    for c in ("open", "high", "low", "close"):
        m = np.full(shape, np.nan)
        m[ci[on], si[on]] = px[c].to_numpy(dtype=float)[on]
        mats[c] = m
    has = np.zeros(shape, dtype=bool)
    has[ci[on], si[on]] = True
    bad = np.zeros(shape, dtype=bool)
    cidx = {d: i for i, d in enumerate(cal)}
    kidx = {c: i for i, c in enumerate(codes)}
    for c, d in bad_open:
        if d in cidx and c in kidx:
            bad[cidx[d], kidx[c]] = True
    order_ok = bool((np.diff(si) >= 0).all())
    if not order_ok:
        raise SystemExit("🔴 px 가 종목 순 정렬이 아니다 — 중단")
    bounds = np.searchsorted(si, np.arange(len(codes) + 1))
    return Market(cal, cal64, codes, mats["open"], mats["high"], mats["low"], mats["close"], has, bad,
                  dt, px["close"].to_numpy(dtype=float), bounds)


def ub_mask(mk: Market, elig: Dict[pd.Timestamp, set], down: Optional[float], up: Optional[float],
            scan_idx: Sequence[int]) -> np.ndarray:
    """§5 `U_b(s,d)` = `U(s,d)` ∩ D 봉 있음(밴드 기준가 = D 종가) ∩ D+1 봉·원본 시가 > 0 ∩ `lo ≤ open ≤ hi`(run.band_ok 식)."""
    M = np.zeros((mk.n_cal, mk.n_stock), dtype=bool)
    kidx = {c: i for i, c in enumerate(mk.codes)}
    for d in scan_idx:
        if d + 1 >= mk.n_cal:
            continue
        ks = np.array(sorted(kidx[c] for c in elig.get(pd.Timestamp(mk.cal[d]), ()) if c in kidx), dtype=np.int64)
        if not len(ks):
            continue
        ref, op = mk.C[d, ks], mk.O[d + 1, ks]
        ok = mk.HAS[d, ks] & mk.HAS[d + 1, ks] & ~mk.BAD[d + 1, ks] & (op > 0) & (ref > 0)
        if down is not None:
            ok &= op >= ref * (1.0 - down)
        if up is not None:
            ok &= op <= ref * (1.0 + up)
        M[d, ks[ok]] = True
    return M


@dataclass
class Pools:
    """날짜별 추출 집합 — 멤버십 행렬 · 정렬 목록 · 패딩 행렬(벡터 대체 추출용)."""
    M: np.ndarray
    lists: Dict[int, np.ndarray]
    pad: np.ndarray
    size: np.ndarray


def make_pools(M: np.ndarray) -> Pools:
    lists = {int(d): np.flatnonzero(M[d]) for d in np.flatnonzero(M.any(axis=1))}
    size = M.sum(axis=1).astype(np.int64)
    pad = np.zeros((M.shape[0], max(1, int(size.max()) if len(size) else 1)), dtype=np.int64)
    for d, v in lists.items():
        pad[d, :len(v)] = v
    return Pools(M, lists, pad, size)


# ════════════════════════════════════════════════════════════════════════════
# 2. 추출 — 종목 단위 대응(주판·가짜 룰·병기판 ①) · 날짜 독립(병기판 ②)
# ════════════════════════════════════════════════════════════════════════════
def first_groups(d_lot: np.ndarray, g_lot: np.ndarray) -> List[Tuple[int, np.ndarray]]:
    """종목 g 의 L 첫 등장일 d0 → [(d0, 그날 처음 나온 g 들(오름차순))] d0 오름차순."""
    first: Dict[int, int] = {}
    for d, g in zip(d_lot.tolist(), g_lot.tolist()):
        if g not in first or d < first[g]:
            first[g] = d
    by: Dict[int, List[int]] = {}
    for g, d in first.items():
        by.setdefault(d, []).append(g)
    return [(d, np.array(sorted(by[d]), dtype=np.int64)) for d in sorted(by)]


def draw_mapped(rng: np.random.Generator, d_lot: np.ndarray, g_lot: np.ndarray,
                groups: List[Tuple[int, np.ndarray]], P: Pools, n_stock: int) -> Dict[str, Any]:
    """§5 주판 — π(g) = g 의 첫 등장일 추출 집합에서 «그날 첫 등장 g 들끼리» 비복원 추출 → g 의 모든 날에 π(g).
    그날 π(g) ∉ 집합이면 그날만 집합에서 균등 대체 추출. 집합이 비면 h = −1(로트 탈락 · 계수).
    난수 소비 순서: 첫 등장일 오름차순 × `choice(size=k, replace=False)` → 대체 대상 로트(로트 순) `integers`."""
    pi = np.full(n_stock, -1, dtype=np.int64)
    n_short = 0
    for d0, gs in groups:
        pool = P.lists.get(d0)
        if pool is None or not len(pool):
            continue
        if len(gs) > len(pool):                    # 병기판 ① 에서만 가능(L 을 빼서 모자람)
            n_short += len(gs)
            pi[gs] = rng.choice(pool, size=len(gs), replace=True)
        else:
            pi[gs] = rng.choice(pool, size=len(gs), replace=False)
    h = pi[g_lot]
    ok = h >= 0
    ok[ok] = P.M[d_lot[ok], h[ok]]
    bad = np.flatnonzero(~ok)
    sz = P.size[d_lot[bad]]
    can = bad[sz > 0]
    if len(can):
        u = rng.integers(0, P.size[d_lot[can]])
        h[can] = P.pad[d_lot[can], u]
    h[bad[sz == 0]] = -1
    return dict(h=h, n_replaced=int(len(can)), n_dropped=int((sz == 0).sum()), n_short=n_short,
                dup_pi=dup_count(np.flatnonzero(pi >= 0), pi[pi >= 0]), dup_real=dup_count(g_lot, h))


def draw_daily(rng: np.random.Generator, day_groups: List[Tuple[int, np.ndarray]], P: Pools, n_lot: int) -> Dict[str, Any]:
    """병기판 ② — 날마다 새로: 그날 L 로트 수만큼 집합에서 비복원 추출(로트 순 배정)."""
    h = np.full(n_lot, -1, dtype=np.int64)
    for d, pos in day_groups:
        h[pos] = rng.choice(P.lists[d], size=len(pos), replace=False)
    return dict(h=h, n_replaced=0, n_dropped=0, n_short=0, dup_pi=0, dup_real=0)


def dup_count(g: np.ndarray, h: np.ndarray) -> int:
    """서로 다른 g 가 같은 h 로 간 건수 = Σ_h (그 h 로 간 서로 다른 g 수 − 1)."""
    m = h >= 0
    if not m.any():
        return 0
    pairs = np.unique(np.stack([h[m], g[m]], axis=1), axis=0)
    _, cnt = np.unique(pairs[:, 0], return_counts=True)
    return int((cnt - 1).sum())


# ════════════════════════════════════════════════════════════════════════════
# 3. 청산 — 벡터화(빠른) 재구현 · 원 코드 경로
# ════════════════════════════════════════════════════════════════════════════
@dataclass(frozen=True)
class SimSpec:
    tp: float
    sl: float
    mh: int                            # ExitRules.max_hold_days(position_monitor 보유기간 · 달력 k)
    smh: int                           # 전략 `_max_hold_days`(데이터 청산 max_hold · 정적 휴장 목록)
    min_len: int                       # generate_signal 최소 봉 수
    trail: Optional[int]               # ma20 trail_ma = 20 · 그 밖 None
    hold_mode: str                     # "count1"(ma20·daytrading) · "elapsed"(minervini)


def spec_of(folder: str, strategy: Any, rules: X.ExitRules) -> SimSpec:
    return SimSpec(tp=float(rules.tp), sl=float(rules.sl), mh=int(rules.max_hold_days),
                   smh=int(strategy._max_hold_days), min_len=int(strategy.get_min_data_length()),
                   trail=getattr(strategy, "_trail_ma", None) if folder != "minervini_volume_dryup" else None,
                   hold_mode="elapsed" if folder == "minervini_volume_dryup" else "count1")


def holiday_counts(cal: Sequence[date]) -> Tuple[List[int], List[int]]:
    """HC[t] = [기준일, cal[t]] 의 비휴일 수 · HCm1[t] = [기준일, cal[t]−1] — `utils.korean_holidays.is_holiday` 그대로."""
    d0, d1 = cal[0] - timedelta(days=7), cal[-1] + timedelta(days=1)
    days = [d0 + timedelta(days=i) for i in range((d1 - d0).days + 1)]
    cum = np.cumsum([0 if is_holiday(datetime(d.year, d.month, d.day)) else 1 for d in days])
    pos = {d: i for i, d in enumerate(days)}
    return [int(cum[pos[d]]) for d in cal], [int(cum[pos[d] - 1]) for d in cal]


class StockView:
    """종목 1개의 달력 정렬 봉 + window_fn 경계(run.make_window_fn 과 같은 px 행 · `date < day` · 120 달력일)."""

    def __init__(self, mk: Market, k: int, days: int = OHLCV_LOOKBACK_DAYS):
        a, b = int(mk.bounds[k]), int(mk.bounds[k + 1])
        pdt = mk.px_date[a:b]
        self.pc_np = mk.px_close[a:b]
        self.pc = self.pc_np.tolist()
        self.cs = np.concatenate([[0.0], np.cumsum(self.pc_np)]).tolist()
        self.J = np.searchsorted(pdt, mk.cal64, side="left").tolist()
        self.S0 = np.searchsorted(pdt, mk.cal64 - np.timedelta64(days, "D"), side="left").tolist()
        self.has = mk.HAS[:, k].tolist()
        self.o = mk.O[:, k].tolist()
        self.h = mk.H[:, k].tolist()
        self.lo = mk.Lo[:, k].tolist()


def _exact_ma(pc: np.ndarray, s0: int, j: int, w: int) -> Optional[float]:
    """rules_daily._ma 그대로(pandas rolling) — 빠른 MA 가 종가와 1e-9 이내로 붙을 때만 부른다."""
    val = pd.Series(pc[s0:j]).rolling(w).mean().iloc[-1]
    if pd.isna(val) or val <= 0:
        return None
    return float(val)


def probe_fast(sp: SimSpec, sv: StockView, E: float, e: int, t: int, HC: List[int], HCm1: List[int]) -> Optional[str]:
    """SellProbe 1회(평가일 = cal[t]) 재구현: 창 비었거나 < min_len ⇒ None → 보유일 ≥ 전략 max_hold ⇒ max_hold →
    (ma20) 수익 중 ∧ 종가 < MA20 ⇒ trail_ma."""
    j, s0 = sv.J[t], sv.S0[t]
    n = j - s0
    if n <= 0 or n < sp.min_len:
        return None
    if sp.hold_mode == "elapsed":
        hold = HC[t] - HC[e]
    else:
        hold = max(0, HC[t] - HCm1[e] - 1)
    if hold >= sp.smh:
        return "max_hold"
    if sp.trail is not None:
        cur = sv.pc[j - 1]
        if (cur - E) / E > 0 and n >= sp.trail:
            ma: Optional[float] = (sv.cs[j] - sv.cs[j - sp.trail]) / sp.trail
            if abs(cur - ma) <= 1e-9 * max(1.0, abs(cur)):
                ma = _exact_ma(sv.pc_np, s0, j, sp.trail)
            if ma is not None and ma > 0 and cur < ma:
                return "trail_ma"
    return None


def sim_fast(sp: SimSpec, sv: StockView, e: int, n_cal: int, HC: List[int], HCm1: List[int]
             ) -> Tuple[str, int, float, float]:
    """exitsim8.simulate_lot(BASIS_D_OPEN) 재구현 → (사유, 청산 달력 index, ret_pct, 청산가). 미청산 = ("open", −1, nan, nan)."""
    tp, sl, mh = sp.tp, sp.sl, sp.mh
    E = float(sv.o[e])
    r = probe_fast(sp, sv, E, e, e, HC, HCm1)                        # k=0 데이터 청산(가격 = 진입가)
    if r:
        return r, e, (E - E) / E * 100.0, E
    if (sv.lo[e] - E) / E <= -sl:                                     # k=0 터치 · 동시면 손절 우선
        px = E * (1.0 - sl)
        return "sl", e, (px - E) / E * 100.0, px
    if (sv.h[e] - E) / E >= tp:
        px = E * (1.0 + tp)
        return "tp", e, (px - E) / E * 100.0, px
    pending = False
    for t in range(e + 1, n_cal):
        k = t - e
        if not sv.has[t]:
            if k >= mh:
                pending = True
            continue
        o = sv.o[t]
        if pending or k >= mh:
            return "max_hold", t, (o - E) / E * 100.0, o
        if (o - E) / E >= tp:
            return "tp", t, (o - E) / E * 100.0, o
        r = probe_fast(sp, sv, E, e, t, HC, HCm1)
        if r:
            return r, t, (o - E) / E * 100.0, o
        if (o - E) / E <= -sl:
            return "sl", t, (o - E) / E * 100.0, o
        if (sv.lo[t] - E) / E <= -sl:
            px = E * (1.0 - sl)
            return "sl", t, (px - E) / E * 100.0, px
        if (sv.h[t] - E) / E >= tp:
            px = E * (1.0 + tp)
            return "tp", t, (px - E) / E * 100.0, px
    return "open", -1, float("nan"), float("nan")


def run_fast(mk: Market, specs: Dict[int, SimSpec], s_arr: np.ndarray, d_arr: np.ndarray, k_arr: np.ndarray,
             HC: List[int], HCm1: List[int]) -> Dict[str, np.ndarray]:
    """로트 (전략, D index, 종목) 묶음 → 결과 배열. 종목별로 묶어 StockView 를 한 번만 만든다."""
    n = len(s_arr)
    reason = np.empty(n, dtype=object)
    exit_i = np.full(n, -1, dtype=np.int64)
    ret = np.full(n, np.nan)
    xpx = np.full(n, np.nan)
    order = np.argsort(k_arr, kind="stable")
    ks = k_arr[order]
    cuts = np.flatnonzero(np.diff(ks)) + 1
    for grp in np.split(order, cuts):
        if not len(grp):
            continue
        sv = StockView(mk, int(k_arr[grp[0]]))
        for i in grp.tolist():
            rs, xi, rt, xp = sim_fast(specs[int(s_arr[i])], sv, int(d_arr[i]) + 1, mk.n_cal, HC, HCm1)
            reason[i], exit_i[i], ret[i], xpx[i] = rs, xi, rt, xp
    return dict(reason=reason, exit_i=exit_i, ret=ret, xpx=xpx)


def run_orig(mk: Market, env: R.Env, probes: Dict[int, Any], rules: Dict[int, X.ExitRules], s_arr: np.ndarray,
             d_arr: np.ndarray, k_arr: np.ndarray) -> Dict[str, np.ndarray]:
    """원 코드 경로(대체 경로 · 인쇄 전용 표본 대조) — 원장 `run.lot_row` 의 청산 호출 그대로."""
    n = len(s_arr)
    reason = np.empty(n, dtype=object)
    exit_i = np.full(n, -1, dtype=np.int64)
    ret = np.full(n, np.nan)
    xpx = np.full(n, np.nan)
    cidx = env.cal_idx
    for i in range(n):
        code, d = str(mk.codes[k_arr[i]]), mk.cal[int(d_arr[i])]
        bars = env.bars(code)
        d1 = env.next_day(d)
        px_open = float(bars[d1].open)
        q = Z.arm_b_qty(px_open)
        rl = rules[int(s_arr[i])]
        pos = X.Pos(code, d1, SRC8.aware(datetime.combine(d1, R.ENTRY_TIME)), px_open, q.qty, X.BASIS_D_OPEN)
        ex = X.simulate_lot(pos, rl, R.build_path(env.cal, env.cal_idx, bars, d1, rl.max_hold_days),
                            probes[int(s_arr[i])])
        if ex.closed and ex.exit_date is not None:
            reason[i], exit_i[i], ret[i], xpx[i] = ex.reason, cidx[ex.exit_date], ex.ret_pct, ex.price
        else:
            reason[i] = X.EXIT_OPEN
    return dict(reason=reason, exit_i=exit_i, ret=ret, xpx=xpx)


def guard_compare(reason: Sequence[str], exit_date: Sequence[str], ret: Sequence[float],
                  want_reason: Sequence[str], want_date: Sequence[str], want_ret: Sequence[float],
                  tol: float = RET_TOL) -> Dict[str, int]:
    """재현 가드 — 로트별 (exit_reason, exit_date, ret_pct) 대조. 한 항목이라도 다르면 그 로트는 불일치."""
    n_r = n_d = n_x = n_any = 0
    for a, b, c, wa, wb, wc in zip(reason, exit_date, ret, want_reason, want_date, want_ret):
        br = a != wa
        bd = b != wb
        bx = not (c == c and wc == wc and abs(float(c) - float(wc)) <= tol)
        n_r += br
        n_d += bd
        n_x += bx
        n_any += br or bd or bx
    return dict(n=len(want_reason), reason=n_r, date=n_d, ret=n_x, any=n_any)


# ════════════════════════════════════════════════════════════════════════════
# 4. 검정 — P2 이진 비교(에피소드 첫 행 · 종목 클러스터 CR1 · 정규 근사) · Holm · 라벨
# ════════════════════════════════════════════════════════════════════════════
def p2_binary(y1: np.ndarray, c1: np.ndarray, y0: np.ndarray, c0: np.ndarray, w0: np.ndarray) -> Dict[str, float]:
    """룰=1 · 무작위=0 이진 회귀 기울기(= 가중 평균 차)의 종목 클러스터 CR1 SE.

    Δ = mean(y1) − Σw0·y0/Σw0 · ψ_c = Σ_{i∈c} y1 잔차/n1 − Σ_{j∈c} w0_j·y0 잔차/Σw0 (run_calib.cr1_test 와 같은 꼴) ·
    V = G/(G−1)·(N−1)/(N−K)·Σψ² · N = n1 + Σw0(가중 로트 수) · K = 2 · G = 룰·무작위 합친 고유 종목 수.
    p_up = Φ(−Δ/SE)(룰 > 무작위) · p_down = Φ(Δ/SE).
    """
    n1, W0 = float(len(y1)), float(w0.sum())
    if n1 < 2 or W0 <= 0:
        return dict(delta=np.nan, se=np.nan, p_up=np.nan, p_down=np.nan, G=0, N=n1 + W0)
    m1 = float(y1.mean())
    m0 = float((w0 * y0).sum() / W0)
    cl = np.concatenate([c1, c0])
    uniq, inv = np.unique(cl, return_inverse=True)
    wts = np.concatenate([(y1 - m1) / n1, -(w0 * (y0 - m0)) / W0])
    psi = np.bincount(inv, weights=wts, minlength=len(uniq))
    G, N, K = len(uniq), n1 + W0, 2
    v = G / (G - 1) * (N - 1) / (N - K) * float((psi ** 2).sum())
    se = math.sqrt(v)
    delta = m1 - m0
    if se <= 0:
        return dict(delta=delta, se=se, p_up=np.nan, p_down=np.nan, G=G, N=N)
    z = delta / se
    return dict(delta=delta, se=se, p_up=0.5 * math.erfc(z / math.sqrt(2)), p_down=0.5 * math.erfc(-z / math.sqrt(2)),
                G=G, N=N)


def holm(ps: Dict[Any, float], alpha: float = ALPHA) -> Dict[Any, bool]:
    """Holm step-down — p 오름차순 i 번째(0부터) 문턱 α/(m−i) · 처음 실패에서 멈춤 · NaN 은 기각 안 함(맨 뒤)."""
    keys = sorted(ps, key=lambda k: (not (ps[k] == ps[k]), ps[k] if ps[k] == ps[k] else 0.0, str(k)))
    m = len(keys)
    out = {k: False for k in keys}
    for i, k in enumerate(keys):
        p = ps[k]
        if p == p and p <= alpha / (m - i):
            out[k] = True
        else:
            break
    return out


def label(T: float, up_pass: bool, down_pass: bool, mde: float) -> str:
    """§5 판정 라벨(결과 전 고정)."""
    if up_pass and T >= T_MIN:
        return LAB_UP
    if down_pass and T <= -T_MIN:
        return LAB_DOWN
    if abs(T) < T_MIN and mde <= T_MIN:
        return LAB_NONE
    return LAB_HOLD


# ════════════════════════════════════════════════════════════════════════════
# 5. main
# ════════════════════════════════════════════════════════════════════════════
def _f(x: float, nd: int = 3) -> str:
    return "—" if x is None or not np.isfinite(x) else f"{x:+.{nd}f}"


def _p(x: float) -> str:
    return "—" if x is None or not np.isfinite(x) else f"{x:.4f}"


def _won(x: float) -> str:
    return "—" if x is None or not np.isfinite(x) else f"{int(round(x)):,}"


def main(argv: Optional[Sequence[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="무작위 진입 대조군 §5 (사전등록 동결 0bfbe92)")
    ap.add_argument("--guard-only", action="store_true", help="로드 · n_eligible 전수 대조 · 재현 가드만(추출·판정 없음)")
    ap.add_argument("--out", default=None)
    a = ap.parse_args(argv)
    out_dir = Path(a.out) if a.out else BASE
    started = datetime.now().isoformat(timespec="seconds")
    T0 = time.perf_counter()
    tm: Dict[str, float] = {}

    # ── 가드 ────────────────────────────────────────────────────────────────
    md5s = D.check_inputs()
    prereg_blob = D.check_prereg_frozen()
    blobs = R.guard_blobs()
    sha = R.git_sha()
    strategies = {f: load8(f) for f in STRATS}
    adapters = {f: getattr(importlib.import_module(R.STRATS[f]["module"]), R.STRATS[f]["cls"])() for f in STRATS}
    rules = {f: SP.resolve_live_tp_sl(f, strategies[f]) for f in STRATS}
    for f in STRATS:
        R.guard_rules(f, rules[f], strategies[f], adapters[f])
    exit_meta = json.loads(EXIT_META.read_text(encoding="utf-8"))
    fp_want = exit_meta["db_fingerprint"]["sha256"]
    log(f"[가드] md5 6항목 ✓ · 사전등록 blob = {D.PREREG_SHA} ✓ · 전략 blob {len(blobs)} = {R.BASE_SHA} ✓ · "
        f"tp/sl/밴드 = PREREG ✓ · sha {sha[:10]}")

    # ── L ──────────────────────────────────────────────────────────────────
    led = pd.read_csv(LEDGER_DIR / "ledger.csv", dtype=str, keep_default_na=False)
    L = led[(led["band_ok"] == "True") & (led["exit_reason"] != X.EXIT_OPEN) & (led["exit_reason"] != "")
            & (led["entry_price"] != "")].copy()
    L = L.sort_values(["strategy", "scan_date", "stock_code"], kind="mergesort").reset_index(drop=True)
    n_L = {f: int((L["strategy"] == f).sum()) for f in STRATS}
    log(f"[L] {len(L):,} · " + " · ".join(f"{SHORT[f]} {n_L[f]:,}" for f in STRATS))

    # ── DB 로드 ─────────────────────────────────────────────────────────────
    t = time.perf_counter()
    conn = R._connect()
    cal = [pd.Timestamp(x).date() for x in LD.load_trading_calendar(conn, R.PX_START, R.W_END)]
    fp = LD.db_fingerprint(conn, R.PX_START, R.W_END)
    if fp["sha256"] != fp_want:
        conn.close()
        raise SystemExit(f"🔴 DB 지문 {fp['sha256'][:12]} ≠ ③ 진단 실행 {fp_want[:12]} — 중단")
    px = LD.load_prices(conn, R.PX_START, R.W_END)
    bad_open = R.load_bad_open(conn, R.PX_START, R.W_END)
    conn.close()
    uni = LD.build_universe(px)
    mk = build_market(px, cal, bad_open)
    scan_days = [pd.Timestamp(x) for x in cal if R.W_START <= x.isoformat() <= R.W_END]
    cal_i = {x: i for i, x in enumerate(cal)}
    scan_idx = [cal_i[x.date()] for x in scan_days]
    HC, HCm1 = holiday_counts(cal)
    tm["load"] = time.perf_counter() - t
    log(f"[로드] 달력 {len(cal)}일 · 스캔일 {len(scan_days)} · DB 지문 {fp['sha256'][:12]} = ③ ✓ · px {len(px):,}행 · "
        f"종목 {mk.n_stock:,} · {tm['load']:.0f}s")

    # ── U(s,d) 재구성 · n_eligible 전수 대조 · U_b ─────────────────────────────
    t = time.perf_counter()
    diag = pd.read_csv(LEDGER_DIR / "scan_diag.csv", dtype=str, keep_default_na=False)
    want_ne = {(r.strategy, r.scan_date): int(r.n_eligible) for r in diag.itertuples()}
    pools: Dict[int, Pools] = {}
    ne_check: Dict[str, Dict[str, int]] = {}
    ub_sizes: Dict[str, List[int]] = {}
    for si, f in enumerate(STRATS):
        elig, _info = SC.eligible_for_dates(uni, adapters[f], scan_days)
        n_bad = n_tot = 0
        for d in scan_days:
            n_tot += 1
            if len(elig.get(d, ())) != want_ne.get((f, d.strftime("%Y-%m-%d")), -1):
                n_bad += 1
        ne_check[f] = dict(n=n_tot, mismatch=n_bad)
        if n_bad:
            raise SystemExit(f"🔴 |U(s,d)| ≠ scan_diag.n_eligible — {f} {n_bad}/{n_tot}일 — 중단(§5 🔒)")
        down, up = R.STRATS[f]["band"]
        pools[si] = make_pools(ub_mask(mk, elig, down, up, scan_idx))
        ub_sizes[f] = pools[si].size[scan_idx].tolist()
    tm["universe"] = time.perf_counter() - t
    log("[U] n_eligible 전수 일치 ✓ " + " · ".join(f"{SHORT[f]} {ne_check[f]['n']}일" for f in STRATS)
        + f" · {tm['universe']:.0f}s")

    # ── L 배열 · L ⊂ U_b 확인 · 에피소드 ─────────────────────────────────────
    kidx = {c: i for i, c in enumerate(mk.codes)}
    Ls: Dict[int, Dict[str, Any]] = {}
    for si, f in enumerate(STRATS):
        sub = L[L["strategy"] == f]
        d_lot = np.array([cal_i[date.fromisoformat(x)] for x in sub["scan_date"]], dtype=np.int64)
        g_lot = np.array([kidx[c] for c in sub["stock_code"]], dtype=np.int64)
        s_ep = np.zeros(len(sub), dtype=np.int64)
        _eid, first = RC.episodes(s_ep, g_lot, d_lot)
        in_ub = pools[si].M[d_lot, g_lot]
        Ls[si] = dict(idx=sub.index.to_numpy(), d=d_lot, g=g_lot, first=first, in_ub=int(in_ub.sum()),
                      ret=pd.to_numeric(sub["ret_pct"]).to_numpy(dtype=float),
                      pnl=pd.to_numeric(sub["pnl_won"]).to_numpy(dtype=float),
                      notional=pd.to_numeric(sub["notional"]).to_numpy(dtype=float),
                      groups=first_groups(d_lot, g_lot),
                      day_groups=[(int(d), np.flatnonzero(d_lot == d)) for d in np.unique(d_lot)])
        if int(in_ub.sum()) != len(sub):
            raise SystemExit(f"🔴 L 로트 {len(sub) - int(in_ub.sum())}개가 U_b 밖 — {f} — 중단(정의 불일치)")
    log("[L] L ⊂ U_b ✓ · 에피소드 첫 행 " + " · ".join(f"{SHORT[STRATS[s]]} {int(Ls[s]['first'].sum()):,}" for s in Ls))

    # ── 재현 가드(L 전체) ────────────────────────────────────────────────────
    specs = {si: spec_of(f, strategies[f], rules[f]) for si, f in enumerate(STRATS)}
    t = time.perf_counter()
    s_all = np.concatenate([np.full(len(Ls[s]["d"]), s, dtype=np.int64) for s in Ls])
    d_all = np.concatenate([Ls[s]["d"] for s in Ls])
    k_all = np.concatenate([Ls[s]["g"] for s in Ls])
    res_L = run_fast(mk, specs, s_all, d_all, k_all, HC, HCm1)
    rows_L = pd.concat([L.loc[Ls[s]["idx"]] for s in Ls])
    xd = [mk.cal[i].isoformat() if i >= 0 else "" for i in res_L["exit_i"].tolist()]
    guard = guard_compare(res_L["reason"].tolist(), xd, res_L["ret"].tolist(), rows_L["exit_reason"].tolist(),
                          rows_L["exit_date"].tolist(), pd.to_numeric(rows_L["ret_pct"]).tolist())
    guard_per = {}
    off = 0
    for s in Ls:
        n = len(Ls[s]["d"])
        sl_ = slice(off, off + n)
        guard_per[STRATS[s]] = guard_compare(res_L["reason"][sl_].tolist(), xd[sl_], res_L["ret"][sl_].tolist(),
                                             rows_L["exit_reason"].iloc[sl_].tolist(),
                                             rows_L["exit_date"].iloc[sl_].tolist(),
                                             pd.to_numeric(rows_L["ret_pct"].iloc[sl_]).tolist())
        off += n
    tm["guard"] = time.perf_counter() - t
    rate = guard["any"] / max(1, guard["n"])
    path = "vector" if rate <= GUARD_TOL else "fallback"
    log(f"[가드] 벡터화 재구현 L {guard['n']:,} 대조 · 불일치 {guard['any']} ({rate:.5%}) — reason {guard['reason']} · "
        f"date {guard['date']} · ret {guard['ret']} ⇒ 경로 = {'벡터화' if path == 'vector' else '대체(원 코드 + 캐시)'} · "
        f"{tm['guard']:.1f}s")
    mism_rows = []
    if guard["any"]:
        for i in range(len(rows_L)):
            r0 = rows_L.iloc[i]
            if (res_L["reason"][i] != r0["exit_reason"] or xd[i] != r0["exit_date"]
                    or not abs(res_L["ret"][i] - float(r0["ret_pct"])) <= RET_TOL):
                mism_rows.append(dict(strategy=r0["strategy"], scan_date=r0["scan_date"], code=r0["stock_code"],
                                      want=(r0["exit_reason"], r0["exit_date"], r0["ret_pct"]),
                                      got=(res_L["reason"][i], xd[i], res_L["ret"][i])))
                if len(mism_rows) >= 20:
                    break
        for m in mism_rows[:10]:
            log(f"   불일치 {m}")
    if a.guard_only:
        log(f"[guard-only] 끝 · {time.perf_counter() - T0:.0f}s")
        return 0

    # ── 원 코드 경로 준비(대체 경로 · 인쇄 전용 표본 대조) ─────────────────────
    book = R.build_book(px)
    env = R.Env(cal=cal, book=book, uni={}, excl={}, imp_dates={}, corp_dates={}, bad_open=set(),
                minute_fn=lambda p: set())
    probes = {si: SP.SellProbe(f, strategies[f], R.make_window_fn(book)) for si, f in enumerate(STRATS)}
    rules_i = {si: rules[f] for si, f in enumerate(STRATS)}

    # ── ④ 추출(주판 200 · 가짜 100 · 병기판 ①② 각 200) ─────────────────────────
    t = time.perf_counter()
    pools_b1: Dict[int, Pools] = {}
    for s in Ls:
        M1 = pools[s].M.copy()
        M1[Ls[s]["d"], Ls[s]["g"]] = False                                   # U_b(s,d) \ L(s,d)
        pools_b1[s] = make_pools(M1)
    draws: Dict[str, Dict[int, Dict[str, Any]]] = {b: {} for b in BOARDS}
    for b, n_r, seed in (("main", N_REP, SEED_REP), ("fake", N_FAKE, SEED_FAKE), ("b1", N_REP, SEED_REP),
                         ("b2", N_REP, SEED_REP)):
        for s in Ls:
            draws[b][s] = dict(h=np.empty((n_r, len(Ls[s]["d"])), dtype=np.int64), n_replaced=[], n_dropped=[],
                               n_short=[], dup_pi=[], dup_real=[])
        for r in range(n_r):
            rng = np.random.default_rng([seed[0], seed[1], r])
            for s in Ls:                                                     # 전략 순서 = STRATS(고정)
                Lx = Ls[s]
                if b == "b2":
                    o = draw_daily(rng, Lx["day_groups"], pools[s], len(Lx["d"]))
                else:
                    o = draw_mapped(rng, Lx["d"], Lx["g"], Lx["groups"], pools_b1[s] if b == "b1" else pools[s],
                                    mk.n_stock)
                dr = draws[b][s]
                dr["h"][r] = o["h"]
                for key in ("n_replaced", "n_dropped", "n_short", "dup_pi", "dup_real"):
                    dr[key].append(o[key])
    tm["draw"] = time.perf_counter() - t
    log(f"[추출] 4판 · {tm['draw']:.1f}s")

    # ── 청산 캐시: (전략, D, 종목) 로트마다 1회 ────────────────────────────────
    nC, nS = mk.n_cal, mk.n_stock
    keys = []
    for b in BOARDS:
        for s in Ls:
            h = draws[b][s]["h"]
            dd = np.broadcast_to(Ls[s]["d"], h.shape)
            m = h >= 0
            keys.append(np.unique((s * nC + dd[m]) * nS + h[m]))
    ukeys = np.unique(np.concatenate(keys))
    u_s, rem = np.divmod(ukeys, nC * nS)
    u_d, u_k = np.divmod(rem, nS)
    n_cache = len(ukeys)
    pilot = np.array([mk.cal[int(x)].strftime("%Y-%m") == PILOT_MONTH for x in u_d])
    log(f"[캐시] 고유 로트 {n_cache:,} · 파일럿({PILOT_MONTH}) {int(pilot.sum()):,}")
    runner = ((lambda s_, d_, k_: run_fast(mk, specs, s_, d_, k_, HC, HCm1)) if path == "vector"
              else (lambda s_, d_, k_: run_orig(mk, env, probes, rules_i, s_, d_, k_)))
    t = time.perf_counter()
    res_p = runner(u_s[pilot], u_d[pilot], u_k[pilot])
    secs_pilot = time.perf_counter() - t
    per_lot = secs_pilot / max(1, int(pilot.sum()))
    elapsed = time.perf_counter() - T0
    projected = elapsed + per_lot * (n_cache - int(pilot.sum())) + 120.0      # + 통계·출력 여유 120s
    time_hold = projected + SECS_STEP3 > 3600.0
    log(f"[파일럿] {int(pilot.sum()):,} 로트 {secs_pilot:.1f}s ({per_lot * 1e3:.2f}ms/로트) · 예상 총 "
        f"{projected:.0f}s + ③ {SECS_STEP3:.0f}s ⇒ 1시간 {'초과 🔴 판별 보류' if time_hold else '이내 ✓'}")
    tm["pilot"] = secs_pilot
    res = {k: np.empty(n_cache, dtype=v.dtype) for k, v in res_p.items()}
    for k in res:
        res[k][pilot] = res_p[k]
    if not time_hold:
        t = time.perf_counter()
        rest = ~pilot
        res_r = runner(u_s[rest], u_d[rest], u_k[rest])
        for k in res:
            res[k][rest] = res_r[k]
        tm["sim"] = time.perf_counter() - t
        log(f"[청산] {int(rest.sum()):,} 로트 {tm['sim']:.0f}s")

    # ── 인쇄 전용: 무작위 로트 표본 원 코드 대조(벡터화 경로일 때) ─────────────────
    sample_chk: Dict[str, Any] = {}
    if path == "vector" and not time_hold:
        t = time.perf_counter()
        rng_s = np.random.default_rng(list(SEED_SAMPLE))
        pick = np.sort(rng_s.choice(n_cache, size=min(SAMPLE_N, n_cache), replace=False))
        ro = run_orig(mk, env, probes, rules_i, u_s[pick], u_d[pick], u_k[pick])
        xo = [mk.cal[i].isoformat() if i >= 0 else "" for i in ro["exit_i"].tolist()]
        xf = [mk.cal[i].isoformat() if i >= 0 else "" for i in res["exit_i"][pick].tolist()]
        ret_o = [0.0 if (r == X.EXIT_OPEN) else v for r, v in zip(ro["reason"].tolist(), ro["ret"].tolist())]
        ret_f = [0.0 if (r == X.EXIT_OPEN) else v for r, v in zip(res["reason"][pick].tolist(), res["ret"][pick].tolist())]
        sample_chk = guard_compare(res["reason"][pick].tolist(), xf, ret_f, ro["reason"].tolist(), xo, ret_o)
        sample_chk["secs"] = round(time.perf_counter() - t, 1)
        log(f"[표본 대조 · 인쇄만] 무작위 로트 {sample_chk['n']:,} 원 코드 vs 벡터화 불일치 {sample_chk['any']} · "
            f"{sample_chk['secs']}s")

    finished_sim = time.perf_counter()
    out = dict(sha=sha, started=started, md5s=md5s, prereg_blob=prereg_blob, fp=fp, n_L=n_L, ne_check=ne_check,
               guard=guard, guard_per=guard_per, guard_rate=rate, path=path, mism_rows=mism_rows, n_cache=n_cache,
               pilot=dict(month=PILOT_MONTH, n=int(pilot.sum()), secs=round(secs_pilot, 2),
                          ms_per_lot=round(per_lot * 1e3, 3), projected_s=round(projected, 1),
                          step3_s=SECS_STEP3, over=bool(time_hold)),
               sample_chk=sample_chk, ub_sizes={f: dict(min=int(min(v)), median=float(np.median(v)), max=int(max(v)))
                                                for f, v in ub_sizes.items()},
               first_rows={STRATS[s]: int(Ls[s]["first"].sum()) for s in Ls},
               n_codes={STRATS[s]: int(len(np.unique(Ls[s]["g"]))) for s in Ls})

    if time_hold:
        verdict = {f: dict(label=LAB_HOLD_TIME) for f in STRATS}
        out.update(verdict=verdict, fake=None, stats=None, boards=None, draws_summary=None)
        return finish(out, out_dir, T0, tm)

    # ── 표본 값 배열 ─────────────────────────────────────────────────────────
    def lookup(b: str, s: int) -> Dict[str, np.ndarray]:
        h = draws[b][s]["h"]
        dd = np.broadcast_to(Ls[s]["d"], h.shape)
        key = (s * nC + dd) * nS + np.maximum(h, 0)
        j = np.searchsorted(ukeys, key)
        j = np.minimum(j, n_cache - 1)
        valid = (h >= 0) & (ukeys[j] == key)
        closed = valid & (res["reason"][j] != X.EXIT_OPEN)
        ret = np.where(closed, res["ret"][j], np.nan)
        E = mk.O[dd + 1, np.maximum(h, 0)]
        xp = np.where(closed, res["xpx"][j], np.nan)
        raw = np.floor(1_000_000.0 / E)
        qty = np.where(raw >= 1, raw, 1.0)
        pnl = np.round(qty * (xp - E))
        net_won = pnl - qty * E * COST / 100.0
        return dict(ret=ret, closed=closed, valid=valid, net_won=net_won, h=h)

    # ── 룰 쪽 ─────────────────────────────────────────────────────────────────
    stats: Dict[str, Any] = {}
    main_vals: Dict[int, Dict[str, np.ndarray]] = {}
    pool_parts: Dict[int, Dict[str, np.ndarray]] = {}
    for s in Ls:
        f = STRATS[s]
        Lx = Ls[s]
        yL = Lx["ret"] - COST
        net_L = Lx["pnl"] - Lx["notional"] * COST / 100.0
        mv = lookup("main", s)
        main_vals[s] = mv
        rep_mean = np.nanmean(mv["ret"] - COST, axis=1)
        rep_win = np.array([np.mean(v[np.isfinite(v)] > 0) for v in mv["ret"]])
        rep_net = np.array([np.nanmean(np.where(c, n, np.nan)) for c, n in zip(mv["closed"], mv["net_won"])])
        T = float(yL.mean() - np.median(rep_mean))
        fr = Lx["first"]
        y0 = (mv["ret"][:, fr] - COST).ravel()
        c0 = mv["h"][:, fr].ravel()
        ok0 = np.isfinite(y0)
        pool_parts[s] = dict(y0=y0[ok0], c0=c0[ok0], w0=np.full(int(ok0.sum()), 1.0 / N_REP))
        tst = p2_binary(yL[fr], Lx["g"][fr], pool_parts[s]["y0"], pool_parts[s]["c0"], pool_parts[s]["w0"])
        stats[f] = dict(T=T, rule_mean=float(yL.mean()), rand_median=float(np.median(rep_mean)),
                        rand_q=[float(np.percentile(rep_mean, q)) for q in (2.5, 50, 97.5)],
                        rule_win=float(np.mean(Lx["ret"] > 0)), rand_win_median=float(np.median(rep_win)),
                        rule_net_won=float(net_L.mean()), rand_net_won_median=float(np.median(rep_net)),
                        n_L=int(len(yL)), n_first=int(fr.sum()), n_pool=int(ok0.sum()),
                        n_open_excl=int((mv["valid"] & ~mv["closed"]).sum()),
                        n_open_excl_first=int((~ok0).sum()), **tst, mde=MDE_K * tst["se"])
    log("[주판] " + " · ".join(f"{SHORT[f]} T {stats[f]['T']:+.3f}%p" for f in STRATS))

    # ── ⑤ 가짜 룰 거부율 ─────────────────────────────────────────────────────
    t = time.perf_counter()
    fake_rows: List[Dict[str, Any]] = []
    for s in Ls:
        fv = lookup("fake", s)
        fr = Ls[s]["first"]
        pp = pool_parts[s]
        for j in range(N_FAKE):
            y1 = fv["ret"][j, fr] - COST
            c1 = fv["h"][j, fr]
            ok1 = np.isfinite(y1)
            tj = p2_binary(y1[ok1], c1[ok1], pp["y0"], pp["c0"], pp["w0"])
            fake_rows.append(dict(j=j, strategy=STRATS[s], delta=tj["delta"], se=tj["se"], p_up=tj["p_up"],
                                  p_down=tj["p_down"], n1=int(ok1.sum())))
    ps = [r[k] for r in fake_rows for k in ("p_up", "p_down")]
    n_rej = sum(1 for p in ps if p == p and p < FAKE_P)
    fake_rate = n_rej / len(ps)
    fake_fail = fake_rate > FAKE_MAX
    fake = dict(n_p=len(ps), n_rej=n_rej, rate=fake_rate, fail=fake_fail,
                per={f"{STRATS[s]}|{k}": sum(1 for r in fake_rows if r["strategy"] == STRATS[s] and r[k] < FAKE_P)
                     for s in Ls for k in ("p_up", "p_down")},
                two_sided=sum(1 for r in fake_rows if 2 * min(r["p_up"], r["p_down"]) < FAKE_P) / len(fake_rows),
                p05=sum(1 for p in ps if p == p and p < 0.05) / len(ps))
    tm["fake"] = time.perf_counter() - t
    log(f"[가짜 룰] 한쪽 p {len(ps)}개 중 p<{FAKE_P} {n_rej} = {fake_rate:.3f} ⇒ "
        f"{'> 0.16 🔴 전 전략 판별 보류' if fake_fail else '≤ 0.16 판정 진행'}")

    # ── ⑥ 판정 ───────────────────────────────────────────────────────────────
    verdict: Dict[str, Dict[str, Any]] = {}
    pmap = {(f, k): stats[f][k] for f in STRATS for k in ("p_up", "p_down")}
    hol = holm(pmap)
    for f in STRATS:
        st = stats[f]
        if fake_fail:
            lab = LAB_HOLD_FAKE
        else:
            lab = label(st["T"], hol[(f, "p_up")], hol[(f, "p_down")], st["mde"])
        verdict[f] = dict(label=lab, holm_up=hol[(f, "p_up")], holm_down=hol[(f, "p_down")],
                          mde_le=bool(st["mde"] <= T_MIN))
    log("[판정] " + " · ".join(f"{SHORT[f]} {verdict[f]['label']}" for f in STRATS))

    # ── 병기판 ①② (인쇄만) ─────────────────────────────────────────────────
    boards: Dict[str, Dict[str, Any]] = {}
    for b in ("b1", "b2"):
        boards[b] = {}
        for s in Ls:
            f = STRATS[s]
            v = lookup(b, s)
            rep_mean = np.nanmean(v["ret"] - COST, axis=1)
            fr = Ls[s]["first"]
            y0 = (v["ret"][:, fr] - COST).ravel()
            c0 = v["h"][:, fr].ravel()
            ok0 = np.isfinite(y0)
            tst = p2_binary(Ls[s]["ret"][fr] - COST, Ls[s]["g"][fr], y0[ok0], c0[ok0],
                            np.full(int(ok0.sum()), 1.0 / N_REP))
            rep_net = np.array([np.nanmean(np.where(c, n, np.nan)) for c, n in zip(v["closed"], v["net_won"])])
            rep_win = np.array([np.mean(x[np.isfinite(x)] > 0) for x in v["ret"]])
            boards[b][f] = dict(T=float(stats[f]["rule_mean"] - np.median(rep_mean)),
                                rand_median=float(np.median(rep_mean)), rand_win_median=float(np.median(rep_win)),
                                rand_net_won_median=float(np.median(rep_net)), p_up=tst["p_up"], p_down=tst["p_down"],
                                se=tst["se"], n_open_excl=int((v["valid"] & ~v["closed"]).sum()),
                                n_dropped=int((~v["valid"]).sum()))

    # ── 추출 요약 · 반복별 기록 ─────────────────────────────────────────────
    dsum: Dict[str, Dict[str, Any]] = {}
    rep_rows: List[Dict[str, Any]] = []
    for b in BOARDS:
        dsum[b] = {}
        for s in Ls:
            f = STRATS[s]
            dr = draws[b][s]
            dsum[b][f] = {k: dict(sum=int(np.sum(dr[k])), mean=float(np.mean(dr[k])), min=int(np.min(dr[k])),
                                  max=int(np.max(dr[k]))) for k in ("n_replaced", "n_dropped", "n_short", "dup_pi",
                                                                     "dup_real")}
            v = main_vals[s] if b == "main" else lookup(b, s)
            for r in range(dr["h"].shape[0]):
                x = v["ret"][r]
                okr = np.isfinite(x)
                rep_rows.append(dict(board=b, rep=r, strategy=f, n_lots=int(okr.sum()),
                                     n_open_excl=int((v["valid"][r] & ~v["closed"][r]).sum()),
                                     mean_net_pct=round(float(np.mean(x[okr] - COST)), 6) if okr.any() else "",
                                     win_rate=round(float(np.mean(x[okr] > 0)), 6) if okr.any() else "",
                                     net_won_mean=int(round(float(np.nanmean(np.where(v["closed"][r], v["net_won"][r],
                                                                                      np.nan))))) if okr.any() else "",
                                     n_replaced=dr["n_replaced"][r], n_dropped=dr["n_dropped"][r],
                                     dup_pi=dr["dup_pi"][r], dup_real=dr["dup_real"][r]))
    tm["stats"] = time.perf_counter() - finished_sim
    cache_reason = {k: int(v) for k, v in pd.Series(res["reason"]).value_counts().items()}
    out.update(verdict=verdict, fake=fake, stats=stats, boards=boards, draws_summary=dsum, cache_reason=cache_reason,
               holm_all=hol)
    _write_csv(out_dir / "random_entry_reps.csv", rep_rows)
    _write_csv(out_dir / "random_entry_fakes.csv", fake_rows)
    return finish(out, out_dir, T0, tm)


def _write_csv(p: Path, rows: List[Dict[str, Any]]) -> None:
    if not rows:
        return
    with open(p, "w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0]), lineterminator="\n")
        w.writeheader()
        w.writerows(rows)


def _clean(o: Any) -> Any:
    if isinstance(o, dict):
        return {str(k) if not isinstance(k, tuple) else "|".join(map(str, k)): _clean(v) for k, v in o.items()}
    if isinstance(o, (list, tuple)):
        return [_clean(v) for v in o]
    if isinstance(o, (np.integer,)):
        return int(o)
    if isinstance(o, (np.floating, float)):
        return None if not np.isfinite(o) else float(o)
    if isinstance(o, (np.bool_,)):
        return bool(o)
    return o


def finish(out: Dict[str, Any], out_dir: Path, T0: float, tm: Dict[str, float]) -> int:
    out["finished"] = datetime.now().isoformat(timespec="seconds")
    out["secs_total"] = round(time.perf_counter() - T0, 1)
    out["secs"] = {k: round(v, 2) for k, v in tm.items()}
    meta = dict(prereg=f"{D.PREREG} ({D.PREREG_SHA})", prereg_blob=out["prereg_blob"], git_sha=out["sha"],
                started=out["started"], finished=out["finished"], secs_total=out["secs_total"], secs=out["secs"],
                secs_step3=SECS_STEP3, secs_step3_plus_this=round(SECS_STEP3 + out["secs_total"], 1),
                input_md5=out["md5s"], db_fingerprint=dict((k, v) for k, v in out["fp"].items() if k != "per_stock"),
                db_fingerprint_same_as_step3=True,
                seeds=dict(rep=f"default_rng([{SEED_REP[0]}, {SEED_REP[1]}, r]) r=0..{N_REP - 1}",
                           fake=f"default_rng([{SEED_FAKE[0]}, {SEED_FAKE[1]}, j]) j=0..{N_FAKE - 1}",
                           board1=f"= rep 시드(해석 기록 I9)", board2=f"= rep 시드(해석 기록 I9)",
                           sample_check=list(SEED_SAMPLE)),
                n_rep=N_REP, n_fake=N_FAKE, path=out["path"], guard=out["guard"], guard_per=out["guard_per"],
                guard_rate=out["guard_rate"], n_cache_lots=out["n_cache"], pilot=out["pilot"],
                sample_check=out["sample_chk"], n_L=out["n_L"], n_eligible_check=out["ne_check"],
                first_rows=out["first_rows"], n_codes=out["n_codes"], ub_sizes=out["ub_sizes"],
                mde_k=MDE_K, z_holm1=Z_HOLM1, z_power=Z_POWER,
                fake=out.get("fake"), verdict=out["verdict"], stats=out.get("stats"), boards=out.get("boards"),
                draws_summary=out.get("draws_summary"), cache_reason=out.get("cache_reason"),
                outputs=["run_random_entry.py", "RESULTS_random_entry.md", "run_meta_random_entry.json",
                         "random_entry_reps.csv", "random_entry_fakes.csv", "run_random_entry.log"])
    (out_dir / "run_meta_random_entry.json").write_text(json.dumps(_clean(meta), ensure_ascii=False, indent=1),
                                                         encoding="utf-8")
    (out_dir / "RESULTS_random_entry.md").write_text(render(out), encoding="utf-8")
    log(f"[끝] {out['secs_total']:.0f}s (+ ③ {SECS_STEP3:.0f}s = {SECS_STEP3 + out['secs_total']:.0f}s) → "
        f"{out_dir / 'RESULTS_random_entry.md'}")
    return 0


# ════════════════════════════════════════════════════════════════════════════
# 6. 결과 문서
# ════════════════════════════════════════════════════════════════════════════
INTERP = [
    "I1 **L 재계수** — 원장 `band_ok=True ∧ exit_reason ∉ {open, 빈칸} ∧ entry_price 있음`(③ 진단 `run_exit_diag.py` 와 같은 거르기). "
    "정렬 = (전략, scan_date, 종목) · 이 순서가 로트 순(난수 소비·대체 추출 순서)이다.",
    "I2 **U_b** — `U(s,d)` 중 D 봉(밴드 기준가 = D 종가 · 원장 `run.lot_row` 의 ref)이 있고, D+1 이 달력에 있고, D+1 봉이 있고, "
    "원본 시가가 결측/≤0 이 아니고(`run.load_bad_open`), `lo ≤ open ≤ hi`(`run.band_ok` 식 · 경계 포함 · None 쪽 열림)인 종목. "
    "D 봉이 없는 적격 종목은 밴드 기준가가 없어 U_b 밖이다. L 의 모든 로트가 U_b 안인지 실행 시 확인(아니면 중단).",
    "I3 **π 비복원 범위** — 「g 의 L 첫 등장일 U_b 에서 비복원 추출」을 **첫 등장일이 같은 g 들끼리** 비복원으로 읽었다"
    "(문서 괄호 「비복원이라도 대체 추출·날짜 차로 생길 수 있음」 = 첫 등장일이 다른 g 끼리는 독립 추출이라 같은 h 가 나올 수 있다). "
    "그룹 안 g 순서 = 종목 코드 오름차순 · 그룹 순서 = 첫 등장일 오름차순 · `rng.choice(U_b 정렬 목록, k, replace=False)`.",
    "I4 **대체 추출** — 그날 π(g) ∉ U_b(s,d) 인 로트만 그날 U_b(s,d) 에서 균등 1개(`rng.integers`) · 대체된 h 는 그날만 쓴다(π 불변). "
    "π 추출 뒤 로트 순으로 한 번에 뽑는다. 매핑 중복 = Σ_h(그 h 로 간 서로 다른 g 수 − 1) — π 단계(`dup_pi`)와 대체 반영 뒤(`dup_real`) 둘 다 인쇄.",
    "I5 **난수** — 반복 r 마다 `default_rng([20261002, 2, r])` 하나를 전략 순서(ma20 → minervini → daytrading)로 이어 쓴다. "
    "r·j 는 0부터(r = 0..199 · j = 0..99). 가짜 룰 j 는 주판과 같은 추출 절차에 `default_rng([20261002, 3, j])`.",
    "I6 **무작위 로트 모집단** — L 과 같은 거르기를 무작위 쪽에도 적용: 2026-09-23 까지 안 닫힌(`open`) 무작위 로트는 뺀다(건수 인쇄). "
    "밴드·시가는 U_b 가 이미 보장.",
    "I7 **MDE** — 「주 도구 · 80% · Holm 문턱 기준 · FD1 (마-D) 방식」 = FD1 의 `MDE = Z × SD(통계량)`(Z = 유의 문턱 z + 검정력 z) 에서 "
    f"유의 문턱을 **Holm m=6 1단계 한쪽 α/6** 로 둔 것: `MDE = (z_(1−0.05/6) + z_0.80) × SE = ({Z_HOLM1:.4f} + {Z_POWER:.4f}) × SE "
    f"= {MDE_K:.4f} × SE`. SE = 주판 P2 이진 비교의 CR1 SE(도구 교정 §7 「P2 도구 = CR1 SE」). 1단계(가장 엄한 문턱)는 교정 문서 §6 "
    "「Holm m=14 1단계 = 3.75 × SD_null」 선례를 따랐다.",
    "I8 **P2 이진 비교** — 룰 쪽 = L 의 에피소드 첫 행(`run_calib.episodes` · 같은 전략·종목 · 달력 순번 차 > 1 이면 새 에피소드 · L 로트로 계산). "
    "무작위 쪽 = 같은 «위치»(첫 행 로트)의 무작위 로트 — 종목 대응 π 로 에피소드의 모든 날에 같은 h 가 오므로 룰 에피소드 구조를 그대로 물려받는다 · "
    "200 반복 전부 풀 · 로트 가중 1/200 · 미청산 무작위 로트는 뺀다. 클러스터 = **실제 종목 코드**(룰 = g · 무작위 = h · 같은 코드는 룰·무작위 합쳐 한 클러스터). "
    "CR1 = G/(G−1)·(N−1)/(N−K)·Σψ² · N = n1 + Σw(가중 로트 수) · K = 2. p_up = Φ(−Δ/SE) · p_down = Φ(Δ/SE). "
    "Δ(첫 행 가중 평균 차)는 p 에만 쓰고 라벨 크기 조건은 문서의 T(전 로트 · 반복 평균의 중앙값)로 판단한다.",
    "I9 **병기판 시드** — 문서에 병기판 시드가 없어 주판과 같은 `default_rng([20261002, 2, r])` 를 판마다 새로 만들어 썼다(「같은 규칙」). "
    "① = 추출 집합 `U_b(s,d) \\ L(s,d)`(그날 L 로트 종목 제외 · π·대체 모두) · ② = 날마다 그날 L 로트 수만큼 U_b(s,d) 에서 비복원(로트 순 배정). "
    "병기판 p 는 인쇄만(Holm·라벨 없음).",
    "I10 **가짜 룰 거부율** — 가짜 룰 j 를 «룰 쪽»에 두고 주판 200 반복 풀과 같은 P2 이진 비교 → 전략 3 × 한쪽 p 2 = 가짜당 6개 · "
    "**600개 한쪽 p 중 p<0.10 비율**을 판정값으로 썼다(명목 0.10 · 문서의 p 가 한쪽 p 6개라서). 양측 `2·min<0.10` 비율·`p<0.05` 비율·"
    "전략×방향별 건수는 인쇄만.",
    "I11 **청산 재구현** — `exitsim8.simulate_lot(BASIS_D_OPEN)` 의 하루 순서([보유기간(달력 k ≥ max_hold) → 갭 익절] → 데이터 청산 → 갭 손절 → "
    "장중 터치 · 동시 손절 우선 · 결측 봉 건너뜀 · 결측 중 보유기간 도달이면 다음 봉 시가) + `SellProbe`(창 = px 행 `[day−120일, day)` · "
    "`len < get_min_data_length` 면 없음 · 보유일 = 전략 코드 식(ma20·daytrading `count_trading_days_between−1` · minervini "
    "`_trading_days_elapsed`, 휴장 = `utils.korean_holidays.is_holiday`) ≥ `_max_hold_days` ⇒ `max_hold` · ma20 수익 중 종가 < MA20 ⇒ "
    "`trail_ma`). MA20 은 누적합으로 계산하고 종가와 1e-9 이내로 붙으면 원 함수(`pandas rolling`)로 다시 잰다. 비교식은 원 코드와 같은 "
    "수익률 식(`(px − E)/E`).",
    "I12 **재현 가드 대조** — L 전 로트의 (exit_reason, exit_date, ret_pct(|차| ≤ 1e-9 %)) 셋 중 하나라도 다르면 불일치. "
    "추가로 **인쇄 전용** 무작위 로트 표본(캐시에서 비복원 3,000개 · 시드 `[20261002, 9, 0]`)을 원 코드(`simulate_lot` + `SellProbe`)로 "
    "다시 돌려 대조했다(L 에 없는 경로 확인용 · 경로 선택에 쓰지 않음).",
    "I13 **파일럿·시간** — 캐시 고유 로트 중 scan_date 2025-03(③ 과 같은 달)을 먼저 돌려 로트당 시간 × 나머지 + 지금까지 경과 + 여유 120s "
    "+ ③ 31.2s 가 1시간을 넘으면 3전략 모두 판별 보류(부분 판정 없음). 경로(벡터화/대체)와 무관하게 같은 규칙.",
    "I14 **로트당 net(원)** — 룰 = 원장 `pnl_won − notional×0.25%` 평균 · 무작위 = 같은 식(`qty = max(1, floor(1,000,000/E))` · "
    "`pnl = round(qty×(청산가−E))`)의 반복 평균의 중앙값. 인쇄만.",
]

LIMITS = [
    "> 일봉 근사(봉 안 순서 · 장중 청산 · 09:05 규약) — 분봉 재분류는 2025-02-24 이후 봉만 · 시가 밴드 근사 · gross 원장에 비용 0.25% 를 "
    "산술로만 얹음(세금·호가 미끄러짐 미반영).",
    "> W=10 은 전략 max_hold(10/20/50)와 다르다 — 「보유를 더 했으면」이 아니라 «청산 직후 가격 경로의 대칭성»만 잰다.",
    "> 무작위 대조는 «같은 유니버스·같은 날·같은 밴드» 조건부다 — 유니버스 필터 자체의 가치는 재지 않는다. 원장은 생존자 유니버스 · "
    "빈티지 보정 없음(원장 PREREG §8 승계).",
]


def render(o: Dict[str, Any]) -> str:
    A: List[str] = []
    a = A.append
    a("# 무작위 진입 대조군 — 결과 (§5)")
    a("")
    a(f"- 규범: `{D.PREREG}`(🔒 동결 `{D.PREREG_SHA}` · blob `{o['prereg_blob'][:10]}` 일치) §5~§8 · 코드 `exit_diag/run_random_entry.py` · "
      f"git `{o['sha'][:10]}`")
    a("- 주 도구(도구 교정 `tool_calibration/RESULTS.md` · 커밋 `9d25293`) = **K2 = P3 + P2** → §5 p 는 **P2**(에피소드 첫 행 · 종목 클러스터 "
      "CR1 · 정규 근사)를 이진 비교에 적용(분위 부품 P3 는 이진이라 안 씀 · 문서 명시).")
    a("- 🔴 **라이브 룰 변경 근거가 아니다**(§7-6) · 「판별 보류」는 「차이 없음」이 아니다 · 「룰 > 무작위」는 「후보 순위 특징이 있다」가 아니다(§7-5).")
    a(f"- 실행 {o['started']} → {o['finished']} · **{o['secs_total']:.0f}s** (+ ③ 진단 {SECS_STEP3:.0f}s = "
      f"{SECS_STEP3 + o['secs_total']:.0f}s / 상한 3,600s)")
    a("")
    a("## 1. 입력 · 가드")
    a("")
    a(f"- 입력 md5: ledger `{o['md5s']['ledger_worktree']}` · scan_diag `{o['md5s']['scan_diag_worktree']}` (동결값·보관소 파일·MD5SUMS 6항목 일치)")
    a(f"- DB 지문 sha256 `{o['fp']['sha256'][:16]}…` = ③ 진단 `exit_diag/run_meta.json` 값 ✓ · 전략 파일 blob = `{R.BASE_SHA}` ✓ · "
      "tp/sl/max_hold·밴드 = 원장 PREREG ✓")
    a("- **L 재계수**: " + " · ".join(f"{SHORT[f]} {o['n_L'][f]:,}(기대 {D.EXPECT_L[f]:,}{' ✓' if o['n_L'][f] == D.EXPECT_L[f] else ' ≠'})"
                                        for f in STRATS) + f" = {sum(o['n_L'].values()):,}")
    a("- **|U(s,d)| = scan_diag.n_eligible 전수 대조**: " + " · ".join(
        f"{SHORT[f]} {o['ne_check'][f]['n']}일 중 불일치 {o['ne_check'][f]['mismatch']}" for f in STRATS) + " ⇒ **전수 일치**")
    a("- |U_b(s,d)| (스캔 617일 · 최소/중앙/최대): " + " · ".join(
        f"{SHORT[f]} {o['ub_sizes'][f]['min']}/{o['ub_sizes'][f]['median']:g}/{o['ub_sizes'][f]['max']}" for f in STRATS)
      + " · L ⊂ U_b ✓(전 로트)")
    a("- 에피소드 첫 행(P2 표본) / L 고유 종목: " + " · ".join(
        f"{SHORT[f]} {o['first_rows'][f]:,} / {o['n_codes'][f]:,}" for f in STRATS))
    a("")
    a("## 2. 사용 경로 · 재현 가드 · 캐시")
    a("")
    g = o["guard"]
    a(f"- 재현 가드(벡터화 재구현 → L 전체 {g['n']:,} 로트 · 원장 exit_reason·exit_date·ret_pct 대조): **불일치 {g['any']} "
      f"({o['guard_rate']:.4%})** — reason {g['reason']} · date {g['date']} · ret {g['ret']} · 허용 0.1% ⇒ **사용 경로 = "
      f"{'벡터화' if o['path'] == 'vector' else '대체(원 코드 `simulate_lot` + `SellProbe` · 로트별 1회 캐시)'}**")
    a("  - 전략별: " + " · ".join(f"{SHORT[f]} {o['guard_per'][f]['any']}/{o['guard_per'][f]['n']:,}" for f in STRATS))
    a(f"- 캐시 = (전략, 날짜, 종목) 로트마다 청산 1회 · **고유 로트 {o['n_cache']:,}**(4판 전 반복 합집합) · 반복은 캐시에서 인덱스 추출만")
    p = o["pilot"]
    a(f"- 1개월 파일럿(scan_date {p['month']}): {p['n']:,} 로트 {p['secs']}s ({p['ms_per_lot']}ms/로트) · 예상 총 {p['projected_s']:.0f}s + "
      f"③ {p['step3_s']:.0f}s ⇒ 1시간 {'**초과** → 3전략 모두 판별 보류' if p['over'] else '이내'}")
    if o.get("sample_chk"):
        sc = o["sample_chk"]
        a(f"- 인쇄 전용 표본 대조(해석 기록 I12): 무작위 로트 {sc['n']:,}개 원 코드 vs 벡터화 **불일치 {sc['any']}** "
          f"(reason {sc['reason']} · date {sc['date']} · ret {sc['ret']}) · {sc['secs']}s")
    if o.get("cache_reason"):
        a("- 캐시 로트 청산 사유 분포: " + " · ".join(f"`{k}` {v:,}" for k, v in o["cache_reason"].items()))
    a("")
    if o.get("fake") is None:
        a("## 3. 판정")
        a("")
        for f in STRATS:
            a(f"- {f}: **{o['verdict'][f]['label']}**")
        a("")
        return "\n".join(A + interp_tail(o)) + "\n"
    fk = o["fake"]
    a("## 3. ⑤ 가짜 룰 거부율 (판정 «전»)")
    a("")
    a(f"- 가짜 룰 {N_FAKE}개(주판과 같은 종목 단위 대응 추출 · 시드 `default_rng([20261002, 3, j])`) × 3전략 × 한쪽 p 2 = **{fk['n_p']}개 "
      f"한쪽 p 중 p<0.10 = {fk['n_rej']} → 거부율 {fk['rate']:.3f}** ⇒ "
      + ("**> 0.16 → 전 전략 「판별 보류(도구가 이 비교에서 낙관적)」 고정 · 판정 단계 생략**" if fk["fail"]
         else "**≤ 0.16 → 판정 진행**"))
    a("- 인쇄만: 전략×방향별 p<0.10 건수(각 100개 중) — " + " · ".join(
        f"{SHORT[k.split('|')[0]]} {k.split('|')[1]} {v}" for k, v in fk["per"].items()))
    a(f"- 인쇄만: 양측 `2·min(p_up,p_down) < 0.10` 비율 {fk['two_sided']:.3f}(300개) · 한쪽 p<0.05 비율 {fk['p05']:.3f}(600개)")
    a("")
    a("## 4. ⑥ 전략별 판정 (주판 · 종목 단위 대응 · 반복 200)")
    a("")
    a(f"- T = mean(ret_pct − 0.25 | L) − 중앙값_r mean(ret_pct − 0.25 | 무작위 r) (%p) · p = P2 이진 비교(해석 기록 I8) · "
      f"Holm m=6 α 0.05(한쪽 p 6개) · MDE = {MDE_K:.4f} × SE(해석 기록 I7) · 라벨 문턱 0.25%p")
    a("")
    a("| 전략 | T (%p) | 룰 평균 | 무작위 중앙값 [2.5%, 97.5%] | Δ 첫 행 | SE | p_up | p_down | Holm(up/down) | MDE | 라벨 |")
    a("|---|---|---|---|---|---|---|---|---|---|---|")
    for f in STRATS:
        s, v = o["stats"][f], o["verdict"][f]
        a(f"| {SHORT[f]} | **{_f(s['T'])}** | {_f(s['rule_mean'])} | {_f(s['rand_median'])} [{_f(s['rand_q'][0])}, "
          f"{_f(s['rand_q'][2])}] | {_f(s['delta'])} | {s['se']:.3f} | {_p(s['p_up'])} | {_p(s['p_down'])} | "
          f"{'통과' if v['holm_up'] else '—'} / {'통과' if v['holm_down'] else '—'} | {s['mde']:.3f}"
          f"{' ≤ 0.25' if v['mde_le'] else ' > 0.25'} | **{v['label']}** |")
    a("")
    a("| 전략 | L 로트 | 첫 행(n1) | 무작위 풀(첫 행 · 200반복) | 클러스터 G | 룰 승률 | 무작위 승률(중앙값) | 룰 로트당 net(원) | 무작위 로트당 net(원 · 중앙값) | 무작위 미청산 제외(전 반복) |")
    a("|---|---|---|---|---|---|---|---|---|---|")
    for f in STRATS:
        s = o["stats"][f]
        a(f"| {SHORT[f]} | {s['n_L']:,} | {s['n_first']:,} | {s['n_pool']:,} | {s['G']:,} | {s['rule_win']:.3f} | "
          f"{s['rand_win_median']:.3f} | {_won(s['rule_net_won'])} | {_won(s['rand_net_won_median'])} | {s['n_open_excl']:,} |")
    a("")
    a("- 라벨 규칙(결과 전 고정): 룰 > 무작위 = p_up Holm 통과 ∧ T ≥ +0.25 · 룰 < 무작위 = p_down Holm 통과 ∧ T ≤ −0.25 · "
      "차이 없음 = |T| < 0.25 ∧ MDE ≤ 0.25 · 판별 보류 = 그 밖 전부(「못 재봤다」).")
    a("- 해석(문서 §5 🔒 문언): 「차이 없음」 ⇒ 후보 층 결론 강화 · 「룰 > 무작위」 ⇒ 후보 층 유지(룰 자체엔 정보)·추가 파기 없이 다른 층으로 · "
      "「룰 < 무작위」 ⇒ 인쇄 + 별도 결정 문항 · 어느 쪽도 라이브 변경 근거 아님.")
    a("")
    a("## 5. 병기판 (인쇄만 · Holm·라벨 없음)")
    a("")
    a("| 판 | 전략 | T (%p) | 무작위 중앙값 | 무작위 승률 | 무작위 로트당 net(원) | p_up | p_down | 미청산 제외 | 추출 불가 |")
    a("|---|---|---|---|---|---|---|---|---|---|")
    for b, name in (("b1", "① L 밖"), ("b2", "② 날짜 독립")):
        for f in STRATS:
            s = o["boards"][b][f]
            a(f"| {name} | {SHORT[f]} | {_f(s['T'])} | {_f(s['rand_median'])} | {s['rand_win_median']:.3f} | "
              f"{_won(s['rand_net_won_median'])} | {_p(s['p_up'])} | {_p(s['p_down'])} | {s['n_open_excl']:,} | {s['n_dropped']:,} |")
    a("")
    a("## 6. 매핑 중복 · 대체 추출 (반복당 평균 [최소, 최대] · 합)")
    a("")
    a("| 판 | 전략 | 대체 추출 | π 중복(dup_pi) | 대체 뒤 중복(dup_real) | 집합 비어 탈락 | π 비복원 불가(복원 추출) |")
    a("|---|---|---|---|---|---|---|")
    for b in BOARDS:
        for f in STRATS:
            d = o["draws_summary"][b][f]

            def c(k: str) -> str:
                return f"{d[k]['mean']:.1f} [{d[k]['min']}, {d[k]['max']}] · {d[k]['sum']:,}"
            a(f"| {BOARDS[b]} | {SHORT[f]} | {c('n_replaced')} | {c('dup_pi')} | {c('dup_real')} | {c('n_dropped')} | {c('n_short')} |")
    a("")
    return "\n".join(A + interp_tail(o)) + "\n"


def interp_tail(o: Dict[str, Any]) -> List[str]:
    A = ["## 7. 해석 기록 (문서가 정하지 않은 구현 선택 · 결과를 보기 «전»에 코드에 고정)", ""]
    A += [f"{i + 1}. {x}" for i, x in enumerate(INTERP)]
    A += ["", "## 8. 문서와 다르게 한 것", "",
          "- 🔒 항목: 없음(반복 200 · 시드 · 가짜 룰 100 · 거부율 문턱 0.16 · Holm m=6 · 라벨 · 재현 가드 0.1% · 대체 경로 문서 그대로).",
          "- 산출물: 문서 §6-4 는 `run_meta.json` 한 파일이지만 ③ 진단의 `run_meta.json` 은 커밋돼 있어 수정 금지 ⇒ 이 단계 지문은 "
          "`run_meta_random_entry.json` 에 따로 썼다. 반복별 값 `random_entry_reps.csv` · 가짜 룰 p `random_entry_fakes.csv` 추가(검증용).",
          "", "## 9. 한계 (문서 §8 인용)", ""]
    A += LIMITS
    A += ["", "## 10. 실행 지문", "",
          f"- git `{o['sha']}` · 경로 `{o['path']}` · 캐시 로트 {o['n_cache']:,} · 시드 반복 `[20261002, 2, r]` · 가짜 `[20261002, 3, j]`",
          "- 산출물: `run_random_entry.py` · `RESULTS_random_entry.md` · `run_meta_random_entry.json` · `random_entry_reps.csv` · "
          "`random_entry_fakes.csv` · `run_random_entry.log`"]
    return A


if __name__ == "__main__":
    sys.exit(main())
