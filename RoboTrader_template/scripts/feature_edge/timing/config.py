"""Intraday Timing Lab 상수 (측정 전용 Phase 1)."""
import os

INTRADAY_START = "2025-02-24"
INTRADAY_END = "2026-06-12"
OOS_SPLIT = "2026-01-01"
SLIPPAGE_PER_SIDE = 0.001
OPENING_RANGE_MIN = 30
GAP_SKIP_PCT = 0.05
INTRADAY_TRAIL_PCT = 0.03
TIME_EXIT = "1430"
MOM_LOSS_MIN = 30
ATR_STOP_K = 2.0

TIMING_STRATEGIES = (
    "daytrading_3methods_breakout", "deep_mr_dev20", "book_envelope_200d")

_REPORT_DIR = os.path.join("reports", "discovery", "timing_lab")
TRADES_PATH = os.path.join(_REPORT_DIR, "trades.parquet")
REPORT_PATH = os.path.join(_REPORT_DIR, "timing_report.md")
