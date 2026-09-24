"""FD1 재무 부실 경고 층 — 사전등록 `docs/prereg_2026-09-14_fund_distress_warning.md`(v1.0 동결 `70979b8`)
+ 등재문 `docs/prereg_2026-09-14_fund_distress_warning_amendment_2026-09-24.md` 그대로.

단계(각각 별도 프로세스 · 순서 봉인 §3-0-f · 금지 19):
  --phase 1    : §3-5 1단계 게이트(꼬리 «전» 값만) → GATE_FD1_<날짜>.md + gate.json(sha256 봉인)
                 🔴 꼬리·수익률·변동성 대조군 값을 계산·조회·인쇄하지 않는다(G7 은 --phase seal 로 넘긴다).
  --phase 1b   : 게이트 추가분 G9 · G13 본값(개정문 #2 §7 · 꼬리 «전») → gate_addendum.json
  --phase seal : gate.json 이 git HEAD 에 커밋돼 있을 때만. 재측정 창(2024-03-13~12-31 · 판정 제외)에서
                 G7 `p̂_base` → `eps_panel := 0.5 × p̂_base`(β · r̂ 없음 · 금지 21) → seal.json
  --phase 2    : seal.json 이 git HEAD 에 커밋돼 있을 때만. 판정 창(2025-01-01~2026-05-31)을 연다.

DB = `kis_template` SELECT 만(읽기 전용 세션). 라이브 모듈 0줄 변경.
"""
from __future__ import annotations

from backtest.concept_axes.minervini.cap_skip_ledger import bootstrap  # noqa: F401  안전 설정 먼저

import argparse                                                        # noqa: E402
import hashlib                                                         # noqa: E402
import json                                                            # noqa: E402
import subprocess                                                      # noqa: E402
import sys                                                             # noqa: E402
import warnings                                                        # noqa: E402
from collections import defaultdict                                    # noqa: E402
from datetime import datetime                                          # noqa: E402
from pathlib import Path                                               # noqa: E402
from typing import Any, Dict, List, Optional, Tuple                    # noqa: E402

import numpy as np                                                     # noqa: E402
import pandas as pd                                                    # noqa: E402

from backtest.concept_axes.replayer import loader as LD                # noqa: E402

warnings.filterwarnings("ignore", category=UserWarning)
warnings.filterwarnings("ignore", category=FutureWarning)

BASE = Path(__file__).resolve().parent
ROOT = BASE.parents[2]                                   # …/RoboTrader_template
LEDGER_CSV = BASE.parent / "candidate_ledger" / "results" / "ledger.csv"
FLAG_CLIFF_SQL = "RoboTrader_template/backtest/concept_axes/_defs/flag_cliff.sql"
GATE_JSON = BASE / "gate.json"
SEAL_JSON = BASE / "seal.json"
GATE_ADD_JSON = BASE / "gate_addendum.json"

# §3-0-b · §3-0-f — 창(달력 SSOT = daily_prices stock_code='KOSPI')
SAMPLE = ("2024-03-13", "2026-05-31")                    # 표본 창 537
REMEAS = ("2024-03-13", "2024-12-31")                    # 재측정 196 · 판정 제외
JUDGE = ("2025-01-01", "2026-05-31")                     # 판정 341
EXPECT_DAYS = {"sample": 537, "remeas": 196, "judge": 341}
TV_MIN = 1_000_000_000                                   # 유동성 컷 10억
ADJ_EPS = 0.001                                          # |Δadj| > 0.001 (§3-0-b · C1)

# §3-0-c · §2-1 — 슬롯 인쇄 arm(G1·G2). 풀 = screener_snapshots 상위 20 · K = max_positions
POOL_N = 20
SLOT_K = {"daytrading_3methods_breakout": 5, "book_pullback_ma20": 5, "minervini_volume_dryup": 3}
SLOT_TARGET = "daytrading_3methods_breakout"             # C-5 — 판정 대상은 이것 하나
G2_MIN = 0.10

# §3-0-b-ii · §3-2 — phase seal / 2 전용
S_MAIN, S_SENS = 0.08, 0.10
W_MAIN, W_SHORT = 10, (3, 2)
II_THR = -0.08
N_QUINT = 5
LABSORB = 0.5                                            # (라-D) 50% 문턱
N_BOOT = 10_000
SEED = 20260915
Z_MDE = 1.959964 + 0.841621                              # α=.05 양측 · power .80
CRASH_DAY = "2024-08-05"                                 # §3-0-f 6(d)


def log(msg: str = "") -> None:
    print(msg, flush=True)


def git(*args: str) -> str:
    return subprocess.run(["git", *args], cwd=ROOT, capture_output=True, text=True).stdout.strip()


def git_bytes(*args: str) -> bytes:
    return subprocess.run(["git", *args], cwd=ROOT, capture_output=True).stdout


def connect():
    import psycopg2
    conn = psycopg2.connect(**LD.dsn())
    conn.set_session(readonly=True)
    return conn


def jdump(obj: Any) -> str:
    return json.dumps(obj, ensure_ascii=False, sort_keys=True, indent=1, default=str)


# ════════════════════════════════════════════════════════════════════════════
# §1 — PIT · 플래그 D · U1 (순수 함수 · 단위 테스트 대상)
# ════════════════════════════════════════════════════════════════════════════
def pit_year(rcepts: Dict[int, Optional[np.datetime64]], d: np.datetime64) -> Optional[int]:
    """§1-1 — `rcept_dt ≤ D−1`(= `rcept_dt < D` · 달력일) 인 사업연도 중 «가장 최근» y 하나. 없으면 None."""
    vis = [y for y, r in rcepts.items() if r is not None and r < d]
    return max(vis) if vis else None


def flag_d(oi: Optional[float], te: Optional[float], ic: Optional[float], tl: Optional[float],
           oi_prev: Optional[float], prev_visible: bool) -> Tuple[Optional[int], Dict[str, Optional[bool]]]:
    """§1-2 합집합 `D` — 성분 (a)~(d) 와 D. 결측 성분은 None(«모름»).

    SQL 3치 논리 그대로: 참 성분이 하나라도 있으면 D=1 · 성분 (a)(c)(d) 가 «전부» 거짓이면 D=0 · 그 밖은 None.
    (b) 는 (a) 의 부분집합이라 D=0 판정에 필요 없다. (b) 는 전년이 따로 보여야 판정한다(§1-1 「전년 필요 시」).
    (c) 부분잠식 항은 `issued_capital` NULL 이면 «모름»(§1-1 「해당 컬럼 NULL → 모름」).
    """
    a = None if oi is None else oi < 0
    b = None if (oi is None or not prev_visible or oi_prev is None) else (oi < 0 and oi_prev < 0)
    if te is None:
        c = None
    elif te <= 0:
        c = True
    elif ic is None:
        c = None
    else:
        c = ic > 0 and te < 0.5 * ic
    dd = None if (te is None or (te > 0 and tl is None)) else (te > 0 and tl / te > 4)
    comps = {"a": a, "b": b, "c": c, "d": dd}
    if any(v is True for v in comps.values()):
        return 1, comps
    if all(v is False for v in (a, c, dd)):
        return 0, comps
    return None, comps


def u1_tier(D: Optional[int]) -> int:
    """§1-3 U1 — 정렬 키 1단: 비플래그 0 → 모름 1 → 플래그 2."""
    return 1 if D is None else (2 if D == 1 else 0)


def bd_topk(cands: List[Tuple[str, int, Optional[int]]], k: int) -> List[str]:
    """`BD` = `(D, UNK, rank)` 3계단 정렬 뒤 top-K. cands = [(code, rank, D)]."""
    return [c for c, _, _ in sorted(cands, key=lambda x: (u1_tier(x[2]), x[1]))[:k]]


def b_topk(cands: List[Tuple[str, int, Optional[int]]], k: int) -> List[str]:
    return [c for c, _, _ in sorted(cands, key=lambda x: x[1])[:k]]


def load_fin(conn) -> Tuple[Dict[str, Dict[int, tuple]], pd.DataFrame]:
    f = pd.read_sql("""SELECT trim(stock_code) AS stock_code, bsns_year::int AS y, status, rcept_dt,
                              operating_income AS oi, total_equity AS te, issued_capital AS ic,
                              total_liabilities AS tl
                       FROM dart_financials_asfiled""", conn)
    fin: Dict[str, Dict[int, tuple]] = defaultdict(dict)
    for r in f.itertuples(index=False):
        rc = None if (pd.isna(r.rcept_dt) or r.status != "000") else np.datetime64(pd.Timestamp(r.rcept_dt), "D")
        fin[r.stock_code][int(r.y)] = (rc, *(None if pd.isna(v) else float(v) for v in (r.oi, r.te, r.ic, r.tl)))
    return dict(fin), f


def classify(fin: Dict[str, Dict[int, tuple]], codes: np.ndarray, dates: np.ndarray) -> pd.DataFrame:
    """(code, date) 쌍마다 D · 성분 · 모름 사유 · 쓴 y. 종목별로 rcept 사건을 정렬해 searchsorted."""
    n = len(codes)
    out = {k: np.full(n, np.nan) for k in ("D", "fa", "fb", "fc", "fd", "fin_y")}
    unk = np.full(n, "", dtype=object)
    lenient_diff = np.zeros(n, dtype=bool)
    order = np.argsort(codes, kind="stable")
    sc = codes[order]
    bounds = np.flatnonzero(np.r_[True, sc[1:] != sc[:-1], True])
    for lo, hi in zip(bounds[:-1], bounds[1:]):
        idx = order[lo:hi]
        code = sc[lo]
        fc = fin.get(code)
        if not fc:
            unk[idx] = "no_rows"
            continue
        ev = sorted((r, y) for y, (r, *_) in fc.items() if r is not None)
        if not ev:
            unk[idx] = "no_visible_year"
            continue
        r_arr = np.array([e[0] for e in ev], dtype="datetime64[D]")
        y_cmax = np.maximum.accumulate(np.array([e[1] for e in ev]))
        dd_ = dates[idx].astype("datetime64[D]")
        pos = np.searchsorted(r_arr, dd_, side="left") - 1          # rcept < d 인 마지막 사건
        for j, p, d in zip(idx, pos, dd_):
            if p < 0:
                unk[j] = "no_visible_year"
                continue
            y = int(y_cmax[p])
            rc, oi, te, ic, tl = fc[y]
            prev = fc.get(y - 1)
            pv = prev is not None and prev[0] is not None and prev[0] < d
            D, comps = flag_d(oi, te, ic, tl, prev[1] if pv else None, pv)
            out["fin_y"][j] = y
            for k, v in comps.items():
                out["f" + k][j] = np.nan if v is None else float(v)
            if D is None:
                unk[j] = "col_null"
            else:
                out["D"][j] = D
            if D is None and te is not None and te > 0 and ic is None:   # F11(B 특징 연구) 판독과 갈리는 자리
                lenient_diff[j] = True
    df = pd.DataFrame(out)
    df["unk"] = unk
    df["lenient_diff"] = lenient_diff
    return df


# ════════════════════════════════════════════════════════════════════════════
# 데이터
# ════════════════════════════════════════════════════════════════════════════
def trading_days(conn, a: str, b: str) -> List[pd.Timestamp]:
    return LD.load_trading_calendar(conn, a, b)


def load_panel_frame(conn) -> pd.DataFrame:
    """표본 창 전 종목행 + 유동성 · adj 계단 · 창 안 adj 불변 가드(t−20..t). 가격·수익률 열은 안 가져온다."""
    q = f"""
    WITH px AS (
      SELECT stock_code, date::date AS d,
             (close * (volume * COALESCE(adj_factor, 1)))::double precision AS tv,
             (adj_factor IS NULL) AS adj_null,
             LAG(COALESCE(adj_factor, 1)) OVER w AS adj_prev,
             COALESCE(adj_factor, 1) AS adj1,
             MIN(COALESCE(adj_factor, 1)) OVER w21 AS adj_min21,
             MAX(COALESCE(adj_factor, 1)) OVER w21 AS adj_max21
      FROM daily_prices
      WHERE {LD.STOCK_ONLY} AND date::date BETWEEN '2023-12-01' AND '{SAMPLE[1]}'
      WINDOW w AS (PARTITION BY stock_code ORDER BY date::date),
             w21 AS (PARTITION BY stock_code ORDER BY date::date ROWS BETWEEN 20 PRECEDING AND CURRENT ROW)
    )
    SELECT stock_code, d, tv, adj_null,
           (adj_prev IS NOT NULL AND ABS(adj1 - adj_prev) > {ADJ_EPS}) AS adj_step,
           (adj_min21 <> adj_max21) AS adj_guard
    FROM px WHERE d BETWEEN '{SAMPLE[0]}' AND '{SAMPLE[1]}'
    """
    df = pd.read_sql(q, conn)
    df["d"] = pd.to_datetime(df["d"])
    df["tv"] = pd.to_numeric(df["tv"], errors="coerce").fillna(0.0)
    return df


def db_fingerprints(conn) -> Dict[str, Any]:
    """§12 DB 지문 5슬라이스 — daily_prices 3(재측정 · 판정 · 전방 버퍼) + dart_financials_asfiled 2."""
    out = {}
    for name, (a, b) in {"dp_remeas": REMEAS, "dp_judge": JUDGE, "dp_fwd": ("2026-06-01", "2026-06-30")}.items():
        fp = LD.db_fingerprint(conn, a, b)
        out[name] = {k: fp[k] for k in ("sha256", "n_stocks", "n_rows", "window")}
    for name, cond in {"dart_y_le_2022": "bsns_year::int <= 2022", "dart_y_ge_2023": "bsns_year::int >= 2023"}.items():
        f = pd.read_sql(f"""SELECT md5(string_agg(concat_ws('|', stock_code, bsns_year, status, rcept_dt::text,
                                   fs_div, total_equity::text, issued_capital::text, total_liabilities::text,
                                   operating_income::text), ';' ORDER BY stock_code, bsns_year)) AS h,
                                   count(*) AS n
                            FROM dart_financials_asfiled WHERE {cond}""", conn)
        out[name] = {"md5": str(f["h"].iloc[0]), "n_rows": int(f["n"].iloc[0])}
    return out


# ════════════════════════════════════════════════════════════════════════════
# PHASE 1 — 게이트(꼬리 «전»)
# ════════════════════════════════════════════════════════════════════════════
def in_win(s: pd.Series, w: Tuple[str, str]) -> pd.Series:
    return (s >= pd.Timestamp(w[0])) & (s <= pd.Timestamp(w[1]))


def cls_counts(g: pd.DataFrame) -> Dict[str, Any]:
    n = len(g)
    d0, d1 = int((g["D"] == 0).sum()), int((g["D"] == 1).sum())
    u = n - d0 - d1
    return dict(n=n, d0=d0, unk=u, d1=d1, unk_pct=round(100 * u / n, 2) if n else None,
                d1_pct_all=round(100 * d1 / n, 2) if n else None,
                d1_pct_judged=round(100 * d1 / (d0 + d1), 2) if d0 + d1 else None,
                stocks=int(g["stock_code"].nunique()),
                stocks_d1=int(g.loc[g["D"] == 1, "stock_code"].nunique()),
                stocks_d0=int(g.loc[g["D"] == 0, "stock_code"].nunique()))


def gate_slots(fin) -> Dict[str, Any]:
    """G1 · G2(= G10 ② 재현 원장 r̂) — 원장에서 식별 열 4개만 읽는다(청산·수익 열은 읽지 않는다)."""
    L = pd.read_csv(LEDGER_CSV, usecols=["strategy", "scan_date", "stock_code", "rank"],
                    dtype={"stock_code": str, "strategy": str, "scan_date": str})
    L["scan_ts"] = pd.to_datetime(L["scan_date"])
    L = L[in_win(L["scan_ts"], SAMPLE) & (L["rank"] <= POOL_N)].reset_index(drop=True)
    C = classify(fin, L["stock_code"].to_numpy(), L["scan_ts"].to_numpy().astype("datetime64[D]"))
    L["D"] = C["D"].to_numpy()
    res: Dict[str, Any] = {}
    for strat, k in SLOT_K.items():
        g = L[L["strategy"] == strat]
        per_win: Dict[str, Any] = {}
        mism_days: List[str] = []
        rows = []
        for sd, gd in g.groupby("scan_date"):
            cands = [(c, int(r), None if np.isnan(x) else int(x)) for c, r, x in
                     zip(gd["stock_code"], gd["rank"], gd["D"])]
            full_b, full_bd = b_topk(cands, len(cands)), bd_topk(cands, len(cands))   # 두 arm 의 후보 목록 전체
            tb, tbd = full_b[:k], full_bd[:k]
            if len(full_b) != len(full_bd) or set(full_b) != set(full_bd) or len(tb) != len(tbd):
                mism_days.append(sd)
            rows.append((pd.Timestamp(sd), len(full_b), len(full_bd), len(set(tb) ^ set(tbd)), len(tb)))
        R = pd.DataFrame(rows, columns=["d", "matched_b", "matched_bd", "symdiff", "k"])
        for wn, w in (("remeas", REMEAS), ("judge", JUDGE), ("sample", SAMPLE)):
            r = R[in_win(R["d"], w)]
            slots = int(r["k"].sum())
            per_win[wn] = dict(scan_days=int(len(r)), slots=slots, replaced=int(r["symdiff"].sum() // 2),
                               r_hat=round(float(r["symdiff"].sum() / (2 * slots)), 4) if slots else None,
                               days_with_replacement=int((r["symdiff"] > 0).sum()))
        cls = cls_counts(g)
        res[strat] = dict(K=k, pool=POOL_N, g1_mismatch_days=mism_days, g1_days=int(len(R)),
                          windows=per_win, pool_classes=cls)
    return res


def phase1(args) -> int:
    conn = connect()
    t0 = datetime.now()
    cal = {k: trading_days(conn, *w) for k, w in (("sample", SAMPLE), ("remeas", REMEAS), ("judge", JUDGE))}
    ndays = {k: len(v) for k, v in cal.items()}
    log(f"거래일 {ndays} (기대 {EXPECT_DAYS})")
    if ndays != EXPECT_DAYS:
        log("🔴 거래일 수가 문서(§3-0-f · §12 v0.5)와 다르다 — 중단")
        return 2
    days_by_year = pd.Series(pd.to_datetime(cal["sample"])).dt.year.value_counts().sort_index().to_dict()

    fin, fraw = load_fin(conn)
    allrows = load_panel_frame(conn)
    log(f"표본 창 전 종목행 {len(allrows):,}")
    P = allrows[allrows["tv"] >= TV_MIN].reset_index(drop=True)
    C = classify(fin, P["stock_code"].to_numpy(), P["d"].to_numpy().astype("datetime64[D]"))
    P = pd.concat([P, C], axis=1)
    P["year"] = P["d"].dt.year
    P["win"] = np.where(in_win(P["d"], REMEAS), "remeas", "judge")
    P["pref"] = [LD.is_preferred(c) for c in P["stock_code"]]
    log(f"유동성 컷 통과 종목-일 {len(P):,}")

    G: Dict[str, Any] = {}
    # ── 패널 크기(창 · 컷 뒤)
    G["panel"] = {wn: cls_counts(P[P["win"] == wn]) for wn in ("remeas", "judge")}
    G["panel"]["sample"] = cls_counts(P)
    for wn in ("remeas", "judge", "sample"):
        g = P if wn == "sample" else P[P["win"] == wn]
        G["panel"][wn]["mean_per_day"] = round(len(g) / ndays[wn], 1)
    G["panel"]["all_rows_before_cut"] = int(len(allrows))

    # ── G1 · G2 (슬롯 인쇄 arm · 재현 원장 = candidate_ledger)
    S = gate_slots(fin)
    G["G1"] = {s: dict(days=v["g1_days"], mismatch_days=v["g1_mismatch_days"]) for s, v in S.items()}
    G["G2"] = {s: dict(K=v["K"], pool=v["pool"], windows=v["windows"], pool_classes=v["pool_classes"])
               for s, v in S.items()}

    # ── G3 커버리지
    f = fraw.copy()
    f["rc_year"] = pd.to_datetime(f["rcept_dt"]).dt.year
    g3_ledger = {}
    for y, g in f.groupby("y"):
        ok = g[g["status"] == "000"]
        g3_ledger[int(y)] = dict(rows=int(len(g)), rcept_null_pct=round(100 * g["rcept_dt"].isna().mean(), 2),
                                 status_013=int((g["status"] == "013").sum()),
                                 col_null_pct={c: round(100 * ok[c].isna().mean(), 2) if len(ok) else None
                                               for c in ("oi", "te", "ic", "tl")},
                                 restated=int((ok["rc_year"] > ok["y"] + 1).sum()))
    g3_panel = {}
    for y, g in P.groupby("year"):
        judged = g["D"].notna()
        sel = g["fin_y"].notna()
        exp_y = np.where((g["d"].dt.month >= 4), g["d"].dt.year - 1, g["d"].dt.year - 2)
        g3_panel[int(y)] = dict(n=int(len(g)), no_rows_pct=round(100 * (g["unk"] == "no_rows").mean(), 2),
                                no_visible_year_pct=round(100 * (g["unk"] == "no_visible_year").mean(), 2),
                                col_null_pct_of_selected=round(100 * (g.loc[sel, "unk"] == "col_null").mean(), 2)
                                if sel.any() else None,
                                comp_null_pct_of_selected={c: round(100 * g.loc[sel, "f" + c].isna().mean(), 2)
                                                           for c in ("a", "b", "c", "d")} if sel.any() else None,
                                d_rate_judged_pct=round(100 * (g.loc[judged, "D"] == 1).mean(), 2),
                                lagged_fin_y_pct=round(100 * (g.loc[sel, "fin_y"].to_numpy()
                                                               < exp_y[sel.to_numpy()]).mean(), 2))
    G["G3"] = dict(ledger_by_bsns_year=g3_ledger, panel_by_year=g3_panel,
                   lenient_reading_diff_rows=int(P["lenient_diff"].sum()))

    # ── G4 계급 3종 · 모름 사유 · 우선주
    g4 = {}
    for (y, wn), g in P.groupby(["year", "win"]):
        c = cls_counts(g)
        c["unk_reason"] = g.loc[g["D"].isna(), "unk"].value_counts().to_dict()
        c["pref_rows"] = int(g["pref"].sum())
        c["pref_in_unk"] = int((g["pref"] & g["D"].isna()).sum())
        g4[f"{y}/{wn}"] = c
    pref_month = (P[P["pref"]].groupby(P["d"].dt.strftime("%Y-%m"))["stock_code"].nunique().to_dict())
    unk_max = max(v["unk_pct"] for v in g4.values())
    G["G4"] = dict(by_year_window=g4, pref_stocks_by_month=pref_month, unk_max_pct=unk_max,
                   note_over20=[k for k, v in g4.items() if v["unk_pct"] > 20],
                   stop_over50=[k for k, v in g4.items() if v["unk_pct"] > 50])

    # ── G5 연도별 쏠림 (D=1 종목-일 · 원시 + 거래일 정규화)
    def skew(g: pd.DataFrame, win: str) -> Dict[str, Any]:
        cal_y = pd.Series(pd.to_datetime(cal[win])).dt.year.value_counts().to_dict()
        cnt = g[g["D"] == 1].groupby("year").size().to_dict()
        tot = sum(cnt.values())
        raw = {int(y): round(v / tot, 4) for y, v in cnt.items()}
        per = {y: cnt.get(y, 0) / cal_y[y] for y in cal_y}
        s = sum(per.values())
        norm = {int(y): round(v / s, 4) for y, v in per.items()}
        return dict(d1_by_year=cnt, trading_days_by_year=cal_y, raw_share=raw, norm_share=norm,
                    max_raw=max(raw.values()), max_norm=max(norm.values()),
                    pass_=bool(max(raw.values()) <= 0.5 and max(norm.values()) <= 0.5))
    G["G5"] = dict(sample=skew(P, "sample"), judge=skew(P[P["win"] == "judge"], "judge"))

    # ── G6 성분 분해 · 쌍별 중복
    g6 = {}
    for wn in ("remeas", "judge", "sample"):
        g = P if wn == "sample" else P[P["win"] == wn]
        d1 = g[g["D"] == 1]
        n1 = len(d1)
        share = {c: round(float((d1["f" + c] == 1).sum() / n1), 4) for c in "abcd"}
        only = {c: round(float(((d1["f" + c] == 1) & (d1[["f" + o for o in "acd" if o != c]] != 1).all(axis=1)).sum() / n1), 4)
                for c in "acd"}
        mat = {f"{x}&{y}": int(((d1["f" + x] == 1) & (d1["f" + y] == 1)).sum()) for i, x in enumerate("abcd") for y in "abcd"[i:]}
        g6[wn] = dict(n_d1=n1, share_of_D=share, only_share=only, pair_matrix=mat,
                      over90=[c for c, v in share.items() if v > 0.9],
                      P5_a_share=share["a"], P5_refuted=bool(share["a"] < 0.70))
    G["G6"] = g6

    # ── G7 — 🔴 이 단계에서 산출하지 않는다(꼬리 값 · 지시서 금지 · --phase seal 로)
    G["G7"] = dict(status="withheld_phase1",
                   plan="--phase seal: 재측정 창 196일 · 모집단 D∈{0,1}(U1 모름 제외 · Open Q3) · s=0.08 · 창 10")

    # ── 결과 «전» MDE 브래킷(가상 기저율 · 판정 창 · 행/종목 두 극단) — 정본 MDE 는 phase 2 블록 부트스트랩
    j = G["panel"]["judge"]
    n1, n0 = j["d1"], j["d0"]
    k1, k0 = j["stocks_d1"], j["stocks_d0"]
    mde = {}
    for p in (0.05, 0.10, 0.20, 0.30):
        m_rows = Z_MDE * np.sqrt(p * (1 - p) * (1 / n1 + 1 / n0))
        m_stk = Z_MDE * np.sqrt(p * (1 - p) * (1 / k1 + 1 / k0))
        mde[str(p)] = dict(eps_panel=round(0.5 * p, 4), mde_rows_deff1=round(float(m_rows), 4),
                           mde_stocks_full_icc=round(float(m_stk), 4), stocks_ok=bool(m_stk <= 0.5 * p))
    G["MDE_bracket"] = dict(n_d1=n1, n_d0=n0, stocks_d1=k1, stocks_d0=k0, grid=mde)

    # ── G13(h) adj 계단 — 전 종목행 / 컷 통과 · 창 안 adj 불변 가드
    adj = {}
    for wn, w in (("remeas", REMEAS), ("judge", JUDGE), ("sample", SAMPLE)):
        a_all = allrows[in_win(allrows["d"], w)]
        a_cut = P if wn == "sample" else P[P["win"] == wn]
        adj[wn] = dict(step_rows_all=int(a_all["adj_step"].sum()),
                       step_stocks_all=int(a_all.loc[a_all["adj_step"], "stock_code"].nunique()),
                       step_rows_cut=int(a_cut["adj_step"].sum()),
                       guard_unknown_cut=int(a_cut["adj_guard"].sum()),
                       guard_unknown_cut_by_class={k: int(a_cut.loc[m, "adj_guard"].sum()) for k, m in
                                                   (("d0", a_cut["D"] == 0), ("d1", a_cut["D"] == 1),
                                                    ("unk", a_cut["D"].isna()))},
                       adj_null_rows_cut=int(a_cut["adj_null"].sum()))
    G["G13h_adj"] = adj

    fp = db_fingerprints(conn)
    conn.close()
    fc_bytes = git_bytes("show", f"HEAD:{FLAG_CLIFF_SQL}")
    meta = dict(prereg="docs/prereg_2026-09-14_fund_distress_warning.md", freeze_commit="70979b8",
                amendment="docs/prereg_2026-09-14_fund_distress_warning_amendment_2026-09-24.md",
                git_head=git("rev-parse", "HEAD"), git_dirty=bool(git("status", "--porcelain", "--", ".")),
                run_at=t0.isoformat(timespec="seconds"), elapsed_s=round((datetime.now() - t0).total_seconds(), 1),
                trading_days=ndays, trading_days_by_year=days_by_year, db=LD.dsn()["dbname"], db_fingerprint=fp,
                flag_cliff_sql_sha256_head=hashlib.sha256(fc_bytes).hexdigest(),
                tail_values_computed=False, ledger_cols_read=["strategy", "scan_date", "stock_code", "rank"])
    body = jdump(dict(meta=meta, gates=G))
    GATE_JSON.write_bytes(body.encode("utf-8"))
    sha = hashlib.sha256(GATE_JSON.read_bytes()).hexdigest()
    md = gate_md(G, meta, sha, days_by_year)
    out_md = BASE / f"GATE_FD1_{t0.strftime('%Y%m%d')}.md"
    out_md.write_bytes(md.encode("utf-8"))
    log(f"gate.json sha256 = {sha}")
    log(f"→ {out_md.name}")
    return 0


def _pf(ok: bool) -> str:
    return "✅ PASS" if ok else "🔴 FAIL"


def gate_md(G: Dict[str, Any], meta: Dict[str, Any], sha: str, days_by_year: Dict[int, int]) -> str:
    j, r, s = G["panel"]["judge"], G["panel"]["remeas"], G["panel"]["sample"]
    dt = G["G2"][SLOT_TARGET]["windows"]
    g1_ok = all(not v["mismatch_days"] for v in G["G1"].values())
    g2_ok = dt["judge"]["r_hat"] is not None and dt["judge"]["r_hat"] >= G2_MIN
    g4_stop = bool(G["G4"]["stop_over50"])
    g5s, g5j = G["G5"]["sample"], G["G5"]["judge"]
    L: List[str] = []
    a = L.append
    a(f"# FD1 1단계 게이트 — {meta['run_at'][:10]} (꼬리 «전» · §3-5)")
    a("")
    a(f"- 사전등록 `{meta['prereg']}`(동결 `{meta['freeze_commit']}`) + 등재문 `{meta['amendment']}`")
    a(f"- 실행 HEAD `{meta['git_head'][:7]}` · DB `{meta['db']}`(SELECT 전용) · 소요 {meta['elapsed_s']}s")
    a(f"- 🔒 **`gate.json` sha256 = `{sha}`**")
    a("- 🔴 **꼬리(i)(ii) · 수익률 · 변동성 대조군 값: 계산 0 · 조회 0 · 인쇄 0.** 원장은 식별 열 4개"
      f"({', '.join(meta['ledger_cols_read'])})만 읽었다. **G7 은 산출하지 않았다**(아래).")
    a(f"- 거래일(SQL · KOSPI 달력): 표본 {meta['trading_days']['sample']} = 재측정 {meta['trading_days']['remeas']}"
      f" + 판정 {meta['trading_days']['judge']} ✅ 문서 일치 · 연도별 {days_by_year}")
    a(f"- `_defs/flag_cliff.sql` sha256(`git show HEAD:`) = `{meta['flag_cliff_sql_sha256_head']}`")
    a("")
    a("## 패널 크기 (유동성 컷 `close×volume×COALESCE(adj,1) ≥ 10억` 뒤 · 시총 미사용)")
    a("")
    a("| 창 | 종목-일 | 일평균 | 종목 | D=0 | 모름 | D=1 | D=1 %(판정 가능 중) | 모름 % |")
    a("|---|--:|--:|--:|--:|--:|--:|--:|--:|")
    for nm, c in (("재측정 196", r), ("판정 341", j), ("표본 537", s)):
        a(f"| {nm} | {c['n']:,} | {c['mean_per_day']} | {c['stocks']:,} | {c['d0']:,} | {c['unk']:,} | {c['d1']:,} "
          f"| {c['d1_pct_judged']} | {c['unk_pct']} |")
    a(f"\n컷 «전» 표본 창 종목행 {G['panel']['all_rows_before_cut']:,}. 판정 창 고유 종목: D=1 {j['stocks_d1']:,} · "
      f"D=0 {j['stocks_d0']:,}.")
    a("")
    a("## 게이트 판정표")
    a("")
    a("| # | 값 | 문턱(§3-5) | 판정 |")
    a("|---|---|---|---|")
    a(f"| G1 | 날짜별 후보 수 B vs BD 불일치 일수 = " +
      " · ".join(f"{k.split('_')[0]} {len(v['mismatch_days'])}/{v['days']}" for k, v in G["G1"].items()) +
      " | 하루라도 다르면 중단 | " + _pf(g1_ok) + " |")
    a(f"| G2 | daytrading 슬롯 교체율 r̂(재현 원장 · K=5 · 풀 상위 20): 판정 창 **{dt['judge']['r_hat']}** · "
      f"재측정 창 {dt['remeas']['r_hat']} · 표본 {dt['sample']['r_hat']} | < 10% 면 슬롯 arm 「판별 보류」 | "
      + ("✅ PASS" if g2_ok else "🟡 슬롯 arm 판별 보류") + " (패널 주 검정과 무관) |")
    a("| G3 | 커버리지 연도별(아래 표) | 인쇄 | 인쇄 |")
    a(f"| G4 | 모름 최대 {G['G4']['unk_max_pct']}% · 20% 초과 {G['G4']['note_over20'] or '없음'} · "
      f"50% 초과 {G['G4']['stop_over50'] or '없음'} | 20% 초과 병기 · 50% 초과 중단(§4) | "
      + ("🔴 중단" if g4_stop else ("🟡 병기" if G["G4"]["note_over20"] else "✅ 인쇄")) + " |")
    a(f"| G5 | D=1 연도 쏠림 — 표본 창: 원시 최대 {g5s['max_raw']} · 정규화 최대 {g5s['max_norm']} / "
      f"판정 창: 원시 {g5j['max_raw']} · 정규화 {g5j['max_norm']} | 양쪽 ≤ 50% | 표본 창 {_pf(g5s['pass_'])} · "
      f"판정 창 {_pf(g5j['pass_'])}(아래 「개정 필요」) |")
    g6j = G["G6"]["judge"]
    a(f"| G6 | 판정 창 D 성분 비중 a {g6j['share_of_D']['a']} · b {g6j['share_of_D']['b']} · c {g6j['share_of_D']['c']}"
      f" · d {g6j['share_of_D']['d']} | 한 성분 > 90% 면 병기 | " +
      (f"🟡 병기: 「D 는 사실상 ({','.join(g6j['over90'])})」" if g6j["over90"] else "✅ 인쇄") +
      f" · P5 {'반증' if g6j['P5_refuted'] else '유지'}(a ≥ 70%) |")
    a("| G7 | **산출 안 함** — 기저 꼬리율은 꼬리 값이다(지시서 금지) | §5 표본 산술 입력 | ⏸ `--phase seal` |")
    a("")
    a("## G2 상세 — 슬롯 인쇄 arm(인쇄 전용 · 판정 언어 금지)")
    a("")
    a("| 전략 | K | 창 | 스캔일 | 슬롯 | 교체 | r̂ | 교체 있던 날 |")
    a("|---|--:|---|--:|--:|--:|--:|--:|")
    for st, v in G["G2"].items():
        for wn in ("remeas", "judge", "sample"):
            w = v["windows"][wn]
            a(f"| {st.split('_')[0]} | {v['K']} | {wn} | {w['scan_days']} | {w['slots']:,} | {w['replaced']:,} | "
              f"{w['r_hat']} | {w['days_with_replacement']} |")
    a("")
    a("🔴 「후보 ≠ 매수가능 ≈8.5%」(§3-0-h) · 재현 원장 = `candidate_ledger`(안전필터 «이전») · ma20·minervini 는 인쇄만.")
    a("")
    a("## G3 커버리지")
    a("")
    a("원장(`dart_financials_asfiled`) 사업연도별:")
    a("")
    a("| bsns_year | 행 | rcept_dt 결측% | 013 | 결측% oi/te/ic/tl (000) | 정정본(rcept 연도 > y+1) |")
    a("|---|--:|--:|--:|---|--:|")
    for y, v in G["G3"]["ledger_by_bsns_year"].items():
        cn = v["col_null_pct"]
        a(f"| {y} | {v['rows']:,} | {v['rcept_null_pct']} | {v['status_013']} | {cn['oi']}/{cn['te']}/{cn['ic']}/{cn['tl']}"
          f" | {v['restated']} |")
    a("")
    a("패널 달력연도별:")
    a("")
    a("| 연도 | 종목-일 | no_rows% | no_visible_year% | col_null%(선택 y 중) | 성분 결측% a/b/c/d | D 발생률%(판정 가능 중) | y 지연% |")
    a("|---|--:|--:|--:|--:|---|--:|--:|")
    for y, v in G["G3"]["panel_by_year"].items():
        cn = v["comp_null_pct_of_selected"]
        a(f"| {y} | {v['n']:,} | {v['no_rows_pct']} | {v['no_visible_year_pct']} | {v['col_null_pct_of_selected']} | "
          f"{cn['a']}/{cn['b']}/{cn['c']}/{cn['d']} | {v['d_rate_judged_pct']} | {v['lagged_fin_y_pct']} |")
    a(f"\n`issued_capital` NULL 로 (c) 가 «모름» 이 되어 B 특징 연구 F11 판독(NULL→거짓)과 갈리는 종목-일 = "
      f"{G['G3']['lenient_reading_diff_rows']:,}.")
    a("")
    a("## G4 계급 3종 (연도 × 창)")
    a("")
    a("| 연도/창 | n | D=0 | 모름 | D=1 | 모름% | 모름 사유 | 우선주 행(모름) |")
    a("|---|--:|--:|--:|--:|--:|---|--:|")
    for k, v in G["G4"]["by_year_window"].items():
        a(f"| {k} | {v['n']:,} | {v['d0']:,} | {v['unk']:,} | {v['d1']:,} | {v['unk_pct']} | {v['unk_reason']} | "
          f"{v['pref_rows']}({v['pref_in_unk']}) |")
    a(f"\n우선주 종목 수 월별(컷 통과): {G['G4']['pref_stocks_by_month'] or '0'}")
    a("")
    a("## G5 연도별 쏠림 (D=1 종목-일)")
    a("")
    for nm, g in (("표본 창", g5s), ("판정 창", g5j)):
        a(f"- {nm}: 건수 {g['d1_by_year']} · 거래일 {g['trading_days_by_year']} · 원시 {g['raw_share']} · 정규화 {g['norm_share']}")
    a("")
    a("## G6 성분 분해 (D=1 중 비중 · 단독 비중 · 쌍별 중복 행수)")
    a("")
    for wn, v in G["G6"].items():
        a(f"- {wn}: n(D=1) {v['n_d1']:,} · 비중 {v['share_of_D']} · 단독 {v['only_share']} · 중복 {v['pair_matrix']}")
    a("")
    a("## 결과 «전» MDE 브래킷 (판정 창 · 가상 기저율 · α .05 양측 · power .80)")
    a("")
    a("정본 MDE 는 phase 2 종목 블록 부트스트랩이다. 아래는 행 독립(DEFF 1)과 종목 완전상관(유효 n = 고유 종목) 두 극단.")
    a("")
    a("| 가상 p̂_base | eps_panel=0.5p | MDE 행(DEFF 1) | MDE 종목(완전상관) | 종목 극단에서도 MDE ≤ eps |")
    a("|--:|--:|--:|--:|---|")
    for p, v in G["MDE_bracket"]["grid"].items():
        a(f"| {p} | {v['eps_panel']} | {v['mde_rows_deff1']} | {v['mde_stocks_full_icc']} | {'예' if v['stocks_ok'] else '아니오'} |")
    a("")
    a("## G13(h) adj 계단 (|Δadj| > 0.001) · 창 안 adj 불변 가드")
    a("")
    a("| 창 | 계단 행(전 종목행) | 계단 종목 | 계단 행(컷 통과) | 가드 「모른다」(컷 통과) 군별 | adj NULL 행(컷 통과) |")
    a("|---|--:|--:|--:|---|--:|")
    for wn, v in G["G13h_adj"].items():
        a(f"| {wn} | {v['step_rows_all']} | {v['step_stocks_all']} | {v['step_rows_cut']} | "
          f"{v['guard_unknown_cut']} {v['guard_unknown_cut_by_class']} | {v['adj_null_rows_cut']:,} |")
    a("")
    a("## DB 지문 5슬라이스 (§12)")
    a("")
    for k, v in meta["db_fingerprint"].items():
        a(f"- {k}: {v}")
    a("")
    return "\n".join(L) + "\n"


# ════════════════════════════════════════════════════════════════════════════
# PHASE 1b — 게이트 추가분 G9 · G13 본값 (개정문 #2 §7 · seal «전» · 꼬리 «전»)
# ════════════════════════════════════════════════════════════════════════════
DOC_PAD_PER_DAY = {2021: 17.3, 2022: 13.7, 2023: 8.0, 2024: 44.4, 2025: 69.3, 2026: 111.9}   # FD1 §3-0-d
G9_MISS_MAX, G9_TOP_MAX, G13_RATIO_MAX = 0.10, 0.60, 2.0


def day_quintiles(V: pd.Series, d: pd.Series) -> pd.Series:
    """그날 모집단 안 `V` 5분위(0 = 최저 · 4 = 최고) — 결측은 NaN · 그날 유효값 < 5 면 NaN."""
    def q(x: pd.Series) -> pd.Series:
        if x.notna().sum() < N_QUINT:
            return pd.Series(np.nan, index=x.index)
        return pd.qcut(x.rank(method="first"), N_QUINT, labels=False).astype(float)
    return V.groupby(d).transform(q)


def max_year_ratio(per_day: Dict[int, float]) -> float:
    """연도 간 «거래일당» 값의 최대/최소 비(§3-0-d 2 · G13) — 0 이 있으면 inf."""
    v = [x for x in per_day.values()]
    return float("inf") if min(v) <= 0 else max(v) / min(v)


def padding_by_year(conn, a: str, b: str) -> pd.DataFrame:
    """패딩행(OHLC 동일 ∧ volume=0 · FD1 §0-3) 연도별 건수 — 집계만 가져온다(가격 행을 읽지 않는다)."""
    return pd.read_sql(f"""
        SELECT EXTRACT(year FROM date::date)::int AS y,
               COUNT(*) FILTER (WHERE open = high AND high = low AND low = close AND volume = 0) AS pad,
               COUNT(*) AS n
        FROM daily_prices WHERE {LD.STOCK_ONLY} AND date::date BETWEEN '{a}' AND '{b}'
        GROUP BY 1 ORDER BY 1""", conn)


def phase1b(args) -> int:
    gate_sha = hashlib.sha256(GATE_JSON.read_bytes()).hexdigest()
    conn = connect()
    t0 = datetime.now()
    fin, _ = load_fin(conn)
    # ── G9 — V = volatility_20d 의 D−1(그 종목 직전 행) 값 · 모집단 = 그날 유동성 컷 통과 집합(§3-2-b v0.4)
    P = pd.read_sql(f"""
        WITH px AS (
          SELECT stock_code, date::date AS d,
                 (close * (volume * COALESCE(adj_factor, 1)))::double precision AS tv,
                 LAG(volatility_20d) OVER (PARTITION BY stock_code ORDER BY date::date) AS v_prev
          FROM daily_prices WHERE {LD.STOCK_ONLY} AND date::date BETWEEN '2024-01-01' AND '{SAMPLE[1]}')
        SELECT stock_code, d, v_prev AS "V" FROM px
        WHERE d BETWEEN '{SAMPLE[0]}' AND '{SAMPLE[1]}' AND tv >= {TV_MIN}""", conn)
    P["d"] = pd.to_datetime(P["d"])
    C = classify(fin, P["stock_code"].to_numpy(), P["d"].to_numpy().astype("datetime64[D]"))
    P["D"] = C["D"].to_numpy()
    P["cls"] = np.where(P["D"] == 1, "d1", np.where(P["D"] == 0, "d0", "unk"))
    P["Vq"] = day_quintiles(P["V"], P["d"])
    P["year"] = P["d"].dt.year
    P["win"] = np.where(in_win(P["d"], REMEAS), "remeas", "judge")
    miss = {int(y): dict(all=round(float(g["V"].isna().mean()), 4),
                         **{c: round(float(g.loc[g["cls"] == c, "V"].isna().mean()), 4) for c in ("d0", "unk", "d1")})
            for y, g in P.groupby("year")}
    dist = {}
    for wn in ("remeas", "judge", "sample"):
        g = P if wn == "sample" else P[P["win"] == wn]
        dist[wn] = {c: {f"Q{int(q) + 1}": round(float(v), 4) for q, v in
                        g.loc[(g["cls"] == c) & g["Vq"].notna(), "Vq"].value_counts(normalize=True).sort_index().items()}
                    for c in ("d0", "unk", "d1")}
    g9 = dict(rows=int(len(P)), missing_by_year=miss, quintile_share=dist,
              note_missing_over10=[y for y, v in miss.items() if v["all"] > G9_MISS_MAX],
              d1_top_share={wn: dist[wn]["d1"].get("Q5") for wn in dist},
              note_d1_top_over60=[wn for wn in dist if (dist[wn]["d1"].get("Q5") or 0) > G9_TOP_MAX])
    # ── G13 — 패딩 «거래일당» 연도별(전 종목행)
    cal_all = pd.Series(pd.to_datetime(trading_days(conn, "2021-01-01", SAMPLE[1]))).dt.year.value_counts()
    cal_s = pd.Series(pd.to_datetime(trading_days(conn, *SAMPLE))).dt.year.value_counts()
    pad_all = padding_by_year(conn, "2021-01-01", SAMPLE[1])
    pad_s = padding_by_year(conn, *SAMPLE)
    conn.close()

    def per_day(pad: pd.DataFrame, cal: pd.Series) -> Dict[int, Dict[str, Any]]:
        return {int(r.y): dict(pad_rows=int(r.pad), rows=int(r.n), trading_days=int(cal[int(r.y)]),
                               pad_per_day=round(float(r.pad) / int(cal[int(r.y)]), 1)) for r in pad.itertuples()}
    g13_all, g13_s = per_day(pad_all, cal_all), per_day(pad_s, cal_s)
    ratio_s = max_year_ratio({y: v["pad_per_day"] for y, v in g13_s.items()})
    g13 = dict(calendar_years_2021_to_20260531=g13_all, sample_window_by_year=g13_s,
               doc_values_fd1_3_0_d=DOC_PAD_PER_DAY, sample_max_min_ratio=round(ratio_s, 3),
               drift_note=bool(ratio_s > G13_RATIO_MAX),
               deferred_to_phase2=["n_impossible", "(i) 사건 월별 분포", "G12 flag_cliff 군별"])
    meta = dict(gate_json_sha256_unchanged=gate_sha, git_head=git("rev-parse", "HEAD"),
                run_at=t0.isoformat(timespec="seconds"), elapsed_s=round((datetime.now() - t0).total_seconds(), 1),
                tail_values_computed=False, returns_read=False,
                cols_read=["stock_code", "date", "close×volume×adj(유동성 컷)", "volatility_20d(LAG)",
                           "OHLC 동일∧volume=0 건수(SQL 집계)", "dart_financials_asfiled"])
    GATE_ADD_JSON.write_bytes(jdump(dict(meta=meta, G9=g9, G13=g13)).encode("utf-8"))
    sha = hashlib.sha256(GATE_ADD_JSON.read_bytes()).hexdigest()
    L: List[str] = []
    a = L.append
    a("# FD1 1단계 게이트 추가분 — G9 · G13 본값 (개정문 #2 §7 · seal «전»)")
    a("")
    a(f"- 🔒 **`gate_addendum.json` sha256 = `{sha}`** · 기존 `gate.json` sha256 `{gate_sha}`(바이트 불변)")
    a(f"- 실행 HEAD `{meta['git_head'][:7]}` · DB SELECT 전용 · 소요 {meta['elapsed_s']}s")
    a("- 🔴 **꼬리(i)(ii) · 수익률 · 절벽 · 불가능봉 값: 계산 0 · 조회 0 · 인쇄 0.** 읽은 것 = 유동성 컷 · "
      "`volatility_20d`(D−1) · 패딩 건수(SQL 집계) · 재무 원장뿐. `n_impossible`·사건 월별·G12 는 phase 2(개정문 #2 §7).")
    a("")
    a("## 판정표")
    a("")
    a("| # | 값 | 문턱(§3-5) | 판정 |")
    a("|---|---|---|---|")
    a(f"| G9 결측 | 연도별 V 결측 최대 {max(v['all'] for v in miss.values())} | 어느 해 > 10% 면 병기 | "
      + (f"🟡 병기 {g9['note_missing_over10']}" if g9["note_missing_over10"] else "✅ 인쇄") + " |")
    a(f"| G9 쏠림 | D=1 의 최상위(Q5) 비중: 재측정 {g9['d1_top_share']['remeas']} · 판정 {g9['d1_top_share']['judge']} · "
      f"표본 {g9['d1_top_share']['sample']} | > 60% 면 「층화 후 비교 가능한 셀이 없다」 병기 | "
      + (f"🟡 병기 {g9['note_d1_top_over60']}" if g9["note_d1_top_over60"] else "✅ 인쇄") + " |")
    a(f"| G13 | 표본 창 패딩 거래일당 연도 최대/최소 비 {g13['sample_max_min_ratio']} | > 2배 면 「측정기 드리프트」 병기 + "
      f"연도 pooled 금지 | " + ("🟡 병기" if g13["drift_note"] else "✅ 인쇄") + " |")
    a("")
    a("## G9 — `volatility_20d`(D−1) 결측률 (컷 통과 종목-일)")
    a("")
    a("| 연도 | 전체 | D=0 | 모름 | D=1 |")
    a("|---|--:|--:|--:|--:|")
    for y, v in miss.items():
        a(f"| {y} | {v['all']} | {v['d0']} | {v['unk']} | {v['d1']} |")
    a("")
    a("## G9 — 군별 `V` 5분위 분포 (분위 = 그날 컷 통과 집합 안 · Q5 = 최고 변동성)")
    a("")
    a("| 창 | 군 | Q1 | Q2 | Q3 | Q4 | Q5 |")
    a("|---|---|--:|--:|--:|--:|--:|")
    for wn, dd in dist.items():
        for c, v in dd.items():
            a(f"| {wn} | {c} | " + " | ".join(str(v.get(f'Q{i}')) for i in range(1, 6)) + " |")
    a("")
    a("## G13 — 패딩행(OHLC 동일 ∧ volume=0 · 전 종목행) «거래일당»")
    a("")
    a("| 연도 | 달력연도(~2026-05-31) 패딩/일 | 표본 창 안 패딩/일 | 패딩 행 | 거래일 | FD1 §3-0-d 기재값 |")
    a("|---|--:|--:|--:|--:|--:|")
    for y, v in g13_all.items():
        s_ = g13_s.get(y)
        s_pd = s_["pad_per_day"] if s_ else "-"
        a(f"| {y} | {v['pad_per_day']} | {s_pd} | {v['pad_rows']:,} | {v['trading_days']} | "
          f"{DOC_PAD_PER_DAY.get(y)} |")
    a("")
    a("G13 (h) `adj` 계단은 `gate.json`(`fd70b18`)에 이미 있다.")
    (BASE / f"GATE_FD1_{t0.strftime('%Y%m%d')}_addendum.md").write_bytes(("\n".join(L) + "\n").encode("utf-8"))
    log(f"gate_addendum.json sha256 = {sha}")
    return 0


# ════════════════════════════════════════════════════════════════════════════
# PHASE seal / 2 — 꼬리 (🔴 1단계 게이트 커밋 «뒤»에만)
# ════════════════════════════════════════════════════════════════════════════
def require_committed(path: Path) -> str:
    """파일이 HEAD 에 커밋돼 있고 작업 트리 바이트와 같아야 한다. 커밋 시각(ISO)을 돌려준다."""
    rel = path.relative_to(ROOT.parent).as_posix()
    head = git_bytes("show", f"HEAD:{rel}")
    if not head or head != path.read_bytes():
        raise SystemExit(f"🔴 {rel} 가 HEAD 에 커밋돼 있지 않거나 작업 트리와 다르다 — 순서 봉인(§3-0-f) 위반 방지로 중단")
    return git("log", "-1", "--format=%cI", "--", str(path))


def tail_events(px: pd.DataFrame, cal: List[pd.Timestamp], t0_last: Optional[int] = None) -> pd.DataFrame:
    """종목-일마다 꼬리 이진 지표(§3-0-b-ii · §3-2 (ii)) — 절벽 포함(inc)/제외(exc) 두 판.

    창 = t0 다음 «달력» 거래일부터 w 거래일(KOSPI 달력). 창 끝이 달력 끝을 넘으면 NaN(우측 절단).
    `flag_cliff`(§3-4-b 규약 1-b · `_defs/flag_cliff.sql` 과 같은 식) 인 날의 사건은 exc 판에서 세지 않는다.
    px 열 = stock_code, d, open, close, vol_adj, adj1. 전일 = 그 종목의 직전 «행»(SQL LAG 와 같다).
    """
    px = px.sort_values(["stock_code", "d"]).reset_index(drop=True)
    g = px.groupby("stock_code", sort=False)
    prev = g["close"].shift(1)
    ret = px["close"] / prev - 1
    gap = px["open"] / prev - 1
    vma = g["vol_adj"].transform(lambda x: x.shift(1).rolling(20, min_periods=20).mean())
    amin = g["adj1"].transform(lambda x: x.rolling(21, min_periods=21).min())
    amax = g["adj1"].transform(lambda x: x.rolling(21, min_periods=21).max())
    judgeable = (g.cumcount() >= 20) & (amin == amax) & (prev > 0)
    px["cliff"] = judgeable & (ret <= -0.18) & (gap <= 0.80 * ret) & (px["vol_adj"] <= 2.0 * vma)
    px["cliff_unknown"] = ~judgeable
    px["ev_ii"] = ret <= II_THR
    cal_ix = pd.DatetimeIndex(cal)
    px = px[px["d"].isin(cal_ix)]
    piv = {c: px.pivot(index="d", columns="stock_code", values=c).reindex(cal_ix)
           for c in ("open", "close", "cliff", "ev_ii")}
    O = piv["open"].to_numpy(float)
    Cl = piv["close"].to_numpy(float)
    X = piv["cliff"].fillna(False).to_numpy(bool)
    E2 = piv["ev_ii"].fillna(False).to_numpy(bool)
    T = len(cal_ix)
    out = {}
    for tag, excl in (("inc", np.zeros_like(X)), ("exc", X)):
        Oe = np.where(np.isnan(O) | excl, np.inf, O)
        Ee = E2 & ~excl
        for s, w in ((S_MAIN, W_MAIN), (S_SENS, W_MAIN)) + tuple((S_MAIN, ws) for ws in W_SHORT):
            fmin = np.full_like(O, np.inf)
            for k in range(1, w + 1):
                fmin[:T - k] = np.minimum(fmin[:T - k], Oe[k:])
            r = (fmin < Cl * (1 - s)).astype(float)
            r[min(T - w, T if t0_last is None else t0_last + 1):] = np.nan
            out[f"i_s{int(round(s * 100)):02d}_w{w}_{tag}"] = r
        fany = np.zeros_like(E2)
        for k in range(1, W_MAIN + 1):
            fany[:T - k] |= Ee[k:]
        r = fany.astype(float)
        r[min(T - W_MAIN, T if t0_last is None else t0_last + 1):] = np.nan
        out[f"ii_w{W_MAIN}_{tag}"] = r
    cols = piv["open"].columns
    frames = [pd.DataFrame(v, index=cal_ix, columns=cols).stack(future_stack=True).rename(k) for k, v in out.items()]
    res = pd.concat(frames, axis=1).reset_index()
    res.columns = ["d", "stock_code", *out.keys()]
    return res.merge(px[["stock_code", "d", "cliff", "cliff_unknown"]], on=["stock_code", "d"], how="inner")


def load_tail_frame(conn, win: Tuple[str, str]) -> Tuple[pd.DataFrame, List[pd.Timestamp]]:
    """꼬리 계산용 가격(원시 · 가격에 adj 미적용 · volume 에만 COALESCE(adj,1)) + V(volatility_20d).

    읽는 끝 = 창 끝 + W_MAIN 거래일(전방 창에 필요한 만큼만). 그 뒤 날짜는 t0 로 쓰이면 우측 절단(NaN)이다
    ⇒ seal(재측정 창)에서 판정 창 t0 의 꼬리는 «계산되지 않는다»(첫 10거래일 가격은 재측정 t0 의 전방 창으로만 쓰인다).
    """
    cal_all = trading_days(conn, "2023-12-01", "2026-07-31")
    last = max(i for i, d in enumerate(cal_all) if d <= pd.Timestamp(win[1]))
    cal = cal_all[:last + W_MAIN + 1]
    end = pd.Timestamp(cal[-1]).strftime("%Y-%m-%d")
    q = f"""SELECT stock_code, date::date AS d, open, close,
                   (volume * COALESCE(adj_factor,1))::double precision AS vol_adj,
                   COALESCE(adj_factor,1) AS adj1,
                   (close * (volume * COALESCE(adj_factor,1)))::double precision AS tv,
                   volatility_20d AS v20
            FROM daily_prices WHERE {LD.STOCK_ONLY} AND date::date BETWEEN '2023-12-01' AND '{end}'"""
    px = pd.read_sql(q, conn)
    px["d"] = pd.to_datetime(px["d"])
    return px, cal


def build_tail_panel(conn, fin, win: Tuple[str, str]) -> pd.DataFrame:
    px, cal = load_tail_frame(conn, win)
    ev = tail_events(px, cal, t0_last=max(i for i, d in enumerate(cal) if d <= pd.Timestamp(win[1])))
    px = px.sort_values(["stock_code", "d"])
    px["V"] = px.groupby("stock_code")["v20"].shift(1)                    # D−1 시점 값(§3-2-b)
    P = px[in_win(px["d"], win) & (px["tv"] >= TV_MIN)][["stock_code", "d", "V"]]
    P = P.merge(ev, on=["stock_code", "d"], how="left")
    C = classify(fin, P["stock_code"].to_numpy(), P["d"].to_numpy().astype("datetime64[D]"))
    P = pd.concat([P.reset_index(drop=True), C[["D", "unk"]]], axis=1)
    P["Vq"] = day_quintiles(P["V"], P["d"])
    return P


def rates(P: pd.DataFrame, col: str) -> Dict[str, Any]:
    out = {}
    for nm, m in (("d0", P["D"] == 0), ("unk", P["D"].isna()), ("d1", P["D"] == 1)):
        x = P.loc[m, col].dropna()
        out[nm] = dict(n=int(len(x)), rate=round(float(x.mean()), 5) if len(x) else None)
    return out


def deltas(P: pd.DataFrame, col: str) -> Tuple[float, float]:
    """(비층화 delta, V 5분위 층화 delta) — 층화 가중 = 분위의 판정 가능 행 수(D∈{0,1})."""
    Q = P[P["D"].notna() & P[col].notna()]
    raw = Q.loc[Q["D"] == 1, col].mean() - Q.loc[Q["D"] == 0, col].mean()
    num = den = 0.0
    for _, g in Q[Q["Vq"].notna()].groupby("Vq"):
        a, b = g.loc[g["D"] == 1, col], g.loc[g["D"] == 0, col]
        if len(a) and len(b):
            num += len(g) * (a.mean() - b.mean())
            den += len(g)
    return float(raw), float(num / den) if den else float("nan")


def block_boot(P: pd.DataFrame, col: str, stratified: bool, seed: int = SEED, B: int = N_BOOT) -> np.ndarray:
    """종목 블록 부트스트랩 — 종목을 복원추출(다항 가중)해 delta 를 다시 잰다(§3-0-b 군집 · 블록 = 종목)."""
    Q = P[P["D"].notna() & P[col].notna()]
    if stratified:
        Q = Q[Q["Vq"].notna()]
    q = Q["Vq"].astype(int).to_numpy() if stratified else np.zeros(len(Q), int)
    codes = Q["stock_code"].astype("category")
    k = len(codes.cat.categories)
    nq = N_QUINT if stratified else 1
    M = np.zeros((k, nq, 4))                        # [n1, e1, n0, e0]
    ci = codes.cat.codes.to_numpy()
    base = np.where(Q["D"].to_numpy() == 1, 0, 2)
    y = Q[col].to_numpy(float)
    np.add.at(M, (ci, q, base), 1.0)
    np.add.at(M, (ci, q, base + 1), y)
    rng = np.random.default_rng(seed)
    W = rng.multinomial(k, np.full(k, 1 / k), size=B).astype(float)
    S = np.einsum("bk,kqj->bqj", W, M)
    with np.errstate(invalid="ignore", divide="ignore"):
        dq = S[:, :, 1] / S[:, :, 0] - S[:, :, 3] / S[:, :, 2]
    wq = S[:, :, 0] + S[:, :, 2]
    ok = np.isfinite(dq)
    return (np.where(ok, dq, 0.0) * wq).sum(1) / np.where(ok, wq, 0.0).sum(1)


def label_panel(delta: float, delta_raw: float, eps: float, p_hi: float, p_lo: float, mde: float) -> str:
    """§3-6 패널 라벨 + §3-2-b (라-D). delta = 층화 후(판정용)."""
    if delta_raw >= eps and abs(delta) < LABSORB * abs(delta_raw):
        return "(라-D) 변동성이 재무를 흡수한다"
    if delta >= eps and p_hi <= 0.05:
        return "(가-D) 부실 경고는 꼬리에서 정보다"
    if delta <= -eps and p_lo <= 0.05:
        return "(다-D) 순위 하락이 꼬리를 «악화»시킨다"
    if abs(delta) < eps and mde <= eps:
        return "(마-D) 구별 불가"
    if mde > eps:
        return "판별 보류(검정력 없음)"
    return "(나-D) 꼬리에서도 정보가 아니다"


def phase_seal(args) -> int:
    gate_time = require_committed(GATE_JSON)
    add_time = require_committed(GATE_ADD_JSON)
    amd2_time = require_committed(ROOT / "docs" / "prereg_2026-09-14_fund_distress_warning_amendment2_2026-09-24.md")
    gate = json.loads(GATE_JSON.read_text(encoding="utf-8"))
    conn = connect()
    fin, _ = load_fin(conn)
    cal = trading_days(conn, *REMEAS)
    P = build_tail_panel(conn, fin, REMEAS)
    conn.close()
    assert P["d"].max() <= pd.Timestamp(REMEAS[1]), "재측정 창 밖 t0"
    col = f"i_s08_w{W_MAIN}_exc"
    judged = P[P["D"].notna() & P[col].notna()]
    p_base = float(judged[col].mean())
    p_incl_unk = float(P[col].dropna().mean())
    ci = cal.index(pd.Timestamp(CRASH_DAY))
    crash_t0 = set(cal[max(0, ci - W_MAIN):ci])                     # 전방 10거래일 창에 2024-08-05 가 든 t0
    p_wo_crash = float(judged.loc[~judged["d"].isin(crash_t0), col].mean())
    rr = rates(P, col)
    ratio = rr["d1"]["rate"] / rr["d0"]["rate"] if rr["d0"]["rate"] else None
    r_hat = gate["gates"]["G2"][SLOT_TARGET]["windows"]["judge"]["r_hat"]
    seal = dict(gate_json_sha256=hashlib.sha256(GATE_JSON.read_bytes()).hexdigest(), gate_commit_time=gate_time,
                gate_addendum_sha256=hashlib.sha256(GATE_ADD_JSON.read_bytes()).hexdigest(),
                gate_addendum_commit_time=add_time, amendment2_commit_time=amd2_time,
                window=REMEAS, trading_days=len(cal), outcome=col,
                population="D∈{0,1}(U1 모름 제외 · FD1 Open Q3)",
                p_base_beta=round(p_base, 6), eps_panel_beta=round(0.5 * p_base, 6),
                eps_formula="eps_panel := 0.5 × p̂_base (r̂ 을 곱하지 않았다 · 금지 21)",
                p_base_incl_unknown_print_only=round(p_incl_unk, 6),
                p_base_without_2024_08_05_window_print_only=round(p_wo_crash, 6),
                crash_excluded_t0=len(crash_t0),
                eps_panel_alpha=None, eps_panel_alpha_note="개정문 #2 §3 — 이 라운드는 (α) 를 정의하지 않는다",
                rates_by_class_print_only=rr, ratio_d1_d0_print_only=round(ratio, 4) if ratio else None,
                r_hat_slot_print_only=r_hat, eps_slot_print_only=round(r_hat * 0.5 * p_base, 6),
                n_rows=int(len(judged)), stocks=int(judged["stock_code"].nunique()),
                git_head=git("rev-parse", "HEAD"), judge_window_t0_tail_values_computed=0)
    SEAL_JSON.write_bytes(jdump(seal).encode("utf-8"))
    sha = hashlib.sha256(SEAL_JSON.read_bytes()).hexdigest()
    md = [f"# FD1 seal — 재측정 창 `p̂_base` · `eps_panel` 서명 ({datetime.now():%Y-%m-%d})", "",
          f"- 🔒 **`seal.json` sha256 = `{sha}`**",
          f"- 선행 커밋(git 사실): gate.json {gate_time} · 게이트 추가분 {add_time} · 개정문 #2 {amd2_time}",
          f"- 창 = 재측정 {REMEAS[0]}~{REMEAS[1]}({len(cal)}거래일 · **판정 제외**) · 결과 = `{col}`"
          "(s=0.08 · 10거래일 · 절벽인 날 사건 제외 · 개정문 #2 §4-3)",
          "- 🔴 **판정 창 t0 의 꼬리 값: 계산 0 · 조회 0 · 인쇄 0.** 판정 창 첫 10거래일 가격은 재측정 창 t0 의 전방 창으로만 읽었다.",
          "", "| 항목 | 값 |", "|---|---|",
          f"| **`p̂_base` (β · 서명)** — 모집단 D∈{{0,1}} | **{p_base:.6f}** (n={len(judged):,} · {seal['stocks']:,}종목) |",
          f"| **`eps_panel := 0.5 × p̂_base`** (r̂ 없음 · 금지 21) | **{0.5 * p_base:.6f}** |",
          "| `eps_panel` (α) | null (개정문 #2 §3) |",
          f"| 참고: 「모름」 포함 `p̂_base` | {p_incl_unk:.6f} |",
          f"| 참고: 전방 창에 2024-08-05 가 든 t0 {len(crash_t0)}일 제외 `p̂_base`(서명 안 씀) | {p_wo_crash:.6f} |",
          f"| 참고: 군별 발생률 D=0 / 모름 / D=1 | {rr['d0']['rate']} (n={rr['d0']['n']:,}) / {rr['unk']['rate']} "
          f"(n={rr['unk']['n']:,}) / {rr['d1']['rate']} (n={rr['d1']['n']:,}) |",
          f"| 참고: D=1/D=0 비(판정 언어 없음 · P3 문턱 1.5 는 판정 창에서) | {seal['ratio_d1_d0_print_only']} |",
          f"| 참고: `eps_slot = r̂ × 0.5 × p̂_base`(슬롯 인쇄 arm · r̂ = G2 판정 창 {r_hat}) | {seal['eps_slot_print_only']} |",
          "", "🔴 이 값을 본 뒤 개정문 #2 를 고치지 않는다(개정문 #2 §8-1). 다음 = 이 파일과 seal.json 커밋 → `--phase 2`."]
    (BASE / f"SEAL_FD1_{datetime.now():%Y%m%d}.md").write_bytes(("\n".join(md) + "\n").encode("utf-8"))
    log(f"seal.json sha256 = {sha} — 커밋 뒤에 --phase 2")
    return 0


def phase2(args) -> int:
    seal_time = require_committed(SEAL_JSON)
    seal = json.loads(SEAL_JSON.read_text(encoding="utf-8"))
    eps = float(seal["eps_panel_beta"])
    conn = connect()
    fin, _ = load_fin(conn)
    P = build_tail_panel(conn, fin, JUDGE)
    conn.close()
    res: Dict[str, Any] = dict(seal_commit_time=seal_time, eps_panel=eps, eps_note="r̂ 을 곱하지 않았다(금지 21)")
    cols = [c for c in P.columns if c.startswith(("i_", "ii_"))]
    for c in cols:
        raw, strat = deltas(P, c)
        res[c] = dict(rates=rates(P, c), delta_raw=round(raw, 6), delta_strat=round(strat, 6))
    main = f"i_s08_w{W_MAIN}_exc"
    bs = block_boot(P, main, stratified=True)
    d_hat = res[main]["delta_strat"]
    cen = bs - bs.mean()
    p_hi = float((1 + (cen >= d_hat).sum()) / (len(bs) + 1))
    p_lo = float((1 + (cen <= d_hat).sum()) / (len(bs) + 1))
    mde = float(Z_MDE * bs.std(ddof=1))
    res["main"] = dict(outcome=main, delta_strat=d_hat, delta_raw=res[main]["delta_raw"], p_one_sided_hi=p_hi,
                       p_one_sided_lo=p_lo, mde_block=round(mde, 6), stocks=int(P["stock_code"].nunique()),
                       label=label_panel(d_hat, res[main]["delta_raw"], eps, p_hi, p_lo, mde),
                       null="종목 블록 부트스트랩 · 중심화(Δ*−mean) · B=%d · seed %d" % (N_BOOT, SEED))
    res["cliff_by_class"] = {k: int(P.loc[m, "cliff"].sum()) for k, m in
                             (("d0", P["D"] == 0), ("unk", P["D"].isna()), ("d1", P["D"] == 1))}
    res["vq_cells"] = P[P["D"].notna()].groupby(["Vq", "D"]).size().unstack(fill_value=0).to_dict()
    ev = P[P[main] == 1]
    res["event_month_max_share"] = round(float(ev.groupby(ev["d"].dt.strftime("%Y-%m")).size().max() / len(ev)), 4)
    res["by_year"] = {int(y): deltas(g, main) for y, g in P.groupby(P["d"].dt.year)}
    (BASE / "phase2.json").write_bytes(jdump(res).encode("utf-8"))
    log(jdump(res["main"]))
    return 0


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--phase", choices=["1", "1b", "seal", "2"], required=True)
    args = ap.parse_args(argv)
    return {"1": phase1, "1b": phase1b, "seal": phase_seal, "2": phase2}[args.phase](args)


if __name__ == "__main__":
    sys.exit(main())
