# -*- coding: utf-8 -*-
# STEP 4 - sensitivities: tighter K, in-regime-window subsample, drawn-stock repeat structure
import os, sys, json
import numpy as np, pandas as pd
from scipy import stats
sys.stdout.reconfigure(encoding="utf-8")

BASE = r"D:\GIT\kis-trading-template\RoboTrader_template\backtest\tasso_labels"
OUT  = os.path.join(BASE, "power")
ZC = stats.norm.ppf(0.975) + stats.norm.ppf(0.80)

dsets = json.load(open(os.path.join(OUT, "date_sets.json"), encoding="utf-8"))
ndj   = json.load(open(os.path.join(OUT, "nd_dist.json"), encoding="utf-8"))
EST, TREAT, CAL = dsets["EST"], set(dsets["TREAT_DATES"]), dsets["CAL"]
assert len(set(EST) & TREAT) == 0

zz = np.load(os.path.join(OUT, "px_wide.npz"), allow_pickle=True)
dates = zz["dates"]
O, H, L, C = (zz[q].astype(np.float64) for q in ["O","H","L","C"])
TV = zz["TV"]
dix = {d: i for i, d in enumerate(dates)}
T, S = O.shape
valid = (~np.isnan(O)) & (~np.isnan(H)) & (~np.isnan(L)) & (~np.isnan(C))
valid = valid & (O > 0) & (H > 0) & (L > 0) & (C > 0)
KS = [1, 5, 20]
RET = {}
for k in KS:
    r = np.zeros((T, S)); t0 = np.arange(0, T-k)
    good = valid[t0+1, :] & valid[t0+k, :]
    rr = np.zeros_like(good, dtype=float)
    np.divide(C[t0+k, :], O[t0+1, :], out=rr, where=good)
    r[t0, :] = np.where(good, rr - 1.0, 0.0)
    RET[k] = r
COST = {2021: 0.0026, 2022: 0.0026, 2023: 0.0023, 2024: 0.0021}

tr_yr = {2021: 150, 2022: 196, 2023: 201, 2024: 114}
w_tr = {y: v/sum(tr_yr.values()) for y, v in tr_yr.items()}
D_CB, D_ALL = ndj["N_CB_dates"], ndj["N_T_dates"]

REG_LO, REG_HI = "2021-02-01", "2024-08-30"
SUBS = {"ALL": EST,
        "IN_REGIME": [d for d in EST if REG_LO <= d <= REG_HI],
        "POST_REGIME": [d for d in EST if d > REG_HI],
        "PRE_REGIME": [d for d in EST if d < REG_LO]}
for nm, v in SUBS.items():
    yy = pd.Series([d[:4] for d in v]).value_counts().sort_index().to_dict()
    print("subsample %-12s n=%3d  years=%s" % (nm, len(v), yy))
print("")

def nd_sampler(dist, rng, n):
    ks = np.array(sorted(int(x) for x in dist))
    ps = np.array([dist[str(kk)] for kk in ks], float)
    return rng.choice(ks, size=n, p=ps/ps.sum())

def run(sub, K, ctrl, k, nrep=200, seed=7):
    EIx = np.array([dix[d] for d in sub]); YRx = np.array([int(d[:4]) for d in sub])
    cv = np.array([COST[y] for y in YRx])
    pools = []
    for t in EIx:
        m = valid[t] & (~np.isnan(TV[t])) & (TV[t] > 0)
        idx = np.flatnonzero(m)
        pools.append(idx[np.argsort(-TV[t, idx], kind="stable")][:K])
    rng = np.random.default_rng(seed + K*13 + k*31 + (0 if ctrl == "rest" else 7) + len(sub))
    m_ctrl = None if ctrl == "rest" else 10
    n = len(sub)
    Dm = np.zeros((nrep, n)); Am = np.zeros((nrep, n))
    uniq_rows = []; uniq_stk = []
    for rep in range(nrep):
        n_d = nd_sampler(ndj["cb_cov"], rng, n)
        n_a = nd_sampler(ndj["full"], rng, n)
        drawn = []
        for a in range(n):
            p = pools[a]
            if p.size < max(30, n_d[a] + (m_ctrl or 1)):
                Dm[rep, a] = np.nan; Am[rep, a] = np.nan; continue
            y = RET[k][EIx[a], p]
            perm = rng.permutation(p.size)
            ds = perm[:n_d[a]]
            cx = perm[n_d[a]:n_d[a]+m_ctrl] if m_ctrl else perm[n_d[a]:]
            Dm[rep, a] = y[ds].mean() - y[cx].mean()
            asel = perm[:n_a[a]]
            Am[rep, a] = y[asel].mean() - cv[a]
            drawn.append(p[ds])
        dd = np.concatenate(drawn)
        uniq_rows.append(dd.size); uniq_stk.append(np.unique(dd).size)
    okc = ~np.isnan(Dm[0])
    varD_y = {}; varA_y = {}
    for yv in [2021, 2022, 2023, 2024]:
        msk = (YRx == yv) & okc
        if msk.sum() > 3:
            varD_y[yv] = float(np.mean([np.nanvar(Dm[r][msk], ddof=1) for r in range(nrep)]))
            varA_y[yv] = float(np.mean([np.nanvar(Am[r][msk], ddof=1) for r in range(nrep)]))
    wsum = sum(w_tr[y] for y in varD_y)
    VD = sum(w_tr[y]/wsum*varD_y[y] for y in varD_y)
    VA = sum(w_tr[y]/wsum*varA_y[y] for y in varA_y)
    VDr = float(np.mean([np.nanvar(Dm[r], ddof=1) for r in range(nrep)]))
    VAr = float(np.mean([np.nanvar(Am[r], ddof=1) for r in range(nrep)]))
    return dict(VD=VD, VA=VA, VD_raw=VDr, VA_raw=VAr,
                rows=np.mean(uniq_rows), stks=np.mean(uniq_stk),
                nday=int(okc.sum()), yrs=sorted(varD_y))

VIF_ABS = {1: 1.00, 5: 1.34, 20: 3.27}   # measured in step3 (K=100, ctrl=rest)
print("=== A. K sensitivity (subsample=ALL, year-reweighted) ===")
res = []
for K in [30, 50, 100, 200]:
    for ctrl in ["rest", 10]:
        for k in KS:
            r = run(SUBS["ALL"], K, ctrl, k)
            SEr = np.sqrt(r["VD"]/D_CB)
            SEa = np.sqrt(r["VA"]*VIF_ABS[k]/D_ALL)
            res.append(dict(sub="ALL", K=K, ctrl=str(ctrl), k=k, nday=r["nday"],
                            sd_delta=np.sqrt(r["VD"]), sd_abs=np.sqrt(r["VA"]),
                            MDE_rel=ZC*SEr*100, MDE_abs=ZC*SEa*100,
                            drawn_rows=r["rows"], drawn_stocks=r["stks"],
                            rows_per_stock=r["rows"]/r["stks"]))
            print("  K=%3d ctrl=%-4s k=%2d | SD(D)=%.4f | MDE_rel=%.3f%%p | MDE_abs=%.3f%%p | drawn %.0f rows / %.0f stocks = %.2f"
                  % (K, ctrl, k, np.sqrt(r["VD"]), ZC*SEr*100, ZC*SEa*100, r["rows"], r["stks"], r["rows"]/r["stks"]))

print("")
print("=== B. subsample sensitivity (K=100, ctrl=rest and m=10) ===")
for nm in ["ALL", "IN_REGIME", "POST_REGIME"]:
    for ctrl in ["rest", 10]:
        for k in KS:
            r = run(SUBS[nm], 100, ctrl, k)
            SEr = np.sqrt(r["VD"]/D_CB); SEa = np.sqrt(r["VA"]*VIF_ABS[k]/D_ALL)
            SEr_raw = np.sqrt(r["VD_raw"]/D_CB)
            res.append(dict(sub=nm, K=100, ctrl=str(ctrl), k=k, nday=r["nday"],
                            sd_delta=np.sqrt(r["VD"]), sd_abs=np.sqrt(r["VA"]),
                            MDE_rel=ZC*SEr*100, MDE_abs=ZC*SEa*100,
                            drawn_rows=r["rows"], drawn_stocks=r["stks"],
                            rows_per_stock=r["rows"]/r["stks"]))
            print("  %-12s ctrl=%-4s k=%2d n=%3d yrs=%s | SD(D)=%.4f | MDE_rel=%.3f%%p (no-rw %.3f) | MDE_abs=%.3f%%p"
                  % (nm, ctrl, k, r["nday"], r["yrs"], np.sqrt(r["VD"]), ZC*SEr*100, ZC*SEr_raw*100, ZC*SEa*100))

pd.DataFrame(res).to_csv(os.path.join(OUT, "sensitivity.csv"), index=False, encoding="utf-8-sig")
print("")
print("treatment repeat structure: ALL %d rows / %d stocks = %.2f | C-B %d / %d = %.2f"
      % (ndj["N_T"], ndj["N_T_stocks"], ndj["N_T"]/ndj["N_T_stocks"],
         ndj["N_CB"], ndj["N_CB_stocks"], ndj["N_CB"]/ndj["N_CB_stocks"]))
print("Saved sensitivity.csv")
