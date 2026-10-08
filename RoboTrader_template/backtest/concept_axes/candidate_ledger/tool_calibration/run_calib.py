"""검정 도구 교정 — 사전등록 `docs/prereg_2026-09-24_test_tool_calibration.md`(🔒 동결 0bfbe92) 그대로.

부품
  P1 전략×종목 블록 순열(블록 크기 5분위 층 안 · 라벨열 scan_date 순 · 원형 반복/절단)
  P2 에피소드 첫 행 · 종목 클러스터 CR1 SE · 정규 근사 p
  P3 (전략, scan_date) 안 3분위(비결측 < 3 인 날 제외)
조합  K1 = P3+P1 · K2 = P3+P2 · K3 = 창 전체+P1 · K4 = 창 전체+P2 · K0 = B 원 도구(재현 대조 · 판정 대상 아님)
가짜  G-종목(t=1) · G-날짜(t=2) · G-AR φ=0.9(t=4) 각 100개(경계 조합은 +300)

입력 = `feature_study/features.csv` 하나(md5 고정 · 불일치면 중단). DB 조회 0 · 라이브 코드 0줄.
실행(워크트리 RoboTrader_template 에서):
  python -m backtest.concept_axes.candidate_ledger.tool_calibration.run_calib --bench     # 시간 측정만
  python -m backtest.concept_axes.candidate_ledger.tool_calibration.run_calib --workers 8 # 본 실행
"""
from __future__ import annotations

import os

for _v in ("OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS", "OMP_NUM_THREADS", "NUMEXPR_NUM_THREADS"):
    os.environ.setdefault(_v, "1")          # 작업 프로세스 여럿 × BLAS 스레드 과다 방지

import argparse                                                        # noqa: E402
import hashlib                                                         # noqa: E402
import json                                                            # noqa: E402
import math                                                            # noqa: E402
import subprocess                                                      # noqa: E402
import sys                                                             # noqa: E402
import time                                                            # noqa: E402
from concurrent.futures import ProcessPoolExecutor                     # noqa: E402
from datetime import datetime                                          # noqa: E402
from pathlib import Path                                               # noqa: E402
from typing import Any, Dict, List, Optional, Tuple                    # noqa: E402

import numpy as np                                                     # noqa: E402
import pandas as pd                                                    # noqa: E402

from backtest.concept_axes.candidate_ledger.feature_study import run_features as RF  # noqa: E402

BASE = Path(__file__).resolve().parent
ROOT = BASE.parents[3]
FEATURES_CSV = BASE.parent / "feature_study" / "features.csv"
SCAN_DIAG = BASE.parent / "results" / "scan_diag.csv"
PREREG = "docs/prereg_2026-09-24_test_tool_calibration.md"
PREREG_COMMIT = "0bfbe92"
MD5_EXPECT = "12216fe9359f5c21d9831400502730eb"

SEED0 = 20261001
PHI = 0.9
P_CAL = 2_000                 # §3 교정 순열 횟수
P_S6 = 10_000                 # §6 재적용 인쇄
STAGE1 = list(range(1, 101))
STAGE2 = list(range(101, 401))
ALPHA, ALPHA05 = 0.10, 0.05
MDE_K, MDE_HOLM = 2.80, 3.75
TOL = 1e-12                   # B(perm_rows)와 같은 부동소수 여유
TIME_LIMIT_S = 30 * 60        # §9 실행 30분(조합 단위 체크포인트)

SNAMES = RF.SNAMES            # 전략 순서 = B 와 동일
SHORT = [RF.STRATS[s]["short"] for s in SNAMES]
N_MIN = RF.N_MIN              # B §4-2 n<30 판정 불가
WINDOWS = ("E", "C")
TYPES = {1: "G-종목", 2: "G-날짜", 4: "G-AR"}
COMBOS = {  # k: (분위, 귀무)
    1: ("date", "P1"), 2: ("date", "P2"), 3: ("window", "P1"), 4: ("window", "P2"), 0: ("window", "K0")}
COMBO_NAME = {1: "K1 (P3+P1)", 2: "K2 (P3+P2)", 3: "K3 (창 전체+P1)", 4: "K4 (창 전체+P2)", 0: "K0 (B 원 도구)"}
RANK = [1, 2, 3, 4]           # §3 순위

LOG: List[str] = []


def log(msg: str = "") -> None:
    LOG.append(msg)
    sys.stderr.write(msg + "\n")
    sys.stderr.flush()


def md5(path: Path) -> str:
    return hashlib.md5(path.read_bytes()).hexdigest()


def git_sha() -> str:
    return subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True, text=True).stdout.strip()


# ════════════════════════════════════════════════════════════════════════════
# 1. 입력 · 달력 · 에피소드
# ════════════════════════════════════════════════════════════════════════════
def load_input(path: Path = FEATURES_CSV, expect: Optional[str] = MD5_EXPECT) -> Tuple[pd.DataFrame, List[str]]:
    """(in_full 표본, 달력). 달력 = features.csv «전 행»(52,540 · 상한 뒤 행 포함)의 scan_date 집합."""
    got = md5(path)
    if expect is not None and got != expect:
        raise SystemExit(f"features.csv md5 불일치 {got} ≠ {expect} — 중단(§1)")
    F = pd.read_csv(path, dtype={"stock_code": str, "scan_date": str}, low_memory=False)
    cal = sorted(F["scan_date"].unique())
    return F[F["in_full"].astype(bool)].reset_index(drop=True), cal   # 표본 = B 와 동일(§1 · in_full)


def episodes(s: np.ndarray, g: np.ndarray, ci: np.ndarray) -> Tuple[np.ndarray, np.ndarray]:
    """§2 P2 — 전략×종목을 달력 순번으로 정렬 · 직전 행과 순번 차 > 1 이면 새 에피소드. (에피소드 id, 첫 행 여부)."""
    o = np.lexsort((ci, g, s))
    ss, gg, cc = s[o], g[o], ci[o]
    new = np.ones(len(o), dtype=bool)
    new[1:] = (ss[1:] != ss[:-1]) | (gg[1:] != gg[:-1]) | (cc[1:] - cc[:-1] > 1)
    eid = np.empty(len(o), dtype=np.int64)
    eid[o] = np.cumsum(new) - 1
    first = np.zeros(len(o), dtype=bool)
    first[o] = new
    return eid, first


def build_data(full: pd.DataFrame, cal: List[str]) -> Dict[str, Any]:
    """전 표본(E∪C) 공통 색인 + 창별 배열(행 순서 = 전략·scan_date·종목 · B prep 와 같음)."""
    codes = np.array(sorted(full["stock_code"].unique()))
    cal_idx = {d: i for i, d in enumerate(cal)}
    ci_full = full["scan_date"].map(cal_idx).to_numpy()
    if np.isnan(ci_full.astype(float)).any():
        raise SystemExit("달력 밖 scan_date — 중단")
    data: Dict[str, Any] = dict(n_rows=len(full), n_codes=len(codes), n_cal=len(cal),
                                gi_full=np.searchsorted(codes, full["stock_code"].to_numpy()).astype(np.int64),
                                ci_full=ci_full.astype(np.int64), W={})
    smap = {n: k for k, n in enumerate(SNAMES)}
    tmp = full.assign(_s=full["strategy"].map(smap), _r=np.arange(len(full)))
    for w in WINDOWS:
        d = tmp[tmp["window"] == w].sort_values(["_s", "scan_date", "stock_code"], kind="mergesort")
        rowid = d["_r"].to_numpy()
        s = d["_s"].to_numpy().astype(np.int64)
        g, ci = data["gi_full"][rowid], data["ci_full"][rowid]
        eid, first = episodes(s, g, ci)
        data["W"][w] = dict(rowid=rowid, s=s, g=g, ci=ci, y=d["ret_pct"].to_numpy(dtype=float), eid=eid, first=first)
    return data


# ════════════════════════════════════════════════════════════════════════════
# 2. 가짜 특징 (§4 · 전 표본 E∪C 한 번 정의 · 행 순서 = features.csv in_full 행 순서)
# ════════════════════════════════════════════════════════════════════════════
def ar1_panel(rng: np.random.Generator, n_cal: int, n_codes: int, phi: float = PHI) -> np.ndarray:
    """x_{g,0} ~ N(0,1) · x_{g,t} = φ x_{g,t−1} + √(1−φ²) ε_{g,t}. 뽑는 순서 = x0(n_codes) → ε(n_cal−1, n_codes)."""
    x = np.empty((n_cal, n_codes))
    x[0] = rng.standard_normal(n_codes)
    eps = rng.standard_normal((n_cal - 1, n_codes))
    c = math.sqrt(1.0 - phi * phi)
    for t in range(1, n_cal):
        x[t] = phi * x[t - 1] + c * eps[t - 1]
    return x


def make_fake(t: int, i: int, data: Dict[str, Any]) -> np.ndarray:
    gi, ci = data["gi_full"], data["ci_full"]
    rng = np.random.default_rng([SEED0, t, i])
    if t == 1:                                            # G-종목
        return rng.standard_normal(data["n_codes"])[gi]
    if t == 2:                                            # G-날짜
        a = rng.standard_normal(data["n_cal"])
        u = rng.random(data["n_rows"])
        return a[ci] + 1e-6 * u
    if t == 4:                                            # G-AR
        return ar1_panel(rng, data["n_cal"], data["n_codes"])[ci, gi]
    raise ValueError(t)


# ════════════════════════════════════════════════════════════════════════════
# 3. 분위 · 통계량
# ════════════════════════════════════════════════════════════════════════════
def tertile(q: np.ndarray) -> np.ndarray:
    return np.where(q <= 1 / 3, 1, np.where(q > 2 / 3, 3, 2)).astype(np.int8)


def make_labels(x: np.ndarray, s: np.ndarray, ci: np.ndarray, mode: str,
                binary: bool = False) -> Tuple[np.ndarray, Dict[str, Any]]:
    """라벨 1/2/3 · 0 = 표본 밖(결측 · P3 의 비결측 < 3 인 날).

    mode 'window' = 전략 안 창 전체(B §4-2) · 'date' = (전략, scan_date) 안(P3). 이진 특징은 1→T3 · 0→T1(B 와 같음).
    """
    x = np.asarray(x, dtype=float)
    ok = ~np.isnan(x)
    df = pd.DataFrame({"x": x, "s": s, "d": ci})
    keys = ["s"] if mode == "window" else ["s", "d"]
    if binary:
        lab = np.where(x == 1.0, 3, 1).astype(np.int8)
    else:
        lab = tertile(df.groupby(keys)["x"].rank(pct=True, method="average").to_numpy())
    lab[~ok] = 0
    info: Dict[str, Any] = {}
    if mode == "date":
        cnt = df.groupby(keys)["x"].transform("count").to_numpy()
        small = ok & (cnt < 3)
        lab[small] = 0
        day_n = df[ok].groupby(keys).size()
        for k in range(len(SNAMES)):
            dn = day_n[day_n.index.get_level_values(0) == k] if len(day_n) else day_n
            info[SHORT[k]] = dict(days=int(len(dn)), days_excl=int((dn < 3).sum()),
                                  rows_excl=int((small & (s == k)).sum()))
    return lab, info


def delta_stat(y: np.ndarray, lab: np.ndarray, s: np.ndarray) -> Dict[str, Any]:
    """B §4-2 — Δ_s = mean(T3) − mean(T1) · n<30 판정 불가 · Δ_pool = Σ n_s Δ_s / Σ n_s(n_s = 표본 행 전부)."""
    S = len(SNAMES)
    per = np.full(S, np.nan)
    n, n1, n3 = np.zeros(S), np.zeros(S), np.zeros(S)
    ok = np.zeros(S, dtype=bool)
    for k in range(S):
        m = (s == k) & (lab > 0)
        m1, m3 = m & (lab == 1), m & (lab == 3)
        n[k], n1[k], n3[k] = m.sum(), m1.sum(), m3.sum()
        ok[k] = n1[k] >= N_MIN and n3[k] >= N_MIN
        if ok[k]:
            per[k] = y[m3].mean() - y[m1].mean()
    pool = float((n[ok] * per[ok]).sum() / n[ok].sum()) if ok.any() else np.nan
    return dict(pool=pool, per=per, n=n, n1=n1, n3=n3, ok=ok)


def perm_p(null: np.ndarray, obs: float) -> float:
    """양측 `(1 + #{|Δ_perm| ≥ |Δ_obs|}) / (1 + 횟수)` · 순열 Δ 가 NaN(분모 0)이면 0 으로 센다."""
    if not np.isfinite(obs):
        return np.nan
    nl = np.nan_to_num(null, nan=0.0)
    return float((1 + int((np.abs(nl) >= abs(obs) - TOL).sum())) / (1 + len(nl)))


# ── K0 : (strategy, scan_date) 블록 안 라벨 섞기(B §4-3) ─────────────────────
def k0_null(y, lab, s, ci, st, rng, P) -> Tuple[np.ndarray, np.ndarray]:
    S = len(SNAMES)
    per = np.full((S, P), np.nan)
    num, den = np.zeros(P), 0.0
    for k in range(S):
        if not st["ok"][k]:
            continue
        r = np.flatnonzero((s == k) & (lab > 0))
        r = r[np.argsort(ci[r], kind="mergesort")]
        _, starts, sizes = np.unique(ci[r], return_index=True, return_counts=True)
        s3, s1 = np.zeros(P), np.zeros(P)
        for m in np.unique(sizes):
            bl = np.flatnonzero(sizes == m)
            rows = r[(starts[bl][:, None] + np.arange(m)[None, :]).ravel()]
            L = np.broadcast_to(lab[rows].reshape(len(bl), m), (P, len(bl), m))
            Lp = rng.permuted(L, axis=2).reshape(P, -1)
            yy = y[rows]
            s3 += (Lp == 3) @ yy
            s1 += (Lp == 1) @ yy
        dk = s3 / st["n3"][k] - s1 / st["n1"][k]
        per[k] = dk
        num += st["n"][k] * dk
        den += st["n"][k]
    return num / den, per


# ── P1 : 전략×종목 블록 순열 ──────────────────────────────────────────────────
def p1_struct(s: np.ndarray, g: np.ndarray, ci: np.ndarray, keep: np.ndarray) -> List[Dict[str, Any]]:
    """전략별 블록(종목 · scan_date 순) · 블록 크기 5분위 층 · 층 안 짝 후보 색인.

    층 안 블록 g 가 짝 h 에게서 받는 j 번째 라벨 = 블록 h 의 (j mod m_h) 번째 라벨(원형 반복 · 길면 앞 m_g 개만).
    src[r, h] = 층의 r 번째 행(블록 순 · scan_date 순)이 짝 h 에게서 받는 라벨의 창 배열 색인.
    """
    out = []
    for k in range(len(SNAMES)):
        r = np.flatnonzero((s == k) & keep)
        r = r[np.lexsort((ci[r], g[r]))]
        gk = g[r]
        starts = np.flatnonzero(np.r_[True, gk[1:] != gk[:-1]]) if len(r) else np.zeros(0, dtype=np.int64)
        sizes = np.diff(np.r_[starts, len(r)]).astype(np.int64)
        q = pd.Series(sizes, dtype=float).rank(pct=True, method="average").to_numpy()
        stratum = 1 + (q > 0.2).astype(int) + (q > 0.4) + (q > 0.6) + (q > 0.8)
        strata = []
        for z in range(1, 6):
            bS = np.flatnonzero(stratum == z)
            if len(bS) == 0:
                continue
            mS, stS = sizes[bS], starts[bS]
            seg = np.r_[0, np.cumsum(mS)[:-1]].astype(np.int64)
            pos = np.arange(int(mS.sum())) - np.repeat(seg, mS)
            own = np.repeat(stS, mS) + pos                                  # 이 층 행의 r 안 위치
            src = r[stS[None, :] + (pos[:, None] % mS[None, :])]            # (R, k)
            strata.append(dict(k=len(bS), yrows=r[own], src=src.astype(np.int64), seg=seg, sizes=mS))
        out.append(dict(n_rows=len(r), n_blocks=len(sizes), strata=strata))
    return out


def p1_quant(S: Dict[str, Any], lab: np.ndarray, y: np.ndarray) -> np.ndarray:
    """(4, k, k) — [g, h] = 블록 g 가 짝 h 의 라벨열을 받을 때 (ΣyT3, #T3, ΣyT1, #T1)."""
    labs = lab[S["src"]]
    yr = y[S["yrows"]][:, None]
    e3, e1 = labs == 3, labs == 1
    seg = S["seg"]
    return np.stack([np.add.reduceat(e3 * yr, seg, axis=0), np.add.reduceat(e3.astype(np.int64), seg, axis=0),
                     np.add.reduceat(e1 * yr, seg, axis=0), np.add.reduceat(e1.astype(np.int64), seg, axis=0)])


def p1_partners(rng: np.random.Generator, k: int, P: int) -> np.ndarray:
    """(P, k) — 행 p 의 g 열 = π_p(g)(층 안 균등 순열)."""
    return np.argsort(rng.random((P, k)), axis=1)


def p1_null(y, lab, st, struct, rng, P, chunk: int = 2_000) -> Tuple[np.ndarray, np.ndarray]:
    S_ = len(SNAMES)
    per = np.full((S_, P), np.nan)
    num, den = np.zeros(P), 0.0
    for k in range(S_):
        if not st["ok"][k]:
            continue
        tot = np.zeros((4, P))
        for S in struct[k]["strata"]:
            Q = p1_quant(S, lab, y)
            Pi = p1_partners(rng, S["k"], P)
            ar = np.arange(S["k"])[None, :]
            for a in range(0, P, chunk):
                tot[:, a:a + chunk] += Q[:, ar, Pi[a:a + chunk]].sum(axis=2)
        with np.errstate(invalid="ignore", divide="ignore"):
            dk = tot[0] / tot[1] - tot[2] / tot[3]
        per[k] = dk
        num += st["n"][k] * dk
        den += st["n"][k]
    return num / den, per


# ── P2 : 종목 클러스터 CR1 ───────────────────────────────────────────────────
def cr1_test(y: np.ndarray, lab: np.ndarray, s: np.ndarray, cl: np.ndarray, st: Dict[str, Any],
             n_cl: Optional[int] = None) -> Dict[str, Any]:
    """Δ_s(차이 평균)의 종목 클러스터 로버스트 분산 CR1 = G/(G−1)·(N−1)/(N−K) · Σ_g ψ_g².

    ψ_g = Σ_{i∈g} w_i u_i · w = 1/n3(T3) · −1/n1(T1) · u = 자기 분위 평균에서 뺀 잔차.
    풀링 = 전략별 절편·기울기 적층 회귀의 선형결합 a·β(a_s = n_s/Σn) · 클러스터 = 종목(전략 가로질러 하나) · K = 2·S_ok.
    """
    S_ = len(SNAMES)
    n_cl = int(cl.max()) + 1 if n_cl is None else n_cl
    se_s, p_s = np.full(S_, np.nan), np.full(S_, np.nan)
    ok = st["ok"]
    den = st["n"][ok].sum()
    psi_pool = np.zeros(n_cl)
    N_all, used = 0, np.zeros(n_cl, dtype=bool)
    for k in range(S_):
        if not ok[k]:
            continue
        m1, m3 = (s == k) & (lab == 1), (s == k) & (lab == 3)
        n1, n3 = st["n1"][k], st["n3"][k]
        w = np.where(m3, 1.0 / n3, np.where(m1, -1.0 / n1, 0.0))
        u = np.where(m3, y - y[m3].mean(), np.where(m1, y - y[m1].mean(), 0.0))
        m = m1 | m3
        psi = np.bincount(cl[m], weights=(w * u)[m], minlength=n_cl)
        Nk, Gk = int(m.sum()), int(np.unique(cl[m]).size)
        v = Gk / (Gk - 1) * (Nk - 1) / (Nk - 2) * float((psi ** 2).sum())
        se_s[k] = math.sqrt(v)
        p_s[k] = math.erfc(abs(st["per"][k]) / se_s[k] / math.sqrt(2)) if se_s[k] > 0 else np.nan
        psi_pool += st["n"][k] / den * psi
        N_all += Nk
        used[cl[m]] = True
    if not ok.any():
        return dict(se=np.nan, p=np.nan, se_s=se_s, p_s=p_s)
    G, K = int(used.sum()), 2 * int(ok.sum())
    v = G / (G - 1) * (N_all - 1) / (N_all - K) * float((psi_pool ** 2).sum())
    se = math.sqrt(v)
    p = math.erfc(abs(st["pool"]) / se / math.sqrt(2)) if se > 0 else np.nan
    return dict(se=se, p=p, se_s=se_s, p_s=p_s)


def episode_mean_sample(D: Dict[str, Any], x: np.ndarray) -> Tuple[np.ndarray, ...]:
    """에피소드 평균(병기 · 인쇄만) — 특징·결과 = 에피소드 행 평균(특징은 비결측만) · 날짜·전략·종목 = 첫 행."""
    eid = D["eid"]
    ne = int(eid.max()) + 1
    okx = ~np.isnan(x)
    xs = np.bincount(eid, weights=np.where(okx, x, 0.0), minlength=ne)
    xc = np.bincount(eid, weights=okx.astype(float), minlength=ne)
    ys = np.bincount(eid, weights=D["y"], minlength=ne) / np.bincount(eid, minlength=ne)
    with np.errstate(invalid="ignore", divide="ignore"):
        xm = xs / xc
    fi = np.flatnonzero(D["first"])
    fi = fi[np.argsort(eid[fi])]
    return xm, ys, D["s"][fi], D["g"][fi], D["ci"][fi]


# ════════════════════════════════════════════════════════════════════════════
# 4. 조합 하나 실행 (창 E·C)
# ════════════════════════════════════════════════════════════════════════════
def _p1_cached(cache: Optional[Dict], key: Tuple, D, keep) -> List[Dict[str, Any]]:
    if cache is None:
        return p1_struct(D["s"], D["g"], D["ci"], keep)
    kk = key + (hashlib.md5(keep.tobytes()).hexdigest(),)
    if kk not in cache:
        cache[kk] = p1_struct(D["s"], D["g"], D["ci"], keep)
    return cache[kk]


def run_window(k: int, x_win: np.ndarray, D: Dict[str, Any], seed: List[int], P: int, binary: bool = False,
               cache: Optional[Dict] = None, n_codes: Optional[int] = None, w: str = "E",
               keep_null: bool = False) -> Dict[str, Any]:
    mode, kind = COMBOS[k]
    rng = np.random.default_rng(seed)            # 창마다 같은 시드로 새 생성기(해석 기록 10)
    out: Dict[str, Any] = {}
    if kind in ("P1", "K0"):
        y, s, ci = D["y"], D["s"], D["ci"]
        lab, info = make_labels(x_win, s, ci, mode, binary)
        st = delta_stat(y, lab, s)
        if not np.isfinite(st["pool"]):
            null, nper = np.full(P, np.nan), np.full((len(SNAMES), P), np.nan)
        elif kind == "K0":
            null, nper = k0_null(y, lab, s, ci, st, rng, P)
        else:
            struct = _p1_cached(cache, (w, k), D, lab > 0)
            null, nper = p1_null(y, lab, st, struct, rng, P)
        out.update(p=perm_p(null, st["pool"]),
                   p_s=[perm_p(nper[j], st["per"][j]) if st["ok"][j] else np.nan for j in range(len(SNAMES))],
                   sd=float(np.nanstd(null, ddof=1)) if np.isfinite(null).any() else np.nan,
                   sd_s=[float(np.nanstd(nper[j], ddof=1)) if st["ok"][j] else np.nan for j in range(len(SNAMES))])
        if keep_null:
            out["null"] = null
    else:                                         # P2 — 에피소드 첫 행 표본 안에서 분위·Δ·CR1
        fi = np.flatnonzero(D["first"])
        y, s, ci, g = D["y"][fi], D["s"][fi], D["ci"][fi], D["g"][fi]
        lab, info = make_labels(x_win[fi], s, ci, mode, binary)
        st = delta_stat(y, lab, s)
        cr = cr1_test(y, lab, s, g, st, n_codes) if np.isfinite(st["pool"]) else dict(
            se=np.nan, p=np.nan, se_s=np.full(len(SNAMES), np.nan), p_s=np.full(len(SNAMES), np.nan))
        out.update(p=cr["p"], p_s=list(cr["p_s"]), sd=cr["se"], sd_s=list(cr["se_s"]))
        xm, ym, sm, gm, cm = episode_mean_sample(D, x_win)          # 병기 · 인쇄만
        labm, _ = make_labels(xm, sm, cm, mode, False)             # 평균값은 연속값으로 분위
        stm = delta_stat(ym, labm, sm)
        crm = cr1_test(ym, labm, sm, gm, stm, n_codes) if np.isfinite(stm["pool"]) else dict(p=np.nan)
        out.update(p_epmean=crm["p"], delta_epmean=stm["pool"])
    out.update(delta=st["pool"], delta_s=list(st["per"]), n=list(st["n"]), n1=list(st["n1"]), n3=list(st["n3"]),
               ok=[bool(v) for v in st["ok"]], p3=info)
    return out


def run_combo(k: int, x_full: np.ndarray, data: Dict[str, Any], seed: List[int], P: int, binary: bool = False,
              cache: Optional[Dict] = None, keep_null: bool = False) -> Dict[str, Any]:
    return {w: run_window(k, x_full[data["W"][w]["rowid"]], data["W"][w], seed, P, binary, cache,
                          data["n_codes"], w, keep_null) for w in WINDOWS}


# ── 작업 프로세스 ────────────────────────────────────────────────────────────
_DATA: Dict[str, Any] = {}
_CACHE: Dict[Tuple, Any] = {}


def _init(data: Dict[str, Any]) -> None:
    _DATA.clear()
    _DATA.update(data)
    _CACHE.clear()


def _task(args: Tuple[int, int, int, int]) -> Tuple[int, int, int, Dict[str, Any], float]:
    k, t, i, P = args
    t0 = time.perf_counter()
    x = make_fake(t, i, _DATA)
    res = run_combo(k, x, _DATA, [SEED0, 3, k, i, t], P, cache=_CACHE)
    if i != 1:                                     # P3 제외 건수는 구조로 정해짐 ⇒ i=1 것만 남김
        for w in WINDOWS:
            res[w].pop("p3", None)
    return k, t, i, res, time.perf_counter() - t0


def _task_feature(args: Tuple[int, str, str, int, int]) -> Tuple[str, Dict[str, Any]]:
    k, fid, col, P, _ = args
    x = _DATA["feat"][col]
    res = {}
    for wi, w in enumerate(WINDOWS):
        D = _DATA["W"][w]
        res[w] = run_window(k, x[D["rowid"]], D, [SEED0, 6, wi, int(fid[1:])], P, fid in RF.BINARY,
                            None, _DATA["n_codes"], w)
    return fid, res


# ════════════════════════════════════════════════════════════════════════════
# 5. 판정 (§5)
# ════════════════════════════════════════════════════════════════════════════
def classify(counts: Dict[int, Tuple[int, int]]) -> str:
    """counts[t] = (p<0.10 개수, 가짜 개수). 정수 비교(경계 포함): 0.07 ≤ r ≤ 0.13 합격 · r<0.04 ∨ r>0.16 불합격."""
    inside = all(100 * c >= 7 * n and 100 * c <= 13 * n for c, n in counts.values())
    if inside:
        return "합격"
    if any(100 * c < 4 * n or 100 * c > 16 * n for c, n in counts.values()):
        return "불합격"
    return "경계"


def stage2_verdict(counts: Dict[int, Tuple[int, int]]) -> str:
    return "합격" if all(100 * c >= 7 * n and 100 * c <= 13 * n for c, n in counts.values()) else "불합격"


def rej_counts(R: Dict, k: int, idxs: List[int], w: str = "E", key: str = "p", a: float = ALPHA,
               j: Optional[int] = None) -> Dict[int, Tuple[int, int]]:
    out = {}
    for t in TYPES:
        ps = []
        for i in idxs:
            v = R[k][t][i][w][key] if j is None else R[k][t][i][w][key][j]
            ps.append(np.nan if v is None else v)
        ps = np.array(ps, dtype=float)
        out[t] = (int((ps < a).sum()), int(np.isfinite(ps).sum()))
    return out


# ════════════════════════════════════════════════════════════════════════════
# 6. 문서
# ════════════════════════════════════════════════════════════════════════════
INTERP = [
    "1. **달력** — DB 없이 `features.csv` «전 행»(52,540 · in_full 밖 상한 뒤 행 포함)의 scan_date 집합(617일)을 "
    "KOSPI 거래일 달력으로 썼다(in_full 만의 집합은 606일 · 09-08 에서 끝나 쓰지 않음). 원장 `run.py:774-775` 는 "
    "DB `stock_code='KOSPI'` 달력의 창(2024-03-13~2026-09-23) 전 거래일을 스캔하고 `results/scan_diag.csv` 에 전략별 한 줄씩 "
    "남긴다(원장 `run_meta.json` n_scan_days 617). 실행 시 `scan_diag.csv`(md5 보관소 일치 확인) scan_date 집합과 같음을 확인했다.",
    "2. **에피소드** — 창마다 in_full 행으로 (전략, 종목)을 달력 순번으로 정렬 · 순번 차 > 1 이면 새 에피소드(문서 §2 P2 식). "
    "`ep_first` 열은 쓰지 않았고, C 에서 재계산 첫 행 = `ep_first` 와 행 단위 전부 일치함을 실행 시 확인했다.",
    "3. **P2 표본** — 에피소드 첫 행만 남긴 표본 «안에서» 분위·Δ_s·풀링·CR1 을 모두 계산했다(B 의 에피소드 검정 "
    "`test_feature(EP)` 선례 · 대표값 = 첫 행). K2(P3+P2)의 「비결측 < 3 인 날 제외」도 이 표본(그날 첫 행 수)에 적용했다.",
    "4. **에피소드 평균(병기·인쇄만)** — 특징·`ret_pct` 를 에피소드 행 평균으로, 날짜·전략·종목은 첫 행 값으로 두고 같은 절차.",
    "5. **CR1** — Δ_s 는 T1∪T3 행에서 절편+T3 더미 회귀의 기울기와 같다. CR1 = G/(G−1)·(N−1)/(N−K)·Σ_g ψ_g²(Stata 형) · "
    "전략별 K=2. 풀링 SE 는 전략별 절편·기울기 적층 회귀(K = 2·S_ok)에서 a_s = n_s/Σn 선형결합의 분산 · "
    "클러스터 = 종목(전략을 가로질러 한 클러스터). p = 2Φ(−|Δ_pool|/SE_pool) = erfc(|z|/√2).",
    "6. **풀링 가중 n_s** — B 와 같이 그 전략 표본의 비결측 행 전부(T2 포함). P3 에서는 제외된 날의 행을 빼고, P2 에서는 에피소드 수. "
    "n1 또는 n3 < 30 인 전략은 풀링에서 뺀다(B §4-2 · 순열에서도 관측 기준 전략 집합 고정).",
    "7. **P1 층** — 전략 안 블록 크기의 `rank(pct=True, method='average')` q 로 층 = 1 + #{q > 0.2, 0.4, 0.6, 0.8}"
    "(§4-2 3분위와 같은 오른쪽 닫힘 · 동률 블록은 한 층).",
    "8. **P1 원형 반복/절단** — 블록 g 의 j 번째 라벨 = π(g) 라벨열의 (j mod m_π(g)) 번째(scan_date 순). "
    "π(g) 가 길면 앞에서부터 m_g 개(「앞에서 절단」을 «앞부분을 남긴다»로 읽음), 짧으면 처음부터 원형 반복.",
    "9. **P1 통계량** — 순열마다 T1·T3 개수가 바뀌므로 Δ_s 를 순열 라벨의 개수로 다시 나눈다. 풀링 가중 n_s 는 고정.",
    "10. **순열 난수** — `default_rng([20261001, 3, k, i, t])` 를 창(E·C)마다 새로 만든다(E 결과가 C 실행 여부와 무관). "
    "소비 순서: P1 = 전략(ma20→minervini→daytrading) × 층 1→5 마다 `random((P, k))` 의 argsort · "
    "K0 = 전략 × 블록 크기 오름차순마다 `permuted(axis=2)`(B 와 같은 분포 · 난수열은 다름).",
    "11. **가짜 특징** — 전 표본(E∪C in_full 49,651행)에서 한 번 정의해 E·C 가 같은 특징을 쓴다. 종목 집합 = in_full 종목 "
    "정렬(사전순) · G-날짜 `a_d` 는 617일 달력 순 · `u_row` 는 features.csv 의 in_full 행 순 · "
    "G-AR 은 `x0 = standard_normal(n종목)` → `ε = standard_normal((616, n종목))`(시간 우선) 순서로 뽑는다.",
    "12. **C 창** — 모든 가짜·조합에서 E 와 같은 절차로 계산해 인쇄만 했다(판정 0). 2단계도 C 를 같이 인쇄.",
    "13. **2단계** — 1단계 「경계」인 K1~K4 조합 전부에 i=101…400 을 돌렸다(K0 는 판정 대상이 아니라 1단계만).",
    "14. **§6 재적용 난수** — 문서에 시드가 없어 `default_rng([20261001, 6, w, f])`(w=0 E·1 C · f=특징 번호)로 새로 잡았다"
    "(가짜 특징 시드 1·2·3·4 와 겹치지 않음). 이진 특징(F06·F11)은 1→T3 · 0→T1(B 와 같음) · P3 에서도 이 라벨에 "
    "「비결측 < 3 인 날 제외」만 적용. 날짜 단위 특징 F03 은 P3 에서 날짜 안 전부 동률 ⇒ 전부 T2 ⇒ 「판정 불가」.",
    "15. **동률·부동소수** — |Δ_perm| ≥ |Δ_obs| − 1e−12(B 구현과 같음) · 순열 Δ 가 NaN(분모 0)이면 0 으로 센다 · "
    "합격 구간 비교는 정수 연산(0.07·0.13 경계 포함 · 0.04·0.16 은 초과/미만만 불합격).",
    "16. **K0 재현** — K0 는 B 의 도구를 이번 G-종목(N(0,1) · 새 시드)에 적용한 것이다. B V-F5(균등분포 · 시드 20260927 · "
    "10,000회)의 가짜·순열과 난수가 다르므로 «같은 값»이 아니라 «가까운 값»이 재현의 뜻이다.",
    "17. **SD_null** — 순열 도구 = 순열 Δ 의 표준편차(ddof=1) · P2 도구 = CR1 SE. 가짜 유형별 값은 그 유형 가짜들의 평균.",
]

LIMITS = [
    "> 교정은 **창 E · 이 원장**에서의 명목 맞추기다. 다른 결과 변수(꼬리 빈도·r5)·다른 표본(뉴스 창)에 그대로 옮겨도 된다는 "
    "보장은 없다 — 그 검정의 문서가 같은 가짜 특징 시험을 **자기 표본에서** 한 번 더 인쇄하게 한다(권고 · 강제 아님).",
    "> P1 의 원형 반복·절단은 행마다 바뀌는 특징에서 근사다. P3 는 날짜 간 효과(국면)를 버린다 — 「국면 효과」 자체는 "
    "이 도구로 못 잰다(패널 ⑥-5 규칙화 금지와 정합).",
    "> 세 종류 가짜 특징은 종목·날짜 이원 상관의 일부만 대표한다. 「셋 다 합격」은 필요조건이지 충분조건이 아니다.",
]


def fr(c: int, n: int) -> str:
    return f"{c / n:.3f} ({c}/{n})" if n else "—"


def rate_table(R: Dict, combos: List[int], idx_of: Dict[int, List[int]], w: str, key: str = "p",
               a: float = ALPHA) -> List[str]:
    out = ["| 조합 | 가짜 수 | " + " | ".join(TYPES.values()) + " |", "|---|---|---|---|---|"]
    for k in combos:
        c = rej_counts(R, k, idx_of[k], w, key, a)
        out.append(f"| {COMBO_NAME[k]} | {len(idx_of[k])} | " + " | ".join(fr(*c[t]) for t in TYPES) + " |")
    return out


def f2(x, nd=3) -> str:
    return "—" if x is None or not np.isfinite(x) else f"{x:.{nd}f}"


def fs(x, nd=2) -> str:
    return "—" if x is None or not np.isfinite(x) else f"{x:+.{nd}f}"


# ════════════════════════════════════════════════════════════════════════════
# 7. 주 실행
# ════════════════════════════════════════════════════════════════════════════
def prepare() -> Tuple[pd.DataFrame, Dict[str, Any], Dict[str, Any]]:
    full, cal = load_input()
    chk: Dict[str, Any] = dict(n_full=len(full), n_cal=len(cal), cal_first=cal[0], cal_last=cal[-1])
    if SCAN_DIAG.exists():
        sd = pd.read_csv(SCAN_DIAG, dtype=str)
        chk["scan_diag_md5"] = md5(SCAN_DIAG)
        chk["cal_eq_scan_diag"] = sorted(sd["scan_date"].unique()) == cal
    if (cal[0], cal[-1]) != ("2024-03-13", "2026-09-23") or not chk.get("cal_eq_scan_diag", False):
        raise SystemExit(f"달력 확인 실패 {chk} — 중단")
    data = build_data(full, cal)
    C = data["W"]["C"]
    epC = full["ep_first"].astype(bool).to_numpy()[C["rowid"]]
    chk["ep_first_C_match"] = bool((epC == C["first"]).all())
    chk["ep_first_C_n"] = int(C["first"].sum())
    chk["ep_first_E_n"] = int(data["W"]["E"]["first"].sum())
    chk["ep_first_E_csv_true"] = int(full["ep_first"].astype(bool).to_numpy()[data["W"]["E"]["rowid"]].sum())
    if not chk["ep_first_C_match"]:
        raise SystemExit("C 에피소드 재계산 ≠ ep_first — 중단")
    for w in WINDOWS:
        D = data["W"][w]
        chk[f"rows_{w}"] = {SHORT[k]: int((D["s"] == k).sum()) for k in range(len(SNAMES))}
        chk[f"eps_{w}"] = {SHORT[k]: int(((D["s"] == k) & D["first"]).sum()) for k in range(len(SNAMES))}
    return full, data, chk


def bench(workers: int) -> int:
    full, data, chk = prepare()
    log(f"[bench] 확인 {chk}")
    _init(data)
    est = 0.0
    for k in (1, 2, 3, 4, 0):
        ts = []
        for t in TYPES:
            for i in (9001, 9002):          # 교정에 쓰지 않는 번호 · p 는 보지 않는다(시간만)
                _, _, _, _, dt = _task((k, t, i, P_CAL))
                ts.append(dt)
                log(f"[bench] {COMBO_NAME[k]} {TYPES[t]} i={i}: {dt:.2f}s")
        m = float(np.mean(ts[1:])) if len(ts) > 1 else ts[0]
        est += m * 300
        log(f"[bench] {COMBO_NAME[k]} 평균 {m:.2f}s/가짜(E+C) → 1단계 300개 ≈ {m * 300:.0f}s(단일 프로세스)")
    log(f"[bench] 1단계 합계 ≈ {est:.0f}s 단일 · 작업자 {workers} 기준 ≈ {est / workers:.0f}s "
        f"(2단계 최악 K1~K4 × 900개 ≈ +{est * 3 / workers:.0f}s)")
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--bench", action="store_true")
    ap.add_argument("--workers", type=int, default=8)
    ap.add_argument("--compare-prev", default=None, help="이전 실행 calib.json — 가짜 p 전부 일치 여부만 기록(결정론 확인)")
    a = ap.parse_args(argv)
    if a.bench:
        return bench(a.workers)
    T0 = time.perf_counter()
    started = datetime.now().isoformat(timespec="seconds")
    sha = git_sha()
    log(f"[시작] {started} · git {sha} · 사전등록 {PREREG} ({PREREG_COMMIT}) · 작업자 {a.workers}")
    full, data, chk = prepare()
    log(f"[입력] features.csv md5 {MD5_EXPECT} 일치 · in_full {chk['n_full']:,}행 · 달력 {chk['n_cal']}일 "
        f"{chk['cal_first']}~{chk['cal_last']} (scan_diag 일치 {chk['cal_eq_scan_diag']})")
    log(f"[에피소드] C 재계산 = ep_first {chk['ep_first_C_match']} ({chk['ep_first_C_n']:,}) · "
        f"E 재계산 {chk['ep_first_E_n']:,} (csv ep_first E True {chk['ep_first_E_csv_true']})")
    for w in WINDOWS:
        log(f"[표본 {w}] 행 {chk[f'rows_{w}']} · 에피소드 {chk[f'eps_{w}']}")

    R: Dict[int, Dict[int, Dict[int, Dict[str, Any]]]] = {k: {t: {} for t in TYPES} for k in COMBOS}
    p3info: Dict[int, Dict[str, Any]] = {}
    tsum: Dict[int, float] = {}
    idx_of: Dict[int, List[int]] = {k: list(STAGE1) for k in COMBOS}
    stopped = None
    main_k_box: List[Optional[int]] = [None]
    out = BASE

    s6: Dict[str, Any] = {}

    def checkpoint(stage: str) -> None:
        js = dict(prereg=PREREG, prereg_commit=PREREG_COMMIT, stage=stage, git_sha=sha,
                  combos={COMBO_NAME[k]: {TYPES[t]: {str(i): R[k][t][i] for i in sorted(R[k][t])} for t in TYPES}
                          for k in COMBOS},
                  s6_reapply_print_only=dict(main_tool=COMBO_NAME.get(main_k_box[0]), features=s6))
        (out / "calib.json").write_text(json.dumps(_clean(js), ensure_ascii=False), encoding="utf-8")
        (out / "run_log.txt").write_text("\n".join(LOG), encoding="utf-8")

    with ProcessPoolExecutor(max_workers=a.workers, initializer=_init, initargs=(data,)) as ex:
        # ── 1단계: K1~K4 먼저, K0(대조) 마지막
        for k in (1, 2, 3, 4, 0):
            if time.perf_counter() - T0 > TIME_LIMIT_S:
                stopped = f"실행 30분 초과 — {COMBO_NAME[k]} 1단계 전 중단"
                log(f"🔴 {stopped}")
                break
            t1 = time.perf_counter()
            tasks = [(k, t, i, P_CAL) for t in TYPES for i in STAGE1]
            for kk, t, i, res, _ in ex.map(_task, tasks, chunksize=5):
                if i == 1:
                    p3info.setdefault(kk, {})[t] = {w: res[w].pop("p3", None) for w in WINDOWS}
                R[kk][t][i] = res
            tsum[k] = time.perf_counter() - t1
            c = rej_counts(R, k, STAGE1)
            log(f"[1단계] {COMBO_NAME[k]}: " + " · ".join(f"{TYPES[t]} {fr(*c[t])}" for t in TYPES)
                + (f" ⇒ {classify(c)}" if k else " (대조 · 판정 대상 아님)") + f" ({tsum[k]:.0f}s)")
            checkpoint(f"stage1 {COMBO_NAME[k]}")
        verdict1 = {k: classify(rej_counts(R, k, STAGE1)) for k in RANK if all(len(R[k][t]) == 100 for t in TYPES)}
        verdict = dict(verdict1)
        # ── 2단계: 경계 조합 전부(순위 순)
        for k in RANK:
            if stopped or verdict1.get(k) != "경계":
                continue
            if time.perf_counter() - T0 > TIME_LIMIT_S:
                stopped = f"실행 30분 초과 — {COMBO_NAME[k]} 2단계 전 중단"
                log(f"🔴 {stopped}")
                break
            t1 = time.perf_counter()
            tasks = [(k, t, i, P_CAL) for t in TYPES for i in STAGE2]
            for kk, t, i, res, _ in ex.map(_task, tasks, chunksize=5):
                res[WINDOWS[0]].pop("p3", None)
                res[WINDOWS[1]].pop("p3", None)
                R[kk][t][i] = res
            idx_of[k] = STAGE1 + STAGE2
            c = rej_counts(R, k, idx_of[k])
            verdict[k] = stage2_verdict(c)
            tsum[f"{k}_s2"] = time.perf_counter() - t1
            log(f"[2단계] {COMBO_NAME[k]} (400개): " + " · ".join(f"{TYPES[t]} {fr(*c[t])}" for t in TYPES)
                + f" ⇒ {verdict[k]} ({tsum[f'{k}_s2']:.0f}s)")
            checkpoint(f"stage2 {COMBO_NAME[k]}")
        # ── 주 도구: 합격 중 순위 최상위(더 높은 순위가 모두 확정된 뒤)
        main_k = None
        for k in RANK:
            v = verdict.get(k)
            if v is None or v == "경계":
                break
            if v == "합격":
                main_k = k
                break
        main_k_box[0] = main_k
        log("[판정] " + " · ".join(f"{COMBO_NAME[k]} {verdict.get(k, '미실행')}" for k in RANK)
            + f" ⇒ 주 도구 {COMBO_NAME[main_k] if main_k else '미확정'}")
    # ── §6 인쇄(합격 시 · 판정 아님)
    if main_k and not stopped:
        t1 = time.perf_counter()
        P6 = P_S6 if COMBOS[main_k][1] == "P1" else 0
        feat = {col: pd.to_numeric(full[col], errors="coerce").to_numpy(dtype=float) for _, col in RF.FEATS}
        with ProcessPoolExecutor(max_workers=a.workers, initializer=_init, initargs=(dict(data, feat=feat),)) as ex6:
            for fid, res in ex6.map(_task_feature, [(main_k, fid, col, P6, 0) for fid, col in RF.FEATS]):
                s6[fid] = res
        tsum["s6"] = time.perf_counter() - t1
        log(f"[§6] 14특징 주 도구 재적용(인쇄만) {tsum['s6']:.0f}s")
        for fid, col in RF.FEATS:
            log(f"  {fid} {col}: " + " · ".join(f"{w} Δ {fs(s6[fid][w]['delta'])} p {f2(s6[fid][w]['p'], 4)}"
                                                for w in WINDOWS))
    checkpoint("done")
    prev_cmp = None
    if a.compare_prev:
        prev = json.loads(Path(a.compare_prev).read_text(encoding="utf-8"))["combos"]
        cur = json.loads((out / "calib.json").read_text(encoding="utf-8"))["combos"]
        n_eq = n_all = 0
        for cn, tv in cur.items():
            for tn, iv in tv.items():
                for i, r in iv.items():
                    for w in WINDOWS:
                        n_all += 1
                        pv = prev.get(cn, {}).get(tn, {}).get(i, {}).get(w, {})
                        n_eq += int(pv.get("p") == r[w]["p"] and pv.get("p_s") == r[w]["p_s"])
        prev_cmp = dict(path=Path(a.compare_prev).name, n_equal=n_eq, n_total=n_all)
        log(f"[결정론] 이전 실행 calib.json 과 가짜 p(풀링·전략별) 일치 {n_eq}/{n_all}")
    secs = time.perf_counter() - T0
    finished = datetime.now().isoformat(timespec="seconds")
    md = results_md(R, idx_of, verdict1, verdict, main_k, s6, chk, p3info, tsum, sha, started, finished, secs,
                    stopped, prev_cmp)
    (out / "RESULTS.md").write_text("\n".join(md), encoding="utf-8")
    meta = dict(prereg=PREREG, prereg_commit=PREREG_COMMIT, git_sha=sha,
                input=FEATURES_CSV.relative_to(ROOT).as_posix(), determinism_check=prev_cmp,
                input_md5=MD5_EXPECT, checks=chk, workers=a.workers, started=started, finished=finished,
                secs=round(secs, 1), secs_by_step={str(k): round(v, 1) for k, v in tsum.items()}, stopped=stopped,
                seeds=dict(G_stock="default_rng([20261001, 1, i])", G_date="default_rng([20261001, 2, i])",
                           G_AR="default_rng([20261001, 4, i])", perm="default_rng([20261001, 3, k, i, t]) · 창마다 새로",
                           s6="default_rng([20261001, 6, w, f])"),
                n_perm=dict(calib=P_CAL, s6=P_S6), stage1=STAGE1[:1] + STAGE1[-1:], stage2=STAGE2[:1] + STAGE2[-1:],
                verdict_stage1={COMBO_NAME[k]: v for k, v in verdict1.items()},
                verdict={COMBO_NAME[k]: v for k, v in verdict.items()},
                main_tool=COMBO_NAME[main_k] if main_k else None, numpy=np.__version__, pandas=pd.__version__)
    (out / "run_meta.json").write_text(json.dumps(_clean(meta), ensure_ascii=False, indent=1), encoding="utf-8")
    log(f"[끝] {finished} · {secs:.0f}s")
    (out / "run_log.txt").write_text("\n".join(LOG), encoding="utf-8")
    return 0


def _clean(o):
    """JSON 직렬화 — NaN/inf → null · numpy 스칼라·배열 → 파이썬 값."""
    if isinstance(o, dict):
        return {str(k): _clean(v) for k, v in o.items()}
    if isinstance(o, (list, tuple)):
        return [_clean(v) for v in o]
    if isinstance(o, np.ndarray):
        return [_clean(v) for v in o.tolist()]
    if isinstance(o, (bool, np.bool_)):
        return bool(o)
    if isinstance(o, (int, np.integer)):
        return int(o)
    if isinstance(o, (float, np.floating)):
        return float(o) if np.isfinite(o) else None
    return o if o is None or isinstance(o, str) else str(o)


def results_md(R, idx_of, verdict1, verdict, main_k, s6, chk, p3info, tsum, sha, started, finished, secs,
               stopped, prev_cmp=None) -> List[str]:
    run_k = [k for k in (1, 2, 3, 4, 0) if all(len(R[k][t]) >= 100 for t in TYPES)]
    s1 = {k: STAGE1 for k in COMBOS}
    md = ["# 검정 도구 교정 — 결과 (2026-09-26)", "",
          f"- 규범: `{PREREG}`(🔒 동결 `{PREREG_COMMIT}`) · 코드 `tool_calibration/run_calib.py` · git `{sha[:10]}`",
          f"- 입력: `feature_study/features.csv` md5 `{MD5_EXPECT}`(일치) · DB 조회 0",
          "- 🔴 **이 결과는 라이브 변경 근거가 아니다**(§8-5). §6-2 재적용은 **인쇄만** — B 판정(0/14 「없음」) 재개봉 없음.",
          f"- 실행 {started} → {finished} · {secs:.0f}s" + (f" · 🔴 {stopped}" if stopped else ""), ""]
    md += ["## 1. 표본", "",
           f"- in_full {chk['n_full']:,}행(B §2-2 전수 · E∪C) · 달력 {chk['n_cal']}일({chk['cal_first']}~{chk['cal_last']} · "
           f"`scan_diag.csv` scan_date 집합과 같음 {chk['cal_eq_scan_diag']})",
           f"- 에피소드 재계산: C 첫 행 {chk['ep_first_C_n']:,} = `ep_first` 와 행 단위 일치 {chk['ep_first_C_match']} · "
           f"E 첫 행 {chk['ep_first_E_n']:,}(csv `ep_first` 의 E True 는 {chk['ep_first_E_csv_true']} — 문서 §2 P2 대로 재계산)", "",
           "| 창 | " + " | ".join(f"{s} 행 / 에피소드" for s in SHORT) + " |", "|---|---|---|---|"]
    for w in WINDOWS:
        md.append(f"| {w} | " + " | ".join(f"{chk[f'rows_{w}'][s]:,} / {chk[f'eps_{w}'][s]:,}" for s in SHORT) + " |")
    md += ["", "- P3 「비결측 < 3 인 날」 제외(가짜 특징 · 결측 없음 ⇒ 구조로 정해짐): 날 수 / 제외 날 / 제외 행", ""]
    for k in (1, 2):
        if k in p3info:
            info = p3info[k][1]
            md.append(f"  - {COMBO_NAME[k]}: " + " · ".join(
                f"{w} " + ", ".join(f"{s} {v['days']}/{v['days_excl']}/{v['rows_excl']}" for s, v in (info[w] or {}).items())
                for w in WINDOWS))
    md += ["", "## 2. 1단계 — 가짜 특징 `p<0.10` 거부율 (창 E · 판정 대상)", ""]
    md += rate_table(R, run_k, s1, "E")
    md += ["", "| 조합 | 1단계 판정 |", "|---|---|"]
    for k in RANK:
        md.append(f"| {COMBO_NAME[k]} | {verdict1.get(k, '미실행')} |")
    md.append("| K0 (B 원 도구) | 대조(판정 대상 아님) |")
    s2 = [k for k in RANK if len(idx_of[k]) > 100]
    md += ["", "## 3. 2단계 (경계 조합만 · 400개 기준)", ""]
    if s2:
        md += rate_table(R, s2, idx_of, "E")
        md += [""] + [f"- {COMBO_NAME[k]}: 2단계 ⇒ **{verdict[k]}**" for k in s2]
    else:
        md.append("- 경계 조합 없음 ⇒ 2단계 미실행.")
    md += ["", "## 4. 판정 · 주 도구", ""]
    md += [f"- {COMBO_NAME[k]}: **{verdict.get(k, '미실행')}**" for k in RANK]
    if main_k:
        md.append(f"- 🔒 **주 도구 = {COMBO_NAME[main_k]}**(합격 조합 중 §3 순위 최상위 · 더 높은 순위 조합은 모두 확정 불합격).")
    else:
        md += ["- 🔴 **도구 미확정** — 합격 조합 없음(또는 순위 높은 조합 미확정). §5: 후속 검정(NW1 게이트 · 청산 짝 비교 · "
               "무작위 진입 대조군 · 후보 특징) **전부 보류 유지** · 새 도구는 개정문 먼저 + 새 시드."]
    md += ["", "## 5. 인쇄만 — C 창 · `p<0.05` · 전략별 · 에피소드 평균", "", "### 5-1. 창 C `p<0.10` (인쇄만)", ""]
    md += rate_table(R, run_k, idx_of, "C")
    md += ["", "### 5-2. `p<0.05` 거부율 (명목 0.05 · 인쇄만)", ""]
    for w in WINDOWS:
        md += [f"창 {w}", ""] + rate_table(R, run_k, idx_of, w, "p", ALPHA05) + [""]
    md += ["### 5-3. 전략별 Δ_s 검정 `p<0.10` 거부율 (인쇄만 · 창 E)", "",
           "| 조합 | 가짜 | " + " | ".join(SHORT) + " |", "|---|---|---|---|---|"]
    for k in run_k:
        for t in TYPES:
            cells = []
            for j in range(len(SNAMES)):
                c = rej_counts(R, k, idx_of[k], "E", "p_s", ALPHA, j)[t]
                cells.append(fr(*c))
            md.append(f"| {COMBO_NAME[k]} | {TYPES[t]} | " + " | ".join(cells) + " |")
    md += ["", "### 5-4. P2 에피소드 평균 변형 `p<0.10` (병기 · 인쇄만)", ""]
    for w in WINDOWS:
        md += [f"창 {w}", ""] + rate_table(R, [k for k in (2, 4) if k in run_k], idx_of, w, "p_epmean") + [""]
    md += ["## 6. K0 재현 (B V-F5 = 0.34 · `p<0.05` 0.23)", ""]
    if 0 in run_k:
        c = rej_counts(R, 0, STAGE1)
        c5 = rej_counts(R, 0, STAGE1, "E", "p", ALPHA05)
        r0 = c[1][0] / c[1][1]
        se0 = math.sqrt(0.34 * 0.66 / c[1][1])
        md.append(f"- K0 · G-종목 · 창 E: `p<0.10` **{fr(*c[1])}** · `p<0.05` {fr(*c5[1])} "
                  f"(B V-F5 0.34 / 0.23 · 가짜·순열 난수가 달라 «가까운 값»이 재현 — 해석 기록 16)")
        md.append(f"- 차이 {r0 - 0.34:+.2f} = 이항 SE(0.34 · {c[1][1]}개) {se0:.3f} 의 {abs(r0 - 0.34) / se0:.1f}배 · "
                  f"K0 거부율은 명목 0.10 의 {r0 / 0.10:.1f}배(B V-F5 는 3.4배)"
                  + (" — 「B 도구는 G-종목에서 과대 거부」가 재현됐다." if 100 * c[1][0] > 16 * c[1][1] else
                     " — 🔴 과대 거부가 재현되지 않았다(0.16 이하)."))
    md += ["", "## 7. §6 인쇄 (판정 아님)", ""]
    if main_k and s6:
        md += s6_md(R, idx_of, main_k, s6)
    else:
        md.append("- 합격 조합 없음 ⇒ §6 미실행.")
    md += ["", "## 8. 해석 기록 (문서가 정하지 않은 구현 선택 · 결과를 보기 «전»에 코드에 고정)", ""] + INTERP
    md += ["", "## 9. 문서와 다르게 한 것", "", "- 없음(모든 🔒 항목 문서 그대로 · 구현 선택은 §8 해석 기록)."]
    md += ["", "## 10. 한계 (문서 §10 인용)", ""] + LIMITS
    s6perm = f"{P_S6:,}회(§6)" if main_k and COMBOS[main_k][1] == "P1" else "§6 0회(주 도구 P2)"
    md += ["", "## 11. 실행 지문", "",
           f"- git `{sha}` · 입력 md5 `{MD5_EXPECT}` · 순열 {P_CAL:,}회(교정) / {s6perm}",
           "- 시간(초): " + " · ".join(f"{k}={v:.0f}" for k, v in tsum.items()),
           "- 산출물: `run_calib.py` · `RESULTS.md` · `calib.json`(조합×종류×가짜 번호별 p · 창별 · §6 재적용 값) · "
           "`run_log.txt` · `run_meta.json`"]
    if prev_cmp:
        md.append(f"- 결정론 확인: 1차 실행(보고 형식 수정 «전») `calib.json` 과 가짜 p(풀링·전략별) "
                  f"**{prev_cmp['n_equal']:,}/{prev_cmp['n_total']:,} 일치** — 이번 실행은 같은 시드·같은 코드 경로의 재실행이며 "
                  "바뀐 것은 문서 형식(거부율 소수 3자리 · §6 주석 · K0 이항 SE 줄)과 §6 값을 `calib.json` 에 저장한 것뿐이다.")
    md.append("")
    return md


def s6_md(R, idx_of, main_k, s6) -> List[str]:
    kind = COMBOS[main_k][1]
    md = [f"주 도구 {COMBO_NAME[main_k]} · SD_null = " + ("순열 Δ 표준편차(10,000회)" if kind == "P1" else "CR1 SE"),
          ""]
    if kind == "P2":
        md += ["- 주 도구가 P2(CR1 분석식 · 정규 근사 p)라 §6 에는 **순열이 없다**(0회) — 문서 §3 의 「10,000회(§6)」와 "
               "해석 기록 14 의 §6 시드는 순열 도구일 때만 해당하며 이번에는 쓰이지 않았다.",
               "- 풀링 SD = Δ_pool 의 CR1 SE(전략을 가로지르는 종목 클러스터 · 해석 기록 5) · 전략 SD = Δ_s 의 CR1 SE · "
               "표본 수(에피소드 첫 행)는 §7-2 표의 n.", ""]
    md += [ "### 7-1. 검정력 표 — MDE = 2.80 × SD_null(단일 · 양측 0.05 · 80%) · Holm m=14 1단계 = 3.75 × SD_null (%p)", ""]
    for w in WINDOWS:
        md += [f"창 {w}", "", "| 특징 | 풀링 SD / MDE / Holm | " + " | ".join(f"{s} SD / MDE / Holm" for s in SHORT) + " |",
               "|---|---|---|---|---|"]
        for t in TYPES:
            idx = idx_of[main_k]
            sd = np.nanmean([R[main_k][t][i][w]["sd"] for i in idx])
            sds = [np.nanmean([R[main_k][t][i][w]["sd_s"][j] for i in idx]) for j in range(len(SNAMES))]
            md.append(f"| {TYPES[t]}(평균 {len(idx)}개) | {_mde(sd)} | " + " | ".join(_mde(v) for v in sds) + " |")
        for fid, col in RF.FEATS:
            r = s6[fid][w]
            md.append(f"| {fid} `{col}` | {_mde(r['sd'])} | " + " | ".join(_mde(v) for v in r["sd_s"]) + " |")
        md.append("")
    md += ["### 7-2. B 14특징 주 도구 재적용 — 🔴 인쇄만", "",
           "> 🔴 B 판정(「특징 있음」 0/14)은 **재개봉하지 않는다.** 아래 p 가 작아도 「있음」 선언 금지 · 「경향」「약한 신호」 등 "
           "중간 언어 금지. 작은 p 특징을 다음 사전등록 후보로 쓰려면 **새 표본(라이브 전수 저장 2026-09-28~ 전향분)** 에서만.", ""]
    for w in WINDOWS:
        md += [f"창 {w}", "", "| 특징 | Δ_pool(%p) | p | " + " | ".join(f"{s} Δ_s (n)" for s in SHORT) + " |",
               "|---|---|---|---|---|---|"]
        for fid, col in RF.FEATS:
            r = s6[fid][w]
            cells = [f"{fs(r['delta_s'][j])} ({int(r['n'][j]):,}{'' if r['ok'][j] else ' ✗n<30'})"
                     for j in range(len(SNAMES))]
            md.append(f"| {fid} `{col}` | {fs(r['delta'])} | {f2(r['p'], 4)} | " + " | ".join(cells) + " |")
        md.append("")
    md += ["### 7-3. 전 조합 거부율 표", "",
           "- 위 §2(1단계)·§3(2단계)·§5(C·`p<0.05`·전략별·에피소드 평균) 가 합격·불합격 조합 모두의 전체 표다(은닉 없음).", ""]
    return md


def _mde(sd) -> str:
    if sd is None or not np.isfinite(sd):
        return "—"
    return f"{sd:.3f} / {MDE_K * sd:.2f} / {MDE_HOLM * sd:.2f}"


if __name__ == "__main__":
    sys.exit(main())
