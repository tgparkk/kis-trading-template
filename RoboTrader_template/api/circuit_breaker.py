"""
Circuit Breaker 패턴 구현 - KIS API 장애 대응

상태:
- CLOSED: 정상 동작, API 호출 허용
- OPEN: 장애 감지, API 호출 차단 (빠른 실패)
- HALF_OPEN: 복구 시도 중, 제한적 API 호출 허용
"""
import time
import threading
from enum import Enum
from typing import Optional, Callable, Any
from dataclasses import dataclass, field
from utils.logger import setup_logger

logger = setup_logger(__name__)


class CircuitState(Enum):
    CLOSED = "CLOSED"
    OPEN = "OPEN"
    HALF_OPEN = "HALF_OPEN"


@dataclass
class CircuitBreakerConfig:
    """Circuit Breaker 설정"""
    failure_threshold: int = 5          # OPEN 전환까지 연속 실패 횟수
    recovery_timeout: float = 30.0      # OPEN → HALF_OPEN 전환 대기 시간(초)
    half_open_max_calls: int = 2        # HALF_OPEN에서 허용할 테스트 호출 수
    success_threshold: int = 2          # HALF_OPEN → CLOSED 전환까지 연속 성공 횟수


class CircuitBreaker:
    """Circuit Breaker 구현"""

    def __init__(self, name: str = "kis_api", config: Optional[CircuitBreakerConfig] = None):
        self.name = name
        self.config = config or CircuitBreakerConfig()
        self._state = CircuitState.CLOSED
        self._failure_count = 0
        self._success_count = 0
        self._last_failure_time: float = 0
        self._half_open_calls = 0
        self._lock = threading.Lock()
        self._on_state_change_cb: Optional[Callable] = None

        # 통계
        self.stats = {
            'total_calls': 0,
            'total_failures': 0,
            'total_blocked': 0,
            'circuit_open_count': 0,
            'last_state_change': None,
        }

    @property
    def state(self) -> CircuitState:
        with self._lock:
            if self._state == CircuitState.OPEN:
                # 복구 타임아웃 경과 시 HALF_OPEN으로 전환
                if time.time() - self._last_failure_time >= self.config.recovery_timeout:
                    self._transition_to(CircuitState.HALF_OPEN)
            return self._state

    def on_state_change(self, callback: Callable[[str, CircuitState, CircuitState], None]):
        """상태 변경 콜백 등록 (name, old_state, new_state)"""
        self._on_state_change_cb = callback

    def _transition_to(self, new_state: CircuitState):
        """상태 전환 (lock 내부에서 호출)"""
        old_state = self._state
        if old_state == new_state:
            return

        self._state = new_state
        self.stats['last_state_change'] = time.time()

        if new_state == CircuitState.HALF_OPEN:
            self._half_open_calls = 0
            self._success_count = 0
        elif new_state == CircuitState.CLOSED:
            self._failure_count = 0
            self._success_count = 0
        elif new_state == CircuitState.OPEN:
            self.stats['circuit_open_count'] += 1

        logger.warning(f"🔌 CircuitBreaker[{self.name}] {old_state.value} → {new_state.value}")

        if self._on_state_change_cb:
            try:
                self._on_state_change_cb(self.name, old_state, new_state)
            except Exception as e:
                logger.error(f"CircuitBreaker 콜백 오류: {e}")

    def can_execute(self) -> bool:
        """현재 API 호출 가능 여부"""
        current_state = self.state  # 이 호출로 OPEN→HALF_OPEN 전환도 체크
        with self._lock:
            if current_state == CircuitState.CLOSED:
                return True
            elif current_state == CircuitState.HALF_OPEN:
                return self._half_open_calls < self.config.half_open_max_calls
            else:  # OPEN
                return False

    def record_success(self):
        """API 호출 성공 기록"""
        with self._lock:
            self.stats['total_calls'] += 1
            self._failure_count = 0

            if self._state == CircuitState.HALF_OPEN:
                self._success_count += 1
                if self._success_count >= self.config.success_threshold:
                    self._transition_to(CircuitState.CLOSED)

    def record_failure(self):
        """API 호출 실패 기록"""
        with self._lock:
            self.stats['total_calls'] += 1
            self.stats['total_failures'] += 1
            self._failure_count += 1
            self._last_failure_time = time.time()

            if self._state == CircuitState.HALF_OPEN:
                # HALF_OPEN에서 실패 → 즉시 OPEN으로
                self._transition_to(CircuitState.OPEN)
            elif self._state == CircuitState.CLOSED:
                if self._failure_count >= self.config.failure_threshold:
                    self._transition_to(CircuitState.OPEN)

    def record_blocked(self):
        """차단된 호출 기록"""
        with self._lock:
            self.stats['total_blocked'] += 1

    def record_half_open_call(self):
        """HALF_OPEN 테스트 호출 기록"""
        with self._lock:
            self._half_open_calls += 1

    def reset(self):
        """수동 리셋"""
        with self._lock:
            self._transition_to(CircuitState.CLOSED)
            self._failure_count = 0
            self._success_count = 0
            logger.info(f"🔌 CircuitBreaker[{self.name}] 수동 리셋 완료")

    def get_status(self) -> dict:
        """현재 상태 반환"""
        return {
            'name': self.name,
            'state': self.state.value,
            'failure_count': self._failure_count,
            'success_count': self._success_count,
            **self.stats
        }


# 싱글턴 인스턴스
_default_breaker: Optional[CircuitBreaker] = None
_breaker_lock = threading.Lock()


def get_circuit_breaker(name: str = "kis_api") -> CircuitBreaker:
    """기본 Circuit Breaker 인스턴스 반환"""
    global _default_breaker
    with _breaker_lock:
        if _default_breaker is None or _default_breaker.name != name:
            _default_breaker = CircuitBreaker(name=name)
        return _default_breaker
