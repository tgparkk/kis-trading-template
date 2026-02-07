"""
비동기 유틸리티 모듈
- ThreadPoolExecutor 호출에 타임아웃 적용
"""
import asyncio
from utils.logger import setup_logger

logger = setup_logger(__name__)


async def run_with_timeout(executor, func, *args, timeout_seconds=30, default=None):
    """
    ThreadPoolExecutor 호출에 타임아웃을 적용하는 래퍼

    Args:
        executor: ThreadPoolExecutor
        func: 동기 함수
        *args: 함수 인자
        timeout_seconds: 타임아웃 (초)
        default: 타임아웃 시 반환값

    Returns:
        func 결과 또는 타임아웃 시 default
    """
    loop = asyncio.get_event_loop()
    try:
        result = await asyncio.wait_for(
            loop.run_in_executor(executor, func, *args),
            timeout=timeout_seconds
        )
        return result
    except asyncio.TimeoutError:
        logger.warning(f"API 호출 타임아웃 ({timeout_seconds}초): {func.__name__}({args[:2]}...)")
        return default
