# -*- coding: utf-8 -*-
# STEP 5 - consolidated decision table + figures
import os, sys, json
import numpy as np, pandas as pd
from scipy import stats
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
sys.stdout.reconfigure(encoding="utf-8")
BASE = r"D:\GIT\kis-trading-template\RoboTrader_template\backtest\tasso_labels"
OUT  = os.path.join(BASE, "power"); FIG = os.path.join(OUT, "figures")
ZC = stats.norm.ppf(0.975) + stats.norm.ppf(0.80)

sens = pd.read_csv(os.path.join(OUT, "sensitivity.csv"))
fin  = pd.read_csv(os.path.join(OUT, "mde_final.csv"))
acf  = json.load(open(os.path.join(OUT, "acf_final.json")))
ndj  = json.load(open(os.path.join(OUT, "nd_dist.json"), encoding="utf-8"))
D_CB, D_ALL = ndj["N_CB_dates"], ndj["N_T_dates"]

print("MDE = (z_0.975 + z_0.80) * SE_target = %.6f * SE_target" % ZC)
print("SE_target = sqrt( Vbar_perdate * VIF / D_target ) * max(1, SE_stock/SE_date)")
print("Vbar_perdate = sum_y w_y * Var_y(series)   w_y = treatment date share by year")
print("VIF = 1 + 2*sum_{h=1..k} (1 - h/D_target) * rho_h")
print("D_target: relative arm = %d (C-B covered dates) | absolute arm = %d (all treatment dates)" % (D_CB, D_ALL))
print("")
print("### PRIMARY DECISION TABLE  (k=5, subsample=ALL 315 days, year-reweighted)")
print("%-6s %-6s | %-9s %-9s | %-10s %-10s | %s" %
      ("K", "ctrl", "SD(delta)", "SD(abs)", "MDE_rel", "MDE_abs", "verdict_rel"))
s5 = sens[(sens["sub"] == "ALL") & (sens.k == 5)].sort_values(["K", "ctrl"])
for _, r in s5.iterrows():
    v = "EXECUTE" if r.MDE_rel <= 1.0 else ("CONDITIONAL" if r.MDE_rel <= 1.5 else "STOP")
    print("%-6d %-6s | %-9.4f %-9.4f | %-10.3f %-10.3f | %s"
          % (r.K, r.ctrl, r.sd_delta, r.sd_abs, r.MDE_rel, r.MDE_abs, v))

print("")
print("### ALL k  (subsample=ALL, year-reweighted)")
for k in [1, 5, 20]:
    sub = sens[(sens["sub"] == "ALL") & (sens.k == k)]
    print("k=%2d | MDE_rel %.3f-%.3f  | MDE_abs %.3f-%.3f | annualized MDE_rel %.1f-%.1f %%p/yr (250/k trades)"
          % (k, sub.MDE_rel.min(), sub.MDE_rel.max(), sub.MDE_abs.min(), sub.MDE_abs.max(),
             sub.MDE_rel.min()*250/k, sub.MDE_rel.max()*250/k))

print("")
print("### D_target sensitivity  (k=5, how MDE_rel moves if C-B coverage shrinks)")
print("%-6s %-6s | %s" % ("K", "ctrl", "  D=633    D=600    D=570    D=540"))
for _, r in s5.iterrows():
    vals = [r.MDE_rel*np.sqrt(D_CB/d) for d in [633, 600, 570, 540]]
    print("%-6d %-6s |  %s" % (r.K, r.ctrl, "  ".join("%6.3f" % v for v in vals)))

print("")
print("### stock-block vs date-block SE ratio (6th-round check: iid was 3.63x optimistic)")
for _, r in fin[fin.k.isin([1,5,20])].iterrows():
    print("  K=%3d ctrl=%-4s k=%2d | ratio(rel)=%.3f  ratio(abs)=%.3f  G_stock=%d"
          % (r.K, r.ctrl, r.k, r.ratio_stock_date_rel, r.ratio_stock_date_abs, r.G_stock))

print("")
print("### drawn-stock repeat structure vs treatment (rows per stock)")
print("  treatment ALL %.2f | treatment C-B %.2f" % (ndj["N_T"]/ndj["N_T_stocks"], ndj["N_CB"]/ndj["N_CB_stocks"]))
for K in [30, 50, 100, 200]:
    v = sens[(sens["sub"] == "ALL") & (sens.K == K) & (sens.k == 5)].rows_per_stock.mean()
    print("  simulated K=%3d : %.2f" % (K, v))

print("")
print("### Delta(d) autocorrelation, measured (K=100 ctrl=rest)")
for k in [1, 5, 20]:
    a = acf["K100_rest_k%d" % k]["delta"]
    print("  k=%2d  rho_1..rho_10: %s | max|rho_h| h<=k = %.3f"
          % (k, " ".join("%+.3f" % x for x in a[:10]), max(abs(x) for x in a[:max(k,1)])))
print("### Absolute R(d) autocorrelation")
for k in [1, 5, 20]:
    a = acf["K100_rest_k%d" % k]["absr"]
    print("  k=%2d  rho_1..rho_10: %s" % (k, " ".join("%+.3f" % x for x in a[:10])))

# figure
fig, ax = plt.subplots(1, 2, figsize=(13, 4.6))
for ctrl, mk in [("rest", "o"), ("10", "s")]:
    for k, cl in [(1, "tab:blue"), (5, "tab:red"), (20, "tab:gray")]:
        s = sens[(sens["sub"] == "ALL") & (sens.ctrl == ctrl) & (sens.k == k)].sort_values("K")
        ax[0].plot(s.K, s.MDE_rel, marker=mk, color=cl, ls="-" if ctrl == "rest" else "--",
                   label="k=%d ctrl=%s" % (k, "pool-rest" if ctrl == "rest" else "m=10"))
        ax[1].plot(s.K, s.MDE_abs, marker=mk, color=cl, ls="-" if ctrl == "rest" else "--",
                   label="k=%d ctrl=%s" % (k, "pool-rest" if ctrl == "rest" else "m=10"))
for i, t in enumerate(["MDE_rel  (C-B primary)", "MDE_abs  (absolute companion)"]):
    ax[i].axhline(1.0, color="green", lw=1.4); ax[i].axhline(1.5, color="red", lw=1.4)
    ax[i].text(205, 1.02, "1.0%p go-line", color="green", fontsize=8)
    ax[i].text(205, 1.52, "1.5%p stop-line", color="red", fontsize=8)
    ax[i].set_xscale("log"); ax[i].set_xticks([30, 50, 100, 200]); ax[i].set_xticklabels([30, 50, 100, 200])
    ax[i].set_xlabel("pool = top-K by trading value"); ax[i].set_ylabel("MDE (%p per trade)")
    ax[i].set_title(t); ax[i].grid(alpha=.3); ax[i].legend(fontsize=7)
plt.tight_layout(); plt.savefig(os.path.join(FIG, "mde_by_K.png"), dpi=130); plt.close()

fig, ax = plt.subplots(figsize=(8, 4))
yrs = {"2021": 92, "2022": 50, "2023": 44, "2024": 129}
tre = {"2021": 150, "2022": 196, "2023": 201, "2024": 114}
x = np.arange(4); w = 0.38
ax.bar(x-w/2, [yrs[y]/315 for y in yrs], w, label="estimation sample (315 label-free days)")
ax.bar(x+w/2, [tre[y]/661 for y in tre], w, label="treatment (661 label days)")
ax.set_xticks(x); ax.set_xticklabels(list(yrs)); ax.set_ylabel("share of days")
ax.set_title("Representativeness gap: year composition"); ax.legend(); ax.grid(alpha=.3, axis="y")
plt.tight_layout(); plt.savefig(os.path.join(FIG, "year_mix.png"), dpi=130); plt.close()
print("")
print("figures: mde_by_K.png, year_mix.png, acf.png, mde_vs_threshold.png")
