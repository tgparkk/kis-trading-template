"""경로·상수 — 사전등록 §2·§3-3·§5·부록 C 시드 표.

🔒 시드·상한·가족은 사전등록 값 그대로다. 바꾸면 새 가족(§13-3).
설정 파일(`config/key.ini`·`.env`)은 라이브 트리에만 있다 — **읽기만**(복사·출력·로그 금지).
테스트는 env `KIS_LLM_SHADOW_CONFIG_DIR`(RoboTrader_template 역할 폴더)·`KIS_LLM_SHADOW_HOME` 으로 바꾼다.
"""
from __future__ import annotations

import os
from pathlib import Path

PKG_DIR = Path(__file__).resolve().parent
RT_ROOT = PKG_DIR.parents[3]                       # …/RoboTrader_template
REPO_ROOT = RT_ROOT.parent
PREREG_MD = RT_ROOT / "docs" / "prereg_2026-09-26_llm_candidate_shadow.md"

LIVE_TREE = "D:/GIT/kis-trading-template"          # 🔴 라이브 트리 — 여기서 실행 금지(§13-5)
LIVE_CONFIG_DIR = "D:/GIT/kis-trading-template/RoboTrader_template"


def config_dir() -> Path:
    """`config/key.ini`·`.env` 가 있는 RoboTrader_template 폴더(기본 = 라이브 트리 · 읽기 전용)."""
    return Path(os.environ.get("KIS_LLM_SHADOW_CONFIG_DIR", LIVE_CONFIG_DIR))


def key_ini_path() -> Path:
    return config_dir() / "config" / "key.ini"


def dotenv_path() -> Path:
    return config_dir() / ".env"


def home_dir() -> Path:
    """런너 전용 상태 폴더(git 밖) = `%LOCALAPPDATA%/kis-llm-shadow`."""
    env = os.environ.get("KIS_LLM_SHADOW_HOME")
    if env:
        return Path(env)
    return Path(os.environ.get("LOCALAPPDATA", str(Path.home()))) / "kis-llm-shadow"


def exe_path() -> Path:
    """§5-2 고정 설치 exe(`npm install --prefix …/cli @anthropic-ai/claude-code@2.1.283`)."""
    return home_dir() / "cli" / "node_modules" / "@anthropic-ai" / "claude-code" / "bin" / "claude.exe"


def cli_package_json() -> Path:
    return home_dir() / "cli" / "node_modules" / "@anthropic-ai" / "claude-code" / "package.json"


def frozen_path() -> Path:
    return home_dir() / "frozen.json"


def lock_path() -> Path:
    return home_dir() / "runner.lock"


def dart_forward_dir() -> Path:
    return home_dir() / "dart_forward"


def log_dir() -> Path:
    return home_dir() / "logs"


def archive_dir() -> Path:
    """§4 원장 해시 보관소."""
    return Path(os.environ.get("KIS_LLM_SHADOW_ARCHIVE", "D:/research-archive/llm_shadow"))


# ── §5-8 가족 사다리 (가족 = (모델, 규칙) · 섞기·풀링 금지) ─────────────────────────
FAMILIES = {
    "F1": dict(model="claude-opus-5-5", rules="all"),
    "F2": dict(model="claude-sonnet-5", rules="all"),
    "F3": dict(model="claude-opus-5-5", rules="A_only"),
    "S1": dict(model="claude-opus-5-5", rules="search"),
}
MAIN_FAMILIES = ("F1", "F2", "F3")
PROMPT_VERSION = "v1"

# ── §3-3 · §5-4 · §5-6 · §5-9 상한 ───────────────────────────────────────────────
DAILY_CAP = 360            # 1차 채점 ≤ 360종목/일
BATCH_SIZE = 20            # 호출 1회 ≤ 20종목
MAX_PRIMARY_BATCHES = 18
CONCURRENCY = 3
ROTATION_TD = 20           # (B) 순환 20거래일 · 첫 20거래일 조각
DEFAULT_BATCH_TIMEOUT_S = 180   # 잠정(§5-4) — dry-run p95 로 개정문 뒤 frozen.json 에 동결
OVERLOAD_STATUSES = (429, 529)
OVERLOAD_SLEEP_S = 180
REPEAT_MAX = 20
REPEAT_FRAC = 0.05
SEARCH_K_MIN, SEARCH_K_MAX, SEARCH_FRAC = 5, 15, 0.05
SEARCH_MAX_CALLS = 30
SEARCH_DEADLINE = "08:58"
SEARCH_AGG_LAG_TD = 3      # (ㄱ) D+3 판정(거래일)
OPENDART_DAILY_MAX = 60    # 두 프로세스 합산
CATCHUP_TD = 5             # 누락 보충 = 최근 5거래일
DART_TITLE_TD, PRESS_TITLE_TD = 10, 5
DART_TITLE_MAX, PRESS_TITLE_MAX, TITLE_MAX_CHARS = 12, 8, 120
CUTOFF_HHMM = (8, 30)      # §3-5 news.created_at < T 08:30

# ── 부록 C 시드 표 (default_rng([20261004, x, yyyymmdd(D)])) ───────────────────────
SEED_BASE = 20261004
SEED_BATCH_SHUFFLE = 82
SEED_REPEAT_PICK = 83
SEED_A_FILL = 87
SEED_SEARCH_SAMPLE = 88
SEED_REPEAT_SHUFFLE = 90
SEED_RETRY_ORDER = 91
SEED_SEARCH_ORDER = 92
SLICE_KEY = "20261004"     # 조각 = sha256 키(§3-2 · 난수 아님)

# 3전략 전수 스냅샷(`cand_strategies` 플래그 · 채점 조건 아님 · §2)
CAND_STRATEGIES = ("book_pullback_ma20", "minervini_volume_dryup", "daytrading_3methods_breakout")

# 종결 status(§5-3) — 이 값이 shadow 에 있으면 그 칸은 다시 호출하지 않는다.
ST_OK = "ok"
ST_PARSE = "parse_error"
ST_TIMEOUT = "timeout"
ST_CLI = "cli_error"
ST_LIMIT = "limit_error"
ST_MODEL = "model_mismatch"
ST_SKIP = "skipped_cap"
ST_DROP = "dropped_carry"
RETRYABLE = (ST_PARSE, ST_TIMEOUT, ST_CLI)
