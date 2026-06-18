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


INSTANCE_ID = resolve_instance_id(os.environ)
_CONFIG_DIR = resolve_config_dir(os.environ)
# 설정 파일 경로
CONFIG_FILE = _CONFIG_DIR / "key.ini"
TRADING_CONFIG_FILE = _CONFIG_DIR / "trading_config.json"
REAL_TRADING_TABLE = real_trading_table_name(INSTANCE_ID)

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
    if not TRADING_CONFIG_FILE.exists():
        logger.warning("거래 설정 파일을 찾을 수 없습니다: %s", TRADING_CONFIG_FILE)
        logger.warning("기본 설정을 사용합니다.")
        return TradingConfig()
    
    try:
        with open(TRADING_CONFIG_FILE, 'r', encoding='utf-8') as f:
            json_data = json.load(f)
        
        return TradingConfig.from_json(json_data)
        
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