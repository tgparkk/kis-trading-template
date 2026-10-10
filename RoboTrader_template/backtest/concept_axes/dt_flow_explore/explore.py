"""daytrading 후보 × 수급 5종 «탐색» 1회 — BRIEF_dt_flow_explore.md (2026-10-10).

탐색 전용 · 매수 규칙 안 바꿈 · B(동결 40e1355) 규칙·k 바꾸지 않음 · DB SELECT 만(읽기 전용 세션) · KIS 호출 0.
실행(RoboTrader_template 에서 1줄):
    python -m backtest.concept_axes.dt_flow_explore.explore
산출 = 같은 폴더 rows.csv · run_meta.json (+ 표 stdout). RESULTS_2026-10-10.md 는 이 출력으로 쓴다.
"""
from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List

import numpy as np
import pandas as pd

BASE = Path(__file__).resolve().parent
ROOT = BASE.parents[2]                                      # …/RoboTrader_template
LEDGER = BASE.parent / "candidate_ledger" / "results" / "ledger.csv"
STRAT = "daytrading_3methods_breakout"
S0, S1 = "2026-07-03", "2026-09-23"                         # 표본 scan_date 창
LEDGER_END = "2026-09-23"                                   # 원장 W_END(after_cap 기준)
MAX_HOLD = 10
SEED = 20261010
N_BOOT, N_FAKE = 2000, 400
TAIL, MIN_CANDS, MIN_COV = 0.20, 10, 0.80
MONTHS = ("2026-07", "2026-08", "2026-09")

# (id, 이름, 열, 꼬리 방향, 주/탐색)
FEATS = [
    ("F1", "기관 순매수÷거래대금", "f1_orgn", "low", "주"),
    ("F2", "프로그램 순매수÷거래대금", "f2_prog", "low", "주"),
    ("F3", "공매도 거래량 비중", "f3_short", "high", "주"),
    ("F4k3", "신용잔고율 @D-3", "f4_credit_k3", "high", "주"),
    ("F4k4", "신용잔고율 @D-4", "f4_credit_k4", "high", "주"),
    ("X1", "외국인 순매수÷거래대금", "x_frgn", "low", "탐색"),
    ("X2k3", "신용 loan_gvrt @D-3", "x_gvrt_k3", "high", "탐색"),
    ("X2k4", "신용 loan_gvrt @D-4", "x_gvrt_k4", "high", "탐색"),
]


# ════════════════════════════════════════════════════════════════════════════
# 순수 함수 (DB 없음 · tests/test_dt_flow_explore.py 가 손 계산 표로 확인)
# ════════════════════════════════════════════════════════════════════════════
def episode_first(L: pd.DataFrame) -> pd.Series:
    """candidate_ledger/feature_study/run_features.py:386-389 의 묶음 규칙 복사(수정 없음):
    같은 (전략, 종목) 안에서 거래일 색인(cal_i)이 바로 앞 행과 1 넘게 벌어지면(또는 첫 행) 에피소드 첫 행."""
    sub = L.sort_values(["strategy", "stock_code", "cal_i"])
    prev = sub.groupby(["strategy", "stock_code"])["cal_i"].shift(1)
    first = prev.isna() | (sub["cal_i"] - prev > 1)
    return first.reindex(L.index)


def tail_frame(C: pd.DataFrame, col: str, side: str) -> pd.DataFrame:
    """C = 그날 후보 «전부»(scan_date · n_cands · col). B PREREG §5-1 순서:
    후보 < 10 날 제외 → 그날 커버리지(전부 중 비결측) < 80% 날 제외 → 그날 비결측 전부 안에서
    rank(pct, average) · 하위 꼬리 pct ≤ 0.20 / 상위 꼬리 pct > 0.80. 표본 제한은 그 뒤(호출 쪽)."""
    d = C[C["n_cands"] >= MIN_CANDS]
    cov = d.groupby("scan_date")[col].apply(lambda s: s.notna().mean())
    ok = cov.index[cov >= MIN_COV]
    d = d[d["scan_date"].isin(ok) & d[col].notna()].sort_values(["scan_date", "stock_code"]).copy()
    pct = d.groupby("scan_date")[col].rank(pct=True, method="average")
    d["tail"] = (pct <= TAIL) if side == "low" else (pct > 1 - TAIL)
    d.attrs["n_cov_drop"] = int((cov < MIN_COV).sum())
    return d


def day_stats(day: np.ndarray, tail: np.ndarray, y: np.ndarray, n_days: int):
    """날짜별 (꼬리 평균 − 나머지 평균) 과 무게(그날 표본 행 수). 꼬리·나머지 둘 다 있는 날만 유효."""
    t = tail.astype(float)
    n_t = np.bincount(day, weights=t, minlength=n_days)
    n_r = np.bincount(day, weights=1 - t, minlength=n_days)
    s_t = np.bincount(day, weights=y * t, minlength=n_days)
    s_r = np.bincount(day, weights=y * (1 - t), minlength=n_days)
    valid = (n_t > 0) & (n_r > 0)
    with np.errstate(invalid="ignore", divide="ignore"):
        delta = np.where(valid, s_t / np.where(n_t > 0, n_t, 1) - s_r / np.where(n_r > 0, n_r, 1), np.nan)
    return delta, np.where(valid, n_t + n_r, 0.0), valid, n_t


def pooled(delta: np.ndarray, w: np.ndarray) -> float:
    m = w > 0
    return float((delta[m] * w[m]).sum() / w[m].sum()) if m.any() else float("nan")


def within_day_delta(df: pd.DataFrame, ycol: str = "y") -> float:
    """작은 표 하나(scan_date · tail · y)의 날짜 고정효과 Δ — 시험용 진입점."""
    day = pd.factorize(df["scan_date"])[0]
    delta, w, _, _ = day_stats(day, df["tail"].to_numpy(bool), df[ycol].to_numpy(float), day.max() + 1)
    return pooled(delta, w)


# ════════════════════════════════════════════════════════════════════════════
# 특징 하나 분석
# ════════════════════════════════════════════════════════════════════════════
def analyse(C: pd.DataFrame, col: str, side: str, seed_k: int) -> Dict[str, Any]:
    d = tail_frame(C, col, side)
    days = pd.Index(sorted(d["scan_date"].unique()))
    dcode = days.get_indexer(d["scan_date"])
    nd = len(days)
    samp = (d["ep_first"] & d["band_ok"]).to_numpy(bool)
    tail = d["tail"].to_numpy(bool)
    rng = np.random.default_rng([SEED, seed_k])
    out: Dict[str, Any] = dict(n_cov_drop=d.attrs["n_cov_drop"])
    for yname, ycol in (("main", "ret_pct"), ("aux", "r_oc")):
        y = d[ycol].to_numpy(float)
        m = samp & ~np.isnan(y)
        delta, w, valid, n_t = day_stats(dcode[m], tail[m], y[m], nd)
        obs = pooled(delta, w)
        vd = np.flatnonzero(valid)
        idx = rng.integers(0, len(vd), size=(N_BOOT, len(vd)))
        bw, bd = w[vd][idx], delta[vd][idx]
        boot = (bw * bd).sum(1) / bw.sum(1)
        r = dict(delta=obs, lo=float(np.percentile(boot, 2.5)), hi=float(np.percentile(boot, 97.5)),
                 se=float(boot.std(ddof=1)), n_rows=int(w.sum()), n_days=int(valid.sum()),
                 n_tail=int(n_t[valid].sum()))
        r["mde"] = 2.8 * r["se"]
        mon = days.str[:7].to_numpy()
        r["months"] = {mo: pooled(np.where(mon == mo, delta, np.nan), np.where(mon == mo, w, 0)) for mo in MONTHS}
        if yname == "main":
            # 잡음 띠: 그날 비결측 후보 «전부» 안에서 꼬리 표식을 무작위로 섞음(= 날짜 안 무작위 순위 · 동점 구조 유지)
            fakes = np.empty(N_FAKE)
            for b in range(N_FAKE):
                perm = np.lexsort((rng.random(len(d)), dcode))
                ft = tail[perm]
                fd, fw, _, _ = day_stats(dcode[m], ft[m], y[m], nd)
                fakes[b] = pooled(fd, fw)
            fakes = fakes[~np.isnan(fakes)]
            r["noise_pct"] = float(100 * ((fakes < obs).mean() + 0.5 * (fakes == obs).mean()))
            r["p_ref"] = float(((np.abs(fakes) >= abs(obs)).sum() + 1) / (len(fakes) + 1))
            r["noise_band"] = [float(np.percentile(fakes, 2.5)), float(np.percentile(fakes, 97.5))]
            # 민감도: after_cap 날(청산 상한이 원장 끝을 넘는 scan_date) 뺀 Δ
            ac = d["after_cap"].to_numpy(bool)
            m2 = m & ~ac
            d2, w2, _, _ = day_stats(dcode[m2], tail[m2], y[m2], nd)
            r["delta_no_aftercap"] = pooled(d2, w2)
            r["n_no_aftercap"] = int(w2.sum())
        out[yname] = r
    out["tail_share"] = out["main"]["n_tail"] / out["main"]["n_rows"] if out["main"]["n_rows"] else float("nan")
    s = np.sign(out["main"]["delta"])
    mon_same = all(np.sign(v) == s for v in out["main"]["months"].values() if v == v) and \
        all(v == v for v in out["main"]["months"].values())
    np_ = out["main"]["noise_pct"]
    out["label"] = "눈에 띔" if ((np_ < 2.5 or np_ > 97.5) and mon_same
                               and np.sign(out["aux"]["delta"]) == s) else "모름"
    return out


# ════════════════════════════════════════════════════════════════════════════
# DB · 조립
# ════════════════════════════════════════════════════════════════════════════
def q(conn, sql: str, params) -> pd.DataFrame:
    with conn.cursor() as cur:
        cur.execute(sql, params)
        cols = [c[0] for c in cur.description]
        return pd.DataFrame(cur.fetchall(), columns=cols)


def unit_check(C: pd.DataFrame) -> Dict[str, Any]:
    """investor 금액 = 백만원 · program/short = 원 가정 확인. 어긋나면 중단."""
    res: Dict[str, Any] = {}
    tv = (C["acml_tr_pbmn"] / C["dp_trading_value"]).replace([np.inf, -np.inf], np.nan).dropna()
    res["acml_tr_pbmn_over_daily_prices_tv"] = dict(n=int(len(tv)), median=float(tv.median()),
                                                   share_0_9_1_1=float(tv.between(0.9, 1.1).mean()))
    for c in ("f1_orgn", "f2_prog", "x_frgn"):
        v = C[c].dropna()
        res[c] = dict(n=int(len(v)), q01=float(v.quantile(.01)), med=float(v.median()), q99=float(v.quantile(.99)),
                      min=float(v.min()), max=float(v.max()), share_abs_gt1=float((v.abs() > 1).mean()))
    for c in ("f3_short", "f4_credit_k3", "x_gvrt_k3"):
        v = C[c].dropna()
        res[c] = dict(n=int(len(v)), min=float(v.min()), med=float(v.median()), max=float(v.max()))
    bad = (not 0.9 <= res["acml_tr_pbmn_over_daily_prices_tv"]["median"] <= 1.1
           or any(res[c]["share_abs_gt1"] > 0.01 for c in ("f1_orgn", "f2_prog", "x_frgn"))
           or not (0 <= res["f3_short"]["min"] and res["f3_short"]["max"] <= 100))
    res["ok"] = not bad
    return res


def fmt(x: float, nd: int = 2) -> str:
    return "—" if x != x else f"{x:+.{nd}f}"


def sgn(x: float) -> str:
    return "·" if x != x else ("+" if x > 0 else "−")


def main() -> int:
    sys.path.insert(0, str(ROOT))
    from backtest.concept_axes.minervini.cap_skip_ledger import bootstrap  # noqa: F401  읽기 전용 PGOPTIONS
    from backtest.concept_axes.replayer import loader as LD
    import psycopg2

    t_query = datetime.now().isoformat(timespec="seconds")
    L = pd.read_csv(LEDGER, dtype={"stock_code": str, "flags": str, "exit_reason": str})
    L = L[L["strategy"] == STRAT].copy()
    conn = psycopg2.connect(**LD.dsn())
    conn.set_session(readonly=True)
    cal = [pd.Timestamp(x).strftime("%Y-%m-%d") for x in LD.load_trading_calendar(conn, "2024-01-01", "2026-10-31")]
    ci = {d: i for i, d in enumerate(cal)}
    L["cal_i"] = L["scan_date"].map(ci)
    assert L["cal_i"].notna().all(), "원장 scan_date 가 달력에 없음"
    L["ep_first"] = episode_first(L)                         # 이력 = 원장 daytrading 전 행
    C = L[(L["scan_date"] >= S0) & (L["scan_date"] <= S1)].copy()
    C["band_ok"] = C["band_ok"].astype(str) == "True"
    C["n_cands"] = C.groupby("scan_date")["stock_code"].transform("size")
    C["after_cap"] = C["cal_i"] + 1 + MAX_HOLD > ci[LEDGER_END]
    C["d1"] = [cal[int(i) + 1] for i in C["cal_i"]]
    C["k3"] = [cal[int(i) - 3] for i in C["cal_i"]]
    C["k4"] = [cal[int(i) - 4] for i in C["cal_i"]]
    codes = sorted(C["stock_code"].unique())

    inv = q(conn, "SELECT stock_code, date::text AS scan_date, orgn_ntby_tr_pbmn, frgn_ntby_tr_pbmn "
                  "FROM investor_trend_daily WHERE date BETWEEN %s AND %s AND stock_code = ANY(%s)", (S0, S1, codes))
    prg = q(conn, "SELECT stock_code, date::text AS scan_date, acml_tr_pbmn, ntby_tr_pbmn "
                  "FROM program_trade_daily WHERE date BETWEEN %s AND %s AND stock_code = ANY(%s)", (S0, S1, codes))
    sht = q(conn, "SELECT stock_code, date::text AS scan_date, ssts_vol_rlim "
                  "FROM short_sale_daily WHERE date BETWEEN %s AND %s AND stock_code = ANY(%s)", (S0, S1, codes))
    cre = q(conn, "SELECT stock_code, date::text AS cdate, loan_rmnd_rate, loan_gvrt "
                  "FROM credit_balance_daily WHERE date BETWEEN %s AND %s AND stock_code = ANY(%s)",
            (min(C["k4"]), S1, codes))
    # 🔴 adj_factor 곱하지 않음 · 원가격 그대로
    px = q(conn, "SELECT stock_code, date, open, close, trading_value FROM daily_prices "
                 "WHERE date BETWEEN %s AND %s AND stock_code = ANY(%s)", (S0, cal[ci[S1] + 1], codes))
    conn.close()
    for df in (inv, prg, sht, cre):
        assert not df.duplicated([c for c in df.columns if c in ("stock_code", "scan_date", "cdate")]).any()
    key = ["stock_code", "scan_date"]
    C = C.merge(inv, on=key, how="left").merge(prg, on=key, how="left").merge(sht, on=key, how="left")
    for k in ("k3", "k4"):
        c2 = cre.rename(columns={"cdate": k, "loan_rmnd_rate": f"rate_{k}", "loan_gvrt": f"gvrt_{k}"})
        C = C.merge(c2, on=["stock_code", k], how="left")
    pxo = px.rename(columns={"date": "d1"})[["stock_code", "d1", "open", "close"]]
    C = C.merge(pxo, on=["stock_code", "d1"], how="left")
    C = C.merge(px.rename(columns={"date": "scan_date", "trading_value": "dp_trading_value"})
                [["stock_code", "scan_date", "dp_trading_value"]], on=key, how="left")
    num = ["orgn_ntby_tr_pbmn", "frgn_ntby_tr_pbmn", "acml_tr_pbmn", "ntby_tr_pbmn", "ssts_vol_rlim",
           "rate_k3", "rate_k4", "gvrt_k3", "gvrt_k4", "open", "close", "dp_trading_value"]
    C[num] = C[num].apply(pd.to_numeric, errors="coerce").astype(float)
    den = C["acml_tr_pbmn"].where(C["acml_tr_pbmn"] > 0)
    C["f1_orgn"] = C["orgn_ntby_tr_pbmn"] * 1e6 / den
    C["f2_prog"] = C["ntby_tr_pbmn"] / den
    C["x_frgn"] = C["frgn_ntby_tr_pbmn"] * 1e6 / den
    C["f3_short"] = C["ssts_vol_rlim"]
    C["f4_credit_k3"], C["f4_credit_k4"] = C["rate_k3"], C["rate_k4"]
    C["x_gvrt_k3"], C["x_gvrt_k4"] = C["gvrt_k3"], C["gvrt_k4"]
    C["r_oc"] = (C["close"] / C["open"].where(C["open"] > 0) - 1) * 100
    C["entry_is_d1"] = C["entry_date"].isna() | (C["entry_date"] == C["d1"])

    uc = unit_check(C)
    print("[단위]", json.dumps(uc, ensure_ascii=False))
    if not uc["ok"]:
        print("단위 가정 어긋남 — 중단")
        return 2

    base = C[(C["n_cands"] >= MIN_CANDS) & C["ep_first"] & C["band_ok"]]
    res: Dict[str, Any] = {}
    rows_md: List[str] = []
    rows_md2: List[str] = []
    for k, (fid, name, col, side, kind) in enumerate(FEATS):
        r = analyse(C, col, side, k)
        r["miss_rate_base"] = float(base[col].isna().mean())
        res[fid] = r
        a, x = r["main"], r["aux"]
        mon = "".join(sgn(a["months"][mo]) for mo in MONTHS)
        rows_md.append(
            f"| {fid} {name}{' (탐색)' if kind == '탐색' else ''} | {'하위' if side == 'low' else '상위'} | "
            f"{a['n_rows']}·{a['n_tail']}·{a['n_days']} | {100 * r['miss_rate_base']:.0f}% | {fmt(a['delta'])} | "
            f"[{fmt(a['lo'])}, {fmt(a['hi'])}] | {a['noise_pct']:.1f} | {mon} | {fmt(x['delta'])} | "
            f"{a['mde']:.2f} | {r['label']} |")
        rows_md2.append(
            f"| {fid} | {r['n_cov_drop']} | {100 * r['tail_share']:.0f}% | {a['p_ref']:.3f} | "
            f"[{fmt(a['noise_band'][0])}, {fmt(a['noise_band'][1])}] | "
            f"{' / '.join(fmt(a['months'][mo]) for mo in MONTHS)} | [{fmt(x['lo'])}, {fmt(x['hi'])}] · "
            f"n {x['n_rows']} | {fmt(a['delta_no_aftercap'])} (n {a['n_no_aftercap']}) |")
    hdr = ("| 특징 | 꼬리 | n 행·꼬리·날 | 결측률 | Δ 주(%p) | 95% 구간 | 잡음 백분위 | 월 07·08·09 | Δ 보조(%p) "
           "| MDE | 라벨 |\n|---|---|---|---|---|---|---|---|---|---|---|")
    hdr2 = ("| 특징 | 커버리지<80% 날 | 꼬리 비율 | p(참고·낙관) | 잡음 띠 2.5~97.5 | 월별 Δ 주 | 보조 95% 구간 "
            "| Δ 주 · after_cap 날 뺌 |\n|---|---|---|---|---|---|---|---|")
    table = hdr + "\n" + "\n".join(rows_md)
    table2 = hdr2 + "\n" + "\n".join(rows_md2)
    print(table)
    print(table2)

    head = subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True, text=True).stdout.strip()
    sample_stats = dict(
        window_rows=int(len(C)), window_days=int(C["scan_date"].nunique()),
        days_n_cands_lt10=int(C.loc[C["n_cands"] < MIN_CANDS, "scan_date"].nunique()),
        band_ok_rows=int(C["band_ok"].sum()), band_ok_by_month=C[C["band_ok"]]["scan_date"].str[:7]
        .value_counts().sort_index().to_dict(),
        ep_first_band_ok_rows=int((C["ep_first"] & C["band_ok"]).sum()), base_rows=int(len(base)),
        base_days=int(base["scan_date"].nunique()), base_open_mtm=int((base["exit_reason"] == "open").sum()),
        base_after_cap=int(base["after_cap"].sum()), entry_date_ne_d1=int((~C["entry_is_d1"]).sum()),
        r_oc_missing_in_base=int(base["r_oc"].isna().sum()))
    print("[표본]", json.dumps(sample_stats, ensure_ascii=False))
    meta = dict(brief="BRIEF_dt_flow_explore.md", seed=SEED, n_boot=N_BOOT, n_fake=N_FAKE, tail=TAIL,
                min_cands=MIN_CANDS, min_cov=MIN_COV, window=[S0, S1], query_time=t_query, git_head=head,
                ledger_sha256=hashlib.sha256(LEDGER.read_bytes()).hexdigest(), sample=sample_stats,
                unit_check=uc, results=res, table_md=table, table2_md=table2)
    (BASE / "run_meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=1, default=float),
                                        encoding="utf-8")
    keep = ["scan_date", "stock_code", "n_cands", "ep_first", "band_ok", "after_cap", "exit_reason", "ret_pct",
            "d1", "open", "close", "r_oc", "orgn_ntby_tr_pbmn", "frgn_ntby_tr_pbmn", "acml_tr_pbmn", "ntby_tr_pbmn",
            "ssts_vol_rlim", "k3", "rate_k3", "gvrt_k3", "k4", "rate_k4", "gvrt_k4"] + [f[2] for f in FEATS]
    C.sort_values(["scan_date", "stock_code"])[keep].to_csv(BASE / "rows.csv", index=False, encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
