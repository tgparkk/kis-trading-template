"""안전 부트스트랩 — 라이브 모듈을 import 하기 «전에» 이 모듈을 먼저 import 한다.

1. **DB 쓰기 차단(서버 강제)** — `PGOPTIONS=-c default_transaction_read_only=on` 을 넣어
   이 프로세스가 여는 «모든» libpq 연결(라이브 `db.connection` 풀 포함)을 읽기 전용 세션으로 만든다.
2. **라이브 로그 파일을 열지 않는다** — `utils/logger.py` 의 공유 파일 핸들러 슬롯을 NullHandler 로
   선점한다(선례: `../tt_counterfactual/run_ledger.py`). INFO 이하는 끈다.
3. **DB명은 resolver 경유** — 라이브 풀(`db/connection.py`)은 `TIMESCALE_DB` env 를 읽으므로
   `resolve_daily_source_db()` 값을 넣는다. 다른 값이 이미 있으면 중단한다(하드코딩·오접속 방지).
"""
from __future__ import annotations

import logging
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]          # …/RoboTrader_template
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

try:  # cp949 콘솔에서 한글·기호 출력 오류 방지
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")   # type: ignore[attr-defined]
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")   # type: ignore[attr-defined]
except Exception:  # noqa: BLE001
    pass

_RO = "-c default_transaction_read_only=on"
if _RO not in os.environ.get("PGOPTIONS", ""):
    os.environ["PGOPTIONS"] = (os.environ.get("PGOPTIONS", "") + " " + _RO).strip()

import utils.logger as _utils_logger  # noqa: E402

_utils_logger._shared_file_handler = logging.NullHandler()
logging.disable(logging.INFO)

from config.constants import resolve_daily_source_db  # noqa: E402

DB_NAME = resolve_daily_source_db()
_env_db = os.environ.get("TIMESCALE_DB")
if _env_db and _env_db != DB_NAME:
    raise SystemExit(f"TIMESCALE_DB={_env_db!r} 가 resolver 값 {DB_NAME!r} 과 다르다 — 중단")
os.environ["TIMESCALE_DB"] = DB_NAME

LIVE_LOG_DIR_DEFAULT = Path("D:/GIT/kis-trading-template/RoboTrader_template/logs")
