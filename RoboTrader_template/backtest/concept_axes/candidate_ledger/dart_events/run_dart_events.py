"""연구 ① DART 공시 «유형» 이벤트 — 사전등록 `docs/prereg_2026-09-26_dart_disclosure_events.md`(🔒 동결 af3773f) §4~§7.

    cd <worktree>/RoboTrader_template
    $PY -m backtest.concept_axes.candidate_ledger.dart_events.run_dart_events --stage seal      # ④ 봉인 단계
    $PY -m backtest.concept_axes.candidate_ledger.dart_events.run_dart_events --stage unseal    # ⑤ 개봉(봉인 커밋 뒤)

🔴 봉인 단계(④)는 «실제 이벤트 × 결과(ret)» 조인을 하지 않는다 — 구조로 막는다:
   · 격자 결과는 `GridExit`(청산 사유·청산일·R4·R5·corp 플래그 = 결과 의존 «제외» 판정용)와 ret 행렬로 나뉜다.
   · 실제 이벤트 경로(`event_exclusions`)는 `GridExit` 만 받는다. ret 은 `blinded_ret(t)` 로만 읽고, 그 사본은
     태그 t 원공시 칸(u(r), 종목)이 전부 NaN 이다 ⇒ 대조·가짜에서 NaN 을 만나면 즉시 중단(봉인 위반).
   · (a) 특징 열은 `features.csv` 에서 ret 열을 «읽지 않고»(usecols) 만든다.
🔴 개봉 단계(⑤)는 `results/sealed_report.md` 가 있어야만 돈다. 판정 언어 = 있음(+/−) · 없음 · 판별 보류 뿐.
🔴 DB SELECT 만(`bootstrap` = 읽기 전용 세션) · 라이브 코드 import 만 · 재사용 모듈 수정 0줄.
재사용: 청산 = `exit_diag/run_random_entry.sim_fast`(재현 가드 뒤) · 사이징 = `ledger8/sizing.arm_b_qty` ·
tp/sl = `sellprobe8.resolve_live_tp_sl` · 유니버스 = `replayer/loader.{build_universe, universe_snapshot, classify_exclusions}` ·
불가능봉 = `replayer/flags.compute_bar_flags`(padding ∨ locked_limit ∨ cliff · 원장 `run.py:781` 합성) ·
p = `run_random_entry.p2_binary` 와 같은 식(빠른 bincount 판 · 태그마다 원 함수와 대조) · 에피소드(a) = `run_calib.episodes`.
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
from datetime import date, datetime                                    # noqa: E402
from pathlib import Path                                               # noqa: E402
from typing import Any, Dict, List, Optional, Sequence, Tuple          # noqa: E402

import numpy as np                                                     # noqa: E402
import pandas as pd                                                    # noqa: E402

from backtest.concept_axes.candidate_ledger import run as R            # noqa: E402
from backtest.concept_axes.candidate_ledger.dart_events import dart_tags as DT  # noqa: E402
from backtest.concept_axes.candidate_ledger.exit_diag import run_random_entry as RE  # noqa: E402
from backtest.concept_axes.candidate_ledger.tool_calibration import run_calib as RC  # noqa: E402
from backtest.concept_axes.ledger8 import exitsim8 as X                # noqa: E402
from backtest.concept_axes.ledger8 import sellprobe8 as SP             # noqa: E402
from backtest.concept_axes.ledger8 import sizing as Z                  # noqa: E402
from backtest.concept_axes.ledger8.livesignal8 import load8            # noqa: E402
from backtest.concept_axes.replayer import flags as FL                 # noqa: E402
from backtest.concept_axes.replayer import loader as LD                # noqa: E402

warnings.filterwarnings("ignore", message="pandas only supports SQLAlchemy")

BASE = Path(__file__).resolve().parent
RES = BASE / "results"
CACHE = BASE / "cache"                                  # .gitignore(cache/) — 격자·체크포인트
LEDGER_DIR = Path("D:/research-archive/candidate_ledger_20260924")
MD5_LEDGER = "980e58492a7ac2ed11d25526f4488dbc"
MD5_FEATURES = "12216fe9359f5c21d9831400502730eb"
PREREG = R.ROOT / "docs" / "prereg_2026-09-26_dart_disclosure_events.md"

# ── 🔒 사전등록 값 ────────────────────────────────────────────────────────────
FOLDER = "book_pullback_ma20"
EXPECT_RULES = (0.10, 0.08, 50)                         # §6 (tp, sl, max_hold) — 다르면 중단
PX_START, W_END = R.PX_START, "2026-09-23"              # 워밍업 · 보유 경로 끝
U_MIN, U_MAX = "2024-03-21", "2026-07-13"               # §4 워밍업 · §6 상한
A_SCAN_MIN = "2024-03-20"                               # §5 (a) scan_date ≥
E_END = "2025-06-30"                                    # §8 반창 E / C(인쇄만)
SEED = 20261004
N_CTRL, N_FAKE, MAX_REDRAW = 20, 400, 20
EP_GAP = 5                                              # 에피소드: 직전 이벤트 u 로부터 ≤ 5거래일
W5 = 4                                                  # u(r) ∈ [X−4, X]
FAKE_P, FAKE_MAX = 0.10, 0.13
MIN_N, HOLM_M, ALPHA = 30, 7, 0.05
T_MIN, ASYM_MAX = 0.4, 0.02
K_MDE = 3.53
COST = 0.25
BLOCK = 20
GUARD_TOL = 0.001
RET_TOL = RE.RET_TOL
PILOT_MONTH = "2025-03"
CAP_S = 1800.0                                          # §12 30분(검정 실행)
A_WINDOWS = {"W5": (4, 0), "W1": (0, 0), "W20": (19, 0), "Dx": (5, 1)}   # rcept_dt ∈ [D−a, D−b] 거래일(§5 식 그대로)
TAGS = DT.TAGS
RSN = ["open", "tp", "sl", "max_hold", "trail_ma"]
LAB_UP, LAB_DN, LAB_NONE, LAB_HOLD = "있음(+)", "있음(−)", "없음", "판별 보류"
LAB_HOLD_TOOL = "판별 보류(도구)"


def log(msg: str = "") -> None:
    print(msg, file=sys.stderr, flush=True)


def md5(p: Path) -> str:
    h = hashlib.md5()
    with open(p, "rb") as fh:
        for b in iter(lambda: fh.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest()


def rng_of(*key: int) -> np.random.Generator:
    return np.random.default_rng([int(k) for k in key])


def check_inputs() -> Dict[str, str]:
    got = {"ledger.csv": md5(LEDGER_DIR / "ledger.csv"), "features.csv": md5(LEDGER_DIR / "features.csv")}
    if got["ledger.csv"] != MD5_LEDGER or got["features.csv"] != MD5_FEATURES:
        raise SystemExit(f"🔴 입력 md5 불일치 {got} — 중단(§5)")
    return got


# ════════════════════════════════════════════════════════════════════════════
# 1. 로드 · 시장 행렬
# ════════════════════════════════════════════════════════════════════════════
class Env:
    """로드된 시장 — 달력·행렬·유니버스(U(e))·시총 분위·격자 마스크·불가능봉/corp 날짜."""

    def __init__(self) -> None:
        t = time.perf_counter()
        self.sha = R.git_sha()
        self.blobs = R.guard_blobs()
        self.strategy = load8(FOLDER)
        self.rules = SP.resolve_live_tp_sl(FOLDER, self.strategy)
        got = (round(self.rules.tp, 9), round(self.rules.sl, 9), int(self.rules.max_hold_days))
        if got != EXPECT_RULES:
            raise SystemExit(f"🔴 tp/sl/max_hold {got} ≠ §6 {EXPECT_RULES} — 중단")
        conn = R._connect()
        self.cal = [pd.Timestamp(x).date() for x in LD.load_trading_calendar(conn, PX_START, W_END)]
        self.fp = LD.db_fingerprint(conn, PX_START, W_END)
        px = LD.load_prices(conn, PX_START, W_END)
        self.normalize_counts = px.attrs.get("normalize_counts")
        bad_open = R.load_bad_open(conn, PX_START, W_END)
        self.names = LD.load_stock_names(conn)
        corp = LD.load_corp_events(conn)
        cur = conn.cursor()
        cur.execute("SELECT rcept_no, stock_code, report_nm, rcept_dt FROM dart_disclosures ORDER BY rcept_no")
        self.dart = pd.DataFrame(cur.fetchall(), columns=["rcept_no", "stock_code", "report_nm", "rcept_dt"])
        cur.execute("SELECT count(*), max(fetched_at) FROM dart_disclosures")
        n_rows, max_f = cur.fetchone()
        self.dart_meta = dict(rows=int(n_rows), max_fetched_at=str(max_f))
        conn.close()
        self.mk = RE.build_market(px, self.cal, bad_open)
        mk = self.mk
        self.nC, self.nS = mk.n_cal, mk.n_stock
        self.kidx = {c: i for i, c in enumerate(mk.codes)}
        self.cal_i = {d: i for i, d in enumerate(self.cal)}
        self.HC, self.HCm1 = RE.holiday_counts(self.cal)
        self.spec = RE.spec_of(FOLDER, self.strategy, self.rules)
        self.iu0 = int(np.searchsorted(mk.cal64, np.datetime64(U_MIN), side="left"))
        self.iu1 = int(np.searchsorted(mk.cal64, np.datetime64(U_MAX), side="right")) - 1
        if self.cal[self.iu0].isoformat() != U_MIN or self.cal[self.iu1].isoformat() != U_MAX:
            raise SystemExit(f"🔴 달력 {self.cal[self.iu0]}~{self.cal[self.iu1]} ≠ §4·§6 {U_MIN}~{U_MAX} — 중단")
        if self.cal[-1].isoformat() != W_END or self.iu1 + 50 > len(self.cal) - 1:
            raise SystemExit("🔴 상한 산식(u 순번 + 50 ≤ 2026-09-23 순번) 불일치 — 중단")
        log(f"[로드] 달력 {len(self.cal)}일 · px {len(px):,}행 · 종목 {self.nS:,} · dart {len(self.dart):,}행 · "
            f"지문 {self.fp['sha256'][:12]} · {time.perf_counter() - t:.0f}s")
        # ── 불가능봉 · corp 날짜(원장 `run.py:781-782` 합성 · any_in 과 같은 판정) ──
        t = time.perf_counter()
        fl = FL.compute_bar_flags(px)
        m_imp = fl["flag_padding"] | fl["flag_locked_limit"] | fl["flag_cliff"]
        self.imp_dates = R._date_index(zip(px.loc[m_imp, "stock_code"], px.loc[m_imp, "date"]))
        self.corp_dates = R._date_index(corp.keys())
        self.n_imp = int(m_imp.sum())
        # ── U(e): 원시(R1 판정) · 배제 뒤(R2 · 대조 풀) · 시총 분위 ──
        uni = LD.build_universe(px)
        del px, fl
        codes_all = sorted(set(self.mk.codes.tolist()) | set(self.dart["stock_code"].dropna().astype(str)))
        cls = LD.classify_exclusions(codes_all, self.names)
        self.excluded = {c: bool(v["excluded"]) for c, v in cls.items()}
        ex_vec = np.array([self.excluded[c] for c in mk.codes], dtype=bool)
        self.UR = np.zeros((self.nC, self.nS), dtype=bool)           # 원시 U(e)
        self.MC = np.full((self.nC, self.nS), np.nan)
        for e in range(self.iu0 - 1, self.iu1 + 1):
            snap = LD.universe_snapshot(uni, pd.Timestamp(self.cal[e]))
            for c, (mc, _tv) in snap["rows"].items():
                k = self.kidx.get(c)
                if k is not None:
                    self.UR[e, k] = True
                    self.MC[e, k] = mc
        self.UM = self.UR & ~ex_vec[None, :]                          # U(e) = 배제 뒤
        self.Q = np.zeros((self.nC, self.nS), dtype=np.int8)          # 시총 5분위(0 = U(e) 밖)
        for e in range(self.iu0 - 1, self.iu1):
            ks = np.flatnonzero(self.UM[e])
            if len(ks):
                q = pd.Series(self.MC[e, ks]).rank(pct=True).to_numpy()
                self.Q[e, ks] = 1 + (q > 0.2).astype(int) + (q > 0.4) + (q > 0.6) + (q > 0.8)
        # 격자 마스크: u ∈ [U_MIN, U_MAX] · 종목 ∈ U(u−1) · u 봉 · 원본 시가 > 0
        self.GM = np.zeros((self.nC, self.nS), dtype=bool)
        sl = slice(self.iu0, self.iu1 + 1)
        self.GM[sl] = (self.UM[self.iu0 - 1:self.iu1] & mk.HAS[sl] & ~mk.BAD[sl]
                       & (np.nan_to_num(mk.O[sl], nan=0.0) > 0))
        self.block = np.full(self.nC, -1, dtype=np.int64)
        self.block[sl] = (np.arange(self.iu0, self.iu1 + 1) - self.iu0) // BLOCK
        log(f"[유니버스] U(e) 평균 {self.UM[self.iu0 - 1:self.iu1].sum(1).mean():,.0f} · 격자 {int(self.GM.sum()):,} 로트 · "
            f"불가능봉 {self.n_imp:,} · {time.perf_counter() - t:.0f}s")


# ════════════════════════════════════════════════════════════════════════════
# 2. 격자 — (종목, 진입일 u) 로트 청산(sim_fast · 재현 가드 뒤)
# ════════════════════════════════════════════════════════════════════════════
class Grid:
    """RSN(사유 코드 · −1 = 미계산) · XI(청산 달력 index) · R4 · CORP 는 `GridExit` · RET/XPX 는 ret 쪽."""

    def __init__(self, env: Env, path: str):
        self.env = env
        self.path = path
        n = (env.nC, env.nS)
        self.RSN = np.full(n, -1, dtype=np.int8)
        self.XI = np.full(n, -1, dtype=np.int32)
        self.R4 = np.zeros(n, dtype=bool)
        self.CORP = np.zeros(n, dtype=bool)
        self._RET = np.full(n, np.nan)
        self._XPX = np.full(n, np.nan)
        self.n_sim = 0
        self.secs = 0.0
        self.reasons = list(RSN)
        self._probe = None

    def _rcode(self, r: str) -> int:
        if r not in self.reasons:
            self.reasons.append(r)
        return self.reasons.index(r)

    def compute(self, us: np.ndarray, ks: np.ndarray) -> None:
        """미계산 칸만 계산(종목별로 묶어 StockView 1회)."""
        env, mk = self.env, self.env.mk
        need = self.RSN[us, ks] < 0
        us, ks = us[need], ks[need]
        if not len(us):
            return
        cells = np.unique(np.stack([ks, us], axis=1), axis=0)          # (k, u) 사전순 = 종목별 묶음
        t = time.perf_counter()
        end64 = np.datetime64(W_END)
        cuts = np.flatnonzero(np.diff(cells[:, 0])) + 1
        for grp in np.split(cells, cuts):
            k = int(grp[0, 0])
            uu = grp[:, 1]
            if self.path == "vector":
                sv = RE.StockView(mk, int(k))
                out = [RE.sim_fast(env.spec, sv, int(u), env.nC, env.HC, env.HCm1) for u in uu.tolist()]
            else:
                out = self._orig(int(k), uu)
            xi = np.array([o[1] for o in out], dtype=np.int64)
            self.RSN[uu, k] = [self._rcode(o[0]) for o in out]
            self.XI[uu, k] = xi
            self._RET[uu, k] = [o[2] for o in out]
            self._XPX[uu, k] = [o[3] for o in out]
            code = str(mk.codes[k])
            ent = mk.cal64[uu]
            end = np.where(xi >= 0, mk.cal64[np.maximum(xi, 0)], end64)
            for arr, dts in ((self.R4, env.imp_dates.get(code)), (self.CORP, env.corp_dates.get(code))):
                if dts is None or not len(dts):
                    continue
                j = np.searchsorted(dts, ent, side="left")
                arr[uu, k] = (j < len(dts)) & (dts[np.minimum(j, len(dts) - 1)] <= end)
        self.n_sim += len(cells)
        self.secs += time.perf_counter() - t

    def _orig(self, k: int, uu: np.ndarray) -> List[Tuple[str, int, float, float]]:
        """대체 경로(재현 가드 불일치 > 0.1%) — 원 코드 `simulate_lot` + `SellProbe`(원장 `run.lot_row` 호출 그대로)."""
        env, mk = self.env, self.env.mk
        if self._probe is None:
            raise SystemExit("🔴 대체 경로 준비 안 됨")
        renv, probe = self._probe
        code = str(mk.codes[k])
        bars = renv.bars(code)
        out = []
        for u in uu.tolist():
            d1 = env.cal[u]
            px_open = float(bars[d1].open)
            q = Z.arm_b_qty(px_open)
            pos = X.Pos(code, d1, R.SRC8.aware(datetime.combine(d1, R.ENTRY_TIME)), px_open, q.qty, X.BASIS_D_OPEN)
            ex = X.simulate_lot(pos, env.rules, R.build_path(env.cal, renv.cal_idx, bars, d1, env.rules.max_hold_days),
                                probe)
            if ex.closed and ex.exit_date is not None:
                out.append((ex.reason, env.cal_i[ex.exit_date], ex.ret_pct, ex.price))
            else:
                out.append(("open", -1, float("nan"), float("nan")))
        return out

    def fail(self, us: np.ndarray, ks: np.ndarray) -> np.ndarray:
        """R4 ∨ R5(청산 안 됨 = 경로 중 봉 끊김 · 상한 안) — 결과 의존 «제외» 판정(대조·가짜 재추출용)."""
        self.compute(us, ks)
        return self.R4[us, ks] | (self.RSN[us, ks] == 0)

    def exit_view(self) -> "GridExit":
        return GridExit(self)

    def blinded_ret(self, cells_t: Tuple[np.ndarray, np.ndarray]) -> np.ndarray:
        """봉인 단계 ret 사본 — 태그 t 원공시 칸(u(r), 종목)을 NaN 으로 가린다."""
        r = self._RET.copy()
        r[cells_t] = np.nan
        return r

    def unsealed_ret(self) -> Tuple[np.ndarray, np.ndarray]:
        return self._RET, self._XPX


class GridExit:
    """실제 이벤트 경로가 받는 유일한 격자 보기 — ret 없음."""

    def __init__(self, g: Grid):
        self._g = g

    def flags(self, us: np.ndarray, ks: np.ndarray) -> Dict[str, np.ndarray]:
        self._g.compute(us, ks)
        rsn = self._g.RSN[us, ks]
        r4 = self._g.R4[us, ks].copy()
        return dict(R4=r4, R5=(rsn == 0) & ~r4, corp=self._g.CORP[us, ks])


def repro_guard(env: Env) -> Dict[str, Any]:
    """§6 재현 가드 — 원장 ma20 `in_full` 로트 전부를 sim_fast 로 재계산 · (사유, 청산일, ret_pct) 대조."""
    led = pd.read_csv(LEDGER_DIR / "ledger.csv", dtype=str, keep_default_na=False,
                      usecols=["strategy", "scan_date", "stock_code", "exit_reason", "exit_date", "ret_pct"])
    fe = pd.read_csv(LEDGER_DIR / "features.csv", dtype=str, keep_default_na=False,
                     usecols=["strategy", "scan_date", "stock_code", "in_full"])
    key = ["strategy", "scan_date", "stock_code"]
    L = led[led["strategy"] == FOLDER].merge(fe[(fe["strategy"] == FOLDER) & (fe["in_full"] == "True")][key],
                                             on=key, how="inner")
    mk = env.mk
    res = []
    for code, sub in L.groupby("stock_code", sort=True):
        sv = RE.StockView(mk, env.kidx[code])
        for d in sub["scan_date"].tolist():
            e = env.cal_i[date.fromisoformat(d)] + 1
            rs, xi, rt, _xp = RE.sim_fast(env.spec, sv, e, env.nC, env.HC, env.HCm1)
            res.append((rs, env.cal[xi].isoformat() if xi >= 0 else "", rt))
    L = L.sort_values("stock_code", kind="mergesort")
    g = RE.guard_compare([r[0] for r in res], [r[1] for r in res], [r[2] for r in res], L["exit_reason"].tolist(),
                         L["exit_date"].tolist(), pd.to_numeric(L["ret_pct"]).tolist())
    g["rate"] = g["any"] / max(1, g["n"])
    g["path"] = "vector" if g["rate"] <= GUARD_TOL else "fallback"
    return g


# ════════════════════════════════════════════════════════════════════════════
# 3. 이벤트 — 태그 · u · e · 중복 · 창 · R1 · 에피소드 · R2 (결과 열 없음)
# ════════════════════════════════════════════════════════════════════════════
def tag_rows(env: Env) -> pd.DataFrame:
    d = env.dart.copy()
    tg = [DT.tag_of(x) for x in d["report_nm"].tolist()]
    d["tag"] = [x[0] for x in tg]
    d["is_corr"] = [x[1] for x in tg]
    d["t"] = [int(x[2]["t"]) for x in tg]
    d["mgmt_dispute"] = [bool(x[2]["mgmt_dispute"]) for x in tg]
    d["stock_code"] = d["stock_code"].where(d["stock_code"].notna(), None)
    d["rcept_dt"] = pd.to_datetime(d["rcept_dt"]).dt.date
    cal64 = env.mk.cal64
    rd = pd.to_datetime(d["rcept_dt"]).to_numpy(dtype="datetime64[ns]")
    d["u_i"] = np.searchsorted(cal64, rd, side="right")          # rcept_dt «초과» 첫 거래일
    d["e_i"] = d["u_i"] - 1                                       # rcept_dt 이하 마지막 거래일
    d["k"] = [env.kidx.get(c, -1) if c else -1 for c in d["stock_code"].tolist()]
    return d


def tag_cells(env: Env, rows: pd.DataFrame, t: int, with_corr: bool = False) -> Tuple[np.ndarray, np.ndarray]:
    """태그 t 원공시(정정 포함판이면 정정도)의 (u(r), 종목) 칸 — W5 표시·봉인 가림에 쓴다."""
    m = (rows["t"] == t) & (rows["k"] >= 0) & (rows["u_i"] < env.nC)
    if not with_corr:
        m &= ~rows["is_corr"]
    s = rows[m]
    return s["u_i"].to_numpy(dtype=np.int64), s["k"].to_numpy(dtype=np.int64)


def w5_matrix(env: Env, cells: Tuple[np.ndarray, np.ndarray]) -> np.ndarray:
    """TE[X, k] = 종목 k 에 u(r) ∈ [X−4, X] 인 태그 t 원공시가 있다(V3: u(r) ≤ X 만 씀)."""
    D = np.zeros((env.nC + W5 + 2, env.nS), dtype=np.int32)
    u, k = cells
    np.add.at(D, (u, k), 1)
    np.add.at(D, (u + W5 + 1, k), -1)
    return np.cumsum(D, axis=0)[:env.nC] > 0


def episodes_b(u: np.ndarray, key: np.ndarray) -> np.ndarray:
    """같은 key(=(t,g)) 에서 직전 이벤트 u 로부터 ≤ 5거래일 ⇒ 같은 묶음 · 첫 이벤트만 True. 입력은 (u, g, rcept_no) 순."""
    first = np.zeros(len(u), dtype=bool)
    last: Dict[Any, int] = {}
    for i, (uu, kk) in enumerate(zip(u.tolist(), key.tolist())):
        p = last.get(kk)
        first[i] = p is None or uu - p > EP_GAP
        last[kk] = uu
    return first


def build_events(env: Env, rows: pd.DataFrame, t: int, with_corr: bool = False) -> pd.DataFrame:
    """태그 t 이벤트 표(결과 열 없음) — 순서 (u, g, rcept_no) · 플래그: dup · in_window · null_code · R1(a/b) · first · R2 · R3."""
    m = rows["t"] == t
    if not with_corr:
        m &= ~rows["is_corr"]
    ev = rows[m].copy()
    ev["null_code"] = ev["stock_code"].isna()
    ev = ev.sort_values(["rcept_no"], kind="mergesort")
    ev["dup"] = ev.duplicated(subset=["t", "stock_code", "rcept_dt"], keep="first") & ~ev["null_code"]
    ev["in_window"] = (ev["u_i"] >= env.iu0) & (ev["u_i"] <= env.iu1)
    ev["code_s"] = ev["stock_code"].fillna("")
    ev = ev.sort_values(["u_i", "code_s", "rcept_no"], kind="mergesort").reset_index(drop=True)
    cand = ev["in_window"] & ~ev["null_code"] & ~ev["dup"]
    k = ev["k"].to_numpy()
    e = ev["e_i"].to_numpy()
    joined = np.zeros(len(ev), dtype=bool)
    ok = cand.to_numpy() & (k >= 0)
    joined[ok] = env.UR[e[ok], k[ok]]
    ev["R1"] = cand & ~joined
    ev["R1a"] = ev["R1"] & (k < 0)                                # daily_prices 에 없음(상폐 탈락 등)
    ev["R1b"] = ev["R1"] & (k >= 0)                               # e 에 시총 없음
    ev["joined"] = cand & joined
    ev["first"] = False
    ev["R1_first"] = False
    for col, src in (("first", "joined"), ("R1_first", "R1")):
        s = ev[ev[src]]
        ev.loc[s.index, col] = episodes_b(s["u_i"].to_numpy(), s["code_s"].to_numpy())
    ev["R2"] = [bool(env.excluded.get(c, False)) if c else False for c in ev["code_s"].tolist()]
    q = np.zeros(len(ev), dtype=np.int8)
    jj = ev["joined"].to_numpy()
    q[jj] = env.Q[e[jj], k[jj]]
    ev["q"] = q
    lot = (ev["first"] & ~ev["R2"]).to_numpy()
    u = ev["u_i"].to_numpy()
    r3 = np.zeros(len(ev), dtype=bool)
    r3[lot] = ~env.GM[u[lot], k[lot]]
    ev["R3"] = r3
    ev["cand_lot"] = lot                                          # 대조 추출 대상(R3~R5 전)
    return ev


# ════════════════════════════════════════════════════════════════════════════
# 4. 대조 풀 · 추출
# ════════════════════════════════════════════════════════════════════════════
class Pools:
    """(u, 분위 키) 별 대조 풀 — 종목코드 오름차순 · PAD[pid, r] = r 번째 종목 · RANK[pid, k] = 풀 안 위치(−1 = 밖)."""

    def __init__(self, env: Env, TE: np.ndarray, u: np.ndarray, qkey: np.ndarray, QK: Optional[np.ndarray] = None):
        keys = np.stack([u, qkey], axis=1)
        uk, pid = np.unique(keys, axis=0, return_inverse=True)
        self.pid = pid.astype(np.int64).ravel()
        lists = []
        for uu, qq in uk.tolist():
            qm = (env.Q[uu - 1] == qq) if QK is None else (QK[uu] == qq)
            lists.append(np.flatnonzero(env.GM[uu] & qm & ~TE[uu]))
        self.size = np.array([len(x) for x in lists], dtype=np.int64)
        self.PAD = np.zeros((len(lists), max(1, int(self.size.max()) if len(lists) else 1)), dtype=np.int64)
        self.RANK = np.full((len(lists), env.nS), -1, dtype=np.int32)
        for i, x in enumerate(lists):
            self.PAD[i, :len(x)] = x
            self.RANK[i, x] = np.arange(len(x))

    def member(self, pid: np.ndarray, h: np.ndarray) -> np.ndarray:
        return self.RANK[pid, h] >= 0


def draw_uniform(rng: np.random.Generator, P: Pools, pid: np.ndarray, excl: Optional[np.ndarray] = None) -> np.ndarray:
    """풀에서 균등 1개(복원) — 이벤트 순서 벡터 소비 · excl(종목)이 있으면 그 종목을 뺀 풀. 빈 풀 = −1(소비 없음)."""
    size = P.size[pid] - (0 if excl is None else (P.RANK[pid, excl] >= 0).astype(np.int64))
    h = np.full(len(pid), -1, dtype=np.int64)
    ok = size > 0
    if ok.any():
        j = rng.integers(0, size[ok])
        if excl is not None:
            rk = P.RANK[pid[ok], excl[ok]]
            j = j + ((rk >= 0) & (j >= rk))
        h[ok] = P.PAD[pid[ok], j]
    return h


def draw_with_redraw(rng: np.random.Generator, P: Pools, pid: np.ndarray, u: np.ndarray, grid: Grid,
                     excl: Optional[np.ndarray] = None, h0: Optional[np.ndarray] = None) -> Dict[str, Any]:
    """§6 대조 추출 + R4·R5 재추출 — 첫 추출(이벤트 순서) → 실패 로트를 같은 rng 로 같은 풀에서 재추출(라운드마다
    이벤트 순서 · 최대 20회) → 그래도 실패면 −1(비움). h0 가 주어지면 첫 추출을 대신한다(가짜 이벤트 매핑)."""
    h = draw_uniform(rng, P, pid, excl) if h0 is None else h0.copy()
    has = h >= 0
    fail = np.zeros(len(h), dtype=bool)
    fail[has] = grid.fail(u[has], h[has])
    first_fail = int(fail.sum())
    n_first = int(has.sum())
    n_redraw = 0
    for _ in range(MAX_REDRAW):
        idx = np.flatnonzero(fail)
        if not len(idx):
            break
        hn = draw_uniform(rng, P, pid[idx], None if excl is None else excl[idx])
        n_redraw += len(idx)
        h[idx] = hn
        ok = hn >= 0
        f = np.zeros(len(idx), dtype=bool)
        f[ok] = grid.fail(u[idx][ok], hn[ok])
        fail[idx] = f
    n_empty = int(fail.sum()) + int((~has).sum())
    h[fail] = -1
    return dict(h=h, n_first=n_first, first_fail=first_fail, n_redraw=n_redraw, n_empty=n_empty)


def fake_groups(pid: np.ndarray, g: np.ndarray) -> List[Tuple[int, np.ndarray]]:
    """g 의 첫 등장 이벤트 풀 키 → [(pid, 그 키에 처음 나온 g 들(오름차순))] · 순서 = 첫 등장 이벤트 순서(태그마다 고정)."""
    first_pid: Dict[int, int] = {}
    order: Dict[int, None] = {}
    for gi, pi in zip(g.tolist(), pid.tolist()):
        if gi not in first_pid:
            first_pid[gi] = pi
            order.setdefault(pi, None)
    by: Dict[int, List[int]] = {}
    for gi, pi in first_pid.items():
        by.setdefault(pi, []).append(gi)
    return [(pi, np.array(sorted(by[pi]), dtype=np.int64)) for pi in order]


def map_fake(rng: np.random.Generator, P: Pools, pid: np.ndarray, g: np.ndarray,
             groups: List[Tuple[int, np.ndarray]], n_stock: int) -> Tuple[np.ndarray, int, int]:
    """§6 가짜 이벤트 g → h — g 가 처음 나온 이벤트의 풀에서 «그 풀 키에 처음 나온 g 들끼리» 비복원 추출(draw_mapped 선례)
    · 이후 같은 g 는 같은 h · 그 이벤트 풀에 h 가 없으면 그 이벤트만 균등 대체. 반환 = (h, 대체 수, 복원 전환 수)."""
    pi_arr = np.full(n_stock, -1, dtype=np.int64)
    n_short = 0
    for pi, gs in groups:
        sz = int(P.size[pi])
        if sz == 0:
            continue
        pool = P.PAD[pi, :sz]
        if len(gs) > sz:
            n_short += len(gs)
            pi_arr[gs] = rng.choice(pool, size=len(gs), replace=True)
        else:
            pi_arr[gs] = rng.choice(pool, size=len(gs), replace=False)
    h = pi_arr[g]
    ok = h >= 0
    ok[ok] = P.member(pid[ok], h[ok])
    bad = np.flatnonzero(~ok)
    if len(bad):
        h[bad] = draw_uniform(rng, P, pid[bad])
    return h, int(len(bad)), n_short


# ════════════════════════════════════════════════════════════════════════════
# 5. 통계 — CR1(p2_binary 와 같은 식 · bincount 판) · 2원 클러스터(CGM) · Holm · MDE
# ════════════════════════════════════════════════════════════════════════════
def _cl_V(psi_obs: np.ndarray, cl: np.ndarray, n_cl: int, N: float, K: int = 2) -> Tuple[float, int]:
    occ = np.bincount(cl, minlength=n_cl) > 0
    G = int(occ.sum())
    if G < 2:
        return float("nan"), G
    s = np.bincount(cl, weights=psi_obs, minlength=n_cl)
    return G / (G - 1) * (N - 1) / (N - K) * float((s ** 2).sum()), G


def stats_binary(y1: np.ndarray, c1: np.ndarray, b1: np.ndarray, y0: np.ndarray, c0: np.ndarray, b0: np.ndarray,
                 w0: np.ndarray, n_stock: int, n_block: int, two_way: bool = True) -> Dict[str, float]:
    """δ = mean(y1) − Σw0·y0/Σw0 · CR1(종목 · p2_binary 식) · 2원(종목 × 20일 블록 · V_s + V_b − V_sb · V ≤ 0 ⇒ max)."""
    n1, W0 = float(len(y1)), float(w0.sum())
    out: Dict[str, float] = dict(delta=float("nan"), se_cr1=float("nan"), p_cr1=1.0, se_2w=float("nan"), p_2w=1.0,
                                 G=0, Gb=0, n1=n1, W0=W0)
    if n1 < 2 or W0 <= 0:
        return out
    m1, m0 = float(y1.mean()), float((w0 * y0).sum() / W0)
    psi = np.concatenate([(y1 - m1) / n1, -(w0 * (y0 - m0)) / W0])
    cs = np.concatenate([c1, c0])
    N = n1 + W0
    v, G = _cl_V(psi, cs, n_stock, N)
    d = m1 - m0
    out.update(delta=d, G=G)
    if v == v and v > 0:
        se = math.sqrt(v)
        z = d / se
        out.update(se_cr1=se, p_cr1=min(1.0, math.erfc(abs(z) / math.sqrt(2))),
                   p_up=0.5 * math.erfc(z / math.sqrt(2)), p_down=0.5 * math.erfc(-z / math.sqrt(2)))
    if two_way:
        bs = np.concatenate([b1, b0])
        vb, Gb = _cl_V(psi, bs, n_block, N)
        vsb, _ = _cl_V(psi, cs * n_block + bs, n_stock * n_block, N)
        v2 = v + vb - (vsb if vsb == vsb else 0.0)
        if not (v2 > 0):
            v2 = max(x for x in (v, vb) if x == x) if (v == v or vb == vb) else float("nan")
        out.update(Gb=Gb, V_s=v, V_b=vb, V_sb=vsb)
        if v2 == v2 and v2 > 0 and Gb >= 2:
            from scipy import stats as sst
            se2 = math.sqrt(v2)
            z2 = d / se2
            out.update(se_2w=se2, p_2w=min(1.0, 2 * min(float(sst.t.sf(z2, Gb - 1)), float(sst.t.cdf(z2, Gb - 1)))))
    return out


def holm_adj(ps: Sequence[float]) -> List[float]:
    """Holm 보정 p — 오름차순 i(0부터): max_{j≤i} min(1, (m−j)·p_(j)) · m = len(ps)."""
    m = len(ps)
    o = sorted(range(m), key=lambda i: (ps[i], i))
    adj = [1.0] * m
    run = 0.0
    for r, i in enumerate(o):
        run = max(run, min(1.0, (m - r) * ps[i]))
        adj[i] = run
    return adj


def control_arrays(u: np.ndarray, H: np.ndarray, block: np.ndarray) -> Tuple[np.ndarray, ...]:
    """H(20 × n) → (u0, c0, b0, w0, 이벤트 위치) · 가중 재정규화 w = 1/(그 이벤트의 비지 않은 대조 수)."""
    n_ok = (H >= 0).sum(axis=0)
    rr, cc = np.nonzero(H >= 0)
    w = 1.0 / n_ok[cc]
    return u[cc], H[rr, cc], block[u[cc]], w, cc


# ════════════════════════════════════════════════════════════════════════════
# 6. ④ 봉인 단계
# ════════════════════════════════════════════════════════════════════════════
def event_exclusions(gx: GridExit, ev: pd.DataFrame) -> pd.DataFrame:
    """실제 이벤트 R4·R5·corp — `GridExit` 만 받는다(ret 접근 경로 없음)."""
    ev = ev.copy()
    ev["R4"] = False
    ev["R5"] = False
    ev["corp"] = False
    m = (ev["cand_lot"] & ~ev["R3"]).to_numpy()
    f = gx.flags(ev.loc[m, "u_i"].to_numpy(dtype=np.int64), ev.loc[m, "k"].to_numpy(dtype=np.int64))
    ev.loc[m, "R4"] = f["R4"]
    ev.loc[m, "R5"] = f["R5"]
    ev.loc[m, "corp"] = f["corp"]
    ev["keep"] = ev["cand_lot"] & ~ev["R3"] & ~ev["R4"] & ~ev["R5"]
    return ev


def seal_tag(env: Env, grid: Grid, rows: pd.DataFrame, t: int, ckpt: Path) -> Dict[str, Any]:
    """태그 t 봉인 계산 — 이벤트 제외 장부 · 대조 20 · 가짜 400(+새 대조) · 게이트 · 대조 sd · MDE · 비대칭 제외율."""
    T0 = time.perf_counter()
    cells_t = tag_cells(env, rows, t)
    TE = w5_matrix(env, cells_t)
    ev = build_events(env, rows, t)
    ev = event_exclusions(grid.exit_view(), ev)
    D = ev[ev["cand_lot"]].reset_index(drop=True)               # 대조 추출 대상(순서 = (u, g, rcept_no))
    u, g, q = (D[c].to_numpy(dtype=np.int64) for c in ("u_i", "k", "q"))
    P = Pools(env, TE, u, q)
    if (P.RANK[P.pid, g] >= 0).any():
        raise SystemExit(f"🔴 t={t} 이벤트 종목이 자기 대조 풀에 있다(W5 정의 불일치) — 중단")
    RET = grid.blinded_ret(cells_t)                              # 🔴 봉인 사본(태그 t 원공시 칸 NaN)

    # ── 대조 1:1 × 20 ──
    H = np.full((N_CTRL, len(D)), -1, dtype=np.int64)
    cst = dict(n_first=0, first_fail=0, n_redraw=0, n_empty=0)
    for k in range(1, N_CTRL + 1):
        o = draw_with_redraw(rng_of(SEED, 3, t, k), P, P.pid, u, grid)
        H[k - 1] = o["h"]
        for kk in cst:
            cst[kk] += o[kk]
    keep = D["keep"].to_numpy()
    Hk = H[:, keep]
    Hk_drop_empty = int((Hk < 0).sum())
    u_k = u[keep]
    uc, hc, bc, wc, _pos = control_arrays(u_k, Hk, env.block)
    y_ctrl = RET[uc, hc]
    if np.isnan(y_ctrl).any():
        raise SystemExit(f"🔴 t={t} 대조 ret NaN — 봉인 위반 또는 미청산 — 중단")
    corp_ctrl = grid.CORP[uc, hc]
    n_ev = int(keep.sum())
    sd_ctrl = float(np.std(y_ctrl, ddof=1)) if len(y_ctrl) > 1 else float("nan")
    np.savez_compressed(ckpt.with_suffix(".npz"), H=H, u=u, g=g, q=q, keep=keep,
                        rcept_no=D["rcept_no"].to_numpy(dtype=str))

    # ── 가짜 이벤트 400 ──
    Dk = D[keep].reset_index(drop=True)
    uf, gf, pidf = u_k, g[keep], P.pid[keep]
    bf = env.block[uf]
    fk = dict(p_cr1=[], se_cr1=[], p_2w=[], se_2w=[], replaced=0, short=0, fake_redraw=0, fake_empty=0,
              ctrl_first=0, ctrl_first_fail=0, ctrl_redraw=0, ctrl_empty=0, sd_fake=[])
    chk_done = False
    groups = fake_groups(pidf, gf)
    for j in range(1, N_FAKE + 1):
        rng = rng_of(SEED, 4, t, j)
        h0, n_rep, n_short = map_fake(rng, P, pidf, gf, groups, env.nS)
        of = draw_with_redraw(rng, P, pidf, uf, grid, h0=h0)
        hf = of["h"]
        fk["replaced"] += n_rep
        fk["short"] += n_short
        fk["fake_redraw"] += of["n_redraw"]
        fk["fake_empty"] += of["n_empty"]
        okf = hf >= 0
        HF = np.full((N_CTRL, len(hf)), -1, dtype=np.int64)
        for k in range(1, N_CTRL + 1):
            oc = draw_with_redraw(rng_of(SEED, 5, t, j, k), P, pidf, uf, grid, excl=np.maximum(hf, 0))
            HF[k - 1] = np.where(okf, oc["h"], -1)
            fk["ctrl_first"] += oc["n_first"]
            fk["ctrl_first_fail"] += oc["first_fail"]
            fk["ctrl_redraw"] += oc["n_redraw"]
            fk["ctrl_empty"] += oc["n_empty"]
        y1 = RET[uf[okf], hf[okf]]
        cu, ch, cb, cw, _ = control_arrays(uf, HF, env.block)
        y0 = RET[cu, ch]
        if np.isnan(y1).any() or np.isnan(y0).any():
            raise SystemExit(f"🔴 t={t} 가짜 j={j} ret NaN — 봉인 위반 또는 미청산 — 중단")
        st = stats_binary(y1, hf[okf], bf[okf], y0, ch, cb, cw, env.nS, int(env.block.max()) + 1)
        if not chk_done and len(y1) >= 2:                       # 빠른 CR1 = RE.p2_binary 대조(태그마다 1회)
            ref = RE.p2_binary(y1, hf[okf], y0, ch, cw)
            if not (abs(ref["se"] - st["se_cr1"]) <= 1e-9 * max(1.0, ref["se"])
                    and abs(ref["delta"] - st["delta"]) <= 1e-12):
                raise SystemExit(f"🔴 CR1 빠른 판 ≠ p2_binary (t={t}) — 중단")
            chk_done = True
        fk["p_cr1"].append(st["p_cr1"])
        fk["se_cr1"].append(st["se_cr1"])
        fk["p_2w"].append(st["p_2w"])
        fk["se_2w"].append(st["se_2w"])
        fk["sd_fake"].append(float(np.std(y1, ddof=1)) if len(y1) > 1 else float("nan"))
    rej_cr1 = float(np.mean(np.array(fk["p_cr1"]) < FAKE_P))
    rej_2w = float(np.mean(np.array(fk["p_2w"]) < FAKE_P))
    if rej_cr1 <= FAKE_MAX:
        tool = "CR1"
    elif rej_2w <= FAKE_MAX:
        tool = "2way"
    else:
        tool = "fail"
    sd_null = float(np.nanmean(fk["se_2w"] if tool == "2way" else fk["se_cr1"]))

    # ── 제외율(팔별) · 비대칭 ──
    nr2 = ~ev["R2"]
    R1u = int((ev["R1_first"] & nr2).sum())
    lot = ev["cand_lot"]
    ex = dict(R1=R1u, R1a=int((ev["R1_first"] & ev["R1a"] & nr2).sum()), R1b=int((ev["R1_first"] & ev["R1b"] & nr2).sum()),
              R2=int((ev["first"] & ev["R2"]).sum()), R3=int((lot & ev["R3"]).sum()), R4=int((lot & ev["R4"]).sum()),
              R5=int((lot & ev["R5"]).sum()), cand=int(lot.sum()))
    den_e = ex["R1"] + ex["cand"]
    rate_e = (ex["R1"] + ex["R3"] + ex["R4"] + ex["R5"]) / den_e if den_e else float("nan")
    rate_c = cst["first_fail"] / cst["n_first"] if cst["n_first"] else float("nan")
    restricted = bool(rate_e - rate_c > ASYM_MAX)
    mde1 = K_MDE * sd_ctrl * math.sqrt(1 / n_ev + 1 / (N_CTRL * n_ev)) if n_ev else float("nan")
    mde2 = K_MDE * sd_null
    out = dict(
        t=t, tag=TAGS[t - 1], secs=round(time.perf_counter() - T0, 1),
        counts=dict(raw_orig=int((rows["t"] == t).sum() - (rows[(rows["t"] == t)]["is_corr"]).sum()),
                    rows=len(ev), null_code=int(ev["null_code"].sum()), dup=int(ev["dup"].sum()),
                    out_window=int((~ev["in_window"] & ~ev["null_code"] & ~ev["dup"]).sum()),
                    joined=int(ev["joined"].sum()), first=int(ev["first"].sum()), n_final=n_ev,
                    mgmt_dispute_final=int(ev.loc[ev["keep"], "mgmt_dispute"].sum())),
        excl=ex, rate_event=rate_e, rate_ctrl=rate_c, asym_diff=rate_e - rate_c, restricted=restricted,
        ctrl=dict(**cst, kept_lots=int(len(y_ctrl)), empty_in_kept=Hk_drop_empty, sd=sd_ctrl,
                  corp_rate=float(corp_ctrl.mean()) if len(corp_ctrl) else float("nan"),
                  pool_size_min=int(P.size.min()) if len(P.size) else 0,
                  pool_size_median=float(np.median(P.size)) if len(P.size) else 0.0),
        event=dict(corp_rate=float(Dk["corp"].mean()) if len(Dk) else float("nan"),
                   n_codes=int(len(np.unique(gf))), n_blocks=int(len(np.unique(bf)))),
        fake=dict(n=N_FAKE, rej_cr1=rej_cr1, rej_2w=rej_2w, tool=tool,
                  rej_cr1_p05=float(np.mean(np.array(fk["p_cr1"]) < 0.05)),
                  se_cr1_mean=float(np.nanmean(fk["se_cr1"])), se_2w_mean=float(np.nanmean(fk["se_2w"])),
                  sd_fake_mean=float(np.nanmean(fk["sd_fake"])), replaced=fk["replaced"], short=fk["short"],
                  fake_redraw=fk["fake_redraw"], fake_empty=fk["fake_empty"], ctrl_first=fk["ctrl_first"],
                  ctrl_first_fail=fk["ctrl_first_fail"], ctrl_redraw=fk["ctrl_redraw"], ctrl_empty=fk["ctrl_empty"],
                  cr1_matches_p2_binary=chk_done),
        sd_null=sd_null, mde1=mde1, mde2=mde2, none_possible=bool(tool != "fail" and 1.96 * sd_null < T_MIN),
        none_se_1_96=1.96 * sd_null,
    )
    R._atomic_write(ckpt, json.dumps(out, ensure_ascii=False, indent=1, default=float))
    return out


def a_features(env: Env, rows: pd.DataFrame) -> pd.DataFrame:
    """(a) 특징 열 — 원장 in_full ∩ scan_date ≥ 2024-03-20 · 🔴 ret 열을 읽지 않는다(usecols)."""
    fe = pd.read_csv(LEDGER_DIR / "features.csv", dtype=str, keep_default_na=False,
                     usecols=["strategy", "scan_date", "stock_code", "in_full", "band_ok"])
    if "ret_pct" in fe.columns:
        raise SystemExit("🔴 (a) 특징 프레임에 ret 열 — 중단")
    A = fe[(fe["in_full"] == "True") & (fe["scan_date"] >= A_SCAN_MIN)].copy().reset_index(drop=True)
    D_i = np.array([env.cal_i[date.fromisoformat(d)] for d in A["scan_date"]], dtype=np.int64)
    K_i = np.array([env.kidx[c] for c in A["stock_code"]], dtype=np.int64)
    day0 = np.datetime64(env.cal[0].isoformat(), "D")
    n_day = int((np.datetime64(W_END, "D") - day0).astype(int)) + 2
    cal_day = (env.mk.cal64.astype("datetime64[D]") - day0).astype(np.int64)      # 거래일 → 달력일 번호
    for t in range(1, 8):
        for corr in (False, True):
            m = (rows["t"] == t) & (rows["k"] >= 0)
            if not corr:
                m &= ~rows["is_corr"]
            s = rows[m]
            dd = (pd.to_datetime(s["rcept_dt"]).to_numpy(dtype="datetime64[D]") - day0).astype(np.int64)
            ok = (dd >= 0) & (dd < n_day - 1)
            CNT = np.zeros((n_day + 1, env.nS), dtype=np.int32)
            np.add.at(CNT, (dd[ok] + 1, s["k"].to_numpy(dtype=np.int64)[ok]), 1)
            CS = np.cumsum(CNT, axis=0)                              # CS[i] = Σ_{달력일 < i}
            wins = A_WINDOWS if not corr else {"W5": A_WINDOWS["W5"]}
            for w, (a, b) in wins.items():
                lo, hi = cal_day[np.maximum(D_i - a, 0)], cal_day[D_i - b]      # rcept_dt ∈ [cal[D−a], cal[D−b]]
                n = CS[hi + 1, K_i] - CS[lo, K_i]
                A[f"x{t}_{w}{'_corr' if corr else ''}"] = (n > 0).astype(np.int8)
    return A


def k2_sample(A: pd.DataFrame, cal_i: Dict[date, int]) -> np.ndarray:
    """K2 표본(P3+P2) — 전략×종목 에피소드 첫 행 · (전략, scan_date) 안 첫 행 < 3 인 날 제외."""
    smap = {f: i for i, f in enumerate(R.STRATS)}
    s = A["strategy"].map(smap).to_numpy(dtype=np.int64)
    g = pd.factorize(A["stock_code"])[0].astype(np.int64)
    ci = np.array([cal_i[date.fromisoformat(d)] for d in A["scan_date"]], dtype=np.int64)
    _eid, first = RC.episodes(s, g, ci)
    day = pd.Series(first).groupby([A["strategy"], A["scan_date"]]).transform("sum").to_numpy()
    return first & (day >= 3)


def write_events_csv(env: Env, rows: pd.DataFrame, path: Path) -> None:
    parts = []
    for t in range(1, 8):
        ev = build_events(env, rows, t)
        parts.append(pd.DataFrame(dict(
            rcept_no=ev["rcept_no"], stock_code=ev["code_s"], t=t, tag=TAGS[t - 1],
            rcept_dt=ev["rcept_dt"].astype(str),
            e=[env.cal[i].isoformat() if 0 <= i < env.nC else "" for i in ev["e_i"]],
            u=[env.cal[i].isoformat() if 0 <= i < env.nC else "" for i in ev["u_i"]],
            null_code=ev["null_code"], dup=ev["dup"], in_window=ev["in_window"], R1=ev["R1"], R1a=ev["R1a"],
            R1b=ev["R1b"], joined=ev["joined"], episode_first=ev["first"], R1_episode_first=ev["R1_first"],
            R2=ev["R2"], mcap_q=ev["q"], mgmt_dispute=ev["mgmt_dispute"])))
    out = pd.concat(parts, ignore_index=True)
    out.to_csv(path, index=False, encoding="utf-8", lineterminator="\n")


def _f(x: Any, nd: int = 3) -> str:
    return "—" if x is None or not (isinstance(x, (int, float)) and math.isfinite(x)) else f"{x:.{nd}f}"


def sealed_md(meta: Dict[str, Any], tags: List[Dict[str, Any]], a_n: pd.DataFrame, guard: Dict[str, Any],
              grid_meta: Dict[str, Any]) -> str:
    L = ["# 연구 ① DART 공시 이벤트 — 봉인 보고(④) · 결과 조인 전", "",
         f"- 사전등록 `docs/prereg_2026-09-26_dart_disclosure_events.md` · 실행 sha `{meta['git_sha'][:10]}` · "
         f"DB 지문 `{meta['db_fingerprint']['sha256'][:12]}` · dart_disclosures {meta['dart']['rows']:,}행 · "
         f"max(fetched_at) {meta['dart']['max_fetched_at']}",
         "- 🔴 이 문서에는 실제 이벤트 로트의 결과(평균·δ·p)와 대조 로트 평균이 **없다**(§7 · V5). "
         "sd 는 대조(또는 가짜) 로트 ret 의 표준편차뿐이다.",
         f"- 재현 가드(원장 ma20 `in_full` {guard['n']:,}로트 · sim_fast): 불일치 {guard['any']} "
         f"({guard['rate']:.5%}) — 사유 {guard['reason']} · 청산일 {guard['date']} · ret {guard['ret']} ⇒ 경로 = "
         f"{'벡터화(sim_fast)' if guard['path'] == 'vector' else '대체(simulate_lot + SellProbe)'}",
         f"- 격자: {grid_meta['mode']} · 계산 로트 {grid_meta['n_sim']:,} / 격자 {grid_meta['n_grid']:,} · "
         f"파일럿({PILOT_MONTH}) {grid_meta['pilot_n']:,}로트 {grid_meta['pilot_ms_per_lot']:.3f}ms/로트 · "
         f"예상 {grid_meta['projected_s']:.0f}s · 봉인 단계 경과 {meta['secs_total']:.0f}s(상한 {CAP_S:.0f}s)", "",
         "## 1. 이벤트 · 제외 장부(태그 × 팔) — §6 대칭 규칙", "",
         "| t | 태그 | 원공시 | 코드 없음 | 중복 키 | 창 밖 | 조인 | 에피소드 첫 | R1(a/b · 에피소드 단위) | R2 | R3 | R4 | R5 | "
         "최종 이벤트 로트 n | 이벤트 제외율 | 대조 첫추출 실패율 | 차이 | 2%p 제한 |",
         "|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|"]
    for o in tags:
        c, e = o["counts"], o["excl"]
        L.append(f"| {o['t']} | {o['tag']} | {c['raw_orig']:,} | {c['null_code']:,} | {c['dup']:,} | {c['out_window']:,} | "
                 f"{c['joined']:,} | {c['first']:,} | {e['R1']:,} ({e['R1a']:,}/{e['R1b']:,}) | {e['R2']:,} | {e['R3']:,} | "
                 f"{e['R4']:,} | {e['R5']:,} | {c['n_final']:,} | {o['rate_event']:.2%} | {o['rate_ctrl']:.2%} | "
                 f"{o['asym_diff'] * 100:+.2f}%p | {'예 — 「없음」·「있음(+)」 금지' if o['restricted'] else '아니오'} |")
    L += ["", "- 이벤트 제외율 = (R1 + R3 + R4 + R5) / (R1 + R2 뒤 에피소드 첫 후보) · R1 은 R1 이벤트끼리 같은 에피소드 규칙으로 "
          "묶은 단위 · 대조 = (R4 + R5 첫 추출 실패) / 첫 추출(이벤트 R3~R5 제외 전 전부).",
          "- R1a = stock_code 가 daily_prices(2023-01-02~2026-09-23)에 없음 · R1b = 있으나 e 에 시총 행 없음.", "",
          "## 2. 대조 · 가짜 이벤트 게이트 · sd · MDE — §6 · §7", "",
          "| t | 태그 | n(이벤트 첫 로트) | 대조 로트 | 대조 재추출 | 대조 비움 | 대조 sd(ret) | 가짜 p<0.10 거부율 CR1 | 2원 | "
          "쓴 도구 | SD_null | MDE ① | MDE ② | 없음 가능(1.96·SD_null < 0.4) |",
          "|---|---|---|---|---|---|---|---|---|---|---|---|---|---|"]
    for o in tags:
        f, cc = o["fake"], o["ctrl"]
        tool = {"CR1": "CR1", "2way": "2원 클러스터", "fail": "탈락 ⇒ 판별 보류(도구)"}[f["tool"]]
        L.append(f"| {o['t']} | {o['tag']} | {o['counts']['n_final']:,} | {cc['kept_lots']:,} | {cc['n_redraw']:,} | "
                 f"{cc['n_empty']:,} | {_f(cc['sd'])} | {f['rej_cr1']:.4f} ({int(round(f['rej_cr1'] * N_FAKE))}/{N_FAKE}) | "
                 f"{f['rej_2w']:.4f} | {tool} | {_f(o['sd_null'], 4)} | {_f(o['mde1'])} | {_f(o['mde2'])} | "
                 f"{'예' if o['none_possible'] else '아니오'} ({_f(o['none_se_1_96'])}) |")
    L += ["", f"- MDE ① = {K_MDE} × sd(대조) × √(1/n + 1/(20n)) · ② = {K_MDE} × SD_null(쓴 도구의 가짜 400 SE 평균) · 단위 %p.",
          f"- 게이트: 가짜 p<0.10 거부율 ≤ {FAKE_MAX} ⇒ CR1 · 초과 ⇒ 2원 클러스터(종목 × u 20거래일 블록 · t(G_블록−1)) · "
          "둘 다 초과 ⇒ 「판별 보류(도구)」 p = 1.", "",
          "| t | 가짜 재추출(대체 · 복원 전환 · R4R5 재추출 · 비움) | 가짜 대조 첫추출 실패율 | 이벤트 corp_event 비율 | 대조 corp_event 비율 | "
          "풀 크기 최소/중앙 | 이벤트 종목 수 | 채워진 블록 | CR1 = p2_binary 대조 |",
          "|---|---|---|---|---|---|---|---|---|"]
    for o in tags:
        f = o["fake"]
        fr = f["ctrl_first_fail"] / f["ctrl_first"] if f["ctrl_first"] else float("nan")
        L.append(f"| {o['t']} | {f['replaced']:,} · {f['short']:,} · {f['fake_redraw']:,} · {f['fake_empty']:,} | {fr:.2%} | "
                 f"{o['event']['corp_rate']:.2%} | {o['ctrl']['corp_rate']:.2%} | {o['ctrl']['pool_size_min']:,}/"
                 f"{o['ctrl']['pool_size_median']:.0f} | {o['event']['n_codes']:,} | {o['event']['n_blocks']} | "
                 f"{'✓' if f['cr1_matches_p2_binary'] else '—'} |")
    L += ["", "## 3. (a) 원장 결합 — 셀 n 만(인쇄 전용 · 판정 없음 · 결과 조인 없음)", "",
          "K2 표본(에피소드 첫 행 · 날짜 안 첫 행 ≥ 3) · W5 · n_with / n_without.", "",
          "| 전략 | " + " | ".join(TAGS) + " |", "|---|" + "---|" * 7]
    for f in R.STRATS:
        sub = a_n[a_n["strategy"] == f]
        L.append(f"| {R.STRATS[f]['short']} | " + " | ".join(
            f"{int(r.n_with):,} / {int(r.n_without):,}" for r in sub.sort_values("t").itertuples()) + " |")
    L += ["", "## 4. 해석 기록(구현 선택 · 🔒 값 변경 없음)", ""] + [f"- {x}" for x in INTERP] + [""]
    return "\n".join(L)


INTERP = [
    "R5 = 격자 청산 사유 `open`(u ≤ 2026-07-13 이라 상한 안 미청산 = 경로 중 봉 끊김).",
    "R4 = 보유 경로 [u, 청산일(미청산이면 2026-09-23)] 안 불가능봉(padding ∨ locked_limit ∨ cliff · 원장 any_in 과 같은 판정).",
    "순서: 태그(원공시) → 키 (t, g, rcept_dt) 중복 제거(가장 작은 rcept_no) → 창(u ∈ [2024-03-21, 2026-07-13]) → "
    "코드 NULL(건수만 · R1 아님) → R1(원시 U(e) 조인) → 에피소드(조인된 이벤트 · (t,g) 안 직전 u 와 ≤ 5거래일) → R2 → R3 → R4·R5.",
    "대조 추출: rng_k 로 이벤트 순서 벡터 추출(첫 추출) → R4·R5 실패 로트만 같은 rng_k 로 라운드마다 이벤트 순서 재추출(최대 20) → "
    "실패면 비움 · 이벤트 R3~R5 는 대조를 뽑은 뒤 함께 뺀다(난수 소비가 이벤트 결과와 무관).",
    "가중 재정규화 = 이벤트마다 w = 1/(비지 않은 대조 수).",
    "가짜 매핑의 비복원 = g 가 처음 나온 이벤트의 풀 키 (u, 시총 분위) 안에서 그 키에 처음 나온 g 들끼리(draw_mapped 선례) · "
    "대체·R4R5 재추출은 같은 rng([20261004,4,t,j]) 를 이어 소비 · 가짜 대상 = 최종 이벤트 로트(n 과 같은 설계).",
    "가짜의 대조 = 가짜 이벤트와 같은 풀 P_i 에서 h 를 뺀 풀 · rng([20261004,5,t,j,k]) · 재추출 규칙 같음.",
    "2원 클러스터 분산 = 각 차원 G/(G−1)·(N−1)/(N−K)(K=2 · p2_binary 와 같은 소표본 보정) · V ≤ 0 ⇒ max(V_종목, V_블록)(H8 선례) · "
    "블록 = (u 순번 − 2024-03-21 순번) // 20.",
    "(a) 창은 §5 식 그대로 달력 비교: W5 rcept_dt ∈ [cal[D−4], D] · W1 = D · W20 [cal[D−19], D] · D 제외판 [cal[D−5], cal[D−1]]"
    "(D−k = 거래일 k 개 전) — §4 u 정의(u(r) ∈ [X−4, X])와 같되 D 뒤 주말·휴일 접수(u = D+1)는 넣지 않는다(V3: x=1 ⇒ rcept_dt ≤ scan_date). "
    "(b) 대조 풀 W5 는 §4 u 정의 그대로.",
]


def run_seal(a: argparse.Namespace) -> int:
    T0 = time.perf_counter()
    started = datetime.now().isoformat(timespec="seconds")
    RES.mkdir(parents=True, exist_ok=True)
    CACHE.mkdir(parents=True, exist_ok=True)
    md5s = check_inputs()
    env = Env()
    tm: Dict[str, float] = {"load": time.perf_counter() - T0}
    log(f"[가드] md5 ✓ · blob {len(env.blobs)} = {R.BASE_SHA} ✓ · tp/sl/max_hold = {EXPECT_RULES} ✓ · sha {env.sha[:10]}")

    # ── 재현 가드 ──
    t = time.perf_counter()
    guard = repro_guard(env)
    tm["guard"] = time.perf_counter() - t
    log(f"[재현 가드] {guard['n']:,} 로트 · 불일치 {guard['any']} ({guard['rate']:.5%}) ⇒ {guard['path']} · {tm['guard']:.0f}s")
    grid = Grid(env, guard["path"])
    if guard["path"] == "fallback":
        book = R.build_book(LD.load_prices(R._connect(), PX_START, W_END))
        renv = R.Env(cal=env.cal, book=book, uni={}, excl={}, imp_dates={}, corp_dates={}, bad_open=set(),
                     minute_fn=lambda p: set())
        grid._probe = (renv, SP.SellProbe(FOLDER, env.strategy, R.make_window_fn(book)))

    # ── 격자: 파일럿 → 전체(또는 지연) ──
    code_md5 = {p.name: md5(p) for p in (Path(__file__), BASE / "dart_tags.py")}
    key = hashlib.md5(f"{env.sha}|{env.fp['sha256']}|{guard['path']}|{sorted(code_md5.items())}".encode()).hexdigest()[:16]
    gpath = CACHE / f"grid_{key}.npz"
    uu, kk = np.nonzero(env.GM)
    n_grid = len(uu)
    pilot = np.array([env.cal[i].strftime("%Y-%m") == PILOT_MONTH for i in uu])
    if gpath.exists():
        z = np.load(gpath, allow_pickle=False)
        grid.RSN, grid.XI, grid.R4, grid.CORP = z["RSN"], z["XI"], z["R4"], z["CORP"]
        grid._RET, grid._XPX = z["RET"], z["XPX"]
        grid.reasons = [str(x) for x in z["reasons"]]
        gm = json.loads(str(z["meta"]))
        log(f"[격자] 캐시 재사용 {gpath.name} · 계산 로트 {int((grid.RSN >= 0).sum()):,}")
    else:
        t = time.perf_counter()
        grid.compute(uu[pilot], kk[pilot])
        ps = time.perf_counter() - t
        per = ps / max(1, int(pilot.sum()))
        projected = (time.perf_counter() - T0) + per * (n_grid - int(pilot.sum())) + 300.0
        mode = "eager" if projected <= CAP_S else "lazy"
        log(f"[파일럿] {int(pilot.sum()):,} 로트 {ps:.1f}s ({per * 1e3:.3f}ms/로트) · 예상 봉인 합계 {projected:.0f}s ⇒ "
            f"{'전체 격자' if mode == 'eager' else '지연 계산(§6 격자 절차)'}")
        if mode == "eager":
            t = time.perf_counter()
            grid.compute(uu, kk)
            tm["grid"] = time.perf_counter() - t
            log(f"[격자] {n_grid:,} 로트 · {tm['grid']:.0f}s")
        gm = dict(mode=mode, n_grid=n_grid, pilot_n=int(pilot.sum()), pilot_s=round(ps, 2),
                  pilot_ms_per_lot=per * 1e3, projected_s=projected)
        np.savez_compressed(gpath, RSN=grid.RSN, XI=grid.XI, R4=grid.R4, CORP=grid.CORP, RET=grid._RET, XPX=grid._XPX,
                            reasons=np.array(grid.reasons), meta=json.dumps(gm))
    if grid.reasons[0] != X.EXIT_OPEN:
        raise SystemExit(f"🔴 청산 사유 코드 0 ≠ EXIT_OPEN({X.EXIT_OPEN}) — 중단")

    # ── 이벤트 · events.csv · (a) 특징 ──
    t = time.perf_counter()
    rows = tag_rows(env)
    n_mis = int((rows["is_corr"] != rows["report_nm"].str.contains("정정")).sum())
    write_events_csv(env, rows, BASE / "events.csv")
    A = a_features(env, rows)
    A.to_csv(RES / "cells_a_features.csv", index=False, encoding="utf-8", lineterminator="\n")
    k2 = k2_sample(A, env.cal_i)
    a_n = []
    for f in R.STRATS:
        ms = (A["strategy"] == f).to_numpy() & k2
        for tt in range(1, 8):
            x = A.loc[ms, f"x{tt}_W5"].to_numpy()
            a_n.append(dict(strategy=f, t=tt, n_with=int((x == 1).sum()), n_without=int((x == 0).sum())))
    a_n = pd.DataFrame(a_n)
    tm["events"] = time.perf_counter() - t
    log(f"[이벤트] events.csv · (a) 특징 {len(A):,}행 × {A.shape[1] - 5}열 · 정정 판정 불일치(스크립트 식 대비) {n_mis:,} · "
        f"{tm['events']:.0f}s")

    # ── 태그별(체크포인트) ──
    tags = []
    for tt in range(1, 8):
        ck = CACHE / f"seal_t{tt}_{key}.json"
        if ck.exists() and ck.with_suffix(".npz").exists():
            o = json.loads(ck.read_text(encoding="utf-8"))
            log(f"[t={tt}] 체크포인트 재사용")
        else:
            o = seal_tag(env, grid, rows, tt, ck)
            log(f"[t={tt} {TAGS[tt - 1]}] n {o['counts']['n_final']:,} · 제외율 이벤트 {o['rate_event']:.2%} / 대조 "
                f"{o['rate_ctrl']:.2%} · 가짜 거부율 CR1 {o['fake']['rej_cr1']:.3f} 2원 {o['fake']['rej_2w']:.3f} ⇒ "
                f"{o['fake']['tool']} · sd {o['ctrl']['sd']:.3f} · MDE {o['mde1']:.3f}/{o['mde2']:.3f} · {o['secs']:.0f}s")
        tags.append(o)
        el = time.perf_counter() - T0
        if el > CAP_S:
            R._atomic_write(RES / "ABORT_seal.md", f"# 봉인 단계 중단 — 경과 {el:.0f}s > {CAP_S:.0f}s (t={tt} 까지)\n")
            raise SystemExit(f"🔴 봉인 단계 {el:.0f}s > 30분 — 중단·보고(부분 판정 없음 · 체크포인트 t≤{tt})")
    tm["tags"] = sum(o["secs"] for o in tags)

    grid_meta = dict(gm, n_sim=int((grid.RSN >= 0).sum()), path=guard["path"], reasons=grid.reasons,
                     reason_counts={r: int((grid.RSN == i).sum()) for i, r in enumerate(grid.reasons)},
                     n_R4=int(grid.R4.sum()), u_range=[U_MIN, U_MAX], cache=gpath.name, secs_sim=round(grid.secs, 1),
                     guard=guard)
    fake_gate = {o["tag"]: dict(t=o["t"], **o["fake"], sd_null=o["sd_null"]) for o in tags}
    meta = dict(git_sha=env.sha, started=started, finished=datetime.now().isoformat(timespec="seconds"),
                secs_total=round(time.perf_counter() - T0, 1), secs=tm, input_md5=md5s,
                prereg_md5=md5(PREREG), db_fingerprint={k: v for k, v in env.fp.items() if k != "per_stock"},
                dart=env.dart_meta, normalize_counts=env.normalize_counts, is_corr_mismatch_vs_script=n_mis,
                seeds=dict(control="[20261004,3,t,k] k=1..20", fake="[20261004,4,t,j] j=1..400",
                           fake_control="[20261004,5,t,j,k]", vol_matched="[20261004,6,t,k] (개봉 단계 보조)",
                           corr_included="[20261004,7,t,k] (개봉 단계 보조 · 문서에 시드 없음 ⇒ 새로 잡음)"),
                code_md5=code_md5, worktree_dirty=bool(R._git("status", "--porcelain", "--", str(BASE))),
                exit_rules=dict(tp=env.rules.tp, sl=env.rules.sl, max_hold_days=env.rules.max_hold_days,
                                source=env.rules.source), guard_blobs=env.blobs, base_sha=R.BASE_SHA, cache_key=key)
    for name, obj in (("grid_meta.json", grid_meta), ("fake_gate.json", fake_gate), ("run_meta.json", meta),
                      ("seal_tags.json", tags)):
        R._atomic_write(RES / name, json.dumps(obj, ensure_ascii=False, indent=1, default=float))
    R._atomic_write(RES / "sealed_report.md", sealed_md(meta, tags, a_n, guard, grid_meta))
    log(f"[끝] 봉인 단계 {time.perf_counter() - T0:.0f}s → {RES / 'sealed_report.md'}")
    return 0


# ════════════════════════════════════════════════════════════════════════════
# 7. ⑤ 개봉 단계 — (b) 판정 + (a) 인쇄 + 보조
# ════════════════════════════════════════════════════════════════════════════
def _b_stats(RET: np.ndarray, env: Env, u: np.ndarray, g: np.ndarray, H: np.ndarray, tool: str) -> Dict[str, Any]:
    y1 = RET[u, g]
    cu, ch, cb, cw, _ = control_arrays(u, H, env.block)
    y0 = RET[cu, ch]
    st = stats_binary(y1, g, env.block[u], y0, ch, cb, cw, env.nS, int(env.block.max()) + 1)
    se = st["se_2w"] if tool == "2way" else st["se_cr1"]
    p = st["p_2w"] if tool == "2way" else st["p_cr1"]
    return dict(n=len(y1), delta=st["delta"], se=se, p=p, Gb=st["Gb"], se_cr1=st["se_cr1"], p_cr1=st["p_cr1"],
                se_2w=st["se_2w"], p_2w=st["p_2w"])


def _label(delta: float, p_adj: float, lo: float, hi: float, n: int, tool: str, restricted: bool) -> str:
    if tool == "fail":
        return LAB_HOLD_TOOL
    if n < MIN_N:
        return LAB_HOLD
    if p_adj < ALPHA and delta <= -T_MIN:
        return LAB_DN
    if p_adj < ALPHA and delta >= T_MIN and not restricted:
        return LAB_UP
    if not restricted and lo > -T_MIN and hi < T_MIN:
        return LAB_NONE
    return LAB_HOLD


def _aux_draws(env: Env, grid: Grid, ev: pd.DataFrame, TE: np.ndarray, seed2: int, t: int,
               QK: Optional[np.ndarray] = None, qcol: str = "q") -> np.ndarray:
    D = ev[ev["cand_lot"]].reset_index(drop=True)
    u = D["u_i"].to_numpy(dtype=np.int64)
    qk = D[qcol].to_numpy(dtype=np.int64)
    P = Pools(env, TE, u, qk, QK)
    H = np.full((N_CTRL, len(D)), -1, dtype=np.int64)
    for k in range(1, N_CTRL + 1):
        H[k - 1] = draw_with_redraw(rng_of(SEED, seed2, t, k), P, P.pid, u, grid)["h"]
    return H[:, D["keep"].to_numpy()]


def vol_quintiles(env: Env) -> Tuple[np.ndarray, np.ndarray]:
    """u 직전 20거래일 실현변동성(로그수익 20개 표준편차) · U(u−1) 안 5분위 · 키 = 시총분위×10 + 변동성분위."""
    C = env.mk.C
    lr = np.full_like(C, np.nan)
    lr[1:] = np.log(C[1:] / C[:-1])
    V = pd.DataFrame(lr).rolling(20, min_periods=20).std(ddof=1).shift(1).to_numpy()   # [u−20, u−1]
    QK = np.zeros((env.nC, env.nS), dtype=np.int64)
    for uu in range(env.iu0, env.iu1 + 1):
        ks = np.flatnonzero(env.UM[uu - 1] & np.isfinite(V[uu]))
        if len(ks):
            q = pd.Series(V[uu, ks]).rank(pct=True).to_numpy()
            qv = 1 + (q > 0.2).astype(int) + (q > 0.4) + (q > 0.6) + (q > 0.8)
            QK[uu, ks] = env.Q[uu - 1, ks] * 10 + qv
    return QK, V


def run_unseal(a: argparse.Namespace) -> int:
    if not (RES / "sealed_report.md").exists():
        raise SystemExit("🔴 results/sealed_report.md 없음 — 봉인 단계(④)와 그 커밋이 먼저다(§10)")
    T0 = time.perf_counter()
    md5s = check_inputs()
    meta0 = json.loads((RES / "run_meta.json").read_text(encoding="utf-8"))
    gate = json.loads((RES / "fake_gate.json").read_text(encoding="utf-8"))
    tags0 = json.loads((RES / "seal_tags.json").read_text(encoding="utf-8"))
    env = Env()
    if env.fp["sha256"] != meta0["db_fingerprint"]["sha256"]:
        raise SystemExit("🔴 DB 지문이 봉인 단계와 다르다 — 중단")
    key = meta0["cache_key"]
    gm = json.loads((RES / "grid_meta.json").read_text(encoding="utf-8"))
    grid = Grid(env, gm["path"])
    z = np.load(CACHE / gm["cache"], allow_pickle=False)
    grid.RSN, grid.XI, grid.R4, grid.CORP = z["RSN"], z["XI"], z["R4"], z["CORP"]
    grid._RET, grid._XPX = z["RET"], z["XPX"]
    grid.reasons = [str(x) for x in z["reasons"]]
    RET, XPX = grid.unsealed_ret()
    rows = tag_rows(env)
    iE = int(np.searchsorted(env.mk.cal64, np.datetime64(E_END), side="right")) - 1
    QK, _V = vol_quintiles(env)

    # ── (b) 판정 ──
    B: List[Dict[str, Any]] = []
    aux: List[Dict[str, Any]] = []
    for tt in range(1, 8):
        o0 = tags0[tt - 1]
        tool = gate[TAGS[tt - 1]]["tool"]
        zt = np.load(CACHE / f"seal_t{tt}_{key}.npz", allow_pickle=False)
        keep = zt["keep"]
        u, g, H = zt["u"][keep], zt["g"][keep], zt["H"][:, keep]
        st = _b_stats(RET, env, u, g, H, tool if tool != "fail" else "CR1")
        n = st["n"]
        p = 1.0 if (n < MIN_N or tool == "fail" or not (st["p"] == st["p"])) else st["p"]
        crit = 1.96
        if tool == "2way" and st["Gb"] >= 2:
            from scipy import stats as sst
            crit = float(sst.t.ppf(0.975, st["Gb"] - 1))
        lo, hi = st["delta"] - crit * st["se"], st["delta"] + crit * st["se"]
        y1 = RET[u, g]
        ev = build_events(env, rows, tt)
        ev = event_exclusions(grid.exit_view(), ev)
        evk = ev[ev["keep"]].reset_index(drop=True)
        qty = np.array([Z.arm_b_qty(float(env.mk.O[x, k])).qty for x, k in zip(u, g)])
        E = env.mk.O[u, g]
        pnl = qty * (XPX[u, g] - E) - COST / 100 * qty * E
        B.append(dict(t=tt, tag=TAGS[tt - 1], tool=tool, n=n, n_ctrl=int((H >= 0).sum()), delta=st["delta"], se=st["se"],
                      p=p, ci_lo=lo, ci_hi=hi, restricted=o0["restricted"], rate_event=o0["rate_event"],
                      rate_ctrl=o0["rate_ctrl"], mde1=o0["mde1"], mde2=o0["mde2"], mean_event=float(y1.mean()),
                      net_event=float((y1 - COST).mean()), win_rate=float((y1 > 0).mean()),
                      pnl_net_won=int(round(float(pnl.mean()))), expected_sign=["−", "−", "+", "+", "무부호", "무부호", "−"][tt - 1],
                      se_cr1=st["se_cr1"], p_cr1=st["p_cr1"], se_2w=st["se_2w"], p_2w=st["p_2w"]))
        # 보조(인쇄만)
        mE = u <= iE
        for nm, m in (("반창 E(~2025-06-30)", mE), ("반창 C(2025-07-01~)", ~mE)):
            s2 = _b_stats(RET, env, u[m], g[m], H[:, m], "CR1")
            aux.append(dict(t=tt, kind=nm, n=s2["n"], delta=s2["delta"], se=s2["se"], p=s2["p"]))
        qv = evk["q"].to_numpy()
        for qq in range(1, 6):
            m = qv == qq
            s2 = _b_stats(RET, env, u[m], g[m], H[:, m], "CR1")
            aux.append(dict(t=tt, kind=f"시총 {qq}분위", n=s2["n"], delta=s2["delta"], se=s2["se"], p=s2["p"]))
        if tt == 7:
            m = evk["mgmt_dispute"].to_numpy(dtype=bool)
            s2 = _b_stats(RET, env, u[m], g[m], H[:, m], "CR1")
            aux.append(dict(t=tt, kind="경영권분쟁 부분집합", n=s2["n"], delta=s2["delta"], se=s2["se"], p=s2["p"]))
        TE = w5_matrix(env, tag_cells(env, rows, tt))
        ev["qv"] = 0
        mm = ev["cand_lot"].to_numpy()
        ev.loc[mm, "qv"] = QK[ev.loc[mm, "u_i"].to_numpy(dtype=np.int64), ev.loc[mm, "k"].to_numpy(dtype=np.int64)]
        ev.loc[mm & (ev["qv"] == 0).to_numpy(), "keep"] = False
        ev.loc[mm & (ev["qv"] == 0).to_numpy(), "cand_lot"] = False
        Hv = _aux_draws(env, grid, ev, TE, 6, tt, QK=QK, qcol="qv")
        evv = ev[ev["keep"]]
        s2 = _b_stats(RET, env, evv["u_i"].to_numpy(dtype=np.int64), evv["k"].to_numpy(dtype=np.int64), Hv, "CR1")
        aux.append(dict(t=tt, kind="변동성 정합 대조(시총×변동성 5분위)", n=s2["n"], delta=s2["delta"], se=s2["se"], p=s2["p"]))
        evc = event_exclusions(grid.exit_view(), build_events(env, rows, tt, with_corr=True))
        TEc = w5_matrix(env, tag_cells(env, rows, tt, with_corr=True))
        Hc = _aux_draws(env, grid, evc, TEc, 7, tt)
        evck = evc[evc["keep"]]
        s2 = _b_stats(RET, env, evck["u_i"].to_numpy(dtype=np.int64), evck["k"].to_numpy(dtype=np.int64), Hc, "CR1")
        aux.append(dict(t=tt, kind="정정 포함판", n=s2["n"], delta=s2["delta"], se=s2["se"], p=s2["p"]))
    adj = holm_adj([b["p"] for b in B])
    for b, pa in zip(B, adj):
        b["p_holm"] = pa
        b["label"] = _label(b["delta"], pa, b["ci_lo"], b["ci_hi"], b["n"], b["tool"], b["restricted"])
        b["sign_match"] = ("—" if b["expected_sign"] == "무부호" or not (b["delta"] == b["delta"])
                           else ("예" if (b["delta"] > 0) == (b["expected_sign"] == "+") else "아니오"))
    pd.DataFrame(B).to_csv(RES / "cells_b.csv", index=False, encoding="utf-8", lineterminator="\n")

    # ── (a) 인쇄만 ──
    A = pd.read_csv(RES / "cells_a_features.csv", dtype={"stock_code": str, "scan_date": str})
    fr = pd.read_csv(LEDGER_DIR / "features.csv", dtype=str, keep_default_na=False,
                     usecols=["strategy", "scan_date", "stock_code", "ret_pct"])
    A = A.merge(fr, on=["strategy", "scan_date", "stock_code"], how="left", validate="1:1")
    A["y"] = pd.to_numeric(A["ret_pct"])
    ca = []
    variants = [(w, "", None) for w in A_WINDOWS] + [("W5", "_corr", None), ("W5", "", "band_ok")]
    kidx = {c: i for i, c in enumerate(sorted(A["stock_code"].unique()))}
    for w, sfx, sub in variants:
        As = A if sub is None else A[A["band_ok"].astype(str) == "True"].reset_index(drop=True)
        k2 = k2_sample(As, env.cal_i)
        for f in R.STRATS:
            ms = (As["strategy"] == f).to_numpy() & k2
            for tt in range(1, 8):
                x = As.loc[ms, f"x{tt}_{w}{sfx}"].to_numpy()
                y = As.loc[ms, "y"].to_numpy(dtype=float)
                c = np.array([kidx[s] for s in As.loc[ms, "stock_code"]], dtype=np.int64)
                m1 = x == 1
                n1, n0 = int(m1.sum()), int((~m1).sum())
                st = stats_binary(y[m1], c[m1], np.zeros(n1, dtype=np.int64), y[~m1], c[~m1], np.zeros(n0, dtype=np.int64),
                                  np.ones(n0), len(kidx), 1, two_way=False)
                ca.append(dict(variant=f"{w}{sfx}{'_band_ok' if sub else ''}", strategy=R.STRATS[f]["short"], t=tt,
                               tag=TAGS[tt - 1], n_with=n1, n_without=n0, delta=st["delta"], se=st["se_cr1"],
                               p_raw=st["p_cr1"] if n1 >= 2 else float("nan")))
    CA = pd.DataFrame(ca)
    CA.to_csv(RES / "cells_a.csv", index=False, encoding="utf-8", lineterminator="\n")

    # ── RESULTS ──
    L = [f"# 연구 ① DART 공시 이벤트 — 결과(⑤ 개봉) {date.today().isoformat()}", "",
         f"- 봉인 보고 `results/sealed_report.md`(sha {meta0['git_sha'][:10]}) 뒤 개봉 · 입력 md5 {md5s} · "
         f"DB 지문 {env.fp['sha256'][:12]} = 봉인 단계 ✓",
         "- 판정 언어 = 있음(+) · 있음(−) · 없음 · 판별 보류 뿐. 이 결과는 3전략 룰 변경·라이브 배선 근거가 아니다(§13-4).", "",
         "## (b) 판정 — 이벤트 첫 로트 vs 시총 5분위 층화 무작위 대조 1:1×20 · Holm m=7", "",
         "| t | 태그 | 도구 | n | δ (%p) | SE | 원 p | Holm p | 95% CI | 비대칭 제한 | 라벨 | 예상 부호 · 일치 |",
         "|---|---|---|---|---|---|---|---|---|---|---|---|"]
    for b in B:
        L.append(f"| {b['t']} | {b['tag']} | {b['tool']} | {b['n']:,} | {_f(b['delta'])} | {_f(b['se'])} | {_f(b['p'], 4)} | "
                 f"{_f(b['p_holm'], 4)} | [{_f(b['ci_lo'])}, {_f(b['ci_hi'])}] | {'예' if b['restricted'] else '아니오'} | "
                 f"**{b['label']}** | {b['expected_sign']} · {b['sign_match']} |")
    L += ["", "### 보조(인쇄만 · 판정 0)", "",
          "| t | 태그 | 이벤트 net 평균(−0.25%) | 승률 | 로트당 net(원) |", "|---|---|---|---|---|"]
    for b in B:
        L.append(f"| {b['t']} | {b['tag']} | {_f(b['net_event'])} | {b['win_rate']:.1%} | {b['pnl_net_won']:,} |")
    L += ["", "| t | 구분 | n | δ | SE(CR1) | p |", "|---|---|---|---|---|---|"]
    for x in aux:
        L.append(f"| {x['t']} | {x['kind']} | {x['n']:,} | {_f(x['delta'])} | {_f(x['se'])} | {_f(x['p'], 4)} |")
    L += ["", "## (a) 원장 후보 안 공시 있음 vs 없음 — 인쇄만(판정·라벨·Holm 없음)", "",
          "> 🔴 아래 원 p 는 이 표본에서 교정되지 않았다(가짜 게이트 없음).", "",
          "| 변형 | 전략 | t | 태그 | n_with | n_without | δ | SE | 원 p |", "|---|---|---|---|---|---|---|---|---|"]
    for r in CA.itertuples():
        L.append(f"| {r.variant} | {r.strategy} | {r.t} | {r.tag} | {r.n_with:,} | {r.n_without:,} | {_f(r.delta)} | "
                 f"{_f(r.se)} | {_f(r.p_raw, 4)} |")
    n_hold = sum(1 for b in B if b["label"].startswith(LAB_HOLD))
    L += ["", "## 사전 최빈 예측과의 대조(§7)", "",
          "- 사전 인정(§7): 「있음」은 |δ| ≳ 0.4~1.35%p 에서만 · 「없음」은 공급계약·잠정실적만 가능 · 사전 최빈 결과 = 대부분 태그 판별 보류.",
          f"- 봉인 뒤·개봉 전 사실: 비대칭 2%p 제한 {sum(1 for b in B if b['restricted'])}/7 태그 발동(sealed_report §1) ⇒ "
          "「없음」·「있음(+)」 가능 태그는 자기주식취득뿐.",
          f"- 결과: 판별 보류 {n_hold}/7 · " + " · ".join(f"{b['tag']} {b['label']}" for b in B), "",
          "## 사전등록 이탈", "",
          "- 🔒 항목(태그 정규식·순서·정정 규칙·u·W5·표본·m=7·n ≥ 30·0.4%p·2%p·게이트 0.13·시드·재추출·대체 도구·라벨) 이탈 **0**.",
          "- 문서가 정하지 않은 구현 선택은 봉인 «전»에 `results/sealed_report.md` §4 해석 기록에 적었다"
          "(정정 포함판 보조 시드 `[20261004,7,t,k]` 포함).",
          f"- 개봉 실행 HEAD `{R.git_sha()[:10]}` · 개봉 뒤 코드 수정 = 이 보고서 문안 절 추가뿐(통계·판정 경로 0줄).",
          "- 봉인 값 대조(V5): 아래 n·sd·MDE 는 봉인 단계 체크포인트를 그대로 읽는다(재계산 없음).", "",
          "| t | 태그 | n | 대조 sd | MDE ① | MDE ② |", "|---|---|---|---|---|---|"]
    for b, o in zip(B, tags0):
        L.append(f"| {b['t']} | {b['tag']} | {o['counts']['n_final']:,} | {_f(o['ctrl']['sd'])} | {_f(o['mde1'])} | "
                 f"{_f(o['mde2'])} |")
    R._atomic_write(BASE / f"RESULTS_{date.today().isoformat()}.md", "\n".join(L) + "\n")
    log(f"[끝] 개봉 {time.perf_counter() - T0:.0f}s")
    return 0


def main(argv: Optional[Sequence[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="연구 ① DART 공시 이벤트(사전등록 af3773f)")
    ap.add_argument("--stage", choices=["seal", "unseal"], required=True)
    a = ap.parse_args(argv)
    return run_seal(a) if a.stage == "seal" else run_unseal(a)


if __name__ == "__main__":
    sys.exit(main())
