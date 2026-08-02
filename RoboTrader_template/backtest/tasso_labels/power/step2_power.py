# -*- coding: utf-8 -*-
# STEP 2 - variance measurement -> SE -> MDE
#   Draws (stock, date) ONLY from label-free trading days (EST).
#   No treatment (stock, date) forward return is ever computed.
#   NOTE: mean returns are deliberately NOT reported (freeze protection).
import os, sys, json
import numpy as np, pandas as pd
from scipy import stats
sys.stdout.reconfigure(encoding="utf-8")

BASE = r"D:\GIT\kis-trading-template\RoboTrader_template\backtest\tasso_labels"
OUT  = os.path.join(BASE, "power")
RNG_MASTER = 20260802
Z = stats.norm.ppf(0.975) + stats.norm.ppf(0.80)
print("MDE coef (z_{1-a/2}+z_{power}) = %.6f   [alpha=0.05 two-sided, power=0.80]" % Z)

dsets = json.load(open(os.path.join(OUT, "date_sets.json"), encoding="utf-8"))
ndj   = json.load(open(os.path.join(OUT, "nd_dist.json"), encoding="utf-8"))
EST, TREAT, CAL = dsets["EST"], set(dsets["TREAT_DATES"]), dsets["CAL"]

zz = np.load(os.path.join(OUT, "px_wide.npz"), allow_pickle=True)
dates, codes = zz["dates"], zz["codes"]
O, H, L, C = (zz[q].astype(np.float64) for q in ["O","H","L","C"])
TV = zz["TV"]
dix = {d: i for i, d in enumerate(dates)}
T, S = O.shape

valid = (~np.isnan(O)) & (~np.isnan(H)) & (~np.isnan(L)) & (~np.isnan(C))
valid = valid & (O > 0) & (H > 0) & (L > 0) & (C > 0)

assert len(set(EST) & TREAT) == 0
EI = np.array([dix[d] for d in EST])
print("[PROOF] EST %d days | intersect(TREAT)=%d | range %s~%s"
      % (len(EST), len(set(EST) & TREAT), EST[0], EST[-1]))

KS = [1, 5, 20]
RET, OKM = {}, {}
for k in KS:
    r  = np.zeros((T, S)); okm = np.zeros((T, S), dtype=bool)
    t0 = np.arange(0, T-k)
    good = valid[t0+1, :] & valid[t0+k, :]
    rr   = np.zeros_like(good, dtype=float)
    np.divide(C[t0+k, :], O[t0+1, :], out=rr, where=good)
    rr   = np.where(good, rr - 1.0, 0.0)
    r[t0, :] = rr; okm[t0, :] = good
    RET[k], OKM[k] = r, okm
    print("  k=%2d  tradable cells on EST days: %d" % (k, okm[EI].sum()))

Wl = 20
Hm = np.where(valid, H, np.nan)
prevmax = np.full((T, S), np.nan)
for t in range(Wl, T):
    prevmax[t] = np.nanmax(Hm[t-Wl:t], axis=0)
vv = valid.astype(np.float64)
cs = np.cumsum(np.vstack([np.zeros((1, S)), vv]), axis=0)
nprev = np.zeros((T, S))
for t in range(Wl, T):
    nprev[t] = cs[t] - cs[t-Wl]
T1 = valid & (nprev >= Wl) & (H > prevmax)
print("  T1 (20d high breakout) mean stocks per EST day: %.1f" % T1[EI].sum(1).mean())

COST = {2021: 0.0026, 2022: 0.0026, 2023: 0.0023, 2024: 0.0021}
cost_vec = np.array([COST[int(d[:4])] for d in EST])

def build_pool(K, setup):
    pools = []
    for t in EI:
        m = valid[t] & (~np.isnan(TV[t])) & (TV[t] > 0)
        if setup: m = m & T1[t]
        idx = np.flatnonzero(m)
        if idx.size == 0:
            pools.append(np.array([], int)); continue
        o = idx[np.argsort(-TV[t, idx], kind="stable")]
        pools.append(o[:K])
    return pools

MEDTV = 1372e8
ranks, unis, tv100, tv200 = [], [], [], []
for t in EI:
    m = valid[t] & (~np.isnan(TV[t])) & (TV[t] > 0)
    v = np.sort(TV[t, m])[::-1]
    unis.append(v.size); ranks.append(int((v >= MEDTV).sum()))
    if v.size >= 100: tv100.append(v[99])
    if v.size >= 200: tv200.append(v[199])
print("")
print("[liquidity calibration] median universe on EST days: %d stocks" % int(np.median(unis)))
print("  stocks with TV >= 1372 eok (treatment median TV): median count %d (top %.2f pct)"
      % (int(np.median(ranks)), 100*np.median(ranks)/np.median(unis)))
print("  top100 cutoff TV median %.0f eok | top200 cutoff TV median %.0f eok"
      % (np.median(tv100)/1e8, np.median(tv200)/1e8))

def nd_sampler(dist, rng, n):
    ks = np.array(sorted(int(x) for x in dist))
    ps = np.array([dist[str(kk)] for kk in ks], float)
    return rng.choice(ks, size=n, p=ps/ps.sum())

def one_rep(pools, k, ndist, rng, m_ctrl):
    D = len(pools)
    n_d = nd_sampler(ndist, rng, D)
    dlt = np.full(D, np.nan); ab = np.full(D, np.nan)
    a_stk = []; a_wr = []; a_wa = []; a_y = []; a_dt = []
    for a in range(D):
        p = pools[a]
        need = n_d[a] + (m_ctrl if m_ctrl else 1)
        if p.size < max(30, need):
            continue
        t = EI[a]
        y = RET[k][t, p]
        perm = rng.permutation(p.size)
        dsel = perm[:n_d[a]]
        csel = perm[n_d[a]:n_d[a]+m_ctrl] if m_ctrl else perm[n_d[a]:]
        mu_d, mu_c = y[dsel].mean(), y[csel].mean()
        dlt[a] = mu_d - mu_c
        ab[a]  = mu_d - cost_vec[a]
        a_stk.append(p[dsel]); a_y.append(y[dsel]); a_dt.append(np.full(dsel.size, a))
        a_wr.append(np.full(dsel.size,  1.0/n_d[a])); a_wa.append(np.full(dsel.size, 1.0/n_d[a]))
        a_stk.append(p[csel]); a_y.append(y[csel]); a_dt.append(np.full(csel.size, a))
        a_wr.append(np.full(csel.size, -1.0/csel.size)); a_wa.append(np.zeros(csel.size))
    okv = ~np.isnan(dlt); Dn = int(okv.sum())
    return dict(delta=dlt, absr=ab, ok=okv, D=Dn,
                s=np.concatenate(a_stk), y=np.concatenate(a_y),
                wr=np.concatenate(a_wr)/Dn, wa=np.concatenate(a_wa)/Dn,
                dd=np.concatenate(a_dt))

def cluster_se(s, w, y, center_by=None, theta=None):
    if center_by is not None:
        dfx = pd.DataFrame({"g": center_by, "y": y})
        y = y - dfx.groupby("g")["y"].transform("mean").values
    else:
        y = y - theta
    sg = pd.Series(w*y).groupby(pd.Series(s)).sum().values
    G = sg.size
    return float(np.sqrt(max(G/(G-1.0), 1.0) * np.sum((sg - sg.mean())**2))), G

def cbb_se(x, b, rng, B=800):
    n = x.size; nb = int(np.ceil(n/b))
    st = rng.integers(0, n, size=(B, nb))
    off = np.arange(b)
    idx = (st[:, :, None] + off[None, None, :]).reshape(B, -1)[:, :n] % n
    return float(np.std(x[idx].mean(1), ddof=1))

POSCAL = {d: i for i, d in enumerate(CAL)}
def cal_acf(pairs, hmax):
    arr = np.full(len(CAL), np.nan)
    for d, v in pairs: arr[POSCAL[d]] = v
    m = np.nanmean(arr); sd = np.nanstd(arr)
    out = []
    for h in range(1, hmax+1):
        a, b = arr[:-h], arr[h:]
        okp = ~np.isnan(a) & ~np.isnan(b)
        out.append(float(np.mean((a[okp]-m)*(b[okp]-m))/sd**2) if okp.sum() > 8 else np.nan)
    return np.array(out)

NREP = 120
ARMS = {"rel_CB":  (ndj["cb_cov"], ndj["N_CB_dates"], ndj["N_CB"]),
        "abs_ALL": (ndj["full"],   ndj["N_T_dates"],  ndj["N_T"])}
res, acf_store = [], {}
for setup in [False, True]:
  for K in [100, 200]:
    pools = build_pool(K, setup)
    psz = np.array([p.size for p in pools])
    tag = "top%d%s" % (K, "_T1" if setup else "")
    print("")
    print("="*96)
    print("POOL %s | pool size on EST days: median %d min %d | days with lt 30: %d"
          % (tag, int(np.median(psz)), psz.min(), int((psz < 30).sum())))
    for arm in ["rel_CB", "abs_ALL"]:
        ndist, Dtgt, Ntgt = ARMS[arm]
        for m_ctrl in ([None, 10] if arm == "rel_CB" else [None]):
            for k in KS:
                rng = np.random.default_rng(RNG_MASTER + k*17 + K + int(setup)*3 + (m_ctrl or 0))
                sdD=[]; sdA=[]; seDs=[]; seAs=[]; seDd=[]; seAd=[]; cbbD=[]; cbbA=[]; Gs=[]; Dns=[]
                acc = None
                for rep in range(NREP):
                    R = one_rep(pools, k, ndist, rng, m_ctrl)
                    dl = R["delta"][R["ok"]]; ab = R["absr"][R["ok"]]; Dn = R["D"]
                    Dns.append(Dn)
                    sdD.append(dl.std(ddof=1)); sdA.append(ab.std(ddof=1))
                    seDd.append(dl.std(ddof=1)/np.sqrt(Dn)); seAd.append(ab.std(ddof=1)/np.sqrt(Dn))
                    ss, G = cluster_se(R["s"], R["wr"], R["y"], center_by=R["dd"])
                    seDs.append(ss); Gs.append(G)
                    nz = R["wa"] != 0
                    sa, _ = cluster_se(R["s"][nz], R["wa"][nz], R["y"][nz], theta=float(np.mean(ab)))
                    seAs.append(sa)
                    if rep < 25:
                        b = max(k, 2)
                        cbbD.append(cbb_se(dl, b, rng)); cbbA.append(cbb_se(ab, b, rng))
                    if rep < 40:
                        idxok = np.flatnonzero(R["ok"])
                        A1 = cal_acf([(EST[i], R["delta"][i]) for i in idxok], 25)
                        A2 = cal_acf([(EST[i], R["absr"][i])  for i in idxok], 25)
                        acc = (A1, A2) if acc is None else (acc[0]+A1, acc[1]+A2)
                acfD, acfA = acc[0]/40.0, acc[1]/40.0
                acf_store["%s|%s|m%s|k%d" % (tag, arm, m_ctrl, k)] = dict(delta=acfD.tolist(), absr=acfA.tolist())
                Hh = max(k, 1)
                vifD = 1 + 2*sum((1-h/Dtgt)*acfD[h-1] for h in range(1, Hh+1))
                vifA = 1 + 2*sum((1-h/Dtgt)*acfA[h-1] for h in range(1, Hh+1))
                res.append(dict(pool=tag, arm=arm, ctrl=(m_ctrl if m_ctrl else "rest"), k=k,
                    D_est=int(np.mean(Dns)), sd_delta=np.mean(sdD), sd_abs=np.mean(sdA),
                    se_date_rel=np.mean(seDd), se_stock_rel=np.mean(seDs),
                    se_date_abs=np.mean(seAd), se_stock_abs=np.mean(seAs),
                    cbb_rel=np.mean(cbbD), cbb_abs=np.mean(cbbA),
                    G_stock=int(np.mean(Gs)), D_target=Dtgt, N_target=Ntgt,
                    acf1_rel=acfD[0], acf1_abs=acfA[0], vif_rel=vifD, vif_abs=vifA))
                print("  %-9s %-7s ctrl=%-4s k=%2d | SDd=%.4f SDa=%.4f | SEd=%.5f SEs=%.5f G=%4d | CBB=%.5f | acf1d=%+.3f acf1a=%+.3f"
                      % (tag, arm, str(m_ctrl or "rest"), k, np.mean(sdD), np.mean(sdA),
                         np.mean(seDd), np.mean(seDs), int(np.mean(Gs)), np.mean(cbbD),
                         acfD[0], acfA[0]))

pd.DataFrame(res).to_csv(os.path.join(OUT, "power_raw.csv"), index=False, encoding="utf-8-sig")
json.dump(acf_store, open(os.path.join(OUT, "acf.json"), "w"))
print("")
print("Saved power_raw.csv / acf.json")
