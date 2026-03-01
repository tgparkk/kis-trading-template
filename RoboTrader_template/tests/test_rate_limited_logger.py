"""
RateLimitedLogger 단위 테스트

동일 에러/경고 메시지의 반복 로깅 제한 기능을 검증합니다.
"""
import logging
import time
from unittest.mock import MagicMock, call, patch

import pytest

from utils.rate_limited_logger import RateLimitedLogger


@pytest.fixture
def mock_logger():
    """테스트용 mock logger 생성"""
    logger = MagicMock(spec=logging.Logger)
    logger.name = "test_logger"
    logger.level = logging.DEBUG
    return logger


@pytest.fixture
def rate_logger(mock_logger):
    """기본 설정의 RateLimitedLogger 생성 (분당 5회, 요약 60초)"""
    return RateLimitedLogger(mock_logger, max_per_minute=5, summary_interval_seconds=60)


class TestNormalLogging:
    """정상 범위 내 로깅 테스트"""

    def test_normal_logging_passes_through(self, rate_logger, mock_logger):
        """한도 이내의 메시지는 정상적으로 로깅된다"""
        # 5회까지는 모두 통과해야 함
        for i in range(5):
            rate_logger.error(f"에러 발생: 테스트 #{i}")

        # 서로 다른 메시지이므로 5회 모두 호출
        assert mock_logger.error.call_count == 5

    def test_same_message_within_limit(self, rate_logger, mock_logger):
        """동일 메시지도 한도 이내면 정상 로깅"""
        msg = "동일 에러 메시지"
        for _ in range(5):
            rate_logger.error(msg)

        assert mock_logger.error.call_count == 5


class TestDuplicateSuppression:
    """중복 메시지 억제 테스트"""

    def test_duplicate_suppressed_after_limit(self, rate_logger, mock_logger):
        """6번째 동일 메시지는 억제된다"""
        msg = "가상 매도 기록 저장 실패: unsupported operand type"

        for _ in range(10):
            rate_logger.error(msg)

        # 5회만 실제 로깅, 나머지 5회 억제
        assert mock_logger.error.call_count == 5

    def test_different_messages_not_suppressed(self, rate_logger, mock_logger):
        """서로 다른 메시지는 각각 독립적으로 한도가 적용된다"""
        for i in range(5):
            rate_logger.error(f"에러 A: 종목 {i}")
            rate_logger.error(f"에러 B: 종목 {i}")

        # 각 메시지가 5회씩 = 총 10회 (모두 한도 이내)
        assert mock_logger.error.call_count == 10

    def test_different_messages_independent_limits(self, rate_logger, mock_logger):
        """한 메시지가 한도에 도달해도 다른 메시지는 영향받지 않는다"""
        msg_a = "에러 A: 동일 메시지"
        msg_b = "에러 B: 다른 메시지"

        # A를 7회 (5회 통과, 2회 억제)
        for _ in range(7):
            rate_logger.error(msg_a)

        # B를 3회 (모두 통과)
        for _ in range(3):
            rate_logger.error(msg_b)

        # A: 5회 + B: 3회 = 8회
        assert mock_logger.error.call_count == 8


class TestInfoDebugPassthrough:
    """INFO, DEBUG 레벨 무제한 통과 테스트"""

    def test_info_debug_not_rate_limited(self, rate_logger, mock_logger):
        """INFO와 DEBUG 메시지는 rate limit이 적용되지 않는다"""
        msg_info = "정보 메시지 반복"
        msg_debug = "디버그 메시지 반복"

        for _ in range(20):
            rate_logger.info(msg_info)
            rate_logger.debug(msg_debug)

        assert mock_logger.info.call_count == 20
        assert mock_logger.debug.call_count == 20

    def test_info_not_counted_for_error_limit(self, rate_logger, mock_logger):
        """INFO 호출은 ERROR 카운터에 영향을 주지 않는다"""
        msg = "같은 텍스트"

        # INFO 20회 -> 카운터에 영향 없음
        for _ in range(20):
            rate_logger.info(msg)

        # ERROR 5회 -> 모두 통과해야 함
        for _ in range(5):
            rate_logger.error(msg)

        assert mock_logger.info.call_count == 20
        assert mock_logger.error.call_count == 5


class TestWarningRateLimited:
    """WARNING 레벨도 rate limit 적용 테스트"""

    def test_warning_also_rate_limited(self, rate_logger, mock_logger):
        """WARNING 메시지도 rate limit이 적용된다"""
        msg = "경고: 반복되는 문제"

        for _ in range(10):
            rate_logger.warning(msg)

        # 5회만 통과
        assert mock_logger.warning.call_count == 5


class TestCounterReset:
    """카운터 리셋 테스트"""

    def test_counter_resets_after_minute(self, mock_logger):
        """1분 경과 후 카운터가 리셋되어 다시 로깅 가능"""
        rate_logger = RateLimitedLogger(mock_logger, max_per_minute=3, summary_interval_seconds=120)
        msg = "반복 에러"

        # 1분 윈도우 내에서 5회 -> 3회만 통과
        for _ in range(5):
            rate_logger.error(msg)
        assert mock_logger.error.call_count == 3

        # 시간을 1분 이상 앞으로 진행 (time.time 패치)
        original_time = time.time
        with patch('utils.rate_limited_logger.time') as mock_time:
            mock_time.time.return_value = original_time() + 61.0
            # 리셋 후 다시 3회 허용
            for _ in range(5):
                rate_logger.error(msg)

        # 기존 3 + 리셋 후 3 = 6
        assert mock_logger.error.call_count == 6


class TestSummaryLogging:
    """억제 요약 로그 테스트"""

    def test_summary_logged_for_suppressed(self, mock_logger):
        """억제된 메시지가 있으면 요약 로그가 출력된다"""
        rate_logger = RateLimitedLogger(mock_logger, max_per_minute=2, summary_interval_seconds=1)

        msg = "가상 매도 DB 저장 실패"

        # 10회 호출 -> 2회 통과, 8회 억제
        for _ in range(10):
            rate_logger.error(msg)

        assert mock_logger.error.call_count == 2

        # 1초 이상 대기하여 summary interval 경과
        time.sleep(1.1)

        # 다음 호출 시 요약이 트리거됨 (1분 윈도우는 아직 유효)
        rate_logger.error(msg)

        # 요약 로그가 warning으로 출력되었는지 확인
        summary_calls = [
            c for c in mock_logger.warning.call_args_list
            if '중복 로그 요약' in str(c)
        ]
        assert len(summary_calls) >= 1

        # 요약 메시지에 억제 횟수가 포함되어 있는지 확인
        summary_msg = str(summary_calls[0])
        assert '추가 발생' in summary_msg
        assert '총' in summary_msg

    def test_no_summary_when_nothing_suppressed(self, mock_logger):
        """억제된 메시지가 없으면 요약 로그가 출력되지 않는다"""
        rate_logger = RateLimitedLogger(mock_logger, max_per_minute=10, summary_interval_seconds=1)

        # 5회 호출 -> 한도 10 이내이므로 모두 통과
        for _ in range(5):
            rate_logger.error("에러 발생")

        time.sleep(1.1)

        # 다음 호출로 요약 체크 트리거
        rate_logger.error("에러 발생")

        # warning으로 요약 메시지가 출력되지 않아야 함
        summary_calls = [
            c for c in mock_logger.warning.call_args_list
            if '중복 로그 요약' in str(c)
        ]
        assert len(summary_calls) == 0


class TestCriticalRateLimited:
    """CRITICAL 레벨 rate limit 테스트"""

    def test_critical_rate_limited(self, rate_logger, mock_logger):
        """CRITICAL 메시지도 rate limit이 적용된다"""
        msg = "시스템 장애"

        for _ in range(8):
            rate_logger.critical(msg)

        assert mock_logger.critical.call_count == 5


class TestThreadSafety:
    """스레드 안전성 테스트"""

    def test_concurrent_logging(self, mock_logger):
        """여러 스레드에서 동시에 호출해도 안전하다"""
        import threading

        rate_logger = RateLimitedLogger(mock_logger, max_per_minute=5, summary_interval_seconds=60)
        msg = "동시 에러"
        barrier = threading.Barrier(10)

        def log_many():
            barrier.wait()
            for _ in range(20):
                rate_logger.error(msg)

        threads = [threading.Thread(target=log_many) for _ in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        # 정확히 5회만 통과해야 함 (스레드 안전)
        assert mock_logger.error.call_count == 5


class TestMessageKeyTruncation:
    """메시지 키 truncation 테스트"""

    def test_long_messages_truncated_to_key(self, rate_logger, mock_logger):
        """100자 이상의 메시지는 앞 100자가 같으면 동일 메시지로 취급"""
        prefix = "A" * 100
        msg1 = prefix + " suffix1"
        msg2 = prefix + " suffix2"

        # 앞 100자가 같으므로 같은 key
        for _ in range(3):
            rate_logger.error(msg1)
        for _ in range(3):
            rate_logger.error(msg2)

        # 같은 key로 취급, 총 5회만 통과 (max_per_minute=5)
        assert mock_logger.error.call_count == 5


class TestLoggerDelegation:
    """로거 속성 위임 테스트"""

    def test_name_property(self, rate_logger, mock_logger):
        """name 속성이 올바르게 위임된다"""
        assert rate_logger.name == "test_logger"

    def test_set_level(self, rate_logger, mock_logger):
        """setLevel이 올바르게 위임된다"""
        rate_logger.setLevel(logging.WARNING)
        mock_logger.setLevel.assert_called_once_with(logging.WARNING)

    def test_is_enabled_for(self, rate_logger, mock_logger):
        """isEnabledFor가 올바르게 위임된다"""
        mock_logger.isEnabledFor.return_value = True
        assert rate_logger.isEnabledFor(logging.ERROR) is True
        mock_logger.isEnabledFor.assert_called_once_with(logging.ERROR)
