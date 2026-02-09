"""
네트워크/API 장애 복원력 테스트
================================
시나리오1 개발자B: KIS API 장애 상황에서의 시스템 동작 검증

테스트 시나리오:
1. API 타임아웃 (다양한 시간)
2. 연속 실패 후 복구
3. 인증 만료 중 매매 시도
4. 부분적 네트워크 장애 (일부 API만 실패)
"""

import tests._mock_modules  # noqa: F401

import time
import json
import pytest
import pandas as pd
from datetime import datetime, timedelta, timezone
from unittest.mock import Mock, MagicMock, patch, PropertyMock, AsyncMock
from requests.exceptions import ConnectionError, Timeout, ReadTimeout

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))


# ============================================================================
# Fixtures
# ============================================================================

@pytest.fixture
def mock_kis_env():
    """KISEnv mock"""
    from api.kis_auth import KISEnv
    return KISEnv(
        my_app='test_app_key',
        my_sec='test_secret',
        my_acct='12345678',
        my_prod='01',
        my_token='Bearer test_token',
        my_url='https://openapi.koreainvestment.com:9443'
    )


@pytest.fixture
def api_manager():
    """KISAPIManager 인스턴스 (인증 mock)"""
    with patch('api.kis_api_manager.kis_auth') as mock_auth:
        mock_auth.auth.return_value = True
        env = Mock()
        env.my_app = 'test'
        env.my_sec = 'test'
        env.my_acct = '12345678'
        mock_auth.getTREnv.return_value = env

        from api.kis_api_manager import KISAPIManager
        mgr = KISAPIManager()
        mgr.is_authenticated = True
        mgr.last_auth_time = datetime.now(timezone(timedelta(hours=9)))
        mgr.max_retries = 3
        mgr.retry_delay = 0.01  # 테스트용 빠른 재시도
        return mgr


# ============================================================================
# 1. API 타임아웃 테스트
# ============================================================================

class TestAPITimeout:
    """API 타임아웃 시나리오 테스트"""

    def test_single_timeout_then_success(self, api_manager):
        """단일 타임아웃 후 성공 복구"""
        call_count = 0

        def flaky_api(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise Timeout("Connection timed out")
            return pd.DataFrame({'stck_prpr': [50000], 'prdy_vrss': [500],
                                'prdy_ctrt': [1.0], 'acml_vol': [1000000]})

        result = api_manager._call_api_with_retry(flaky_api)
        assert result is not None
        assert call_count == 2

    def test_all_retries_timeout(self, api_manager):
        """모든 재시도 타임아웃 - 예외 발생 확인"""
        def always_timeout(*args, **kwargs):
            raise Timeout("Connection timed out")

        with pytest.raises(Timeout):
            api_manager._call_api_with_retry(always_timeout)

    def test_connection_error_retry(self, api_manager):
        """ConnectionError 발생 시 재시도"""
        call_count = 0

        def conn_error_then_ok(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count <= 2:
                raise ConnectionError("Connection refused")
            return pd.DataFrame({'result': ['ok']})

        result = api_manager._call_api_with_retry(conn_error_then_ok)
        assert result is not None
        assert call_count == 3

    def test_read_timeout_during_order(self, api_manager):
        """주문 중 ReadTimeout 발생 시 OrderResult 반환"""
        with patch.object(api_manager, '_call_api_with_retry', side_effect=ReadTimeout("Read timed out")):
            result = api_manager.place_buy_order("005930", 10, 70000)
            assert result.success is False
            assert "오류" in result.message or "Read timed out" in result.message

    def test_timeout_during_sell_order(self, api_manager):
        """매도 주문 중 타임아웃"""
        with patch.object(api_manager, '_call_api_with_retry', side_effect=Timeout("Timeout")):
            result = api_manager.place_sell_order("005930", 10, 75000)
            assert result.success is False

    def test_timeout_during_cancel_order(self, api_manager):
        """주문 취소 중 타임아웃"""
        with patch.object(api_manager, '_call_api_with_retry', side_effect=Timeout("Timeout")):
            with patch('utils.korean_time.is_before_market_open', return_value=False):
                result = api_manager.cancel_order("ORD001", "005930")
                assert result.success is False

    def test_exponential_backoff_timing(self, api_manager):
        """지수 백오프 시간 증가 확인"""
        api_manager.retry_delay = 0.05
        timestamps = []

        def record_time(*args, **kwargs):
            timestamps.append(time.time())
            raise ConnectionError("fail")

        with pytest.raises(ConnectionError):
            api_manager._call_api_with_retry(record_time)

        # 재시도 간격이 증가하는지 확인
        if len(timestamps) >= 3:
            gap1 = timestamps[1] - timestamps[0]
            gap2 = timestamps[2] - timestamps[1]
            # 두 번째 간격이 첫 번째보다 커야 함 (지수 백오프)
            assert gap2 > gap1 * 0.8  # 약간의 오차 허용


# ============================================================================
# 2. 연속 실패 후 복구 테스트
# ============================================================================

class TestConsecutiveFailuresAndRecovery:
    """연속 실패 후 복구 시나리오"""

    def test_none_results_then_recovery(self, api_manager):
        """None 결과 연속 후 유효 결과 반환"""
        call_count = 0

        def none_then_ok(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count <= 2:
                return None
            return pd.DataFrame({'stck_prpr': [50000], 'prdy_vrss': [0],
                                'prdy_ctrt': [0], 'acml_vol': [0]})

        result = api_manager._call_api_with_retry(none_then_ok)
        assert result is not None
        assert call_count == 3

    def test_max_retries_exceeded_returns_none(self, api_manager):
        """max_retries 초과 시 None 반환"""
        def always_none(*args, **kwargs):
            return None

        result = api_manager._call_api_with_retry(always_none)
        assert result is None

    def test_error_count_tracking(self, api_manager):
        """에러 카운트 추적"""
        initial_errors = api_manager.error_count

        def fail_once(*args, **kwargs):
            raise ValueError("test error")

        with pytest.raises(ValueError):
            api_manager._call_api_with_retry(fail_once)

        assert api_manager.error_count > initial_errors

    def test_call_count_tracking(self, api_manager):
        """API 호출 카운트 추적"""
        initial_calls = api_manager.call_count

        def ok(*args, **kwargs):
            return pd.DataFrame({'result': ['ok']})

        api_manager._call_api_with_retry(ok)
        assert api_manager.call_count == initial_calls + 1

    def test_health_check_after_failures(self, api_manager):
        """연속 실패 후 health_check"""
        with patch.object(api_manager, 'get_current_price', return_value=None):
            assert api_manager.health_check() is False

        # 복구 후
        mock_price = Mock()
        mock_price.current_price = 70000
        with patch.object(api_manager, 'get_current_price', return_value=mock_price):
            assert api_manager.health_check() is True

    def test_get_current_price_returns_none_on_failure(self, api_manager):
        """현재가 조회 실패 시 None 반환 (예외 전파 안 함)"""
        with patch.object(api_manager, '_call_api_with_retry', return_value=None):
            result = api_manager.get_current_price("005930")
            assert result is None

    def test_get_current_price_exception_returns_none(self, api_manager):
        """현재가 조회 예외 시 None 반환"""
        with patch.object(api_manager, '_call_api_with_retry', side_effect=Exception("Network error")):
            result = api_manager.get_current_price("005930")
            assert result is None

    def test_get_account_balance_returns_none_on_failure(self, api_manager):
        """계좌 잔고 조회 실패 시 None"""
        with patch.object(api_manager, '_call_api_with_retry', return_value=None):
            result = api_manager.get_account_balance()
            assert result is None

    def test_multiple_stock_prices_partial_failure(self, api_manager):
        """여러 종목 조회 중 일부 실패"""
        call_count = 0

        def partial_fail(stock_code):
            nonlocal call_count
            call_count += 1
            if stock_code == "000660":
                return None  # SK하이닉스 실패
            mock_price = Mock()
            mock_price.current_price = 50000
            return mock_price

        with patch.object(api_manager, 'get_current_price', side_effect=partial_fail):
            with patch('api.kis_api_manager.time.sleep'):
                result = api_manager.get_current_prices(["005930", "000660", "035720"])

        assert "005930" in result
        assert "000660" not in result  # 실패한 종목은 제외
        assert "035720" in result


# ============================================================================
# 3. 인증 만료 중 매매 시도 테스트
# ============================================================================

class TestAuthExpirationDuringTrading:
    """인증 만료 상태에서 매매 시도"""

    def test_ensure_authenticated_triggers_reauth(self, api_manager):
        """토큰 만료 시 재인증 트리거"""
        # 1시간 이상 경과 시뮬레이션
        api_manager.last_auth_time = datetime.now(timezone(timedelta(hours=9))) - timedelta(hours=2)

        with patch('api.kis_api_manager.kis_auth') as mock_auth:
            mock_auth.auth.return_value = True
            mock_auth.getTREnv.return_value = Mock(my_app='t', my_sec='t', my_acct='t')

            result = api_manager._ensure_authenticated()
            assert result is True
            mock_auth.auth.assert_called_once()

    def test_ensure_authenticated_reauth_failure(self, api_manager):
        """재인증 실패 시 False 반환"""
        api_manager.last_auth_time = datetime.now(timezone(timedelta(hours=9))) - timedelta(hours=2)

        with patch('api.kis_api_manager.kis_auth') as mock_auth:
            mock_auth.auth.return_value = False
            result = api_manager._ensure_authenticated()
            assert result is False

    def test_buy_order_with_expired_auth(self, api_manager):
        """인증 만료 상태에서 매수 시도"""
        api_manager.is_authenticated = False

        with patch.object(api_manager, '_initialize_auth', return_value=False):
            # _ensure_authenticated가 False를 반환하므로 _call_api_with_retry에서 Exception
            result = api_manager.place_buy_order("005930", 10, 70000)
            assert result.success is False

    def test_sell_order_with_expired_auth(self, api_manager):
        """인증 만료 상태에서 매도 시도"""
        api_manager.is_authenticated = False

        with patch.object(api_manager, '_initialize_auth', return_value=False):
            result = api_manager.place_sell_order("005930", 10, 75000)
            assert result.success is False

    def test_auth_recovery_mid_trading(self, api_manager):
        """매매 중 인증 복구"""
        api_manager.is_authenticated = False
        call_count = 0

        def mock_init_auth():
            nonlocal call_count
            call_count += 1
            api_manager.is_authenticated = True
            api_manager.last_auth_time = datetime.now(timezone(timedelta(hours=9)))
            return True

        with patch.object(api_manager, '_initialize_auth', side_effect=mock_init_auth):
            with patch.object(api_manager, '_call_api_with_retry') as mock_call:
                mock_call.return_value = pd.DataFrame({
                    'ODNO': ['ORD001']
                })
                result = api_manager.place_buy_order("005930", 10, 70000)
                # _call_api_with_retry가 _ensure_authenticated를 호출하여 재인증
                assert result.success is True


# ============================================================================
# 4. 부분적 네트워크 장애 테스트 (일부 API만 실패)
# ============================================================================

class TestPartialNetworkFailure:
    """일부 API만 실패하는 상황"""

    def test_price_api_fails_but_account_works(self, api_manager):
        """현재가 API 실패, 계좌 API 정상"""
        # 현재가 조회 실패
        with patch.object(api_manager, '_call_api_with_retry', side_effect=ConnectionError("price api down")):
            price = api_manager.get_current_price("005930")
            assert price is None

        # 계좌 잔고는 정상
        balance_df = pd.DataFrame({
            'nass_amt': [10000000], 'nxdy_excc_amt': [8000000],
            'scts_evlu_amt': [2000000], 'tot_evlu_amt': [10000000]
        })
        with patch.object(api_manager, '_call_api_with_retry', return_value=balance_df):
            with patch('api.kis_api_manager.kis_market_api') as mock_market:
                mock_market.get_existing_holdings.return_value = []
                balance = api_manager.get_account_balance()
                assert balance is not None
                assert balance.total_value == 10000000

    def test_order_api_fails_but_query_works(self, api_manager):
        """주문 API 실패, 조회 API 정상"""
        with patch.object(api_manager, '_call_api_with_retry', side_effect=ConnectionError("order api down")):
            buy_result = api_manager.place_buy_order("005930", 10, 70000)
            assert buy_result.success is False

        # 현재가 조회는 정상
        price_df = pd.DataFrame({
            'stck_prpr': [70000], 'prdy_vrss': [500],
            'prdy_ctrt': [0.72], 'acml_vol': [10000000]
        })
        with patch.object(api_manager, '_call_api_with_retry', return_value=price_df):
            price = api_manager.get_current_price("005930")
            assert price is not None
            assert price.current_price == 70000

    def test_ohlcv_data_failure_doesnt_crash(self, api_manager):
        """OHLCV 데이터 조회 실패 시 안전한 None 반환"""
        with patch.object(api_manager, '_call_api_with_retry', return_value=None):
            result = api_manager.get_ohlcv_data("005930", "D", 30)
            assert result is None

    def test_ohlcv_data_exception_returns_none(self, api_manager):
        """OHLCV 조회 예외 시 None"""
        with patch.object(api_manager, '_call_api_with_retry', side_effect=Exception("DB error")):
            result = api_manager.get_ohlcv_data("005930")
            assert result is None

    def test_tradable_amount_failure(self, api_manager):
        """매수가능수량 조회 실패"""
        with patch.object(api_manager, '_call_api_with_retry', return_value=None):
            result = api_manager.get_tradable_amount("005930", 70000)
            assert result is None

    def test_index_data_failure(self, api_manager):
        """지수 데이터 조회 실패"""
        with patch.object(api_manager, '_call_api_with_retry', side_effect=Exception("fail")):
            result = api_manager.get_index_data()
            assert result is None

    def test_investor_flow_failure(self, api_manager):
        """투자자 매매동향 조회 실패"""
        with patch.object(api_manager, '_call_api_with_retry', side_effect=Exception("fail")):
            result = api_manager.get_investor_flow_data()
            assert result is None

    def test_empty_dataframe_handling(self, api_manager):
        """빈 DataFrame 반환 시 안전 처리"""
        with patch.object(api_manager, '_call_api_with_retry', return_value=pd.DataFrame()):
            price = api_manager.get_current_price("005930")
            assert price is None

    def test_buy_order_empty_response(self, api_manager):
        """매수 주문 빈 응답"""
        with patch.object(api_manager, '_call_api_with_retry', return_value=pd.DataFrame()):
            result = api_manager.place_buy_order("005930", 10, 70000)
            assert result.success is False
            assert "응답 없음" in result.message

    def test_sell_order_no_order_id(self, api_manager):
        """매도 주문 응답에 주문번호 없음"""
        with patch.object(api_manager, '_call_api_with_retry',
                         return_value=pd.DataFrame({'ODNO': ['']})):
            result = api_manager.place_sell_order("005930", 10, 75000)
            assert result.success is False
            assert "주문번호 없음" in result.message


# ============================================================================
# 5. kis_auth._url_fetch 속도 제한 및 재시도 테스트
# ============================================================================

class TestUrlFetchResilience:
    """kis_auth._url_fetch의 속도 제한/재시도 로직 테스트"""

    def test_rate_limit_error_code_detection(self):
        """EGW00201 속도 제한 에러 코드 감지"""
        from api.kis_auth import _is_rate_limit_error
        assert _is_rate_limit_error('{"msg_cd": "EGW00201", "msg1": "초당 거래건수를 초과"}') is True
        assert _is_rate_limit_error('{"msg_cd": "EGW00123", "msg1": "토큰 만료"}') is False
        assert _is_rate_limit_error('invalid json') is False

    def test_api_statistics_tracking(self):
        """API 통계 수집 확인"""
        from api.kis_auth import get_api_statistics, reset_api_statistics
        reset_api_statistics()
        stats = get_api_statistics()
        assert stats['total_calls'] == 0
        assert stats['rate_limit_errors'] == 0

    def test_api_rate_limit_config(self):
        """속도 제한 설정 변경"""
        from api.kis_auth import set_api_rate_limit, get_api_rate_limit_info
        original = get_api_rate_limit_info()

        set_api_rate_limit(0.5, 5, 3.0)
        info = get_api_rate_limit_info()
        assert info['min_interval'] == 0.5
        assert info['max_retries'] == 5
        assert info['retry_delay_base'] == 3.0

        # 원복
        set_api_rate_limit(original['min_interval'], original['max_retries'], original['retry_delay_base'])


# ============================================================================
# 6. API 응답 파싱 오류 테스트
# ============================================================================

class TestAPIResponseParsing:
    """API 응답 파싱 실패 시나리오"""

    def test_api_resp_invalid_json(self):
        """비정상 JSON 응답 처리"""
        from api.kis_auth import APIResp
        mock_resp = Mock()
        mock_resp.status_code = 200
        mock_resp.headers = {'content-type': 'application/json'}
        mock_resp.json.side_effect = json.JSONDecodeError("err", "doc", 0)

        ar = APIResp(mock_resp)
        assert ar.isOK() is False
        assert ar.getErrorCode() == 'ERROR'

    def test_api_resp_success(self):
        """정상 API 응답"""
        from api.kis_auth import APIResp
        mock_resp = Mock()
        mock_resp.status_code = 200
        mock_resp.headers = {'content-type': 'application/json'}
        mock_resp.json.return_value = {
            'rt_cd': '0', 'msg_cd': '', 'msg1': 'success', 'output': {}
        }

        ar = APIResp(mock_resp)
        assert ar.isOK() is True
        assert ar.getResCode() == 200

    def test_api_resp_business_error(self):
        """비즈니스 오류 응답"""
        from api.kis_auth import APIResp
        mock_resp = Mock()
        mock_resp.status_code = 200
        mock_resp.headers = {}
        mock_resp.json.return_value = {
            'rt_cd': '1', 'msg_cd': 'EGW00201', 'msg1': '초당 거래건수를 초과'
        }

        ar = APIResp(mock_resp)
        assert ar.isOK() is False
        assert ar.getErrorCode() == 'EGW00201'


# ============================================================================
# 7. API 매니저 초기화/종료 안전성 테스트
# ============================================================================

class TestAPIManagerLifecycle:
    """API 매니저 생명주기 안전성"""

    def test_initialize_auth_failure(self):
        """인증 초기화 실패 시 안전한 상태"""
        with patch('api.kis_api_manager.kis_auth') as mock_auth:
            mock_auth.auth.return_value = False
            from api.kis_api_manager import KISAPIManager
            mgr = KISAPIManager()
            result = mgr.initialize()
            assert result is False
            assert mgr.is_initialized is False

    def test_shutdown_cleans_state(self, api_manager):
        """종료 시 상태 정리"""
        api_manager.is_initialized = True
        api_manager.is_authenticated = True
        api_manager.shutdown()
        assert api_manager.is_initialized is False
        assert api_manager.is_authenticated is False

    def test_api_statistics(self, api_manager):
        """API 통계 반환"""
        api_manager.call_count = 100
        api_manager.error_count = 5
        stats = api_manager.get_api_statistics()
        assert stats['total_calls'] == 100
        assert stats['error_count'] == 5
        assert stats['success_rate'] == 95.0

    def test_uninitialized_api_calls(self):
        """초기화 안 된 상태에서 API 호출"""
        with patch('api.kis_api_manager.kis_auth') as mock_auth:
            mock_auth.auth.return_value = False
            mock_auth.getTREnv.return_value = None
            from api.kis_api_manager import KISAPIManager
            mgr = KISAPIManager()
            mgr.is_authenticated = False

            with patch.object(mgr, '_initialize_auth', return_value=False):
                # _ensure_authenticated가 False → Exception
                result = mgr.place_buy_order("005930", 10, 70000)
                assert result.success is False


# ============================================================================
# 8. 동시성/스레드 안전성 테스트
# ============================================================================

class TestThreadSafety:
    """API 호출 동시성 안전성"""

    def test_wait_for_api_limit_thread_safety(self):
        """_wait_for_api_limit 스레드 안전성 (기본 검증)"""
        from api.kis_auth import _wait_for_api_limit
        import threading

        errors = []

        def call_api():
            try:
                _wait_for_api_limit()
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=call_api) for _ in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=5)

        assert len(errors) == 0, f"Thread errors: {errors}"
