"""매수후보 특징 연구(B ④) — 사전등록 `docs/prereg_2026-09-24_candidate_feature_study.md`(동결 e11fc75) 그대로.

단계(각각 별도 프로세스 · 순서 봉인):
  --phase features : 원장 + DB(SELECT 전용) → features.csv · 결측률 · V-F1~F4
  --phase explore  : 탐색 창 E 만 연다 → 후보 특징 · V-F5 → RESULTS_explore.md + explore.json(sha256 봉인)
  --phase confirm  : explore.json 봉인 확인 뒤에만 C·에피소드·H-a → RESULTS_2026-09-24.md

라이브 코드는 «호출»만 한다(minervini `build_context` · `compute_rs_percentile_12w`). DB 쓰기 0.
"""
from __future__ import annotations

from backtest.concept_axes.minervini.cap_skip_ledger import bootstrap  # noqa: F401  안전 설정 먼저

import argparse                                                        # noqa: E402
import hashlib                                                         # noqa: E402
import importlib                                                       # noqa: E402
import json                                                            # noqa: E402
import subprocess                                                      # noqa: E402
import sys                                                             # noqa: E402
import time                                                            # noqa: E402
import warnings                                                        # noqa: E402
from collections import Counter, defaultdict                           # noqa: E402
from datetime import datetime, timedelta                               # noqa: E402
from pathlib import Path                                               # noqa: E402
from typing import Any, Dict, List, Optional, Tuple                    # noqa: E402

import numpy as np                                                     # noqa: E402
import pandas as pd                                                    # noqa: E402

from backtest.concept_axes.replayer import loader as LD                # noqa: E402
from backtest.concept_axes.replayer import scan as SC                  # noqa: E402

warnings.filterwarnings("ignore", category=FutureWarning)

BASE = Path(__file__).resolve().parent
ROOT = BASE.parents[3]
LEDGER_DIR = BASE.parent / "results"
PX_START, W_START, W_END = "2023-01-02", "2024-03-13", "2026-09-23"
E_WIN = ("2024-03-13", "2025-06-30")
C_WIN = ("2025-07-01", "2026-09-23")
HA_TEST = ("2025-07-01", "2026-06-04")          # §4-5 검정 창
HA_EVID = ("2026-06-05", "2026-09-23")          # 근거 73일 구간(인쇄만)
EXCL_F0104 = ("2026-06-05", "2026-09-22")       # §4-4-5 F01·F04 인쇄
SEED = 20260925
SEED_FAKE = 20260927
N_PERM = 10_000
HOLM_M = 14
E_MIN_DELTA, E_P, C_P, N_MIN = 1.0, 0.10, 0.05, 30
RS_LOOKBACK = 260

STRATS = {
    "book_pullback_ma20": dict(short="ma20", module="strategies.book_pullback_ma20.screener",
                               cls="BookPullbackMa20ScreenerAdapter", lookback=90, sanity=None, max_hold=50),
    "minervini_volume_dryup": dict(short="minervini", module="strategies.minervini_volume_dryup.screener",
                                   cls="MinerviniVolumeDryupScreenerAdapter", lookback=260, sanity=90, max_hold=20),
    "daytrading_3methods_breakout": dict(short="daytrading",
                                         module="strategies.daytrading_3methods_breakout.screener",
                                         cls="Daytrading3MethodsBreakoutScreenerAdapter", lookback=60, sanity=None,
                                         max_hold=10),
}
SNAMES = list(STRATS)
FEATS = [("F01", "rank"), ("F02", "score"), ("F03", "n_passed"), ("F04", "rank_frac"), ("F05", "gap"),
         ("F06", "band_ok_i"), ("F07", "vol_ratio20"), ("F08", "market_cap"), ("F09", "trading_value"),
         ("F10", "rs12w"), ("F11", "fin_distress"), ("F12", "fin_growth"), ("F13", "frgn5"), ("F14", "frgn20")]
BINARY = {"F06", "F11"}
DATE_LEVEL = {"F03"}
ITD_COLS = [f"{w}_ntby_{k}" for w in ("prsn", "frgn", "orgn") for k in ("qty", "tr_pbmn")]

LOG: List[str] = []


def log(msg: str = "") -> None:
    print(msg, flush=True)
    LOG.append(msg)


def git_sha() -> str:
    return subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True, text=True).stdout.strip()


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def connect():
    import psycopg2
    conn = psycopg2.connect(**LD.dsn())
    conn.set_session(readonly=True)
    return conn


# ════════════════════════════════════════════════════════════════════════════
# 1. 특징 계산
# ════════════════════════════════════════════════════════════════════════════
def rs12w_all(px: pd.DataFrame, uni, need: Dict[str, set]) -> Dict[Tuple, float]:
    """F10 — 전략·날짜별 frames(적격 ∧ `date≤D` 봉≥1 ∧ 불가능봉 가드 통과 · 260봉) → minervini `build_context`."""
    mod = importlib.import_module(STRATS["minervini_volume_dryup"]["module"])
    rs_adapter = getattr(mod, STRATS["minervini_volume_dryup"]["cls"])()
    from utils.data_sanity import IMPOSSIBLE_DROP_PCT as thr  # 가드 문턱(라이브와 같은 값)
    book = {}
    for c, g in px.groupby("stock_code", sort=False):
        g = g[["date", "close"]].reset_index(drop=True)
        cl = pd.to_numeric(g["close"], errors="coerce")
        ret = cl.where(cl > 0).pct_change(fill_method=None)
        drop = (ret < thr).to_numpy()
        book[str(c)] = (g["date"].to_numpy(), g, np.concatenate([[0], np.cumsum(drop)]))
    out: Dict[Tuple, float] = {}
    for s in SNAMES:
        spec = STRATS[s]
        adapter = getattr(importlib.import_module(spec["module"]), spec["cls"])()
        days = sorted(need.get(s, set()))
        elig, _info = SC.eligible_for_dates(uni, adapter, days)
        gl = spec["lookback"] if spec["sanity"] is None else spec["sanity"]
        t0 = time.perf_counter()
        for d in days:
            t = pd.Timestamp(d).to_datetime64()
            frames = {}
            for code in sorted(elig.get(d, set())):
                ent = book.get(code)
                if ent is None:
                    continue
                dates, g, cs = ent
                i = int(np.searchsorted(dates, t, side="right")) - 1
                if i < 0:
                    continue
                # 가드 창 = 원장 스캔과 같은 창(끝 min(lookback, sanity) 봉) — 창 안 연속 변화율(첫 봉 제외)
                a = max(0, i + 1 - min(gl, spec["lookback"]))
                if cs[i + 1] - cs[a + 1] > 0:
                    continue
                frames[code] = g.iloc[max(0, i + 1 - RS_LOOKBACK):i + 1]
            ctx = rs_adapter.build_context(frames, pd.Timestamp(d).date()) or {}
            for code, v in ctx.items():
                out[(s, pd.Timestamp(d), code)] = float(v["rs_value"])
        log(f"  [F10] {spec['short']}: 스캔일 {len(days)} · {time.perf_counter() - t0:.0f}s")
    return out


def fin_features(conn, rows: pd.DataFrame) -> pd.DataFrame:
    """F11(FD1 D · U1 모름) · F12(영업이익 YoY · F1 사유 코드) — `rcept_dt ≤ D−1` 가장 최근 y 하나."""
    f = pd.read_sql("""SELECT trim(stock_code) AS stock_code, bsns_year::int AS y, rcept_dt, operating_income AS oi,
                              total_equity AS te, issued_capital AS ic, total_liabilities AS tl
                       FROM dart_financials_asfiled WHERE status = '000'""", conn)
    fin: Dict[str, Dict[int, tuple]] = defaultdict(dict)
    for r in f.itertuples(index=False):
        rc = None if pd.isna(r.rcept_dt) else pd.Timestamp(r.rcept_dt)
        fin[r.stock_code][int(r.y)] = (rc, *(None if pd.isna(v) else float(v) for v in (r.oi, r.te, r.ic, r.tl)))
    res = []
    for code, d in zip(rows["stock_code"], rows["scan_ts"]):
        fc = fin.get(code)
        o = dict(fin_distress=np.nan, fd_a=np.nan, fd_b=np.nan, fd_c=np.nan, fd_d=np.nan, fin_unk="",
                 fin_growth=np.nan, fg_reason="", fin_y=np.nan, fin_rcept_max=pd.NaT, fin_lagged=False)
        if not fc:
            o.update(fin_unk="no_rows", fg_reason="no_rows")
            res.append(o)
            continue
        vis = [y for y, v in fc.items() if v[0] is not None and v[0] < d]
        if not vis:
            o.update(fin_unk="no_visible_year", fg_reason="no_visible_year")
            res.append(o)
            continue
        y = max(vis)
        rc, oi, te, ic, tl = fc[y]
        exp_y = d.year - 1 if (d.month, d.day) >= (4, 1) else d.year - 2
        prev = fc.get(y - 1)
        prev_vis = prev is not None and prev[0] is not None and prev[0] < d
        o["fin_y"], o["fin_lagged"] = y, y < exp_y
        o["fin_rcept_max"] = max(rc, prev[0]) if prev_vis else rc      # V-F2 — 쓴 rcept_dt 의 최댓값
        # ── F11 성분(FD1 §1-2) — 필요한 컬럼이 없으면 그 성분은 판정 불가
        a = None if oi is None else oi < 0
        b = (None if (oi is None or not prev_vis or prev[1] is None) else (oi < 0 and prev[1] < 0))
        if te is None:
            c = None
        else:
            c = te <= 0 or (ic is not None and ic > 0 and te < 0.5 * ic)
        dd = None if (te is None or tl is None) else (te > 0 and tl / te > 4)
        comps = [a, c, dd]                       # (b) ⊂ (a)
        o.update(fd_a=np.nan if a is None else float(a), fd_b=np.nan if b is None else float(b),
                 fd_c=np.nan if c is None else float(c), fd_d=np.nan if dd is None else float(dd))
        if any(x is True for x in comps + [b]):
            o["fin_distress"] = 1.0
        elif all(x is False for x in comps):
            o["fin_distress"] = 0.0
        else:
            o["fin_unk"] = "col_null"
        # ── F12(F1 사유 코드 그대로)
        if not prev_vis:
            o["fg_reason"] = "prev_year_invisible"
        elif prev[1] is None or oi is None:
            o["fg_reason"] = "oi_missing"
        elif prev[1] <= 0:
            o["fg_reason"] = "prev_oi_nonpositive"
        else:
            o["fin_growth"], o["fg_reason"] = oi / prev[1] - 1.0, "ok"
        res.append(o)
    return pd.DataFrame(res, index=rows.index)


def flow_features(conn, rows, cal_idx, cal, close_map) -> pd.DataFrame:
    """F13·F14 — KOSPI 달력 D−h…D−1 «전부» `foreign_flow` 행 · Σ 순매수량 × 원시 종가 / 시총."""
    ff = pd.read_sql("""SELECT trim(stock_code) AS stock_code, date, foreign_net_vol, source, created_at
                        FROM foreign_flow ORDER BY stock_code, date, created_at, source""", conn)
    ff["date"] = pd.to_datetime(ff["date"])
    n_dup = int(ff.duplicated(["stock_code", "date"]).sum())
    ff = ff.drop_duplicates(["stock_code", "date"], keep="first")
    fmap = {(c, d): float(v) for c, d, v in zip(ff["stock_code"], ff["date"], ff["foreign_net_vol"]) if v == v}
    out = {"frgn5": [], "frgn20": [], "frgn_maxdate": []}
    for code, d, mc in zip(rows["stock_code"], rows["scan_ts"], rows["market_cap"]):
        j = cal_idx[d]
        maxd = pd.NaT
        for h, key in ((5, "frgn5"), (20, "frgn20")):
            days = cal[j - h:j]
            tot, ok = 0.0, len(days) == h and mc == mc and mc > 0
            for dd in days if ok else ():
                v, cl = fmap.get((code, dd)), close_map.get((code, dd))
                if v is None or cl is None:
                    ok = False
                    break
                tot += v * cl
            out[key].append(tot / mc if ok else np.nan)
            if ok:
                maxd = days[-1]
        out["frgn_maxdate"].append(maxd)
    df = pd.DataFrame(out, index=rows.index)
    df.attrs["n_dup"] = n_dup
    return df


def itd_features(conn, rows, cal_idx, cal) -> pd.DataFrame:
    """인쇄만 — `investor_trend_daily` D−5…D−1 5거래일 전부 · 합."""
    it = pd.read_sql(f"SELECT trim(stock_code) AS stock_code, date, {', '.join(ITD_COLS)} FROM investor_trend_daily",
                     conn)
    it["date"] = pd.to_datetime(it["date"])
    it = it.drop_duplicates(["stock_code", "date"])
    m = {(c, d): v for c, d, v in zip(it["stock_code"], it["date"], it[ITD_COLS].to_numpy(dtype=float))}
    vals = []
    for code, d in zip(rows["stock_code"], rows["scan_ts"]):
        j = cal_idx[d]
        vs = [m.get((code, dd)) for dd in cal[j - 5:j]]
        vals.append(np.sum(vs, axis=0) if all(v is not None for v in vs) and len(vs) == 5
                    else np.full(len(ITD_COLS), np.nan))
    return pd.DataFrame(np.array(vals), columns=[f"itd5_{c}" for c in ITD_COLS], index=rows.index)


def qfr_features(conn, rows) -> pd.DataFrame:
    """인쇄만 — `read_financial_ratio`(pit_reader.py:460) 규약 벌크 재현: statement_ym 월말 ≤ D−60일 · 최신 1행."""
    q = pd.read_sql("""SELECT trim(stock_code) AS stock_code, statement_ym, sales_growth, operating_income_growth
                       FROM quant_financial_ratio""", conn)
    q["me"] = pd.to_datetime(q["statement_ym"] + "01", format="%Y%m%d", errors="coerce") + pd.offsets.MonthEnd(0)
    q = q.dropna(subset=["me"]).sort_values(["stock_code", "me"])
    by = {c: (g["me"].to_numpy(), g[["sales_growth", "operating_income_growth"]].to_numpy(dtype=float))
          for c, g in q.groupby("stock_code")}
    out = []
    for code, d in zip(rows["stock_code"], rows["scan_ts"]):
        ent = by.get(code)
        if ent is None:
            out.append((np.nan, np.nan))
            continue
        k = int(np.searchsorted(ent[0], (d - timedelta(days=60)).to_datetime64(), side="right")) - 1
        out.append(tuple(ent[1][k]) if k >= 0 else (np.nan, np.nan))
    return pd.DataFrame(out, columns=["qfr_sales_growth", "qfr_oi_growth"], index=rows.index)


def news_features(conn, rows, cal_idx, cal) -> pd.DataFrame:
    """§3-3 — `news_stock.news_id = news.id` · published_at ∈ [D−4 거래일 00:00, D+1 00:00)."""
    nw = pd.read_sql("""SELECT ns.stock_code, n.published_at, n.overall_score
                        FROM news_stock ns JOIN news n ON ns.news_id = n.id
                        WHERE n.published_at IS NOT NULL""", conn)
    nw["stock_code"] = nw["stock_code"].str.strip()
    pa = pd.to_datetime(nw["published_at"])
    if getattr(pa.dt, "tz", None) is not None:
        pa = pa.dt.tz_convert("Asia/Seoul").dt.tz_localize(None)
    nw["published_at"] = pa
    nw = nw.sort_values(["stock_code", "published_at"])
    by = {c: (g["published_at"].to_numpy(dtype="datetime64[ns]"), g["overall_score"].to_numpy(dtype=float))
          for c, g in nw.groupby("stock_code")}
    out = []
    for code, d in zip(rows["stock_code"], rows["scan_ts"]):
        j = cal_idx[d]
        lo = cal[j - 4].to_datetime64()
        hi = (d + pd.Timedelta(days=1)).to_datetime64()
        ent = by.get(code)
        if ent is None:
            out.append((0, np.nan))
            continue
        a, b = np.searchsorted(ent[0], lo, side="left"), np.searchsorted(ent[0], hi, side="left")
        sc = ent[1][a:b]
        out.append((int(b - a), float(np.nanmean(sc)) if (b > a and np.isfinite(sc).any()) else np.nan))
    df = pd.DataFrame(out, columns=["n_news", "news_score"], index=rows.index)
    df.attrs["news_min"] = str(nw["published_at"].min())
    return df


def phase_features(out: Path) -> Dict[str, Any]:
    T0 = time.perf_counter()
    L = pd.read_csv(LEDGER_DIR / "ledger.csv", dtype={"stock_code": str, "flags": str, "exit_reason": str})
    L["flags"] = L["flags"].fillna("")
    L["scan_ts"] = pd.to_datetime(L["scan_date"])
    log(f"[입력] ledger {len(L):,}행 · sha256 {sha256(LEDGER_DIR / 'ledger.csv')[:12]}")
    conn = connect()
    cal = [pd.Timestamp(d) for d in LD.load_trading_calendar(conn, PX_START, W_END)]
    cal_idx = {d: i for i, d in enumerate(cal)}
    fp = LD.db_fingerprint(conn, PX_START, W_END)
    led_fp = json.loads((LEDGER_DIR / "run_meta.json").read_text(encoding="utf-8"))["db_fingerprint"]["sha256"]
    log(f"[DB] 달력 {len(cal)}일 · 지문 {fp['sha256'][:12]} (원장 {led_fp[:12]} · 일치 {fp['sha256'] == led_fp})")
    px = LD.load_prices(conn, PX_START, W_END)
    uni = LD.build_universe(px)
    log(f"[DB] px {len(px):,}행 · {px['stock_code'].nunique():,}종목 ({time.perf_counter() - T0:.0f}s)")

    # ── 표본 (§2-2)
    iend = cal_idx[pd.Timestamp(W_END)]
    L["cal_i"] = L["scan_ts"].map(cal_idx)
    L["max_hold"] = L["strategy"].map({s: STRATS[s]["max_hold"] for s in SNAMES})
    L["after_cap"] = L["cal_i"] + 1 + L["max_hold"] > iend
    L["imp"] = L["flags"].str.contains("impossible_bar", regex=False)
    has_e = L["entry_price"].notna()
    has_r = L["ret_pct"].notna()

    def reason(r):
        if r.after_cap:
            return "after_cap"
        if "no_next_day" in r.flags:
            return "no_next_day"
        if "no_open" in r.flags or r.entry_price != r.entry_price:
            return "no_open"
        if r.ret_pct != r.ret_pct:
            return "no_ret(sim_error)"
        if r.imp:
            return "impossible_bar"
        return ""
    L["excl_reason"] = [reason(r) for r in L[["after_cap", "flags", "entry_price", "ret_pct", "imp"]].itertuples()]
    L["in_full"] = L["excl_reason"] == ""
    L["window"] = np.where(L["scan_date"] <= E_WIN[1], "E", "C")
    L["sens_cap"] = L["after_cap"] & has_e & has_r & ~L["imp"]          # 민감도 ①(상한 뒤 · open 평가 포함)
    L["sens_imp"] = ~L["after_cap"] & has_e & has_r & L["imp"]          # 민감도 ②(impossible_bar)

    # ── 결과 변수 r5·r10 (KOSPI 달력 · 원시 종가 · 창 끝 넘으면 결측)
    close_map = {(c, d): float(v) for c, d, v in zip(px["stock_code"], px["date"], px["close"])}
    L["entry_ts"] = pd.to_datetime(L["entry_date"])
    for h in (5, 10):
        vals = []
        for c, e, ep in zip(L["stock_code"], L["entry_ts"], L["entry_price"]):
            j = cal_idx.get(e) if e == e else None
            if j is None or not (ep == ep) or j + h > iend:
                vals.append(np.nan)
                continue
            cl = close_map.get((c, cal[j + h]))
            vals.append((cl / ep - 1.0) * 100 if cl is not None else np.nan)
        L[f"r{h}"] = vals
    L["hit"] = np.where(L["ret_pct"].notna(), (L["ret_pct"] > 0).astype(float), np.nan)

    # ── F01~F09
    L["rank_frac"] = L["rank"] / L["n_passed"]
    L["gap"] = L["entry_price"] / L["ref_close"] - 1.0
    L["band_ok_i"] = L["band_ok"].map({"True": 1.0, "False": 0.0, True: 1.0, False: 0.0})
    vol_by = {str(c): (g["date"].to_numpy(), g["volume"].to_numpy(dtype=float)) for c, g in px.groupby("stock_code")}
    v20, v20_end = [], []
    for c, d, dv in zip(L["stock_code"], L["scan_ts"], L["d_volume"]):
        dates, vol = vol_by[c]
        i = int(np.searchsorted(dates, d.to_datetime64(), side="left"))
        if i < 20:
            v20.append(np.nan)
            v20_end.append(pd.NaT)
            continue
        m = vol[i - 20:i].mean()
        v20.append(dv / m if m > 0 else np.nan)
        v20_end.append(pd.Timestamp(dates[i - 1]))
    L["vol_ratio20"], L["v20_end"] = v20, v20_end

    # ── F10
    t = time.perf_counter()
    need = {s: set(L.loc[L["strategy"] == s, "scan_ts"]) for s in SNAMES}
    rs = rs12w_all(px, uni, need)
    L["rs12w"] = [rs.get((s, d, c), np.nan) for s, d, c in zip(L["strategy"], L["scan_ts"], L["stock_code"])]
    log(f"[F10] {time.perf_counter() - t:.0f}s")

    # ── F11~F14 · 인쇄만
    L = L.join(fin_features(conn, L))
    fl = flow_features(conn, L, cal_idx, cal, close_map)
    L = L.join(fl)
    L = L.join(itd_features(conn, L, cal_idx, cal))
    L = L.join(qfr_features(conn, L))
    nwf = news_features(conn, L, cal_idx, cal)
    L = L.join(nwf)

    # ── 에피소드 첫 행 (C 판정 표본 · 전략×종목 · 달력상 연속 거래일 묶음)
    L["ep_first"] = False
    sub = L[L["in_full"] & (L["window"] == "C")].sort_values(["strategy", "stock_code", "cal_i"])
    prev = sub.groupby(["strategy", "stock_code"])["cal_i"].shift(1)
    L.loc[sub.index[(prev.isna() | (sub["cal_i"] - prev > 1)).to_numpy()], "ep_first"] = True

    # ── V-F1 · V-F2
    mv = L[L["strategy"] == "minervini_volume_dryup"]
    mism = mv[~np.isclose(mv["rs12w"], mv["rs_value"], equal_nan=False)]
    vf1 = dict(n=len(mv), n_mismatch=len(mism), rows=mism[["scan_date", "stock_code", "rs_value", "rs12w"]]
               .head(20).astype(str).values.tolist())
    log(f"[V-F1] minervini rs12w = rs_value: {len(mv) - len(mism)}/{len(mv)} 일치 · 불일치 {len(mism)}")
    vf2 = dict(fin=int((L["fin_rcept_max"].notna() & (L["fin_rcept_max"] >= L["scan_ts"])).sum()),
               frgn=int((L["frgn_maxdate"].notna() & (L["frgn_maxdate"] >= L["scan_ts"])).sum()),
               v20=int((L["v20_end"].notna() & (L["v20_end"] >= L["scan_ts"])).sum()))
    log(f"[V-F2] PIT 위반: 재무 {vf2['fin']} · 외국인 {vf2['frgn']} · F07 창 {vf2['v20']}")

    # ── V-F3 표본 대수
    vf3 = []
    for s in SNAMES:
        for w in ("E", "C"):
            g = L[(L["strategy"] == s) & (L["window"] == w)]
            cnt = g["excl_reason"].value_counts().to_dict()
            vf3.append(dict(strategy=STRATS[s]["short"], window=w, n=len(g), full=int(cnt.pop("", 0)), **cnt))
    ok3 = all(r["n"] == r["full"] + sum(v for k, v in r.items() if k not in ("strategy", "window", "n", "full"))
              for r in vf3)
    log(f"[V-F3] 원장 = 표본 + 사유별 제외: {ok3}")

    # ── V-F4 손계산(DB SELECT 직접 · 시드 20260925 · 전략별 1행)
    vf4 = verify_f4(conn, L, cal, cal_idx)
    conn.close()

    feat_cols = [c for _, c in FEATS]
    keep = (["strategy", "scan_date", "stock_code", "rank", "window", "in_full", "excl_reason", "sens_cap",
             "sens_imp", "ep_first", "band_ok", "exit_reason", "flags", "excl_class", "exit_date", "ret_pct", "hit",
             "r5", "r10"] + [c for c in feat_cols if c not in ("rank",)]
            + ["fin_unk", "fg_reason", "fin_y", "fin_lagged", "fd_a", "fd_b", "fd_c", "fd_d", "n_news", "news_score",
               "qfr_sales_growth", "qfr_oi_growth"] + [f"itd5_{c}" for c in ITD_COLS])
    F = L[keep].copy()
    F.to_csv(out / "features.csv", index=False, encoding="utf-8")

    # 결측률(판정 표본 · 전략 × 창)
    miss = {}
    for s in SNAMES:
        for w in ("E", "C"):
            g = F[F["in_full"] & (F["strategy"] == s) & (F["window"] == w)]
            miss[f"{STRATS[s]['short']}/{w}"] = {c: round(float(g[c].isna().mean()) * 100, 1) for c in feat_cols}
    log("[결측률 %] (판정 표본)")
    log("  " + " | ".join(["특징"] + list(miss)))
    for c in feat_cols:
        log("  " + " | ".join([c] + [f"{miss[k][c]:.1f}" for k in miss]))
    meta = dict(phase="features", n_rows=len(F), n_full=int(F["in_full"].sum()), db_fingerprint=fp["sha256"],
                ledger_fingerprint=led_fp, fp_match=fp["sha256"] == led_fp, missing_pct=miss, vf1=vf1, vf2=vf2,
                vf3=vf3, vf3_ok=ok3, vf4=vf4, frgn_dup_rows=fl.attrs.get("n_dup"), news_min=nwf.attrs.get("news_min"),
                secs=round(time.perf_counter() - T0, 1))
    return meta


def verify_f4(conn, L, cal, cal_idx) -> List[Dict[str, Any]]:
    rng = np.random.default_rng(SEED)
    res = []
    cur = conn.cursor()
    for s in SNAMES:
        g = L[L["in_full"] & (L["strategy"] == s) & L["frgn5"].notna() & L["rs12w"].notna()]
        if g.empty:
            g = L[L["in_full"] & (L["strategy"] == s)]
        r = g.iloc[int(rng.integers(0, len(g)))]
        code, d = r["stock_code"], r["scan_date"]
        cur.execute("""SELECT date, volume * COALESCE(adj_factor,1) FROM daily_prices
                       WHERE stock_code=%s AND date < %s ORDER BY date DESC LIMIT 20""", (code, d))
        vv = [float(x[1]) for x in cur.fetchall()]
        f07 = r["d_volume"] / np.mean(vv) if len(vv) == 20 else np.nan
        j = cal_idx[pd.Timestamp(d)]
        days = [x.strftime("%Y-%m-%d") for x in cal[j - 5:j]]
        cur.execute("""SELECT f.date::text, f.foreign_net_vol, p.close FROM foreign_flow f
                       JOIN daily_prices p ON p.stock_code=f.stock_code AND p.date=f.date::text
                       WHERE f.stock_code=%s AND f.date::text = ANY(%s)""", (code, days))
        fr = cur.fetchall()
        f13 = sum(float(a) * float(b) for _, a, b in fr) / r["market_cap"] if len(fr) == 5 else np.nan
        # F10 손계산: 그날 원장 유니버스(frames)를 쓰지 않고 자기 종가 60봉 수익률만 SELECT — 백분위 재현 대신 순위 부호 점검
        cur.execute("""SELECT close FROM daily_prices WHERE stock_code=%s AND date <= %s
                       ORDER BY date DESC LIMIT 61""", (code, d))
        cc = [float(x[0]) for x in cur.fetchall()]
        r60 = cc[0] / cc[60] - 1 if len(cc) == 61 else np.nan
        res.append(dict(strategy=STRATS[s]["short"], scan_date=d, stock_code=code,
                        F07=r["vol_ratio20"], F07_sql=f07, F07_ok=bool(np.isclose(r["vol_ratio20"], f07, equal_nan=True)),
                        F13=r["frgn5"], F13_sql=f13, F13_ok=bool(np.isclose(r["frgn5"], f13, equal_nan=True)),
                        F10=r["rs12w"], ret60_sql=r60))
        log(f"[V-F4] {res[-1]}")
    return res


# ════════════════════════════════════════════════════════════════════════════
# 2. 통계량 · 순열
# ════════════════════════════════════════════════════════════════════════════
def labels_for(x: pd.Series, fid: str) -> np.ndarray:
    if fid in BINARY:
        return np.where(x.to_numpy() == 1.0, 3, 1).astype(np.int8)
    q = x.rank(pct=True, method="average").to_numpy()
    return np.where(q <= 1 / 3, 1, np.where(q > 2 / 3, 3, 2)).astype(np.int8)


def prep(df: pd.DataFrame, fid: str, col: str, ycol: str = "ret_pct"):
    """비결측 행만 · 전략별 분위 라벨 · (전략, 날짜) 블록 정렬."""
    d = df[df[col].notna() & df[ycol].notna()].sort_values(["strategy", "scan_date", "stock_code"])
    lab = np.zeros(len(d), dtype=np.int8)
    for s in SNAMES:
        m = (d["strategy"] == s).to_numpy()
        if m.any():
            lab[m] = labels_for(d.loc[m, col], fid)
    blk = pd.factorize(d["strategy"] + "|" + d["scan_date"])[0].astype(np.float64)
    return d, lab, blk


def stat(d: pd.DataFrame, lab: np.ndarray, ycol: str = "ret_pct") -> Dict[str, Any]:
    y = d[ycol].to_numpy(dtype=float)
    per, num, den = {}, 0.0, 0
    for s in SNAMES:
        m = (d["strategy"] == s).to_numpy()
        n1, n3 = int((m & (lab == 1)).sum()), int((m & (lab == 3)).sum())
        mu1 = float(y[m & (lab == 1)].mean()) if n1 else np.nan
        mu3 = float(y[m & (lab == 3)].mean()) if n3 else np.nan
        ok = n1 >= N_MIN and n3 >= N_MIN
        per[s] = dict(n=int(m.sum()), n1=n1, n3=n3, mu1=mu1, mu3=mu3, delta=mu3 - mu1 if ok else np.nan, ok=ok)
        if ok:
            num += per[s]["n"] * per[s]["delta"]
            den += per[s]["n"]
    return dict(per=per, pool=num / den if den else np.nan, n=len(d))


def perm_rows(d, lab, blk, st, seed, ycol="ret_pct", P=N_PERM, B=250) -> float:
    """§4-3 — (strategy, scan_date) 블록 안 라벨 섞기 · 풀링 Δ 양측 p."""
    if not np.isfinite(st["pool"]):
        return np.nan
    rng = np.random.default_rng(seed)
    y = d[ycol].to_numpy(dtype=float)
    strat = d["strategy"].to_numpy()
    sl = []
    for s in SNAMES:
        if st["per"][s]["ok"]:
            idx = np.flatnonzero(strat == s)
            sl.append((slice(idx[0], idx[-1] + 1), st["per"][s]["n1"], st["per"][s]["n3"], st["per"][s]["n"]))
    den = sum(x[3] for x in sl)
    obs, cnt, done = abs(st["pool"]), 0, 0
    while done < P:
        b = min(B, P - done)
        idx = np.argsort(blk[None, :] + rng.random((b, len(y))), axis=1)
        lp = lab[idx]
        num = np.zeros(b)
        for s_, n1, n3, n in sl:
            yy, ll = y[s_], lp[:, s_]
            num += n * ((ll == 3) @ yy / n3 - (ll == 1) @ yy / n1)
        cnt += int((np.abs(num / den) >= obs - 1e-12).sum())
        done += b
    return (1 + cnt) / (P + 1)


def perm_dates(d, lab, st, seed, ycol="ret_pct", P=N_PERM) -> float:
    """§4-3 F03 — 전략 안 날짜열 원형 이동(오프셋 1…T−1)."""
    if not np.isfinite(st["pool"]):
        return np.nan
    rng = np.random.default_rng(seed)
    num = np.zeros(P)
    den = 0
    for s in SNAMES:
        if not st["per"][s]["ok"]:
            continue
        g = d[(d["strategy"] == s).to_numpy()].assign(_l=lab[(d["strategy"] == s).to_numpy()])
        agg = g.groupby("scan_date").agg(sy=(ycol, "sum"), n=(ycol, "size"), l=("_l", "first"))
        T = len(agg)
        L_, sy, nn = agg["l"].to_numpy(), agg["sy"].to_numpy(), agg["n"].to_numpy()
        k = rng.integers(1, T, size=P)
        Lp = L_[(np.arange(T)[None, :] + k[:, None]) % T]
        s3, c3 = (Lp == 3) @ sy, (Lp == 3) @ nn
        s1, c1 = (Lp == 1) @ sy, (Lp == 1) @ nn
        with np.errstate(invalid="ignore", divide="ignore"):
            num += st["per"][s]["n"] * (s3 / c3 - s1 / c1)
        den += st["per"][s]["n"]
    pool = num / den
    return (1 + int((np.abs(np.nan_to_num(pool, nan=0.0)) >= abs(st["pool"]) - 1e-12).sum())) / (P + 1)


def test_feature(df, fid, col, w, ycol="ret_pct", with_p=True) -> Dict[str, Any]:
    d, lab, blk = prep(df, fid, col, ycol)
    st = stat(d, lab, ycol)
    if with_p:
        seed = [SEED, w, int(fid[1:])]
        st["p"] = perm_dates(d, lab, st, seed, ycol) if fid in DATE_LEVEL else perm_rows(d, lab, blk, st, seed, ycol)
    return st


def holm(ps: Dict[str, float], m: int) -> Dict[str, float]:
    items = sorted(ps.items(), key=lambda kv: kv[1])
    out, run = {}, 0.0
    for i, (k, p) in enumerate(items):
        run = max(run, min(1.0, (m - i) * p))
        out[k] = run
    return out


def fmt(x, nd=2):
    return "—" if x is None or (isinstance(x, float) and not np.isfinite(x)) else f"{x:+.{nd}f}" if isinstance(x, float) else str(x)


def row_md(fid, col, st, extra="") -> str:
    cells = [f"{fid} `{col}`", fmt(st["pool"]), (f"{st['p']:.4f}" if "p" in st and st["p"] == st["p"] else "—")]
    for s in SNAMES:
        p = st["per"][s]
        cells.append(f"{fmt(p['mu1'])} / {fmt(p['mu3'])} / **{fmt(p['delta'])}** (n={p['n']:,}{'' if p['ok'] else ' ✗n<30'})")
    return "| " + " | ".join(cells) + (f" | {extra}" if extra else "") + " |"


HDR = ("| 특징 | Δ_pool(%p) | p | ma20 T1/T3/Δ | minervini T1/T3/Δ | daytrading T1/T3/Δ |",
       "|---|---|---|---|---|---|")


# ════════════════════════════════════════════════════════════════════════════
# 3. 탐색 창
# ════════════════════════════════════════════════════════════════════════════
def fake_vf5(E: pd.DataFrame) -> Dict[str, Any]:
    """V-F5 — 종목 단위 상수 노이즈 100개 · E · §4-3 블록 순열.

    값 시드 = default_rng([20260927, i]) (문서). 순열 시드는 문서에 없다 ⇒ default_rng([20260927, 0]) 로
    «결과 쪽»을 블록 안에서 섞은 공통 순열 10,000개를 100개 특징에 같이 쓴다(라벨 섞기와 분포 동치).
    """
    d = E[E["ret_pct"].notna()].sort_values(["strategy", "scan_date", "stock_code"]).reset_index(drop=True)
    codes = np.array(sorted(d["stock_code"].unique()))
    cidx = np.searchsorted(codes, d["stock_code"].to_numpy())
    y = d["ret_pct"].to_numpy(dtype=float)
    blk = pd.factorize(d["strategy"] + "|" + d["scan_date"])[0].astype(np.float64)
    strat = d["strategy"].to_numpy()
    K = 100
    T3 = np.zeros((len(d), K))
    T1 = np.zeros((len(d), K))
    obs = np.zeros(K)
    info = []
    for i in range(1, K + 1):
        v = np.random.default_rng([SEED_FAKE, i]).random(len(codes))[cidx]
        d["_fake"] = v
        lab = np.zeros(len(d), dtype=np.int8)
        for s in SNAMES:
            m = strat == s
            lab[m] = labels_for(d.loc[m, "_fake"], "FX")
        st = stat(d, lab)
        info.append(st)
        obs[i - 1] = st["pool"]
        T3[:, i - 1], T1[:, i - 1] = lab == 3, lab == 1
    sl = []
    for s in SNAMES:
        idx = np.flatnonzero(strat == s)
        sl.append((s, slice(idx[0], idx[-1] + 1)))
    n1 = np.array([[info[k]["per"][s]["n1"] for k in range(K)] for s in SNAMES], dtype=float)
    n3 = np.array([[info[k]["per"][s]["n3"] for k in range(K)] for s in SNAMES], dtype=float)
    ok = np.array([[info[k]["per"][s]["ok"] for k in range(K)] for s in SNAMES])
    nn = np.array([[info[k]["per"][s]["n"] for k in range(K)] for s in SNAMES], dtype=float)
    den = (nn * ok).sum(axis=0)
    rng = np.random.default_rng([SEED_FAKE, 0])
    cnt = np.zeros(K)
    done, B = 0, 250
    while done < N_PERM:
        b = min(B, N_PERM - done)
        idx = np.argsort(blk[None, :] + rng.random((b, len(y))), axis=1)
        yp = y[idx]
        num = np.zeros((b, K))
        for j, (s, s_) in enumerate(sl):
            dd = yp[:, s_] @ T3[s_] / np.where(n3[j] > 0, n3[j], 1) - yp[:, s_] @ T1[s_] / np.where(n1[j] > 0, n1[j], 1)
            num += np.where(ok[j], nn[j], 0) * dd
        cnt += (np.abs(num / den) >= np.abs(obs) - 1e-12).sum(axis=0)
        done += b
    p = (1 + cnt) / (N_PERM + 1)
    return dict(rate=float((p < 0.10).mean()), rate05=float((p < 0.05).mean()), p=p.round(4).tolist(),
                n_rows=len(d), n_stocks=len(codes))


def sample_md(F: pd.DataFrame) -> List[str]:
    out = ["## 1. 표본 정의 · 행수", "",
           "- 전수(판정) = 전략별 상한(D+1 + max_hold 거래일 ≤ 2026-09-23 · KOSPI 달력) 안 ∧ `entry_price` ∧ `ret_pct` ∧ "
           "`impossible_bar` 없음. 제외 사유는 아래 순서로 **하나만** 배정(상한 뒤 → no_next_day → no_open → ret 없음 → impossible_bar).",
           "", "| 전략 | 창 | 원장 | 판정 표본 | after_cap | no_next_day | no_open | no_ret(sim_error) | impossible_bar | 라이브 근사(band_ok) |",
           "|---|---|---|---|---|---|---|---|---|---|"]
    for s in SNAMES:
        for w in ("E", "C"):
            g = F[(F["strategy"] == s) & (F["window"] == w)]
            c = g["excl_reason"].value_counts()
            full = g[g["in_full"]]
            out.append(f"| {STRATS[s]['short']} | {w} | {len(g):,} | **{len(full):,}** | {c.get('after_cap', 0):,} | "
                       f"{c.get('no_next_day', 0):,} | {c.get('no_open', 0):,} | {c.get('no_ret(sim_error)', 0):,} | "
                       f"{c.get('impossible_bar', 0):,} | {int((full['band_ok'].astype(str) == 'True').sum()):,} |")
    full = F[F["in_full"]]
    out += ["", "남기는 행(판정 표본 안 · 건수만): "
            + " · ".join(f"{STRATS[s]['short']}/{w}: corp_event {int(g['flags'].str.contains('corp_event').sum())}"
                         f" · excl_class {int(g['excl_class'].notna().sum())} · vintage_m4 {int(g['flags'].str.contains('vintage_m4').sum())}"
                         f" · 상한 안 open {int((g['exit_reason'] == 'open').sum())}"
                         for s in SNAMES for w in ("E", "C")
                         for g in [full[(full['strategy'] == s) & (full['window'] == w)]]),
            f"- E 행 중 청산일이 C 기간(>2025-06-30)에 걸린 행: {int(((full['window'] == 'E') & (full['exit_date'].fillna('') > E_WIN[1])).sum()):,}(허용 · 인쇄만)", ""]
    return out


def phase_explore(out: Path, F: pd.DataFrame) -> Dict[str, Any]:
    T0 = time.perf_counter()
    E = F[F["in_full"] & (F["window"] == "E")]
    res = {}
    for fid, col in FEATS:
        t = time.perf_counter()
        res[fid] = test_feature(E, fid, col, 0)
        log(f"[E] {fid} {col}: Δ_pool {fmt(res[fid]['pool'])} · p {res[fid]['p']:.4f} ({time.perf_counter() - t:.0f}s)")
    cand = {fid: float(np.sign(r["pool"])) for fid, r in res.items()
            if np.isfinite(r["pool"]) and abs(r["pool"]) >= E_MIN_DELTA and r["p"] < E_P}
    log(f"[E] 후보 특징: {cand or '없음'}")
    t = time.perf_counter()
    vf5 = fake_vf5(E)
    log(f"[V-F5] 가짜 100개 p<0.10 비율 {vf5['rate']:.2f} ({time.perf_counter() - t:.0f}s)")
    md = ["# 탐색 창 E 결과 — 매수후보 특징 연구 (C 개봉 «전» 봉인)", "",
          f"- 사전등록 `docs/prereg_2026-09-24_candidate_feature_study.md`(동결 e11fc75) §4-4-1 · 생성 {datetime.now().isoformat(timespec='seconds')} · git {git_sha()[:10]}",
          "- E = scan_date 2024-03-13~2025-06-30 · 결과 = `ret_pct`(gross %) · 분위 = 특징·전략·창별 3분위 · 순열 10,000회 · 시드 `default_rng([20260925, 0, f])`", ""]
    md += sample_md(F[F["window"] == "E"])
    md += ["## 2. 특징별 탐색 창 표 (T1 평균 / T3 평균 / Δ_s · %p)", "", HDR[0][:-1] + "| 후보 |", HDR[1] + "---|"]
    for fid, col in FEATS:
        md.append(row_md(fid, col, res[fid], "✅ 후보" if fid in cand else ""))
    md += ["", f"- 후보 문턱: |Δ_pool,E| ≥ {E_MIN_DELTA}%p ∧ p_E < {E_P}. 이진 F06 = True−False · F11 = D=1 − D=0(「모름」 제외).",
           f"- **후보 특징**: {', '.join(f'{k}({FEATS[int(k[1:]) - 1][1]} · 부호 {v:+.0f})' for k, v in cand.items()) or '없음 (⇒ C 는 인쇄만 · 전 특징 「없음」)'}",
           "", "## 3. V-F5 — 종목 단위 상수 노이즈 가짜 특징 100개 (E)", "",
           f"- `p_E < 0.10` 비율 = **{vf5['rate']:.2f}**(명목 0.10) · `p_E < 0.05` 비율 = {vf5['rate05']:.2f} · 표본 {vf5['n_rows']:,}행 · 종목 {vf5['n_stocks']:,}",
           "- 순열 시드: 문서 미지정 ⇒ `default_rng([20260927, 0])` 공통 순열(결과 쪽 블록 안 섞기 · 라벨 섞기와 분포 동치)을 100개에 공용.",
           f"- {'🔴 명목 10%를 크게 넘는다 ⇒ 「순열 p 낙관」 경고를 판정문에 병기' if vf5['rate'] > 0.15 else '명목 근처'}", ""]
    path = out / "RESULTS_explore.md"
    path.write_text("\n".join(md), encoding="utf-8")
    seal = dict(candidates=cand, results={k: dict(pool=v["pool"], p=v["p"]) for k, v in res.items()},
                results_explore_sha256=sha256(path), sealed_at=datetime.now().isoformat(timespec="seconds"),
                git_sha=git_sha(), vf5=dict(rate=vf5["rate"], rate05=vf5["rate05"]))
    (out / "explore.json").write_text(json.dumps(seal, ensure_ascii=False, indent=1), encoding="utf-8")
    return dict(phase="explore", candidates=cand, vf5_rate=vf5["rate"], vf5_rate05=vf5["rate05"],
                results_explore_sha256=seal["results_explore_sha256"], sealed_at=seal["sealed_at"],
                e_results={k: dict(pool=v["pool"], p=v["p"],
                                   per={STRATS[s]["short"]: v["per"][s] for s in SNAMES}) for k, v in res.items()},
                secs=round(time.perf_counter() - T0, 1))


# ════════════════════════════════════════════════════════════════════════════
# 4. 확인 창
# ════════════════════════════════════════════════════════════════════════════
def pool_only(df, fid, col, ycol="ret_pct"):
    d, lab, _ = prep(df, fid, col, ycol)
    return stat(d, lab, ycol)


def pool_table(title: str, df: pd.DataFrame, feats=FEATS, ycol="ret_pct", note="") -> List[str]:
    md = [f"### {title}", "", note, "", HDR[0], HDR[1]] if note else [f"### {title}", "", HDR[0], HDR[1]]
    for fid, col in feats:
        md.append(row_md(fid, col, pool_only(df, fid, col, ycol)))
    return md + [""]


def h_a(F: pd.DataFrame) -> Tuple[List[str], Dict[str, Any]]:
    g = F[(F["strategy"] == "book_pullback_ma20") & (F["rank"] <= 20) & (F["n_passed"] >= 11) & F["r5"].notna()]

    def calc(sub, with_p=False):
        sub = sub.sort_values(["scan_date", "rank"])
        lo, hi = np.percentile(sub["r5"], [1, 99])
        yw = sub["r5"].clip(lo, hi).to_numpy()
        top = (sub["rank"] <= 10).to_numpy()
        d_w = yw[~top].mean() - yw[top].mean()
        d_raw = sub.loc[~top, "r5"].mean() - sub.loc[top, "r5"].mean()
        d_ret = sub.loc[~top, "ret_pct"].mean() - sub.loc[top, "ret_pct"].mean()
        d_r10 = sub.loc[~top, "r10"].mean() - sub.loc[top, "r10"].mean()
        r = dict(n=len(sub), n_days=sub["scan_date"].nunique(), n_top=int(top.sum()), n_bot=int((~top).sum()),
                 delta_w=float(d_w), delta_raw=float(d_raw), d_ret=float(d_ret), d_r10=float(d_r10),
                 mu_top=float(yw[top].mean()), mu_bot=float(yw[~top].mean()), winsor=(float(lo), float(hi)))
        if with_p:
            rng = np.random.default_rng([SEED, 2, 0])
            blk = pd.factorize(sub["scan_date"])[0].astype(np.float64)
            lab = (~top).astype(np.int8)
            n_bot, n_top = lab.sum(), (1 - lab).sum()
            cnt, done = 0, 0
            while done < N_PERM:
                b = min(1000, N_PERM - done)
                lp = lab[np.argsort(blk[None, :] + rng.random((b, len(yw))), axis=1)]
                dp = lp @ yw / n_bot - (1 - lp) @ yw / n_top
                cnt += int((np.abs(dp) >= abs(d_w) - 1e-12).sum())
                done += b
            r["p"] = (1 + cnt) / (N_PERM + 1)
        return r
    t = g[(g["scan_date"] >= HA_TEST[0]) & (g["scan_date"] <= HA_TEST[1])]
    main = calc(t, True)
    ev = calc(g[(g["scan_date"] >= HA_EVID[0]) & (g["scan_date"] <= HA_EVID[1])])
    ex = calc(g[g["scan_date"] <= E_WIN[1]])
    verdict = "재현" if (main["p"] < 0.05 and main["delta_w"] > 0) else "재현 안 됨"
    md = ["## 7. ③-a 가설 H-a (단독 사전지정 · m=1)", "",
          "- 표본 = ma20 ∧ rank ≤ 20 ∧ 그날 n_passed ≥ 11 ∧ r5 비결측 · `Δ_a = mean(r5 | 11~20) − mean(r5 | 1~10)` · 표본 1%/99% winsorize · scan_date 블록 순열 10,000 · 시드 `[20260925, 2, 0]`",
          "", "| 구간 | 행 | 날짜 | 1~10 / 11~20 | Δ_a winsor(%p) | Δ_a 원값 | Δ ret_pct | Δ r10 | p |", "|---|---|---|---|---|---|---|---|---|"]
    for name, r in (("**검정 2025-07-01~2026-06-04**", main), ("근거 구간 2026-06-05~09-23(인쇄만)", ev),
                    ("E 창(인쇄만)", ex)):
        md.append(f"| {name} | {r['n']:,} | {r['n_days']} | {r['n_top']:,} / {r['n_bot']:,} | **{fmt(r['delta_w'], 3)}** | "
                  f"{fmt(r['delta_raw'], 3)} | {fmt(r['d_ret'], 3)} | {fmt(r['d_r10'], 3)} | {r['p']:.4f} |" if "p" in r else
                  f"| {name} | {r['n']:,} | {r['n_days']} | {r['n_top']:,} / {r['n_bot']:,} | {fmt(r['delta_w'], 3)} | "
                  f"{fmt(r['delta_raw'], 3)} | {fmt(r['d_ret'], 3)} | {fmt(r['d_r10'], 3)} | — |")
    md += ["", f"- **H-a 판정: {verdict}** (p {main['p']:.4f} · Δ_a {main['delta_w']:+.3f}%p · 「재현」 ⟺ p<0.05 ∧ Δ_a>0)",
           "- 원 방법과의 차이: 원은 `005930` 행 달력 · 시가 결측 시 종가 대체 · 30% 절벽 드롭. 여기는 KOSPI 달력 · 대체 없음 · 드롭 없음 · 원장 D+1 시가.", ""]
    return md, dict(verdict=verdict, **{k: main[k] for k in ("n", "n_days", "delta_w", "delta_raw", "p")},
                    evid_delta=ev["delta_w"], e_delta=ex["delta_w"])


def phase_confirm(out: Path, F: pd.DataFrame, meta_prev: Dict[str, Any]) -> Dict[str, Any]:
    T0 = time.perf_counter()
    seal = json.loads((out / "explore.json").read_text(encoding="utf-8"))
    if sha256(out / "RESULTS_explore.md") != seal["results_explore_sha256"]:
        raise SystemExit("RESULTS_explore.md 가 봉인 뒤 바뀌었다 — 중단")
    cand = seal["candidates"]
    full = F[F["in_full"]]
    E, C = full[full["window"] == "E"], full[full["window"] == "C"]
    EP = C[C["ep_first"]]
    e_res = meta_prev["e_results"]
    c_res, ep_res = {}, {}
    for fid, col in FEATS:
        t = time.perf_counter()
        c_res[fid] = test_feature(C, fid, col, 1, with_p=fid in cand)
        if fid in cand:
            ep_res[fid] = test_feature(EP, fid, col, 3)
            log(f"[C] {fid}: Δ_pool {fmt(c_res[fid]['pool'])} p {c_res[fid]['p']:.4f} · 에피소드 Δ {fmt(ep_res[fid]['pool'])} "
                f"p {ep_res[fid]['p']:.4f} ({time.perf_counter() - t:.0f}s)")
    ps = {fid: (c_res[fid]["p"] if fid in cand and c_res[fid].get("p") == c_res[fid].get("p") else 1.0) for fid, _ in FEATS}
    padj = holm(ps, HOLM_M)
    final = {}
    for fid, col in FEATS:
        if fid not in cand:
            final[fid] = dict(verdict="없음", why="E 후보 아님")
            continue
        sgn = cand[fid]
        r, ep = c_res[fid], ep_res[fid]
        agree = sum(1 for s in SNAMES if r["per"][s]["ok"] and np.sign(r["per"][s]["delta"]) == sgn)
        conds = dict(holm=padj[fid] < C_P, sign=np.sign(r["pool"]) == sgn, two_of_three=agree >= 2,
                     episode=(np.sign(ep["pool"]) == sgn) and ep["p"] < C_P)
        final[fid] = dict(verdict="있음" if all(conds.values()) else "없음", conds={k: bool(v) for k, v in conds.items()},
                          agree=agree, p_holm=padj[fid])
    log("[판정] " + ", ".join(k + ": " + v["verdict"] for k, v in final.items()))
    ha_md, ha = h_a(F)
    vf5 = seal["vf5"]
    warn = vf5["rate"] > 0.15

    md = ["# 매수후보 특징 연구 — 결과 (B ④ · 2026-09-24)", "",
          "- 규범: `docs/prereg_2026-09-24_candidate_feature_study.md`(🔒 동결 e11fc75) · 입력 = `results/ledger.csv`(52,540행 · 원장 커밋 545d61a)",
          "- 🔴 **이 결과는 라이브 변경 근거가 아니다**(§4-6·§5-5 · ~2026-10-16 3전략 룰 변경 0건). 「있음」도 별도 「순위 층 shadow」 사전등록의 입력 후보일 뿐이다.",
          f"- 탐색 결과 봉인: `RESULTS_explore.md` sha256 `{seal['results_explore_sha256'][:16]}…` · 봉인 {seal['sealed_at']} (C 개봉 «전» · 커밋은 못 함 — 아래 「개정 필요」)", ""]
    md += sample_md(F)
    md += ["## 2. 특징 결측률 (판정 표본 · %)", "", "| 특징 | " + " | ".join(meta_prev["missing_pct"]) + " |",
           "|---" * (1 + len(meta_prev["missing_pct"])) + "|"]
    for _, col in FEATS:
        md.append(f"| {col} | " + " | ".join(f"{v[col]:.1f}" for v in meta_prev["missing_pct"].values()) + " |")
    md += ["", "## 3. 탐색 창 E (후보 선정 · `RESULTS_explore.md` 와 같은 값)", "", HDR[0][:-1] + "| 후보 |", HDR[1] + "---|"]
    for fid, col in FEATS:
        r = e_res[fid]
        st = dict(pool=r["pool"], p=r["p"], per={s: r["per"][STRATS[s]["short"]] for s in SNAMES})
        md.append(row_md(fid, col, st, "✅" if fid in cand else ""))
    md += ["", f"- **후보 특징(E)**: {', '.join(f'{k} `{FEATS[int(k[1:]) - 1][1]}`(부호 {v:+.0f})' for k, v in cand.items()) or '없음'}", "",
           "## 4. 확인 창 C", "", "Holm(m=14 · 비후보 p=1) → 방향 → 3전략 중 2 → 에피소드 첫 행(비보정 p<0.05 ∧ 부호) 순서.", "",
           "| 특징 | Δ_pool,C | p_C | Holm p | 부호=E | 전략 일치(/3) | 에피소드 Δ · p (n) | 판정 |", "|---|---|---|---|---|---|---|---|"]
    for fid, col in FEATS:
        r = c_res[fid]
        if fid in cand:
            f_ = final[fid]
            ep = ep_res[fid]
            md.append(f"| {fid} `{col}` | {fmt(r['pool'])} | {r['p']:.4f} | {f_['p_holm']:.4f} | {'예' if f_['conds']['sign'] else '아니오'} | "
                      f"{f_['agree']} | {fmt(ep['pool'])} · {ep['p']:.4f} ({ep['n']:,}) | **{f_['verdict']}** |")
        else:
            md.append(f"| {fid} `{col}` | {fmt(r['pool'])} | — | 1.0 | — | — | — | **없음** |")
    md += ["", "### C 전략별 T1/T3/Δ (인쇄)", "", HDR[0], HDR[1]] + [row_md(fid, col, c_res[fid]) for fid, col in FEATS]
    md += ["", "## 5. 최종 판정 (특징별)", "", "| 특징 | 판정 |", "|---|---|"]
    md += [f"| {fid} `{col}` | **{final[fid]['verdict']}**{'' if fid in cand else ' (E 후보 아님)'} |" for fid, col in FEATS]
    n_yes = sum(v["verdict"] == "있음" for v in final.values())
    md += ["", f"⇒ 「특징 있음」 {n_yes}개 / 14." + (" 전 특징 「없음」 ⇒ 발굴 프로그램 결론(AUC 0.556 천장) **재확인**으로 기록(§4-6)." if n_yes == 0 else ""),
           (f"🔴 V-F5 가짜 특징 p<0.10 비율 {vf5['rate']:.2f} — 「순열 p 낙관」 경고 병기." if warn else
            f"- V-F5 가짜 특징 p<0.10 비율 {vf5['rate']:.2f}(명목 0.10)."), ""]
    md += ["## 6. V-F5 · 검증", "",
           f"- V-F5: 종목 단위 상수 노이즈 100개 E 순열 → `p<0.10` 비율 **{vf5['rate']:.2f}** · `p<0.05` {vf5['rate05']:.2f}",
           f"- V-F1: minervini `rs12w` = 원장 `rs_value` {meta_prev['vf1']['n'] - meta_prev['vf1']['n_mismatch']}/{meta_prev['vf1']['n']} (불일치 {meta_prev['vf1']['n_mismatch']})",
           f"- V-F2 PIT 위반: 재무 {meta_prev['vf2']['fin']} · 외국인 {meta_prev['vf2']['frgn']} · F07 창 {meta_prev['vf2']['v20']}",
           f"- V-F3 표본 대수: {'통과' if meta_prev['vf3_ok'] else '🔴 불일치'}",
           "- V-F4 손계산(전략별 1행 · DB SELECT 직접):"]
    md += [f"  - {v['strategy']} {v['scan_date']} {v['stock_code']}: F07 {v['F07']:.4f} vs SQL {v['F07_sql']:.4f} ({'✓' if v['F07_ok'] else '✗'}) · "
           f"F13 {v['F13']} vs SQL {v['F13_sql']} ({'✓' if v['F13_ok'] else '✗'}) · F10 {v['F10']} · 60봉 수익률(SQL) {v['ret60_sql']:.4f}"
           for v in meta_prev["vf4"]]
    md += ["", *ha_md]
    # ── 민감도 · 보조 · 인쇄만
    md += ["## 8. 민감도 · 보조 결과 · 라이브 근사 (전부 인쇄만 · 판정 불변 · p 미계산)", ""]
    for w, G in (("E", E), ("C", C)):
        md += pool_table(f"라이브 근사(band_ok=True) · {w}", G[G["band_ok"].astype(str) == "True"],
                         [f for f in FEATS if f[0] != "F06"])
    cap = F[F["sens_cap"] | F["in_full"]]
    imp = F[F["sens_imp"] | F["in_full"]]
    for w in ("E", "C"):
        md += pool_table(f"민감도 ① 상한 뒤 행 포함(open 평가) · {w}", cap[cap["window"] == w])
        md += pool_table(f"민감도 ② impossible_bar 포함 · {w}", imp[imp["window"] == w])
    for yc in ("hit", "r5", "r10"):
        for w, G in (("E", E), ("C", C)):
            md += pool_table(f"보조 결과 `{yc}` · {w}", G, ycol=yc)
    md += pool_table("F01·F04 — C 에서 2026-06-05~09-22 뺀 것", C[~C["scan_date"].between(*EXCL_F0104)],
                     [f for f in FEATS if f[0] in ("F01", "F04")])
    ecodes = set(E.loc[E["frgn5"].notna(), "stock_code"])
    md += pool_table("F13·F14 — C 를 E 비결측 종목으로 제한", C[C["stock_code"].isin(ecodes)],
                     [f for f in FEATS if f[0] in ("F13", "F14")])
    md += ["## 9. 인쇄만 항목", ""]
    md += ["### F13 부호 분포(>0 / =0 / <0) · 커버리지", "", "| 전략/창 | 비결측 F13 | >0 | =0 | <0 | F14 비결측 |", "|---|---|---|---|---|---|"]
    for s in SNAMES:
        for w, G in (("E", E), ("C", C)):
            g = G[G["strategy"] == s]
            x = g["frgn5"].dropna()
            md.append(f"| {STRATS[s]['short']}/{w} | {len(x):,}/{len(g):,} | {int((x > 0).sum()):,} | {int((x == 0).sum()):,} | "
                      f"{int((x < 0).sum()):,} | {int(g['frgn20'].notna().sum()):,} |")
    md += ["", f"- `foreign_flow` (stock_code,date) 복수 행: {meta_prev.get('frgn_dup_rows')} (규칙 미발동)", "",
           "### F11 「모름」(U1) · F12 사유 코드 · PIT 연도 후퇴", "", "| 전략/창 | F11 D=1 / D=0 / 모름(사유) | F12 사유 코드 | 기대 연도보다 오래된 y |", "|---|---|---|---|"]
    for s in SNAMES:
        for w, G in (("E", E), ("C", C)):
            g = G[G["strategy"] == s]
            unk = g.loc[g["fin_distress"].isna(), "fin_unk"].value_counts().to_dict()
            md.append(f"| {STRATS[s]['short']}/{w} | {int((g['fin_distress'] == 1).sum()):,} / {int((g['fin_distress'] == 0).sum()):,} / "
                      f"{int(g['fin_distress'].isna().sum()):,} {unk} | {g['fg_reason'].value_counts().to_dict()} | {int(g['fin_lagged'].astype(bool).sum()):,} |")
    md += ["", "### FD1 성분 (a)~(d) 분해 — 1 vs 0 의 ret_pct 차(%p · 성분 판정 가능 행만)", "",
           "| 성분 | " + " | ".join(f"{STRATS[s]['short']}/{w}" for s in SNAMES for w in ("E", "C")) + " |", "|---" * 7 + "|"]
    for comp in ("fd_a", "fd_b", "fd_c", "fd_d"):
        cells = []
        for s in SNAMES:
            for G in (E, C):
                g = G[(G["strategy"] == s) & G[comp].notna()]
                a1, a0 = g.loc[g[comp] == 1, "ret_pct"], g.loc[g[comp] == 0, "ret_pct"]
                cells.append(f"{fmt(a1.mean() - a0.mean()) if len(a1) and len(a0) else '—'} ({len(a1)}/{len(a0)})")
        md.append(f"| {comp} | " + " | ".join(cells) + " |")
    md += [""]
    itd_feats = [(f"P{i + 1}", f"itd5_{c}") for i, c in enumerate(ITD_COLS)]
    md += pool_table("investor_trend_daily 5일 순매수 — C 안 T3−T1(데이터 2026-07-03~09-21 뿐)", C, itd_feats)
    qf = [("Q1", "qfr_sales_growth"), ("Q2", "qfr_oi_growth")]
    for w, G in (("E", E), ("C", C)):
        md += pool_table(f"read_financial_ratio 규약(월말 ≤ D−60일) 대조 · {w}", G, qf)
    md += news_md(E, C)
    md += corr_md(full)
    md += ["## 10. 한계 (사전등록 §7 승계)", "",
           "1. 다중비교 — Holm(m=14)은 가족 내 FWER 만. 등록부 전체 FWER 은 따로 누적.",
           "2. 생존자 편향 — 지금 `daily_prices` 에 남은 종목만(행마다 `survivor_universe`).",
           "3. 빈티지(M4) — `d_volume`·F07 은 현재 DB 값 · 2026-07-03 이전 보정 불가.",
           "4. gross — 수수료·세금 0.",
           "5. 표본 상관 — 블록 순열은 날짜 안 교환성만 · 종목 간 계열상관 미처리 ⇒ p 낙관 가능(V-F5 참조).",
           "6. 원장 근사 — 시가 밴드·일봉 청산·on_tick 재평가 미재현.",
           "7. 수급 커버리지 — F13·F14 는 2025 년까지 약 150종목 · 비무작위 결측.",
           "8. E·C 국면 차이 — 방향 불일치가 국면 탓일 수 있음(판정 불변).", ""]
    return dict(phase="confirm", final=final, ha=ha, secs=round(time.perf_counter() - T0, 1), md=md,
                c_results={k: dict(pool=v["pool"], p=v.get("p")) for k, v in c_res.items()}, p_holm=padj)


def news_md(E, C) -> List[str]:
    md = ["### 뉴스 — 「정보 있나」만 (p 없음 · 승격 없음)", "",
          "| 전략/창 | 커버리지(n_news≥1) | ret 평균 있음−없음(%p) | 뉴스 있는 행 overall_score T3−T1(%p) |", "|---|---|---|---|"]
    signs = {"②": {}, "③": {}}
    for s in SNAMES:
        for w, G in (("E", E[E["scan_date"] >= "2024-12-23"]), ("C", C)):
            g = G[G["strategy"] == s]
            has = g["n_news"] >= 1
            d2 = g.loc[has, "ret_pct"].mean() - g.loc[~has, "ret_pct"].mean()
            h = g[has & g["news_score"].notna()]
            lab = labels_for(h["news_score"], "N") if len(h) else np.array([])
            y = h["ret_pct"].to_numpy()
            d3 = y[lab == 3].mean() - y[lab == 1].mean() if len(h) and (lab == 3).any() and (lab == 1).any() else np.nan
            signs["②"][(s, w)], signs["③"][(s, w)] = np.sign(d2), np.sign(d3)
            md.append(f"| {STRATS[s]['short']}/{w} | {has.mean() * 100:.1f}% ({int(has.sum()):,}/{len(g):,}) | {fmt(d2)} | {fmt(d3)} |")
    for k, v in signs.items():
        same = all(v[(s, "E")] == v[(SNAMES[0], "E")] for s in SNAMES) and all(v[(s, "C")] == v[(SNAMES[0], "C")] for s in SNAMES) \
            and v[(SNAMES[0], "E")] == v[(SNAMES[0], "C")]
        md.append(f"\n- 방향 일치 {k}: **{'예' if same else '아니오'}**")
    return md + ["", "- E 는 2024-12-23 이후 부분만(뉴스 시작일).", ""]


def corr_md(full) -> List[str]:
    md = ["### 알려진 상관 (Spearman · 판정 표본)", ""]
    for s in SNAMES:
        g = full[full["strategy"] == s]
        c = g[["rank", "score", "n_passed", "rank_frac", "vol_ratio20"]].corr(method="spearman")
        md.append(f"- {STRATS[s]['short']}: rank~score {c.loc['rank', 'score']:+.2f} · rank~rank_frac {c.loc['rank', 'rank_frac']:+.2f} · "
                  f"rank~n_passed {c.loc['rank', 'n_passed']:+.2f} · score~vol_ratio20 {c.loc['score', 'vol_ratio20']:+.2f}"
                  + (f" · rs12w 표준편차 {g['rs12w'].std():.2f}(범위 {g['rs12w'].min():.0f}~{g['rs12w'].max():.0f})"
                     if s == "minervini_volume_dryup" else ""))
    return md + [""]


# ════════════════════════════════════════════════════════════════════════════
def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--phase", choices=["features", "explore", "confirm"], required=True)
    a = ap.parse_args(argv)
    out = BASE
    meta_path = out / "run_meta.json"
    meta = json.loads(meta_path.read_text(encoding="utf-8")) if meta_path.exists() else {}
    meta.setdefault("prereg", "docs/prereg_2026-09-24_candidate_feature_study.md (e11fc75)")
    meta.setdefault("seeds", dict(main="default_rng([20260925, w, f])", fake_values="default_rng([20260927, i])",
                                  fake_perm="default_rng([20260927, 0])", ha="default_rng([20260925, 2, 0])",
                                  vf4="default_rng(20260925)"))
    t0 = datetime.now().isoformat(timespec="seconds")
    if a.phase == "features":
        m = phase_features(out)
    else:
        F = pd.read_csv(out / "features.csv", dtype={"stock_code": str, "scan_date": str, "exit_date": str, "flags": str,
                                                    "excl_class": str, "band_ok": str, "fin_unk": str, "fg_reason": str})
        F["flags"] = F["flags"].fillna("")
        F["excl_reason"] = F["excl_reason"].fillna("")
        if a.phase == "explore":
            if (out / "explore.json").exists():
                raise SystemExit("explore.json 이 이미 있다 — 탐색 재실행 금지(봉인)")
            m = phase_explore(out, F)
        else:
            m = phase_confirm(out, F, {**meta["features"], **meta["explore"]})
            md = m.pop("md")
            md += ["## 11. 실행 지문", "",
                   f"- git `{git_sha()}` · 원장 sha256 `{sha256(LEDGER_DIR / 'ledger.csv')[:16]}…` · DB 지문 `{meta['features']['db_fingerprint'][:16]}…`(원장과 일치 {meta['features']['fp_match']})",
                   f"- 행수: 원장 {meta['features']['n_rows']:,} · 판정 표본 {meta['features']['n_full']:,} · 시드 {meta['seeds']}",
                   f"- 시간: features {meta['features']['secs']:.0f}s · explore {meta['explore']['secs']:.0f}s · confirm {m['secs']:.0f}s",
                   "- 실행 로그: `run_log_*.txt`", ""]
            (out / "RESULTS_2026-09-24.md").write_text("\n".join(md), encoding="utf-8")
    m.update(started=t0, finished=datetime.now().isoformat(timespec="seconds"), git_sha=git_sha())
    meta[a.phase] = m
    meta_path.write_text(json.dumps(meta, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
    (out / f"run_log_{a.phase}.txt").write_text("\n".join(LOG), encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
