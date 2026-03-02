"""
로깅 시스템 설정

싱글톤 핸들러 패턴:
- 모든 로거가 동일한 RotatingFileHandler/StreamHandler를 공유
- Windows에서 여러 핸들러가 동일 파일을 rotate할 때 발생하는 PermissionError 방지
- 파일당 최대 10MB, 최대 7개 백업 유지
"""
import logging
import logging.handlers
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional, Union
import time

try:
    # 선택적: 한국시간 변환 지원
    from utils.korean_time import KST
except Exception:
    KST = None

# ============================================================================
# 싱글톤 공유 핸들러 (모듈 레벨)
# ============================================================================
_shared_file_handler: Optional[logging.Handler] = None
_shared_console_handler: Optional[logging.Handler] = None
_shared_file_path: Optional[str] = None  # 현재 공유 핸들러의 파일 경로 추적


def _get_shared_handlers(use_kst: bool = False):
    """공유 핸들러 반환 (없으면 생성)

    동일한 RotatingFileHandler와 StreamHandler를 모든 로거에서 공유하여
    Windows에서 파일 rotate 시 PermissionError를 방지합니다.
    """
    global _shared_file_handler, _shared_console_handler, _shared_file_path

    # 포맷터 (공유)
    formatter = logging.Formatter(
        '%(asctime)s | %(name)s | %(levelname)s | %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )

    # KST 타임스탬프 변환기
    if use_kst and KST is not None:
        def _kst_converter(secs: float):
            try:
                return datetime.fromtimestamp(secs, KST).timetuple()
            except Exception:
                return time.localtime(secs)
        formatter.converter = _kst_converter  # type: ignore[attr-defined]

    # 파일 핸들러 (싱글톤)
    if _shared_file_handler is None:
        log_dir = Path("logs")
        log_dir.mkdir(exist_ok=True)
        today = datetime.now().strftime("%Y%m%d")
        log_file = log_dir / f"trading_{today}.log"

        _shared_file_handler = logging.handlers.RotatingFileHandler(
            log_file, maxBytes=10*1024*1024, backupCount=7, encoding='utf-8'
        )
        _shared_file_handler.setFormatter(formatter)
        _shared_file_path = str(log_file)

    # 콘솔 핸들러 (싱글톤)
    if _shared_console_handler is None:
        _shared_console_handler = logging.StreamHandler(sys.stdout)
        _shared_console_handler.setFormatter(formatter)

    return _shared_file_handler, _shared_console_handler


# 환경변수로 로그 레벨 오버라이드 가능 (예: LOG_LEVEL=DEBUG)
_default_level = getattr(logging, os.environ.get('LOG_LEVEL', 'INFO').upper(), logging.INFO)


def setup_logger(
    name: str,
    level: int = _default_level,
    file_path: Optional[Union[str, Path]] = None,
    use_kst: bool = False,
):
    """로거 설정

    Parameters:
    - name: 로거 이름
    - level: 로그 레벨
    - file_path: 지정 시 해당 경로로 별도 파일 핸들러 추가, 미지정 시 공유 핸들러 사용
    - use_kst: 로그 타임스탬프를 한국시간(KST)으로 변환해 표시
    """
    # 로거 생성/초기화
    logger = logging.getLogger(name)
    logger.setLevel(level)
    logger.propagate = False

    # 이미 핸들러가 있으면 중복 추가 안 함 (싱글톤 핸들러 재사용)
    if logger.handlers:
        return logger

    # 공유 핸들러 가져오기
    file_handler, console_handler = _get_shared_handlers(use_kst)
    logger.addHandler(file_handler)
    logger.addHandler(console_handler)

    # file_path가 별도로 지정된 경우, 추가 파일 핸들러 생성
    if file_path is not None:
        extra_log_file = Path(file_path)
        if not extra_log_file.parent.exists():
            extra_log_file.parent.mkdir(parents=True, exist_ok=True)

        formatter = logging.Formatter(
            '%(asctime)s | %(name)s | %(levelname)s | %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )
        if use_kst and KST is not None:
            def _kst_converter(secs: float):
                try:
                    return datetime.fromtimestamp(secs, KST).timetuple()
                except Exception:
                    return time.localtime(secs)
            formatter.converter = _kst_converter  # type: ignore[attr-defined]

        extra_handler = logging.handlers.RotatingFileHandler(
            extra_log_file, maxBytes=10*1024*1024, backupCount=7, encoding='utf-8'
        )
        extra_handler.setFormatter(formatter)
        logger.addHandler(extra_handler)

    return logger