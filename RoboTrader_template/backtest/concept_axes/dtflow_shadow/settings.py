"""🔒 상수 — 스펙 §4. 바꾸면 사전등록 개정(새 rule_v)."""
from __future__ import annotations

import os
from datetime import time
from pathlib import Path
from typing import Dict, List, Optional, Tuple

PKG = Path(__file__).resolve().parent
RT_ROOT = PKG.parents[2]                       # …/RoboTrader_template
REPO_ROOT = RT_ROOT.parent
PREREG = PKG / "PREREG.md"
LIVE_TREE = "D:/GIT/kis-trading-template"
LIVE_RT = LIVE_TREE + "/RoboTrader_template"

RULE_V = "v1"
SCHEMA = "dtflow_shadow"
WRITER_ROLE = "dtflow_shadow_writer"
FOLDER = "daytrading_3methods_breakout"
PARAMS_HASH = "46594669e8b6af417143556ea3c0066d2ccc9984"

START_NOT_BEFORE = time(7, 50)
REFUSE_AFTER = time(8, 38)
SEAL_DEADLINE = time(8, 40)
SNAPSHOT_NOT_BEFORE = time(9, 3)
START_WINDOW_OPEN = time(7, 40)        # dry-run 거부 창(실제 시계) — 라이브 봇 기동·장 초반
START_WINDOW_CLOSE = time(9, 10)

LOOKBACK_BARS = 60
HIGH_WINDOW = 15
VOL_LOOKBACK = 20
VOL_MULT = 2.0
MAX_MCAP = 500_000_000_000
MIN_TV = 1_000_000_000
IMPOSSIBLE_RET = -0.35
D_ROWS_RATIO_MIN = 0.98

CALL_INTERVAL_S = 0.10
RETRY_BASE_S = 1.5
RETRY_MAX = 3
HTTP_TIMEOUT = (5, 30)
TOKEN_MIN_LEFT_S = 1200
TRS: Dict[str, Tuple[str, str]] = {
    "investor": ("FHKST01010900", "/uapi/domestic-stock/v1/quotations/inquire-investor"),
    "program": ("FHPPG04650201", "/uapi/domestic-stock/v1/quotations/program-trade-by-stock-daily"),
    "short": ("FHPST04830000", "/uapi/domestic-stock/v1/quotations/daily-short-sale"),
    "credit": ("FHPST04760000", "/uapi/domestic-stock/v1/quotations/daily-credit-balance"),
}
KINDS = ("investor", "program", "short", "credit")
SHORT_SPAN_DAYS = 20

INVESTOR_AMT_UNIT = 1_000_000                  # investor *_tr_pbmn = 백만원(DOSSIER_B §0-3)
CREDIT_LAG_K: Optional[int] = None             # 🔒 Task 11 에서 시험 분포로 정해 동결
TRIAL_DAYS = 10
AVAIL_MIN = 0.95

LIVE_SOURCES = (
    "strategies/daytrading_3methods_breakout/screener.py",
    "strategies/_rule_screener_base.py",
    "strategies/books/daytrading_3methods/rules.py",
    "db/quant_daily_reader.py",
    "utils/data_sanity.py",
    "api/kis_market_api.py",
    "api/kis_auth.py",
)


def _local() -> Path:
    return Path(os.environ.get("LOCALAPPDATA", str(Path.home())))


def home_dir() -> Path:
    env = os.environ.get("KIS_DTFLOW_SHADOW_HOME")
    return Path(env) if env else _local() / "kis-dtflow-shadow"


def other_homes() -> List[Path]:
    llm = os.environ.get("KIS_LLM_SHADOW_HOME")
    tasso = os.environ.get("KIS_TASSO_SHADOW_HOME")
    return [Path(llm) if llm else _local() / "kis-llm-shadow", Path(tasso) if tasso else _local() / "kis-tasso-shadow"]


def frozen_path() -> Path:
    return home_dir() / "frozen.json"


def lock_path() -> Path:
    return home_dir() / "runner.lock"


def log_dir() -> Path:
    return home_dir() / "logs"


def archive_dir() -> Path:
    return Path(os.environ.get("KIS_DTFLOW_SHADOW_ARCHIVE", "D:/research-archive/dtflow_shadow"))


def config_dir() -> Path:
    return Path(os.environ.get("KIS_DTFLOW_SHADOW_CONFIG_DIR", LIVE_RT))


def key_ini_path() -> Path:
    return config_dir() / "config" / "key.ini"


def token_path() -> Path:
    return Path(os.environ.get("KIS_DTFLOW_SHADOW_TOKEN", LIVE_RT + "/token_info.json"))
