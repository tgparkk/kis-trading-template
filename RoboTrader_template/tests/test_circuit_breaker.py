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
        
        # 다른 테스트가 sys.modules['api']를 mock으로 교체할 수 있으므로
        # sys.modules에서 직접 circuit_breaker 모듈을 참조
        import sys
        cb_mod = sys.modules['api.circuit_breaker']
        with patch.object(cb_mod, 'get_circuit_breaker', return_value=cb):
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


class _FakeClock:
    """차단기 시계 대역 — sleep 없이 결정론적으로 시간을 민다.
    monotonic() 만 전진하고 time()(벽시계)은 거꾸로 간다 → 경과 시간 계산이 벽시계로
    되돌아가면(R5 회귀) 재개방·HALF_OPEN 전환 테스트가 실패한다."""

    def __init__(self):
        self.t = 1000.0

    def monotonic(self):
        return self.t

    def time(self):
        return 1_700_000_000.0 - (self.t - 1000.0)

    def advance(self, sec):
        self.t += sec


class TestHalfOpenStuckRegression:
    """2026-11-13 15:12:44 사건 회귀 — HALF_OPEN 시험 호출이 판정 없이 끝나 영구 고착.

    15:09 KIS 장애 때 OPEN → HALF_OPEN 뒤 시험 호출 2회가 HTTP 500(EGW00302/EGW00300)
    으로 끝났는데 그 경로가 record_success/record_failure 를 부르지 않아, 시험 횟수만
    소진된 HALF_OPEN 으로 프로세스가 끝날 때까지 모든 시세 호출이 막혔다.
    """

    @staticmethod
    def _modules():
        # sys.modules 의 교체본을 쓴다(tests/dryrun/test_abnormal_scenarios.py 누수 대응 —
        # test_live_min_fix_set_20260915.py 의 설명 참고).
        import sys
        import api.circuit_breaker  # noqa: F401
        import api.kis_auth  # noqa: F401
        return sys.modules['api.circuit_breaker'], sys.modules['api.kis_auth']

    def _setup(self, monkeypatch, **cfg):
        """가짜 시계를 건 차단기 생성. 반환 (cb_mod, ka, cb, clock)."""
        cb_mod, ka = self._modules()
        clock = _FakeClock()
        monkeypatch.setattr(cb_mod, 'time', clock)
        cb = cb_mod.CircuitBreaker("kis_api", cb_mod.CircuitBreakerConfig(**cfg))
        return cb_mod, ka, cb, clock

    @staticmethod
    def _to_half_open(cb, cb_mod, clock):
        for _ in range(cb.config.failure_threshold):
            cb.record_failure()
        assert cb.state == cb_mod.CircuitState.OPEN
        clock.advance(cb.config.recovery_timeout)
        assert cb.state == cb_mod.CircuitState.HALF_OPEN

    @staticmethod
    def _resp(status, body=None, raw=None):
        import json
        import requests
        r = requests.Response()
        r.status_code = status
        r._content = raw if raw is not None else json.dumps(body or {}, ensure_ascii=False).encode('utf-8')
        r.encoding = 'utf-8'
        r.headers['content-type'] = 'text/html' if raw is not None else 'application/json'
        return r

    def _fetch(self, ka, cb_mod, cb, responses, tr_id='FHKST01010100'):
        """requests.get 이 responses 를 차례로 돌려주게 하고 _url_fetch 1회 호출 → (결과, 실제 요청 수)."""
        from types import SimpleNamespace
        with patch.object(cb_mod, 'get_circuit_breaker', return_value=cb), \
             patch.object(ka, '_TRENV', SimpleNamespace(my_url='https://kis.test')), \
             patch.object(ka, '_getBaseHeader', return_value={}), \
             patch.object(ka, '_wait_for_api_limit'), \
             patch.object(ka, '_notify_api_failure'), \
             patch.object(ka, '_max_retries', 0), \
             patch.object(ka.requests, 'get', side_effect=list(responses)) as get:
            result = ka._url_fetch('/uapi/test', tr_id, '', {})
        return result, get.call_count

    OK = {"rt_cd": "0", "msg_cd": "MCA00000", "msg1": "정상처리 되었습니다.", "output": {}}
    DOWN = {"rt_cd": "1", "msg_cd": "EGW00302", "msg1": "거래시간이 초과되었습니다.직전 거래를 반드시 확인하세요."}
    RATE = {"rt_cd": "1", "msg_cd": "EGW00201", "msg1": "초당 거래건수를 초과하였습니다."}
    SESSION_FULL = {"rt_cd": "1", "msg_cd": "OPSQ1002", "msg1": "SESSION FULL"}

    # ---- 차단기 자체 방어 ----

    def test_half_open_reopens_trial_window_when_no_verdict(self, monkeypatch):
        """시험 호출 판정이 recovery_timeout 동안 안 오면 시험 창을 다시 연다."""
        cb_mod, _ka, cb, clock = self._setup(monkeypatch)   # 기본값 5/30/2/2
        self._to_half_open(cb, cb_mod, clock)
        assert cb.can_execute() is True    # 시험 1
        assert cb.can_execute() is True    # 시험 2
        assert cb.can_execute() is False   # 소진 · 판정 대기 중엔 막는다(동작 유지)
        clock.advance(29.9)
        assert cb.can_execute() is False   # 아직 recovery_timeout 전
        clock.advance(0.1)
        assert cb.can_execute() is True    # 판정 없이 30초 → 고착되지 않고 재개방
        cb.record_success()
        assert cb.can_execute() is True
        cb.record_success()
        assert cb.state == cb_mod.CircuitState.CLOSED

    def test_closed_transition_resets_half_open_calls(self, monkeypatch):
        cb_mod, _ka, cb, clock = self._setup(monkeypatch)
        self._to_half_open(cb, cb_mod, clock)
        cb.can_execute()
        cb.can_execute()
        cb.record_success()
        cb.record_success()
        assert cb.state == cb_mod.CircuitState.CLOSED
        assert cb._half_open_calls == 0

    def test_state_read_and_decision_are_atomic(self, monkeypatch):
        """R2 경쟁 회귀: 상태를 읽은 뒤 판단하기 전 틈에 다른 스레드가 OPEN 으로 바꾸면
        옛 HALF_OPEN 값으로 허용해 버렸다. 그 틈은 락 안이어야 한다 — 다른 스레드의
        record_failure 는 판단이 끝날 때까지 기다려야 한다."""
        import threading
        cb_mod, _ka, _cb, clock = self._setup(monkeypatch)
        read_done, go = threading.Event(), threading.Event()

        class GapBreaker(cb_mod.CircuitBreaker):
            hook = True

            @property
            def state(self):
                s = cb_mod.CircuitBreaker.state.fget(self)
                if self.hook and threading.current_thread().name == 'trial':
                    self.hook = False
                    read_done.set()
                    go.wait(5)   # 상태 읽기 ~ 판단 사이의 틈
                return s

        cb = GapBreaker("kis_api")
        self._to_half_open(cb, cb_mod, clock)
        result = {}
        trial = threading.Thread(target=lambda: result.setdefault('ok', cb.can_execute()), name='trial')
        trial.start()
        assert read_done.wait(5)
        failer = threading.Thread(target=cb.record_failure, name='failer')
        failer.start()
        failer.join(0.3)
        blocked_in_gap = failer.is_alive()
        go.set()
        trial.join(5)
        failer.join(5)
        assert blocked_in_gap, "상태 읽기와 판단 사이에 다른 스레드가 상태를 바꿨다(락 밖 읽기)"
        assert result['ok'] is True                       # 판단 시점엔 진짜 HALF_OPEN 이었다
        assert cb.state == cb_mod.CircuitState.OPEN       # 그 뒤 실패로 OPEN

    # ---- 사건 재현 (_url_fetch 경유) ----

    def test_half_open_trials_http500_egw00302_then_recovers(self, monkeypatch):
        """사건 재현: HALF_OPEN 시험이 HTTP 500 EGW00302 → KIS 복구 뒤 풀려야 한다.
        수정 후 흐름 = 첫 시험 500 → failure 기록 → 즉시 OPEN → 두 번째 호출은 차단 →
        recovery_timeout 뒤 HALF_OPEN → 200 두 번 → CLOSED."""
        cb_mod, ka, cb, clock = self._setup(monkeypatch)
        self._to_half_open(cb, cb_mod, clock)

        result, calls = self._fetch(ka, cb_mod, cb, [self._resp(500, self.DOWN)])
        assert result is None and calls == 1
        assert cb.state == cb_mod.CircuitState.OPEN        # 첫 시험 500 → OPEN
        result, calls = self._fetch(ka, cb_mod, cb, [self._resp(500, self.DOWN)])
        assert result is None and calls == 0               # 두 번째는 차단(요청 안 나감)

        clock.advance(cb.config.recovery_timeout)          # 15:14 KIS 복구
        results = [self._fetch(ka, cb_mod, cb, [self._resp(200, self.OK)])[0] for _ in range(3)]
        assert cb.state == cb_mod.CircuitState.CLOSED
        assert all(r is not None for r in results)

    @pytest.mark.parametrize("kind", ["rate_limit_500", "http404", "biz_200"])
    def test_no_verdict_trials_unstick_by_breaker_alone(self, monkeypatch, kind):
        """판정 없이 끝나는 시험(rate-limit 소진·404·200+비즈니스 오류)으로 시험 횟수가 소진돼도
        차단기 자동 재개방만으로 풀린다."""
        cb_mod, ka, cb, clock = self._setup(monkeypatch)
        self._to_half_open(cb, cb_mod, clock)
        neutral = {"rate_limit_500": lambda: self._resp(500, self.RATE),
                   "http404": lambda: self._resp(404, {}),
                   "biz_200": lambda: self._resp(200, self.SESSION_FULL)}[kind]
        for _ in range(cb.config.half_open_max_calls):
            _result, calls = self._fetch(ka, cb_mod, cb, [neutral()])
            assert calls == 1
        assert cb.state == cb_mod.CircuitState.HALF_OPEN
        _result, calls = self._fetch(ka, cb_mod, cb, [neutral()])
        assert calls == 0                                   # 소진 · 판정 대기
        clock.advance(cb.config.recovery_timeout)
        for _ in range(cb.config.success_threshold):
            result, calls = self._fetch(ka, cb_mod, cb, [self._resp(200, self.OK)])
            assert result is not None and calls == 1
        assert cb.state == cb_mod.CircuitState.CLOSED

    # ---- 경로별 기록 ----

    def test_http500_server_error_counts_as_failure(self, monkeypatch):
        """서버 장애성 HTTP 500(rate-limit 아님)은 실패로 센다 → threshold 에서 OPEN."""
        cb_mod, ka, cb, _clock = self._setup(monkeypatch, failure_threshold=2)
        down = {"rt_cd": "1", "msg_cd": "EGW00300", "msg1": "Gateway 라우팅 오류가 발생했습니다."}
        for _ in range(2):
            self._fetch(ka, cb_mod, cb, [self._resp(500, down)])
        assert cb.state == cb_mod.CircuitState.OPEN

    def test_http500_rate_limit_does_not_open(self, monkeypatch):
        """rate-limit(EGW00201)은 장중에 흔하다 — 몇 번이 와도 차단기를 열지 않는다(동작 유지)."""
        cb_mod, ka, cb, _clock = self._setup(monkeypatch, failure_threshold=2)
        for _ in range(5):
            result, _calls = self._fetch(ka, cb_mod, cb, [self._resp(500, self.RATE)])
            assert result is None
        assert cb.state == cb_mod.CircuitState.CLOSED

    def test_http404_does_not_open(self, monkeypatch):
        """404(엔드포인트 미지원)는 조용히 처리 — 차단기를 열지 않는다(동작 유지)."""
        cb_mod, ka, cb, _clock = self._setup(monkeypatch, failure_threshold=2)
        for _ in range(5):
            result, _calls = self._fetch(ka, cb_mod, cb, [self._resp(404, {})])
            assert result is None
        assert cb.state == cb_mod.CircuitState.CLOSED

    @pytest.mark.parametrize("kind", ["OPSQ1002", "html_body"])
    def test_http200_business_error_does_not_close_half_open(self, monkeypatch, kind):
        """200+OPSQ1002(SESSION FULL)·200+HTML 본문(msg_cd='ERROR')은 서버 장애성일 수 있다 →
        판정 보류: HALF_OPEN 을 닫지 않는다."""
        cb_mod, ka, cb, clock = self._setup(monkeypatch)
        self._to_half_open(cb, cb_mod, clock)
        make = (lambda: self._resp(200, self.SESSION_FULL)) if kind == "OPSQ1002" \
            else (lambda: self._resp(200, raw=b"<html><body>maintenance</body></html>"))
        for _ in range(cb.config.half_open_max_calls):
            result, _calls = self._fetch(ka, cb_mod, cb, [make()])
            assert result is not None                       # 응답 객체는 그대로 반환(동작 유지)
        if kind == "html_body":
            assert result.getErrorCode() == 'ERROR'
        assert cb.state == cb_mod.CircuitState.HALF_OPEN

    def test_http200_business_error_does_not_reset_failure_count(self, monkeypatch):
        """CLOSED 에서 200+비즈니스 오류가 연속 실패 카운트를 0 으로 되돌리지 않는다."""
        cb_mod, ka, cb, _clock = self._setup(monkeypatch, failure_threshold=2)
        self._fetch(ka, cb_mod, cb, [self._resp(500, self.DOWN)])
        self._fetch(ka, cb_mod, cb, [self._resp(200, self.SESSION_FULL)])
        self._fetch(ka, cb_mod, cb, [self._resp(500, self.DOWN)])
        assert cb.state == cb_mod.CircuitState.OPEN

    # ---- 우회 TR (R3) ----

    def test_bypass_tr_does_not_consume_half_open_trials(self, monkeypatch):
        """HALF_OPEN 에서 우회 TR(현금매도 등)은 시험 횟수를 쓰지 않는다."""
        cb_mod, ka, cb, clock = self._setup(monkeypatch)
        self._to_half_open(cb, cb_mod, clock)
        for tr_id in ("TTTC0011U", "TTTC0013U", "TTTC8036R"):
            _result, calls = self._fetch(ka, cb_mod, cb, [self._resp(404, {})], tr_id=tr_id)
            assert calls == 1, tr_id
        assert cb._half_open_calls == 0
        assert cb.can_execute() is True and cb.can_execute() is True   # 시세 시험 2회 그대로 남음

    def test_open_sell_passes_buy_blocked(self, monkeypatch):
        """OPEN 에서 현금매도(TTTC0011U)는 통과 · 현금매수(TTTC0012U)는 차단(우회 추가 금지)."""
        cb_mod, ka, cb, _clock = self._setup(monkeypatch, failure_threshold=1)
        cb.record_failure()
        assert cb.state == cb_mod.CircuitState.OPEN
        _result, sell_calls = self._fetch(ka, cb_mod, cb, [self._resp(404, {})], tr_id="TTTC0011U")
        result, buy_calls = self._fetch(ka, cb_mod, cb, [self._resp(200, self.OK)], tr_id="TTTC0012U")
        assert sell_calls == 1
        assert buy_calls == 0 and result is None
        assert cb.stats['total_blocked'] == 1

    # ---- 로그 ----

    def test_blocked_log_shows_actual_state(self, monkeypatch):
        """차단 로그는 기존 문구(「Circuit Breaker OPEN - API 호출 차단」)를 유지하고 실제 상태를 덧붙인다."""
        cb_mod, ka, cb, clock = self._setup(monkeypatch)
        self._to_half_open(cb, cb_mod, clock)
        cb.can_execute()
        cb.can_execute()
        with patch.object(ka.logger, 'warning') as warn:
            result, calls = self._fetch(ka, cb_mod, cb, [])
        assert result is None and calls == 0
        msg = warn.call_args[0][0]
        assert "Circuit Breaker OPEN - API 호출 차단: FHKST01010100" in msg
        assert "state=HALF_OPEN" in msg
