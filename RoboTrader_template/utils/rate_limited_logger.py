"""
Rate-Limited Logger Wrapper

동일한 에러/경고 메시지의 반복 로깅을 제한하여 로그 폭발을 방지합니다.

배경:
  2026-02-27, "가상 매도 기록 저장 실패: unsupported operand type(s) for -:
  'float' and 'decimal.Decimal'" 에러가 4시간 동안 21,780회 기록되어
  237MB 로그 파일을 생성. RotatingFileHandler는 메인 로그 크기를 제한하지만,
  동일 메시지의 폭발적 반복은 방지하지 못함.

사용법:
  import logging
  from utils.rate_limited_logger import RateLimitedLogger

  logger = RateLimitedLogger(logging.getLogger(__name__))
  logger.error("some error")  # 기존 로깅 호출과 동일하게 사용
"""
import logging
import threading
import time
from typing import Dict, Tuple


# 메시지 키 생성 시 사용할 최대 문자 수
_MESSAGE_KEY_MAX_LENGTH = 100


class RateLimitedLogger:
    """동일 에러 메시지 반복 제한 로거

    ERROR, WARNING 레벨의 동일 메시지가 분당 max_per_minute 회를 초과하면
    추가 로그를 억제하고, summary_interval_seconds 마다 억제 요약을 출력합니다.

    INFO, DEBUG 레벨은 제한 없이 통과합니다.
    """

    def __init__(self, logger: logging.Logger,
                 max_per_minute: int = 5,
                 summary_interval_seconds: int = 60):
        """
        Args:
            logger: 실제 로깅을 위임할 logging.Logger 인스턴스
            max_per_minute: 분당 동일 메시지 최대 허용 횟수 (기본 5)
            summary_interval_seconds: 억제 요약 로그 출력 간격 (초, 기본 60)
        """
        self._logger = logger
        self._max_per_minute = max_per_minute
        self._summary_interval = summary_interval_seconds

        # 메시지 키 -> (count, first_seen_time, suppressed_count)
        self._counters: Dict[str, Tuple[int, float, int]] = {}

        # 마지막 요약 출력 시각
        self._last_summary_time: float = time.time()

        # 스레드 안전성
        self._lock = threading.Lock()

    @staticmethod
    def _make_key(message: str) -> str:
        """메시지에서 중복 판별 키를 생성 (앞 100자)"""
        return message[:_MESSAGE_KEY_MAX_LENGTH]

    def _should_log(self, message: str) -> bool:
        """메시지를 로깅해야 하는지 판별하고 카운터를 갱신한다.

        Returns:
            True이면 실제 로그 출력, False이면 억제
        """
        now = time.time()
        key = self._make_key(message)

        with self._lock:
            # 요약 출력 체크
            self._maybe_emit_summary(now)

            if key in self._counters:
                count, first_seen, suppressed = self._counters[key]
                elapsed = now - first_seen

                if elapsed >= 60.0:
                    # 1분 경과 -> 카운터 리셋
                    self._counters[key] = (1, now, 0)
                    return True

                # 같은 1분 윈도우 내
                count += 1
                if count <= self._max_per_minute:
                    self._counters[key] = (count, first_seen, suppressed)
                    return True
                else:
                    # 한도 초과 -> 억제
                    self._counters[key] = (count, first_seen, suppressed + 1)
                    return False
            else:
                # 새 메시지
                self._counters[key] = (1, now, 0)
                return True

    def _maybe_emit_summary(self, now: float) -> None:
        """억제된 메시지가 있으면 요약 로그를 출력하고 카운터를 정리한다.

        _lock 보유 상태에서 호출됨.
        """
        if now - self._last_summary_time < self._summary_interval:
            return

        self._last_summary_time = now

        # 억제된 항목 수집
        keys_to_remove = []
        for key, (count, first_seen, suppressed) in self._counters.items():
            if suppressed > 0:
                preview = key[:50]
                self._logger.warning(
                    f"중복 로그 요약: '{preview}' "
                    f"{suppressed}회 추가 발생 (총 {count}회)"
                )

            # 1분 이상 지난 카운터는 정리
            if now - first_seen >= 60.0:
                keys_to_remove.append(key)

        for key in keys_to_remove:
            del self._counters[key]

    # =========================================================================
    # 표준 로깅 메서드
    # =========================================================================

    def debug(self, msg: str, *args, **kwargs) -> None:
        """DEBUG 레벨 로그 (rate limit 적용 안 함)"""
        self._logger.debug(msg, *args, **kwargs)

    def info(self, msg: str, *args, **kwargs) -> None:
        """INFO 레벨 로그 (rate limit 적용 안 함)"""
        self._logger.info(msg, *args, **kwargs)

    def warning(self, msg: str, *args, **kwargs) -> None:
        """WARNING 레벨 로그 (rate limit 적용)"""
        if self._should_log(str(msg)):
            self._logger.warning(msg, *args, **kwargs)

    def error(self, msg: str, *args, **kwargs) -> None:
        """ERROR 레벨 로그 (rate limit 적용)"""
        if self._should_log(str(msg)):
            self._logger.error(msg, *args, **kwargs)

    def critical(self, msg: str, *args, **kwargs) -> None:
        """CRITICAL 레벨 로그 (rate limit 적용)"""
        if self._should_log(str(msg)):
            self._logger.critical(msg, *args, **kwargs)

    # =========================================================================
    # logging.Logger 호환 속성 위임
    # =========================================================================

    @property
    def name(self) -> str:
        return self._logger.name

    @property
    def level(self) -> int:
        return self._logger.level

    @property
    def handlers(self):
        return self._logger.handlers

    def setLevel(self, level) -> None:
        self._logger.setLevel(level)

    def isEnabledFor(self, level: int) -> bool:
        return self._logger.isEnabledFor(level)

    def getEffectiveLevel(self) -> int:
        return self._logger.getEffectiveLevel()

    def addHandler(self, handler) -> None:
        self._logger.addHandler(handler)

    def removeHandler(self, handler) -> None:
        self._logger.removeHandler(handler)
