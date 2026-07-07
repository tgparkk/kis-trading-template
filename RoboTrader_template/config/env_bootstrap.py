"""
.env 부트스트랩 (표준 라이브러리 전용)

프로젝트의 어떤 모듈보다 먼저 repo-root ``.env`` 를 읽어 ``os.environ`` 에
주입한다. python-dotenv 미의존(봇 venv 미설치) + 무크래시 원칙.

배경: ``config/constants.py`` 는 import 시점에 ``KIS_DATA_SOURCE`` 를,
``db/connection.py`` 는 런타임에 ``TIMESCALE_DB`` 를 읽는다. main.py 가 이
부트스트랩을 최상단에서 호출해야 ``.env`` 플립이 실제로 발효된다.
"""
import os
from pathlib import Path
from typing import Dict, Optional

# 기본 .env 위치: 이 파일(config/env_bootstrap.py) 기준 repo-root
#   config/ 의 부모 = RoboTrader_template/  → CWD 와 무관하게 견고
_DEFAULT_ENV_PATH = Path(__file__).resolve().parent.parent / ".env"


def _strip_quotes(value: str) -> str:
    """VALUE 양끝을 감싼 동일한 따옴표(' 또는 ")를 한 겹 제거한다."""
    if len(value) >= 2 and value[0] == value[-1] and value[0] in ("'", '"'):
        return value[1:-1]
    return value


def load_env_file(path: Optional[str] = None) -> Dict[str, str]:
    """repo-root ``.env`` 를 파싱해 아직 없는 키만 ``os.environ`` 에 설정한다.

    - ``KEY=VALUE`` 라인 파싱. 빈 줄/``#`` 주석/등호 없는 라인은 무시.
    - ``export KEY=VALUE`` 형식 지원, KEY/VALUE 공백 및 감싼 따옴표 제거.
    - 이미 ``os.environ`` 에 있는 키는 덮어쓰지 않는다(OS/명시 env 우선).
    - 파일이 없거나 읽기 실패 시 예외 없이 ``{}`` 반환(부팅 무크래시).

    Returns:
        실제로 새로 설정한 {키: 값} 딕셔너리(로깅/테스트용).
    """
    env_path = Path(path) if path is not None else _DEFAULT_ENV_PATH
    setted: Dict[str, str] = {}
    try:
        with open(env_path, "r", encoding="utf-8") as f:
            lines = f.readlines()
    except (OSError, UnicodeError):
        # 파일 부재/권한/인코딩 문제 — 조용히 빈 결과
        return setted

    for raw in lines:
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[len("export "):].lstrip()
        if "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        if not key:
            continue
        value = _strip_quotes(value.strip())
        # 이미 존재하는 키는 건드리지 않음
        if key in os.environ:
            continue
        os.environ[key] = value
        setted[key] = value
    return setted


def bootstrap() -> Dict[str, str]:
    """멱등 부트스트랩 엔트리포인트. 여러 번 호출해도 안전하다."""
    return load_env_file()


# 모듈 import 시 1회 자동 실행(main.py 는 명시적으로 bootstrap() 호출).
bootstrap()
