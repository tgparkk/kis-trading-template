"""
p5_roe_walkforward.py — ROE Quintile Filter Walk-Forward OOS + Regime + CapSize Cross
======================================================================================
Phase 5, Signal #F-11 (ROE). Stage A universe filter evaluation.

Parameters tested:
  min_quintile in {3, 4, 5}  (Q3+, Q4+, Q5 only)
  holding in {5, 20, 60} days
  Total: 9 combinations

Walk-Forward: 16 target windows, train=24mo, test=3mo, step=3mo
Transaction cost: 0.3% round-trip

Key results (2021-01 ~ 2026-05, 152 stocks):
  - Dominant optimal: Q4+ min_quintile, 60d holding (8/13 windows)
  - OOS Net @0.3%: Mean=9.31pp, Positive=10/13 (76.9%)
  - Q5 vs Q1 L/S spread (60d): +1.05pp (p=0.277, not significant standalone)
  - ROE Q5 + Cap Q5 cross: 20.86% mean 60d return (vs 5.76% ROE Q5 alone)
  - 5선 gates passed: 5/5

Usage: python scripts/10pct_strategy/p5_roe_walkforward.py
"""

import psycopg2
import pandas as pd
import numpy as np
from scipy import stats
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import warnings
warnings.filterwarnings("ignore")

DB = dict(host="127.0.0.1", port=5433, database="robotrader_quant",
          user="robotrader", password="1234")

# Results documented in reports/10pct_strategy/phase5_signals/roe_walkforward.md
# Figures in .omc/scientist/figures/
