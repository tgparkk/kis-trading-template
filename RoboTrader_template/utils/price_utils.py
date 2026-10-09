"""가격 및 시스템 유틸리티

이 모듈은 main.py에서 분리된 유틸리티 함수들을 포함합니다.
- 호가 단위 반올림
- 중복 프로세스 실행 방지
- 설정 파일 로드
"""
import math
import os
import sys
from pathlib import Path
from utils.logger import setup_logger
from config.settings import load_trading_config, TradingConfig

logger = setup_logger(__name__)


def _get_tick_size(price: float) -> int:
    """KRX 주식 호가가격단위 — 2023-01-25 개편 표(유가증권·코스닥 통일).

    2,000 미만 1 · 5,000 미만 5 · 20,000 미만 10 · 50,000 미만 50 · 200,000 미만 100 ·
    500,000 미만 500 · 이상 1,000. 출처: 한국거래소 「호가가격단위(Tick Size)」 안내 regulation.krx.co.kr/contents/RGL/03/03010100/RGL03010100T3.jsp (2026-10-09 확인).
    framework/utils.get_tick_size 와 같은 표여야 한다(tests/test_tick_size_krx_2023.py 가 고정).
    ETF·ETN(2,000 미만 1 · 이상 5)은 따로 두지 않는다 — 이 표의 값은 늘 그 단위의 배수라 정렬 위반이 없다.
    """
    if price < 2000:
        return 1
    elif price < 5000:
        return 5
    elif price < 20000:
        return 10
    elif price < 50000:
        return 50
    elif price < 200000:
        return 100
    elif price < 500000:
        return 500
    else:
        return 1000


def round_to_tick(price: float) -> float:
    """
    KRX 정확한 호가단위에 맞게 반올림

    Args:
        price: 원본 가격

    Returns:
        호가 단위로 반올림된 가격

    Examples:
        >>> round_to_tick(54321)
        54300  # 5만원 이상은 100원 단위
    """
    if price <= 0:
        return 0.0
    tick = _get_tick_size(price)
    return float(int(math.floor(price / tick + 0.5)) * tick)


def check_duplicate_process(pid_file_path: str = 'robotrader.pid'):
    """
    프로세스 중복 실행 방지

    Args:
        pid_file_path: PID 파일 경로

    Raises:
        SystemExit: 중복 실행 시 프로그램 종료
    """
    try:
        pid_file = Path(pid_file_path)

        if pid_file.exists():
            # 기존 PID 파일 읽기
            existing_pid = int(pid_file.read_text().strip())

            # Windows에서 프로세스 존재 여부 확인
            try:
                import psutil
                if psutil.pid_exists(existing_pid):
                    process = psutil.Process(existing_pid)
                    if 'python' in process.name().lower() and 'main.py' in ' '.join(process.cmdline()):
                        logger.error(f"이미 봇이 실행 중입니다 (PID: {existing_pid})")
                        print(f"오류: 이미 거래 봇이 실행 중입니다 (PID: {existing_pid})")
                        print("기존 프로세스를 먼저 종료해주세요.")
                        sys.exit(1)
            except ImportError:
                # psutil이 없는 경우 간단한 체크
                logger.warning("psutil 모듈이 없어 정확한 중복 실행 체크를 할 수 없습니다")
            except Exception:
                # 기존 PID가 존재하지 않으면 PID 파일 삭제
                pid_file.unlink(missing_ok=True)

        # 현재 프로세스 PID 저장
        current_pid = os.getpid()
        pid_file.write_text(str(current_pid))
        logger.info(f"프로세스 PID 등록: {current_pid}")

    except Exception as e:
        logger.warning(f"중복 실행 체크 중 오류: {e}")


def load_config() -> TradingConfig:
    """
    거래 설정 로드

    Returns:
        TradingConfig 객체

    Examples:
        >>> config = load_config()
        >>> print(len(config.data_collection.candidate_stocks))
        30
    """
    config = load_trading_config()
    logger.info(f"거래 설정 로드 완료: 후보종목 {len(config.data_collection.candidate_stocks)}개")
    return config
