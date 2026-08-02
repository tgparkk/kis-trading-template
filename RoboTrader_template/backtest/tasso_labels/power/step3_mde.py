# -*- coding: utf-8 -*-
# STEP 3 - final SE / MDE table with year-mix reweighting + ACF profile + figures
import os, sys, json
import numpy as np, pandas as pd
from scipy import stats
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
sys.stdout.reconfigure(encoding="utf-8")

BASE = r"D:\GIT\kis-trading-template\RoboTrader_template\backtest\tasso_labels"
OUT  = os.path.join(BASE, "power"); FIG = os.path.join(OUT, "figures")
os.makedirs(FIG, exist_ok=True)
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
EI = np.array([dix[d] for d in EST])
YR = np.array([int(d[:4]) for d in EST])

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
cost_vec = np.array([COST[y] for y in YR])

def build_pool(K):
    pools = []
    for t in EI:
        m = valid[t] & (~np.isnan(TV[t])) & (TV[t] > 0)
        idx = np.flatnonzero(m)
        o = idx[np.argsort(-TV[t, idx], kind="stable")]
        pools.append(o[:K])
    return pools

def nd_sampler(dist, rng, n):
    ks = np.array(sorted(int(x) for x in dist))
    ps = np.array([dist[str(kk)] for kk in ks], float)
    return rng.choice(ks, size=n, p=ps/ps.sum())

POSCAL = {d: i for i, d in enumerate(CAL)}
def cal_acf(vals, hmax):
    arr = np.full(len(CAL), np.nan)
    for i, d in enumerate(EST): arr[POSCAL[d]] = vals[i]
    m = np.nanmean(arr); sd = np.nanstd(arr); out = []; npairs = []
    for h in range(1, hmax+1):
        a, b = arr[:-h], arr[h:]
        okp = ~np.isnan(a) & ~np.isnan(b)
        npairs.append(int(okp.sum()))
        out.append(float(np.mean((a[okp]-m)*(b[okp]-m))/sd**2) if okp.sum() > 8 else np.nan)
    return np.array(out), np.array(npairs)

def cluster_se(s, w, y, center_by=None, theta=None):
    if center_by is not None:
        dfx = pd.DataFrame({"g": center_by, "y": y})
        y = y - dfx.groupby("g")["y"].transform("mean").values
    else:
        y = y - theta
    sg = pd.Series(w*y).groupby(pd.Series(s)).sum().values
    G = sg.size
    return float(np.sqrt(max(G/(G-1.0), 1.0) * np.sum((sg - sg.mean())**2))), G

NREP = 200
RNG0 = 20260802
# target scale
D_CB, N_CB = ndj["N_CB_dates"], ndj["N_CB"]
D_ALL, N_ALL = ndj["N_T_dates"], ndj["N_T"]
# treatment year mix (dates)
tr_yr_dates = {2021: 150, 2022: 196, 2023: 201, 2024: 114}
w_tr = {y: v/sum(tr_yr_dates.values()) for y, v in tr_yr_dates.items()}
est_yr = {y: int((YR == y).sum()) for y in [2021, 2022, 2023, 2024]}
print("EST year mix :", est_yr, " -> shares", {y: round(v/len(EST), 3) for y, v in est_yr.items()})
print("TREAT yr mix :", tr_yr_dates, " -> shares", {y: round(v, 3) for y, v in w_tr.items()})

rows = []; acf_out = {}
for K in [100, 200]:
    pools = build_pool(K)
    for ctrl in ["rest", 10]:
        for k in KS:
            rng = np.random.default_rng(RNG0 + K + k*31 + (0 if ctrl == "rest" else 7))
            m_ctrl = None if ctrl == "rest" else 10
            Dmat = np.zeros((NREP, len(EST))); Amat = np.zeros((NREP, len(EST)))
            se_st_rel = []; se_st_abs = []; Gs = []
            for rep in range(NREP):
                n_d = nd_sampler(ndj["cb_cov"] if ctrl != "X" else ndj["full"], rng, len(EST))
                n_a = nd_sampler(ndj["full"], rng, len(EST))
                a_s=[]; a_wr=[]; a_wa=[]; a_y=[]; a_dt=[]
                for a in range(len(EST)):
                    p = pools[a]; t = EI[a]; y = RET[k][t, p]
                    perm = rng.permutation(p.size)
                    ds = perm[:n_d[a]]
                    csx = perm[n_d[a]:n_d[a]+m_ctrl] if m_ctrl else perm[n_d[a]:]
                    Dmat[rep, a] = y[ds].mean() - y[csx].mean()
                    asel = perm[:n_a[a]]
                    Amat[rep, a] = y[asel].mean() - cost_vec[a]
                    a_s.append(p[ds]); a_y.append(y[ds]); a_dt.append(np.full(ds.size, a))
                    a_wr.append(np.full(ds.size, 1.0/n_d[a])); a_wa.append(np.zeros(ds.size))
                    a_s.append(p[csx]); a_y.append(y[csx]); a_dt.append(np.full(csx.size, a))
                    a_wr.append(np.full(csx.size, -1.0/csx.size)); a_wa.append(np.zeros(csx.size))
                    a_s.append(p[asel]); a_y.append(y[asel]); a_dt.append(np.full(asel.size, a))
                    a_wr.append(np.zeros(asel.size)); a_wa.append(np.full(asel.size, 1.0/n_a[a]))
                Sarr = np.concatenate(a_s); Yarr = np.concatenate(a_y)
                Wr = np.concatenate(a_wr)/len(EST); Wa = np.concatenate(a_wa)/len(EST)
                Dt = np.concatenate(a_dt)
                nz = Wr != 0
                s1, G = cluster_se(Sarr[nz], Wr[nz], Yarr[nz], center_by=Dt[nz]); se_st_rel.append(s1); Gs.append(G)
                nz2 = Wa != 0
                s2, _ = cluster_se(Sarr[nz2], Wa[nz2], Yarr[nz2], theta=float(Amat[rep].mean()))
                se_st_abs.append(s2)
            # per-year variance (EST)
            varD_y = {y: float(np.mean([Dmat[r][YR == y].var(ddof=1) for r in range(NREP)])) for y in [2021,2022,2023,2024]}
            varA_y = {y: float(np.mean([Amat[r][YR == y].var(ddof=1) for r in range(NREP)])) for y in [2021,2022,2023,2024]}
            VD_raw = float(np.mean([Dmat[r].var(ddof=1) for r in range(NREP)]))
            VA_raw = float(np.mean([Amat[r].var(ddof=1) for r in range(NREP)]))
            VD_rw  = sum(w_tr[y]*varD_y[y] for y in w_tr)
            VA_rw  = sum(w_tr[y]*varA_y[y] for y in w_tr)
            acfD, npD = cal_acf(Dmat.mean(0)*0 + Dmat[0], 25)
            acfDm = np.mean([cal_acf(Dmat[r], 25)[0] for r in range(40)], axis=0)
            acfAm = np.mean([cal_acf(Amat[r], 25)[0] for r in range(40)], axis=0)
            acf_out["K%d_%s_k%d" % (K, ctrl, k)] = dict(delta=acfDm.tolist(), absr=acfAm.tolist(),
                                                        npairs=npD.tolist())
            Hh = max(k, 1)
            vifD = 1 + 2*sum((1-h/D_CB)*acfDm[h-1] for h in range(1, Hh+1))
            vifA = 1 + 2*sum((1-h/D_ALL)*acfAm[h-1] for h in range(1, Hh+1))
            vifD = max(vifD, 1.0); vifA = max(vifA, 1.0)
            # stock-block inflation ratio measured at EST scale
            se_date_rel_est = float(np.mean([Dmat[r].std(ddof=1) for r in range(NREP)]))/np.sqrt(len(EST))
            se_date_abs_est = float(np.mean([Amat[r].std(ddof=1) for r in range(NREP)]))/np.sqrt(len(EST))
            rat_rel = float(np.mean(se_st_rel))/se_date_rel_est
            rat_abs = float(np.mean(se_st_abs))/se_date_abs_est
            # final SE at target scale
            SE_rel = np.sqrt(VD_rw*vifD/D_CB)  * max(1.0, rat_rel)
            SE_abs = np.sqrt(VA_rw*vifA/D_ALL) * max(1.0, rat_abs)
            SE_rel_raw = np.sqrt(VD_raw*vifD/D_CB) * max(1.0, rat_rel)
            SE_abs_raw = np.sqrt(VA_raw*vifA/D_ALL) * max(1.0, rat_abs)
            rows.append(dict(K=K, ctrl=str(ctrl), k=k,
                sd_delta_est=np.sqrt(VD_raw), sd_abs_est=np.sqrt(VA_raw),
                sd_delta_rw=np.sqrt(VD_rw),  sd_abs_rw=np.sqrt(VA_rw),
                se_date_rel_est=se_date_rel_est, se_stock_rel_est=float(np.mean(se_st_rel)),
                se_date_abs_est=se_date_abs_est, se_stock_abs_est=float(np.mean(se_st_abs)),
                ratio_stock_date_rel=rat_rel, ratio_stock_date_abs=rat_abs,
                acf1_rel=acfDm[0], acf1_abs=acfAm[0], vif_rel=vifD, vif_abs=vifA,
                SE_rel_target=SE_rel, SE_abs_target=SE_abs,
                SE_rel_target_noRW=SE_rel_raw, SE_abs_target_noRW=SE_abs_raw,
                MDE_rel=ZC*SE_rel*100, MDE_abs=ZC*SE_abs*100,
                MDE_rel_noRW=ZC*SE_rel_raw*100, MDE_abs_noRW=ZC*SE_abs_raw*100,
                G_stock=int(np.mean(Gs)),
                sdD_2021=np.sqrt(varD_y[2021]), sdD_2022=np.sqrt(varD_y[2022]),
                sdD_2023=np.sqrt(varD_y[2023]), sdD_2024=np.sqrt(varD_y[2024])))
            print("K=%3d ctrl=%-4s k=%2d | SD(D) est %.4f -> rw %.4f | SE_rel %.5f  MDE_rel %.3f%%p | SE_abs %.5f MDE_abs %.3f%%p | vif %.2f/%.2f | ratio s/d %.3f/%.3f"
                  % (K, ctrl, k, np.sqrt(VD_raw), np.sqrt(VD_rw), SE_rel, ZC*SE_rel*100,
                     SE_abs, ZC*SE_abs*100, vifD, vifA, rat_rel, rat_abs))

df = pd.DataFrame(rows)
df.to_csv(os.path.join(OUT, "mde_final.csv"), index=False, encoding="utf-8-sig")
json.dump(acf_out, open(os.path.join(OUT, "acf_final.json"), "w"))

print("")
print("ACF profile (K=100, ctrl=rest):")
for k in KS:
    a = acf_out["K100_rest_k%d" % k]
    print("  k=%2d delta: " % k + " ".join("%+.3f" % v for v in a["delta"][:12]))
    print("  k=%2d abs  : " % k + " ".join("%+.3f" % v for v in a["absr"][:12]))
print("  npairs lag1..12: " + " ".join(str(v) for v in acf_out["K100_rest_k5"]["npairs"][:12]))

print("")
print("per-year SD(delta) [K=100 ctrl=rest]:")
for k in KS:
    r = df[(df.K == 100) & (df.ctrl == "rest") & (df.k == k)].iloc[0]
    print("  k=%2d  2021 %.4f | 2022 %.4f | 2023 %.4f | 2024 %.4f" %
          (k, r.sdD_2021, r.sdD_2022, r.sdD_2023, r.sdD_2024))

fig, ax = plt.subplots(1, 2, figsize=(12, 4.2))
for k in KS:
    a = acf_out["K100_rest_k%d" % k]
    ax[0].plot(range(1, 26), a["delta"], marker="o", ms=3, label="k=%d" % k)
    ax[1].plot(range(1, 26), a["absr"],  marker="o", ms=3, label="k=%d" % k)
for i, ttl in enumerate(["Delta(d) autocorrelation", "Absolute R(d) autocorrelation"]):
    ax[i].axhline(0, color="k", lw=0.8); ax[i].set_title(ttl)
    ax[i].set_xlabel("trading-day lag h"); ax[i].set_ylabel("rho_h"); ax[i].legend(); ax[i].grid(alpha=.3)
plt.tight_layout(); plt.savefig(os.path.join(FIG, "acf.png"), dpi=130); plt.close()

fig, ax = plt.subplots(figsize=(7.5, 4.2))
sub = df[df.ctrl == "rest"]
for K in [100, 200]:
    s = sub[sub.K == K]
    ax.plot(s.k, s.MDE_rel, marker="o", label="MDE_rel K=%d (ctrl=pool rest)" % K)
    ax.plot(s.k, s.MDE_abs, marker="s", ls="--", label="MDE_abs K=%d" % K)
s10 = df[(df.ctrl == "10")]
for K in [100, 200]:
    s = s10[s10.K == K]
    ax.plot(s.k, s.MDE_rel, marker="^", ls=":", label="MDE_rel K=%d (ctrl m=10)" % K)
ax.axhline(1.0, color="green", lw=1.2, label="go threshold 1.0%p")
ax.axhline(1.5, color="red", lw=1.2, label="stop threshold 1.5%p")
ax.set_xlabel("holding window k (trading days)"); ax.set_ylabel("MDE (%p per trade)")
ax.set_title("Pre-registered MDE vs fixed go/no-go thresholds"); ax.grid(alpha=.3)
ax.legend(fontsize=7); plt.tight_layout()
plt.savefig(os.path.join(FIG, "mde_vs_threshold.png"), dpi=130); plt.close()
print("")
print("Saved mde_final.csv, acf_final.json, figures/acf.png, figures/mde_vs_threshold.png")
