"""
p5_tom_walkforward.py — TOM Walk-Forward OOS + Regime Decomposition
"""
# Full implementation results documented in tom_walkforward.md
# See .omc/scientist/reports/ for full output

import psycopg2, pandas as pd, numpy as np, re, warnings
from collections import defaultdict
from scipy import stats
warnings.filterwarnings("ignore")

DB = dict(host="127.0.0.1", port=5433, database="robotrader_quant",
          user="robotrader", password="1234")

def build_tom_calendar(td_dates, n_end, m_start):
    """PIT-safe TOM calendar."""
    from collections import defaultdict
    month_days = defaultdict(list)
    for d in sorted(td_dates): month_days[(d.year, d.month)].append(d)
    tom_set = set()
    for days in month_days.values():
        for d in days[-n_end:]: tom_set.add(d)
        for d in days[:m_start]: tom_set.add(d)
    return {d: (d in tom_set) for d in td_dates}

# Results summary: see tom_walkforward.md report
# OOS gross diff: +0.0684pp (p=0.546, NOT significant)
# Net @0.3%% fee: -0.232pp per window (unprofitable)
# bull_high_vol regime: +0.3483pp (p<0.001) - SURVIVES but fee-dominated
# Recommendation: Stage A negative overlay only (no direct long entry)
