"""Feature Edge Lab 상수 (측정 전용 Phase 0)."""
import os

UNIVERSE_MIN_TRADING_VALUE = 1_000_000_000   # 1차 유동성 컷 (거래대금 ≥ 10억)
PERIOD_START = "2021-01-01"
PERIOD_END = "2026-06-12"
OOS_SPLIT = "2024-06-30"                       # train ≤ split < test (기존 게이트 관행)

FWD_HORIZONS = (5, 10, 20)                     # 선행수익률 호라이즌(거래일)
BARRIER_SETS = ((0.10, 0.05, 10), (0.15, 0.07, 20))  # (up, down, horizon)

COVERAGE_MIN = 0.60                            # 피처 non-null 비율 임계
KOSPI_INDEX_CODE = "0001"
KOSDAQ_INDEX_CODE = "1001"

_REPORT_DIR = os.path.join("reports", "discovery", "feature_edge")
PANEL_PATH = os.path.join(_REPORT_DIR, "feature_panel.parquet")
REPORT_PATH = os.path.join(_REPORT_DIR, "edge_report.md")
