"""
설정 파일 로더 모듈
key.ini 파일에서 설정을 읽어 환경변수로 제공
trading_config.json 파일에서 거래 설정을 로드
"""
import json
import logging
import os
import re
import configparser
from pathlib import Path
from core.models import TradingConfig

logger = logging.getLogger(__name__)


def resolve_instance_id(env: dict) -> str:
    raw = (env.get("KIS_INSTANCE_DIR") or "").strip()
    if not raw:
        return "default"
    base = Path(raw).name.lower()
    norm = re.sub(r"[^a-z0-9_]", "_", base).strip("_")
    if not norm or norm == "default":
        raise ValueError(
            f"KIS_INSTANCE_DIR basename이 예약어 'default'로 정규화됨: {raw!r}. "
            "실전 인스턴스 디렉토리는 'default' 이외의 이름을 쓰세요."
        )
    return norm


def resolve_config_dir(env: dict) -> Path:
    raw = (env.get("KIS_INSTANCE_DIR") or "").strip()
    if raw:
        return Path(raw)
    return Path(__file__).parent


def real_trading_table_name(instance_id: str) -> str:
    if instance_id == "default":
        return "real_trading_records"
    return f"real_trading_{instance_id}"


def token_file_name(instance_id: str) -> str:
    """KIS 토큰 캐시 파일명 — 인스턴스별 분리(같은 cwd서 계좌 토큰 충돌 방지)."""
    if instance_id == "default":
        return "token_info.json"
    return f"token_info_{instance_id}.json"


def log_dir_name(instance_id: str) -> str:
    """로그 디렉토리 — 인스턴스별 분리(같은 cwd서 로그 혼선 방지)."""
    if instance_id == "default":
        return "logs"
    return f"logs/{instance_id}"


INSTANCE_ID = resolve_instance_id(os.environ)
_CONFIG_DIR = resolve_config_dir(os.environ)
# 설정 파일 경로
CONFIG_FILE = _CONFIG_DIR / "key.ini"
TRADING_CONFIG_FILE = _CONFIG_DIR / "trading_config.json"
REAL_TRADING_TABLE = real_trading_table_name(INSTANCE_ID)
TOKEN_FILE = token_file_name(INSTANCE_ID)
LOG_DIR = log_dir_name(INSTANCE_ID)

# ---------------------------------------------------------------------------
# 로드 흔적 (2026-08-04) — `bot/initializer.py` 의 `regime_index` 설정 대조용.
#
# 왜 상수를 그냥 읽지 않는가: 대개는 `TRADING_CONFIG_FILE` 을 읽어도 같은 값이
# 나오지만, 그건 「아무도 이 전역을 재대입하지 않는다」는 가정에 기댄다. 대조
# 검사가 로더와 **다른 파일**을 보면 검사가 거짓 경보나 거짓 안심을 낸다 —
# 검사 자체가 무의미해지는 실패라 가정에 기대면 안 된다. 그래서 로더가 실제로
# 연 경로를 그 자리에서 남긴다.
#
# `LAST_TRADING_CONFIG_LOAD_OK=False` 는 **파일은 있는데 못 읽었다**는 뜻이고,
# 이때 `TradingConfig()` 기본값(= strategies 없음)이 쓰인다. 이 경로가 정확히
# 「파일은 auto 라 선언했는데 인스턴스엔 아무것도 안 닿는」 상황을 만든다.
# ⚠️ 이름의 `LOADED` 는 「성공적으로 읽은」이 아니라 **「가장 최근에 읽으려고 시도한」**
#    이다 — 실패해도 남는다(성공 여부는 `LAST_TRADING_CONFIG_LOAD_OK` 가 말한다).
LAST_LOADED_TRADING_CONFIG_PATH = None   # Optional[Path] — 로더 미실행 시 None
LAST_TRADING_CONFIG_LOAD_OK = False

def load_config():
    """설정 파일을 로드하여 환경변수 설정"""
    if not CONFIG_FILE.exists():
        raise FileNotFoundError(f"설정 파일을 찾을 수 없습니다: {CONFIG_FILE}")
    
    config = configparser.ConfigParser()
    config.read(CONFIG_FILE, encoding='utf-8')
    
    # KIS API 설정
    kis_section = config['KIS']
    
    return {
        'KIS_BASE_URL': kis_section.get('KIS_BASE_URL', '').strip('"'),
        'KIS_APP_KEY': kis_section.get('KIS_APP_KEY', '').strip('"'),
        'KIS_APP_SECRET': kis_section.get('KIS_APP_SECRET', '').strip('"'),
        'KIS_ACCOUNT_NO': kis_section.get('KIS_ACCOUNT_NO', '').strip('"'),
        'KIS_HTS_ID': kis_section.get('KIS_HTS_ID', '').strip('"'),
    }

def load_trading_config() -> TradingConfig:
    """거래 설정 파일을 로드하여 TradingConfig 객체 반환"""
    global LAST_LOADED_TRADING_CONFIG_PATH, LAST_TRADING_CONFIG_LOAD_OK
    # 시도한 경로를 **읽기 전에** 기록한다 — 실패해도 "어느 파일을 보려 했는지"는
    # 남아야 대조 검사가 같은 파일을 가리킬 수 있다.
    LAST_LOADED_TRADING_CONFIG_PATH = TRADING_CONFIG_FILE
    LAST_TRADING_CONFIG_LOAD_OK = False

    if not TRADING_CONFIG_FILE.exists():
        logger.warning("거래 설정 파일을 찾을 수 없습니다: %s", TRADING_CONFIG_FILE)
        logger.warning("기본 설정을 사용합니다.")
        return TradingConfig()

    try:
        with open(TRADING_CONFIG_FILE, 'r', encoding='utf-8') as f:
            json_data = json.load(f)

        config = TradingConfig.from_json(json_data)
        LAST_TRADING_CONFIG_LOAD_OK = True
        return config

    except Exception as e:
        logger.warning("거래 설정 파일 로드 실패: %s", e)
        logger.warning("기본 설정을 사용합니다.")
        return TradingConfig()

# 설정 로드
try:
    _config = load_config()
except (FileNotFoundError, KeyError) as e:
    logger.warning("%s", e)
    logger.warning("key.ini.example을 참고하여 key.ini 파일을 생성해주세요.")
    _config = {
        'KIS_BASE_URL': '',
        'KIS_APP_KEY': '',
        'KIS_APP_SECRET': '',
        'KIS_ACCOUNT_NO': '',
        'KIS_HTS_ID': '',
    }

# 전역 변수로 설정값 제공
KIS_BASE_URL = _config['KIS_BASE_URL']
APP_KEY = _config['KIS_APP_KEY']
SECRET_KEY = _config['KIS_APP_SECRET']
ACCOUNT_NUMBER = _config['KIS_ACCOUNT_NO']
HTS_ID = _config['KIS_HTS_ID']