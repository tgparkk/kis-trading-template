"""
Circuit Breaker 및 네트워크 장애 대응 테스트
"""
import time
import pytest
from unittest.mock import patch, MagicMock, PropertyMock
from api.circuit_breaker import CircuitBreaker, CircuitBreakerConfig, CircuitState, get_circuit_breaker


class TestCircuitBreaker:
    """Circuit Breaker 기본 동작 테스트"""

    def test_initial_state_is_closed(self):
        cb = CircuitBreaker("test")
        assert cb.state == CircuitState.CLOSED
        assert cb.can_execute() is True

    def test_stays_closed_under_threshold(self):
        cb = CircuitBreaker("test", CircuitBreakerConfig(failure_threshold=3))
        cb.record_failure()
        cb.record_failure()
        assert cb.state == CircuitState.CLOSED
        assert cb.can_execute() is True

    def test_opens_at_threshold(self):
        cb = CircuitBreaker("test", CircuitBreakerConfig(failure_threshold=3))
        for _ in range(3):
            cb.record_failure()
        assert cb.state == CircuitState.OPEN
        assert cb.can_execute() is False

    def test_success_resets_failure_count(self):
        cb = CircuitBreaker("test", CircuitBreakerConfig(failure_threshold=3))
        cb.record_failure()
        cb.record_failure()
        cb.record_success()
        cb.record_failure()
        cb.record_failure()
        # Still CLOSED because success reset the count
        assert cb.state == CircuitState.CLOSED

    def test_open_to_half_open_after_timeout(self):
        config = CircuitBreakerConfig(failure_threshold=2, recovery_timeout=0.1)
        cb = CircuitBreaker("test", config)
        cb.record_failure()
        cb.record_failure()
        assert cb.state == CircuitState.OPEN
        
        time.sleep(0.15)
        assert cb.state == CircuitState.HALF_OPEN
        assert cb.can_execute() is True

    def test_half_open_to_closed_on_success(self):
        config = CircuitBreakerConfig(failure_threshold=2, recovery_timeout=0.1, success_threshold=1)
        cb = CircuitBreaker("test", config)
        cb.record_failure()
        cb.record_failure()
        time.sleep(0.15)
        
        assert cb.state == CircuitState.HALF_OPEN
        cb.record_success()
        assert cb.state == CircuitState.CLOSED

    def test_half_open_to_open_on_failure(self):
        config = CircuitBreakerConfig(failure_threshold=2, recovery_timeout=0.1)
        cb = CircuitBreaker("test", config)
        cb.record_failure()
        cb.record_failure()
        time.sleep(0.15)
        
        assert cb.state == CircuitState.HALF_OPEN
        cb.record_failure()
        assert cb.state == CircuitState.OPEN

    def test_half_open_limits_calls(self):
        config = CircuitBreakerConfig(failure_threshold=2, recovery_timeout=0.1, half_open_max_calls=1)
        cb = CircuitBreaker("test", config)
        cb.record_failure()
        cb.record_failure()
        time.sleep(0.15)
        
        assert cb.can_execute() is True
        cb.record_half_open_call()
        assert cb.can_execute() is False

    def test_manual_reset(self):
        cb = CircuitBreaker("test", CircuitBreakerConfig(failure_threshold=2))
        cb.record_failure()
        cb.record_failure()
        assert cb.state == CircuitState.OPEN
        
        cb.reset()
        assert cb.state == CircuitState.CLOSED
        assert cb.can_execute() is True

    def test_stats_tracking(self):
        cb = CircuitBreaker("test", CircuitBreakerConfig(failure_threshold=3))
        cb.record_success()
        cb.record_failure()
        cb.record_blocked()
        
        status = cb.get_status()
        assert status['total_calls'] == 2
        assert status['total_failures'] == 1
        assert status['total_blocked'] == 1

    def test_state_change_callback(self):
        changes = []
        config = CircuitBreakerConfig(failure_threshold=2)
        cb = CircuitBreaker("test", config)
        cb.on_state_change(lambda name, old, new: changes.append((name, old.value, new.value)))
        
        cb.record_failure()
        cb.record_failure()
        
        assert len(changes) == 1
        assert changes[0] == ("test", "CLOSED", "OPEN")

    def test_get_circuit_breaker_singleton(self):
        cb1 = get_circuit_breaker("test_singleton")
        cb2 = get_circuit_breaker("test_singleton")
        assert cb1 is cb2


class TestApiTimeouts:
    """API 타임아웃 설정 테스트"""

    def test_timeout_constants_defined(self):
        from api.kis_auth import API_CONNECT_TIMEOUT, API_READ_TIMEOUT, API_REQUEST_TIMEOUT
        assert API_CONNECT_TIMEOUT > 0
        assert API_READ_TIMEOUT > 0
        assert API_REQUEST_TIMEOUT == (API_CONNECT_TIMEOUT, API_READ_TIMEOUT)

    def test_timeout_in_constants(self):
        from config.constants import API_CONNECT_TIMEOUT, API_READ_TIMEOUT
        assert API_CONNECT_TIMEOUT == 5
        assert API_READ_TIMEOUT == 30


class TestUrlFetchCircuitBreaker:
    """_url_fetch의 Circuit Breaker 통합 테스트"""

    def test_url_fetch_blocked_when_circuit_open(self):
        """Circuit Breaker OPEN 시 _url_fetch가 None 반환"""
        from api.circuit_breaker import CircuitBreaker, CircuitBreakerConfig
        
        # Circuit Breaker를 OPEN 상태로 만들기
        config = CircuitBreakerConfig(failure_threshold=1)
        cb = CircuitBreaker("kis_api", config)
        cb.record_failure()
        assert cb.state == CircuitState.OPEN
        
        with patch('api.circuit_breaker.get_circuit_breaker', return_value=cb):
            from api.kis_auth import _url_fetch
            result = _url_fetch("/test", "TEST001", "", {})
            assert result is None


class TestNotifyApiFailure:
    """장애 알림 테스트"""

    def test_notify_does_not_crash(self):
        """장애 알림 함수가 예외 없이 실행되는지 테스트"""
        from api.kis_auth import _send_failure_telegram
        # config/key.ini가 없거나 텔레그램 설정이 없어도 크래시하면 안됨
        _send_failure_telegram("테스트 장애 알림")
        # 예외 없이 완료되면 성공


class TestGracefulDegradation:
    """Graceful Degradation 테스트"""

    def test_api_manager_handles_failure_gracefully(self):
        """API 실패 시 예외 없이 처리"""
        from api.kis_api_manager import KISAPIManager
        
        mgr = KISAPIManager()
        # 존재하지 않는 종목코드로 호출 - None이거나 결과가 와도 크래시 없음
        result = mgr.get_current_price("XXXXXX")
        # 크래시 없이 완료되면 성공 (실제 API 연결 상태에 따라 결과 다름)

    def test_circuit_breaker_blocks_returns_fast(self):
        """Circuit Breaker OPEN 시 빠른 실패"""
        config = CircuitBreakerConfig(failure_threshold=1, recovery_timeout=999)
        cb = CircuitBreaker("test_fast", config)
        cb.record_failure()
        
        start = time.time()
        assert cb.can_execute() is False
        elapsed = time.time() - start
        
        # 즉시 반환 (1ms 이내)
        assert elapsed < 0.01
