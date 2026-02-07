"""
API 계층 유닛 테스트
- kis_auth.py: 토큰 발급/갱신, rate limiting, 인증 실패 처리
- kis_api_manager.py: API 요청/응답 처리, 재시도, rate limiting
- kis_order_api.py: 주문 생성/취소 요청 포맷, 응답 파싱
- kis_account_api.py: 계좌 잔고 조회 응답 파싱
- kis_market_api.py: 시세 조회 응답 파싱
모든 외부 API 호출은 Mock 처리
"""
import pytest
import json
import time
import pandas as pd
from collections import namedtuple
from datetime import datetime, timedelta, timezone
from unittest.mock import Mock, MagicMock, patch, PropertyMock


# ============================================================================
# kis_auth.py 테스트
# ============================================================================

class TestKisAuthAPIResp:
    """APIResp 클래스 테스트"""

    def _make_mock_response(self, status_code=200, json_data=None, headers=None):
        """Mock requests.Response 생성 헬퍼"""
        import requests
        resp = Mock(spec=requests.Response)
        resp.status_code = status_code
        # headers는 실제 dict처럼 동작해야 APIResp._setHeader가 작동함
        resp.headers = headers or {
            'content-type': 'application/json',
            'tr_cont': 'D',
            'gt_uid': 'test-uid'
        }
        if json_data:
            resp.json.return_value = json_data
            resp.text = json.dumps(json_data)
        else:
            resp.json.side_effect = json.JSONDecodeError("", "", 0)
            resp.text = ""
        return resp

    def test_api_resp_success(self):
        """API 응답 성공 케이스 파싱"""
        from api.kis_auth import APIResp

        json_data = {
            'rt_cd': '0',
            'msg_cd': 'MCA00000',
            'msg1': '정상 처리',
            'output': {'stck_prpr': '70000'}
        }
        resp = self._make_mock_response(200, json_data)
        ar = APIResp(resp)

        assert ar.isOK() is True
        assert ar.getResCode() == 200
        assert ar.getErrorCode() == 'MCA00000'
        assert ar.getErrorMessage() == '정상 처리'

    def test_api_resp_business_error(self):
        """API 비즈니스 오류 (rt_cd != 0)"""
        from api.kis_auth import APIResp

        json_data = {
            'rt_cd': '1',
            'msg_cd': 'EGW00201',
            'msg1': '초당 거래건수를 초과'
        }
        resp = self._make_mock_response(200, json_data)
        ar = APIResp(resp)

        assert ar.isOK() is False
        assert ar.getErrorCode() == 'EGW00201'

    def test_api_resp_json_parse_failure(self):
        """API 응답 JSON 파싱 실패"""
        from api.kis_auth import APIResp

        resp = self._make_mock_response(200)
        ar = APIResp(resp)

        assert ar.isOK() is False

    def test_api_resp_http_error_code(self):
        """HTTP 오류 응답 코드 확인"""
        from api.kis_auth import APIResp

        json_data = {'rt_cd': '1', 'msg_cd': 'ERROR', 'msg1': 'Internal Error'}
        resp = self._make_mock_response(500, json_data)
        ar = APIResp(resp)

        assert ar.getResCode() == 500


class TestKisAuthRateLimit:
    """Rate Limiting 관련 테스트"""

    def test_is_rate_limit_error_true(self):
        """속도 제한 오류 감지 - EGW00201"""
        from api.kis_auth import _is_rate_limit_error

        response_text = json.dumps({'msg_cd': 'EGW00201', 'msg1': '초당 거래건수를 초과'})
        assert _is_rate_limit_error(response_text) is True

    def test_is_rate_limit_error_text_match(self):
        """속도 제한 오류 감지 - 텍스트 매칭"""
        from api.kis_auth import _is_rate_limit_error

        response_text = json.dumps({'msg_cd': 'OTHER', 'msg1': '초당 거래건수를 초과하였습니다'})
        assert _is_rate_limit_error(response_text) is True

    def test_is_rate_limit_error_false(self):
        """속도 제한 오류 아닌 경우"""
        from api.kis_auth import _is_rate_limit_error

        response_text = json.dumps({'msg_cd': 'OTHER', 'msg1': '기타 오류'})
        assert _is_rate_limit_error(response_text) is False

    def test_is_rate_limit_error_invalid_json(self):
        """잘못된 JSON 응답"""
        from api.kis_auth import _is_rate_limit_error

        assert _is_rate_limit_error("not json") is False
        assert _is_rate_limit_error("") is False

    def test_set_api_rate_limit(self):
        """API rate limit 설정 동적 변경"""
        from api.kis_auth import set_api_rate_limit, get_api_rate_limit_info

        original = get_api_rate_limit_info()

        try:
            set_api_rate_limit(0.5, 5, 3.0)
            info = get_api_rate_limit_info()
            assert info['min_interval'] == 0.5
            assert info['max_retries'] == 5
            assert info['retry_delay_base'] == 3.0
        finally:
            set_api_rate_limit(original['min_interval'], original['max_retries'], original['retry_delay_base'])


class TestKisAuthStatistics:
    """API 통계 테스트"""

    def test_reset_api_statistics(self):
        """API 통계 초기화"""
        from api.kis_auth import reset_api_statistics, get_api_statistics

        reset_api_statistics()
        stats = get_api_statistics()
        assert stats['total_calls'] == 0
        assert stats['success_calls'] == 0
        assert stats['rate_limit_errors'] == 0
        assert stats['other_errors'] == 0
        assert stats['total_wait_time'] == 0.0
        assert stats['last_rate_limit_time'] is None

    def test_get_api_statistics_rates(self):
        """API 통계 비율 계산"""
        import api.kis_auth as kis_auth_mod
        from api.kis_auth import get_api_statistics, reset_api_statistics

        reset_api_statistics()
        kis_auth_mod._api_stats['total_calls'] = 100
        kis_auth_mod._api_stats['success_calls'] = 95
        kis_auth_mod._api_stats['rate_limit_errors'] = 3

        stats = get_api_statistics()
        assert stats['success_rate'] == 95.0
        assert stats['rate_limit_rate'] == 3.0

        reset_api_statistics()


class TestKisAuthEnvironment:
    """KIS 환경 설정 테스트"""

    def test_kis_env_named_tuple(self):
        """KISEnv 구조체 확인"""
        from api.kis_auth import KISEnv

        env = KISEnv(
            my_app='test_app',
            my_sec='test_secret',
            my_acct='12345678',
            my_prod='01',
            my_token='Bearer test_token',
            my_url='https://openapi.koreainvestment.com:9443'
        )
        assert env.my_app == 'test_app'
        assert env.my_acct == '12345678'
        assert env.my_prod == '01'

    @patch('api.kis_auth.APP_KEY', 'test_app_key')
    @patch('api.kis_auth.SECRET_KEY', 'test_secret_key')
    @patch('api.kis_auth.KIS_BASE_URL', 'https://test.api.com')
    @patch('api.kis_auth.ACCOUNT_NUMBER', '1234567801')
    def test_changeTREnv_with_account(self):
        """changeTREnv로 환경 설정 변경"""
        from api.kis_auth import changeTREnv, getTREnv

        changeTREnv("Bearer test_token_123")
        env = getTREnv()

        assert env is not None
        assert env.my_app == 'test_app_key'
        assert env.my_sec == 'test_secret_key'
        assert env.my_acct == '12345678'
        assert env.my_prod == '01'
        assert env.my_token == 'Bearer test_token_123'

    @patch('api.kis_auth.APP_KEY', 'test_app_key')
    @patch('api.kis_auth.SECRET_KEY', 'test_secret_key')
    @patch('api.kis_auth.KIS_BASE_URL', 'https://test.api.com')
    @patch('api.kis_auth.ACCOUNT_NUMBER', '12345')
    def test_changeTREnv_short_account(self):
        """짧은 계좌번호로 환경 설정"""
        from api.kis_auth import changeTREnv, getTREnv

        changeTREnv("Bearer token", product='01')
        env = getTREnv()
        assert env.my_acct == '12345'
        assert env.my_prod == '01'


class TestKisAuthHelpers:
    """인증 헬퍼 함수 테스트"""

    @patch('api.kis_auth._TRENV')
    def test_get_access_token_strips_bearer(self, mock_env):
        """get_access_token이 Bearer 접두사 제거"""
        from api.kis_auth import KISEnv
        mock_env_obj = KISEnv('app', 'sec', 'acct', '01', 'Bearer my_token_value', 'url')
        with patch('api.kis_auth._TRENV', mock_env_obj):
            from api.kis_auth import get_access_token
            token = get_access_token()
            assert token == 'my_token_value'

    @patch('api.kis_auth._TRENV', None)
    def test_is_initialized_false_when_no_env(self):
        """환경 미설정 시 is_initialized False"""
        from api.kis_auth import is_initialized
        assert is_initialized() is False

    @patch('api.kis_auth._TRENV')
    def test_is_initialized_true(self, mock_env):
        """환경 설정 시 is_initialized True"""
        from api.kis_auth import KISEnv
        mock_env_obj = KISEnv('app', 'sec', 'acct', '01', 'Bearer token', 'url')
        with patch('api.kis_auth._TRENV', mock_env_obj):
            from api.kis_auth import is_initialized
            assert is_initialized() is True


class TestKisAuthClass:
    """KisAuth 클래스 테스트"""

    @patch('api.kis_auth.auth')
    def test_initialize_success(self, mock_auth):
        """KisAuth.initialize 성공"""
        from api.kis_auth import KisAuth

        mock_auth.return_value = True
        kis_auth = KisAuth()
        result = kis_auth.initialize()

        assert result is True
        assert kis_auth._initialized is True
        mock_auth.assert_called_once()

    @patch('api.kis_auth.auth')
    def test_initialize_failure(self, mock_auth):
        """KisAuth.initialize 실패"""
        from api.kis_auth import KisAuth

        mock_auth.return_value = False
        kis_auth = KisAuth()
        result = kis_auth.initialize()

        assert result is False
        assert kis_auth._initialized is False

    @patch('api.kis_auth.auth')
    def test_initialize_exception(self, mock_auth):
        """KisAuth.initialize 예외 발생"""
        from api.kis_auth import KisAuth

        mock_auth.side_effect = Exception("connection error")
        kis_auth = KisAuth()
        result = kis_auth.initialize()

        assert result is False


class TestKisAuthTokenValidation:
    """토큰 발급 시 설정값 검증 테스트"""

    @patch('api.kis_auth.APP_KEY', '')
    @patch('api.kis_auth.SECRET_KEY', 'valid_secret')
    def test_auth_fails_with_empty_app_key(self):
        """APP_KEY 비어있으면 인증 실패"""
        from api.kis_auth import auth
        result = auth()
        assert result is False

    @patch('api.kis_auth.APP_KEY', 'your_app_key_here')
    @patch('api.kis_auth.SECRET_KEY', 'your_app_secret_here')
    def test_auth_fails_with_template_values(self):
        """템플릿 값으로 인증 시도하면 실패"""
        from api.kis_auth import auth
        result = auth()
        assert result is False


# ============================================================================
# kis_api_manager.py 테스트
# ============================================================================

class TestKISAPIManagerInit:
    """KISAPIManager 초기화 테스트"""

    def test_initial_state(self):
        """초기 상태 확인"""
        from api.kis_api_manager import KISAPIManager

        manager = KISAPIManager()
        assert manager.is_initialized is False
        assert manager.is_authenticated is False
        assert manager.call_count == 0
        assert manager.error_count == 0

    @patch('api.kis_api_manager.kis_auth')
    def test_initialize_success(self, mock_auth):
        """초기화 성공"""
        from api.kis_api_manager import KISAPIManager

        mock_auth.auth.return_value = True
        mock_env = Mock()
        mock_env.my_app = 'app'
        mock_env.my_sec = 'sec'
        mock_env.my_acct = 'acct'
        mock_auth.getTREnv.return_value = mock_env

        manager = KISAPIManager()
        result = manager.initialize()

        assert result is True
        assert manager.is_initialized is True
        assert manager.is_authenticated is True

    @patch('api.kis_api_manager.kis_auth')
    def test_initialize_auth_failure(self, mock_auth):
        """인증 실패 시 초기화 실패"""
        from api.kis_api_manager import KISAPIManager

        mock_auth.auth.return_value = False
        manager = KISAPIManager()
        result = manager.initialize()

        assert result is False
        assert manager.is_initialized is False


class TestKISAPIManagerRetry:
    """KISAPIManager 재시도 로직 테스트"""

    def test_call_api_with_retry_success(self):
        """재시도 없이 성공"""
        from api.kis_api_manager import KISAPIManager

        manager = KISAPIManager()
        manager.is_authenticated = True
        manager.max_retries = 3
        manager.retry_delay = 0.01

        mock_func = Mock(return_value="success_result")
        result = manager._call_api_with_retry(mock_func, "arg1")

        assert result == "success_result"
        assert mock_func.call_count == 1

    def test_call_api_with_retry_none_then_success(self):
        """첫 시도 None, 재시도에서 성공"""
        from api.kis_api_manager import KISAPIManager

        manager = KISAPIManager()
        manager.is_authenticated = True
        manager.max_retries = 3
        manager.retry_delay = 0.01

        mock_func = Mock(side_effect=[None, "success_result"])
        result = manager._call_api_with_retry(mock_func, "arg1")

        assert result == "success_result"
        assert mock_func.call_count == 2

    def test_call_api_with_retry_all_none(self):
        """모든 시도 None"""
        from api.kis_api_manager import KISAPIManager

        manager = KISAPIManager()
        manager.is_authenticated = True
        manager.max_retries = 2
        manager.retry_delay = 0.01

        mock_func = Mock(return_value=None)
        result = manager._call_api_with_retry(mock_func)

        assert result is None
        assert mock_func.call_count == 2

    def test_call_api_with_retry_exception_then_success(self):
        """예외 발생 후 재시도에서 성공"""
        from api.kis_api_manager import KISAPIManager

        manager = KISAPIManager()
        manager.is_authenticated = True
        manager.max_retries = 3
        manager.retry_delay = 0.01

        mock_func = Mock(side_effect=[Exception("API error"), "recovered"])
        result = manager._call_api_with_retry(mock_func)

        assert result == "recovered"
        assert manager.error_count == 1

    def test_call_api_with_retry_all_exceptions(self):
        """모든 시도 예외 발생"""
        from api.kis_api_manager import KISAPIManager

        manager = KISAPIManager()
        manager.is_authenticated = True
        manager.max_retries = 2
        manager.retry_delay = 0.01

        mock_func = Mock(side_effect=Exception("persistent error"))

        with pytest.raises(Exception, match="persistent error"):
            manager._call_api_with_retry(mock_func)


class TestKISAPIManagerCurrentPrice:
    """KISAPIManager 현재가 조회 테스트"""

    @patch('api.kis_api_manager.kis_market_api')
    @patch('api.kis_api_manager.kis_auth')
    def test_get_current_price_success(self, mock_auth, mock_market):
        """현재가 조회 성공"""
        from api.kis_api_manager import KISAPIManager

        # Mock 설정
        mock_auth.auth.return_value = True
        price_data = pd.DataFrame([{
            'stck_prpr': '70000',
            'prdy_vrss': '500',
            'prdy_ctrt': '0.72',
            'acml_vol': '10000000'
        }])
        mock_market.get_inquire_price.return_value = price_data

        manager = KISAPIManager()
        manager.is_authenticated = True
        manager.max_retries = 1
        result = manager.get_current_price("005930")

        assert result is not None
        assert result.stock_code == "005930"
        assert result.current_price == 70000.0
        assert result.change_amount == 500.0
        assert result.volume == 10000000

    @patch('api.kis_api_manager.kis_market_api')
    @patch('api.kis_api_manager.kis_auth')
    def test_get_current_price_none_response(self, mock_auth, mock_market):
        """현재가 조회 실패 - None 응답"""
        from api.kis_api_manager import KISAPIManager

        mock_auth.auth.return_value = True
        mock_market.get_inquire_price.return_value = None

        manager = KISAPIManager()
        manager.is_authenticated = True
        manager.max_retries = 1
        manager.retry_delay = 0.01
        result = manager.get_current_price("005930")

        assert result is None

    @patch('api.kis_api_manager.kis_market_api')
    @patch('api.kis_api_manager.kis_auth')
    def test_get_current_price_empty_df(self, mock_auth, mock_market):
        """현재가 조회 실패 - 빈 DataFrame"""
        from api.kis_api_manager import KISAPIManager

        mock_auth.auth.return_value = True
        mock_market.get_inquire_price.return_value = pd.DataFrame()

        manager = KISAPIManager()
        manager.is_authenticated = True
        manager.max_retries = 1
        manager.retry_delay = 0.01
        result = manager.get_current_price("005930")

        assert result is None


class TestKISAPIManagerAccountBalance:
    """KISAPIManager 계좌 잔고 조회 테스트"""

    @patch('api.kis_api_manager.kis_market_api')
    @patch('api.kis_api_manager.kis_account_api')
    @patch('api.kis_api_manager.kis_auth')
    def test_get_account_balance_success(self, mock_auth, mock_account, mock_market):
        """계좌 잔고 조회 성공"""
        from api.kis_api_manager import KISAPIManager

        mock_auth.auth.return_value = True
        balance_data = pd.DataFrame([{
            'nass_amt': '10000000',
            'nxdy_excc_amt': '8000000',
            'scts_evlu_amt': '2000000',
            'tot_evlu_amt': '10000000'
        }])
        mock_account.get_inquire_balance_obj.return_value = balance_data
        mock_market.get_existing_holdings.return_value = [
            {'stock_code': '005930', 'quantity': 10, 'avg_price': 70000}
        ]

        manager = KISAPIManager()
        manager.is_authenticated = True
        manager.max_retries = 1
        result = manager.get_account_balance()

        assert result is not None
        assert result.account_balance == 10000000.0
        assert result.available_amount == 8000000.0
        assert len(result.positions) == 1

    @patch('api.kis_api_manager.kis_account_api')
    @patch('api.kis_api_manager.kis_auth')
    def test_get_account_balance_empty(self, mock_auth, mock_account):
        """계좌 잔고 조회 실패 - 빈 응답"""
        from api.kis_api_manager import KISAPIManager

        mock_auth.auth.return_value = True
        mock_account.get_inquire_balance_obj.return_value = pd.DataFrame()

        manager = KISAPIManager()
        manager.is_authenticated = True
        manager.max_retries = 1
        manager.retry_delay = 0.01
        result = manager.get_account_balance()

        assert result is None

    @patch('api.kis_api_manager.kis_market_api')
    @patch('api.kis_api_manager.kis_account_api')
    @patch('api.kis_api_manager.kis_auth')
    def test_get_account_balance_quick_success(self, mock_auth, mock_account, mock_market):
        """계좌 잔고 빠른 조회 (보유 종목 제외)"""
        from api.kis_api_manager import KISAPIManager

        mock_auth.auth.return_value = True
        balance_data = pd.DataFrame([{
            'nass_amt': '10000000',
            'nxdy_excc_amt': '8000000',
            'dnca_tot_amt': '9000000',
            'prvs_rcdl_excc_amt': '7500000',
            'scts_evlu_amt': '2000000',
            'tot_evlu_amt': '10000000'
        }])
        mock_account.get_inquire_balance_obj.return_value = balance_data

        manager = KISAPIManager()
        manager.is_authenticated = True
        manager.max_retries = 1
        result = manager.get_account_balance_quick()

        assert result is not None
        assert result.available_amount == 8000000.0
        assert result.positions == []


class TestKISAPIManagerOrder:
    """KISAPIManager 주문 테스트"""

    @patch('api.kis_api_manager.kis_order_api')
    @patch('api.kis_api_manager.kis_auth')
    def test_place_buy_order_success(self, mock_auth, mock_order):
        """매수 주문 성공"""
        from api.kis_api_manager import KISAPIManager

        mock_auth.auth.return_value = True
        order_data = pd.DataFrame([{'ODNO': 'ORD-001', 'KRX_FWDG_ORD_ORGNO': 'ORG001'}])
        mock_order.get_order_cash.return_value = order_data

        manager = KISAPIManager()
        manager.is_authenticated = True
        manager.max_retries = 1
        result = manager.place_buy_order("005930", 10, 70000)

        assert result.success is True
        assert result.order_id == 'ORD-001'
        mock_order.get_order_cash.assert_called_once_with(
            "buy", "005930", 10, 70000, "", "00"
        )

    @patch('api.kis_api_manager.kis_order_api')
    @patch('api.kis_api_manager.kis_auth')
    def test_place_buy_order_no_order_id(self, mock_auth, mock_order):
        """매수 주문 실패 - 주문번호 없음"""
        from api.kis_api_manager import KISAPIManager

        mock_auth.auth.return_value = True
        order_data = pd.DataFrame([{'ODNO': '', 'msg': 'failed'}])
        mock_order.get_order_cash.return_value = order_data

        manager = KISAPIManager()
        manager.is_authenticated = True
        manager.max_retries = 1
        result = manager.place_buy_order("005930", 10, 70000)

        assert result.success is False

    @patch('api.kis_api_manager.kis_order_api')
    @patch('api.kis_api_manager.kis_auth')
    def test_place_sell_order_success(self, mock_auth, mock_order):
        """매도 주문 성공"""
        from api.kis_api_manager import KISAPIManager

        mock_auth.auth.return_value = True
        order_data = pd.DataFrame([{'ODNO': 'SELL-001'}])
        mock_order.get_order_cash.return_value = order_data

        manager = KISAPIManager()
        manager.is_authenticated = True
        manager.max_retries = 1
        result = manager.place_sell_order("005930", 10, 72000, order_type="01")

        assert result.success is True
        assert result.order_id == 'SELL-001'
        mock_order.get_order_cash.assert_called_once_with(
            "sell", "005930", 10, 72000, "", "01"
        )

    @patch('api.kis_api_manager.kis_order_api')
    @patch('api.kis_api_manager.kis_auth')
    def test_place_sell_order_none_response(self, mock_auth, mock_order):
        """매도 주문 실패 - 응답 없음"""
        from api.kis_api_manager import KISAPIManager

        mock_auth.auth.return_value = True
        mock_order.get_order_cash.return_value = None

        manager = KISAPIManager()
        manager.is_authenticated = True
        manager.max_retries = 1
        manager.retry_delay = 0.01
        result = manager.place_sell_order("005930", 10, 72000)

        assert result.success is False
        assert "응답 없음" in result.message

    @patch('api.kis_api_manager.kis_order_api')
    @patch('api.kis_api_manager.kis_auth')
    def test_place_buy_order_exception(self, mock_auth, mock_order):
        """매수 주문 예외 발생"""
        from api.kis_api_manager import KISAPIManager

        mock_auth.auth.return_value = True
        mock_order.get_order_cash.side_effect = Exception("network error")

        manager = KISAPIManager()
        manager.is_authenticated = True
        manager.max_retries = 1
        result = manager.place_buy_order("005930", 10, 70000)

        assert result.success is False
        assert "오류" in result.message


class TestKISAPIManagerUtility:
    """KISAPIManager 유틸리티 테스트"""

    def test_rate_limit_enforces_interval(self):
        """_rate_limit이 최소 간격을 보장"""
        from api.kis_api_manager import KISAPIManager

        manager = KISAPIManager()
        manager.last_call_time = time.time()

        start = time.time()
        manager._rate_limit()
        elapsed = time.time() - start

        # 최소 간격(0.06초) 근사 확인 (약간의 오차 허용)
        assert elapsed >= 0.04

    def test_get_api_statistics(self):
        """API 통계 반환"""
        from api.kis_api_manager import KISAPIManager

        manager = KISAPIManager()
        manager.call_count = 50
        manager.error_count = 5
        manager.is_authenticated = True

        stats = manager.get_api_statistics()
        assert stats['total_calls'] == 50
        assert stats['error_count'] == 5
        assert stats['success_rate'] == 90.0
        assert stats['is_authenticated'] is True

    def test_shutdown(self):
        """API 매니저 종료"""
        from api.kis_api_manager import KISAPIManager

        manager = KISAPIManager()
        manager.is_initialized = True
        manager.is_authenticated = True
        manager.shutdown()

        assert manager.is_initialized is False
        assert manager.is_authenticated is False


class TestKISAPIManagerOHLCV:
    """KISAPIManager OHLCV 데이터 조회 테스트"""

    @patch('api.kis_api_manager.kis_market_api')
    @patch('api.kis_api_manager.kis_auth')
    def test_get_ohlcv_data_short_period(self, mock_auth, mock_market):
        """단기 OHLCV 데이터 조회 (단일 조회)"""
        from api.kis_api_manager import KISAPIManager

        mock_auth.auth.return_value = True
        ohlcv_data = pd.DataFrame([
            {'stck_bsop_date': '20240115', 'stck_oprc': '70000', 'stck_hgpr': '71000',
             'stck_lwpr': '69000', 'stck_clpr': '70500', 'acml_vol': '10000000'}
        ])
        mock_market.get_inquire_daily_itemchartprice.return_value = ohlcv_data

        manager = KISAPIManager()
        manager.is_authenticated = True
        manager.max_retries = 1
        result = manager.get_ohlcv_data("005930", days=30)

        assert result is not None
        assert len(result) == 1

    @patch('api.kis_api_manager.kis_market_api')
    @patch('api.kis_api_manager.kis_auth')
    def test_get_ohlcv_data_long_period(self, mock_auth, mock_market):
        """장기 OHLCV 데이터 조회 (연속 조회 사용)"""
        from api.kis_api_manager import KISAPIManager

        mock_auth.auth.return_value = True
        ohlcv_data = pd.DataFrame([
            {'stck_bsop_date': f'2024{m:02d}15', 'stck_oprc': '70000', 'stck_hgpr': '71000',
             'stck_lwpr': '69000', 'stck_clpr': '70500', 'acml_vol': '10000000'}
            for m in range(1, 7)
        ])
        mock_market.get_inquire_daily_itemchartprice_extended.return_value = ohlcv_data

        manager = KISAPIManager()
        manager.is_authenticated = True
        manager.max_retries = 1
        result = manager.get_ohlcv_data("005930", days=360)

        assert result is not None
        mock_market.get_inquire_daily_itemchartprice_extended.assert_called_once()


# ============================================================================
# kis_order_api.py 테스트
# ============================================================================

class TestKisOrderApiTickSize:
    """KRX 호가단위 테스트"""

    def test_round_to_krx_tick_under_1000(self):
        """1,000원 미만 호가단위 (1원)"""
        from api.kis_order_api import _round_to_krx_tick
        assert _round_to_krx_tick(500) == 500
        assert _round_to_krx_tick(999) == 999

    def test_round_to_krx_tick_1000_5000(self):
        """1,000~5,000원 호가단위 (5원)"""
        from api.kis_order_api import _round_to_krx_tick
        assert _round_to_krx_tick(1003) == 1005
        assert _round_to_krx_tick(4998) == 5000

    def test_round_to_krx_tick_5000_10000(self):
        """5,000~10,000원 호가단위 (10원)"""
        from api.kis_order_api import _round_to_krx_tick
        assert _round_to_krx_tick(5003) == 5000
        assert _round_to_krx_tick(5008) == 5010

    def test_round_to_krx_tick_10000_50000(self):
        """10,000~50,000원 호가단위 (50원)"""
        from api.kis_order_api import _round_to_krx_tick
        assert _round_to_krx_tick(10020) == 10000
        assert _round_to_krx_tick(10030) == 10050

    def test_round_to_krx_tick_50000_100000(self):
        """50,000~100,000원 호가단위 (100원)"""
        from api.kis_order_api import _round_to_krx_tick
        assert _round_to_krx_tick(50051) == 50100
        assert _round_to_krx_tick(50049) == 50000

    def test_round_to_krx_tick_100000_500000(self):
        """100,000~500,000원 호가단위 (500원)"""
        from api.kis_order_api import _round_to_krx_tick
        assert _round_to_krx_tick(100200) == 100000
        assert _round_to_krx_tick(100300) == 100500

    def test_round_to_krx_tick_over_500000(self):
        """500,000원 이상 호가단위 (1,000원)"""
        from api.kis_order_api import _round_to_krx_tick
        assert _round_to_krx_tick(500400) == 500000
        assert _round_to_krx_tick(500600) == 501000

    def test_round_to_krx_tick_zero(self):
        """0원 입력"""
        from api.kis_order_api import _round_to_krx_tick
        assert _round_to_krx_tick(0) == 0

    def test_validate_tick_size_valid(self):
        """유효한 호가단위"""
        from api.kis_order_api import _validate_tick_size
        assert _validate_tick_size(50000) is True
        assert _validate_tick_size(70100) is True
        assert _validate_tick_size(1005) is True

    def test_validate_tick_size_invalid(self):
        """유효하지 않은 호가단위"""
        from api.kis_order_api import _validate_tick_size
        assert _validate_tick_size(70001) is False
        assert _validate_tick_size(1003) is False
        assert _validate_tick_size(0) is False
        assert _validate_tick_size(-100) is False


class TestKisOrderApiGetOrderCash:
    """get_order_cash 함수 테스트"""

    @patch('api.kis_order_api.kis._url_fetch')
    @patch('api.kis_order_api.kis.getTREnv')
    def test_buy_order_request_format(self, mock_env, mock_fetch):
        """매수 주문 요청 파라미터 포맷 검증"""
        from api.kis_order_api import get_order_cash

        mock_env.return_value = Mock(my_acct='12345678', my_prod='01')

        mock_body = Mock()
        mock_body.output = {'ODNO': 'ORD-001'}
        mock_body.rt_cd = '0'
        mock_resp = Mock()
        mock_resp.isOK.return_value = True
        mock_resp.getBody.return_value = mock_body
        mock_fetch.return_value = mock_resp

        result = get_order_cash("buy", "005930", 10, 70000)

        # _url_fetch 호출 검증
        call_args = mock_fetch.call_args
        params = call_args[0][3]  # 4번째 인자가 params
        assert params['PDNO'] == '005930'
        assert params['ORD_QTY'] == '10'
        assert params['ORD_UNPR'] == '70000'
        assert params['ORD_DVSN'] == '00'  # 지정가
        assert call_args[0][1] == 'TTTC0012U'  # 매수 TR ID

    @patch('api.kis_order_api.kis._url_fetch')
    @patch('api.kis_order_api.kis.getTREnv')
    def test_sell_order_request_format(self, mock_env, mock_fetch):
        """매도 주문 요청 파라미터 포맷 검증"""
        from api.kis_order_api import get_order_cash

        mock_env.return_value = Mock(my_acct='12345678', my_prod='01')

        mock_body = Mock()
        mock_body.output = {'ODNO': 'SELL-001'}
        mock_body.rt_cd = '0'
        mock_resp = Mock()
        mock_resp.isOK.return_value = True
        mock_resp.getBody.return_value = mock_body
        mock_fetch.return_value = mock_resp

        result = get_order_cash("sell", "005930", 10, 72000, ord_dvsn="01")

        call_args = mock_fetch.call_args
        assert call_args[0][1] == 'TTTC0011U'  # 매도 TR ID
        params = call_args[0][3]
        assert params['ORD_DVSN'] == '01'  # 시장가

    def test_invalid_order_type(self):
        """잘못된 주문 구분"""
        from api.kis_order_api import get_order_cash
        result = get_order_cash("invalid", "005930", 10, 70000)
        assert result is None

    def test_missing_stock_code(self):
        """종목코드 누락"""
        from api.kis_order_api import get_order_cash
        result = get_order_cash("buy", "", 10, 70000)
        assert result is None

    def test_zero_quantity(self):
        """수량 0"""
        from api.kis_order_api import get_order_cash
        result = get_order_cash("buy", "005930", 0, 70000)
        assert result is None

    def test_limit_order_zero_price(self):
        """지정가 주문인데 가격 0"""
        from api.kis_order_api import get_order_cash
        result = get_order_cash("buy", "005930", 10, 0, ord_dvsn="00")
        assert result is None


class TestKisOrderApiRvsecncl:
    """get_order_rvsecncl (주문 정정/취소) 테스트"""

    def test_missing_ord_orgno(self):
        """주문조직번호 누락"""
        from api.kis_order_api import get_order_rvsecncl
        result = get_order_rvsecncl(ord_orgno="", orgn_odno="ORD-001",
                                    ord_dvsn="00", rvse_cncl_dvsn_cd="02")
        assert result is None

    def test_missing_orgn_odno(self):
        """원주문번호 누락"""
        from api.kis_order_api import get_order_rvsecncl
        result = get_order_rvsecncl(ord_orgno="ORG-001", orgn_odno="",
                                    ord_dvsn="00", rvse_cncl_dvsn_cd="02")
        assert result is None

    def test_invalid_rvse_cncl_dvsn_cd(self):
        """잘못된 정정취소구분코드"""
        from api.kis_order_api import get_order_rvsecncl
        result = get_order_rvsecncl(ord_orgno="ORG-001", orgn_odno="ORD-001",
                                    ord_dvsn="00", rvse_cncl_dvsn_cd="03")
        assert result is None

    def test_cancel_all_forces_zero_qty(self):
        """전량 취소 시 수량 0 처리"""
        from api.kis_order_api import get_order_rvsecncl

        # qty_all_ord_yn="Y"이면서 ord_qty > 0인 경우 0으로 교정되어야 함
        # 하지만 이 함수는 실제 API를 호출하므로 파라미터 검증만 확인
        # (실제 호출 없이 로직 검증)
        # 직접 mock해서 확인
        with patch('api.kis_order_api.kis._url_fetch') as mock_fetch, \
             patch('api.kis_order_api.kis.getTREnv') as mock_env:
            mock_env.return_value = Mock(my_acct='12345678', my_prod='01')

            mock_body = Mock()
            mock_body.output = {'rt_cd': '0'}
            mock_body.rt_cd = '0'
            mock_resp = Mock()
            mock_resp.isOK.return_value = True
            mock_resp.getBody.return_value = mock_body
            mock_fetch.return_value = mock_resp

            get_order_rvsecncl(
                ord_orgno="ORG-001", orgn_odno="ORD-001",
                ord_dvsn="00", rvse_cncl_dvsn_cd="02",
                ord_qty=100, qty_all_ord_yn="Y"
            )

            call_args = mock_fetch.call_args
            params = call_args[0][3]
            assert params['ORD_QTY'] == '0'  # 강제 0 처리


# ============================================================================
# kis_account_api.py 테스트
# ============================================================================

class TestKisAccountApi:
    """계좌 조회 API 테스트"""

    @patch('api.kis_account_api.kis._url_fetch')
    @patch('api.kis_account_api.kis.getTREnv')
    def test_get_inquire_balance_success(self, mock_env, mock_fetch):
        """주식잔고조회 성공"""
        from api.kis_account_api import get_inquire_balance

        mock_env.return_value = Mock(my_acct='12345678', my_prod='01')

        mock_body = Mock()
        mock_body.output1 = [
            {'pdno': '005930', 'prdt_name': '삼성전자', 'hldg_qty': '10', 'pchs_avg_pric': '70000'}
        ]
        mock_resp = Mock()
        mock_resp.isOK.return_value = True
        mock_resp.getBody.return_value = mock_body
        mock_fetch.return_value = mock_resp

        result = get_inquire_balance()

        assert result is not None
        assert len(result) == 1
        assert result.iloc[0]['pdno'] == '005930'

    @patch('api.kis_account_api.kis._url_fetch')
    @patch('api.kis_account_api.kis.getTREnv')
    def test_get_inquire_balance_empty(self, mock_env, mock_fetch):
        """주식잔고조회 - 보유 종목 없음"""
        from api.kis_account_api import get_inquire_balance

        mock_env.return_value = Mock(my_acct='12345678', my_prod='01')

        mock_body = Mock()
        mock_body.output1 = []
        mock_resp = Mock()
        mock_resp.isOK.return_value = True
        mock_resp.getBody.return_value = mock_body
        mock_fetch.return_value = mock_resp

        result = get_inquire_balance()
        assert result is not None
        assert result.empty

    @patch('api.kis_account_api.kis.getTREnv')
    def test_get_inquire_balance_no_env(self, mock_env):
        """주식잔고조회 - 환경 미설정"""
        from api.kis_account_api import get_inquire_balance

        mock_env.return_value = None
        result = get_inquire_balance()
        assert result is None

    @patch('api.kis_account_api.kis._url_fetch')
    @patch('api.kis_account_api.kis.getTREnv')
    def test_get_inquire_balance_obj_success(self, mock_env, mock_fetch):
        """계좌 요약 정보 조회 성공"""
        from api.kis_account_api import get_inquire_balance_obj

        mock_env.return_value = Mock(my_acct='12345678', my_prod='01')

        mock_body = Mock()
        mock_body.output2 = [{
            'nass_amt': '10000000',
            'nxdy_excc_amt': '8000000',
            'scts_evlu_amt': '2000000',
            'tot_evlu_amt': '10000000'
        }]
        mock_resp = Mock()
        mock_resp.isOK.return_value = True
        mock_resp.getBody.return_value = mock_body
        mock_fetch.return_value = mock_resp

        result = get_inquire_balance_obj()
        assert result is not None
        assert result.iloc[0]['nass_amt'] == '10000000'

    @patch('api.kis_account_api.kis._url_fetch')
    @patch('api.kis_account_api.kis.getTREnv')
    def test_get_inquire_psbl_order_success(self, mock_env, mock_fetch):
        """매수가능조회 성공"""
        from api.kis_account_api import get_inquire_psbl_order

        mock_env.return_value = Mock(my_acct='12345678', my_prod='01')

        mock_body = Mock()
        mock_body.output = {'ord_psbl_qty': '14'}
        mock_resp = Mock()
        mock_resp.isOK.return_value = True
        mock_resp.getBody.return_value = mock_body
        mock_fetch.return_value = mock_resp

        result = get_inquire_psbl_order("005930", 70000)
        assert result is not None
        assert result.iloc[0]['ord_psbl_qty'] == '14'

    @patch('api.kis_account_api.kis._url_fetch')
    @patch('api.kis_account_api.kis.getTREnv')
    def test_get_inquire_psbl_order_failed(self, mock_env, mock_fetch):
        """매수가능조회 실패"""
        from api.kis_account_api import get_inquire_psbl_order

        mock_env.return_value = Mock(my_acct='12345678', my_prod='01')

        mock_resp = Mock()
        mock_resp.isOK.return_value = False
        mock_resp.printError = Mock()
        mock_fetch.return_value = mock_resp

        result = get_inquire_psbl_order("005930", 70000)
        assert result is not None
        assert result.empty


# ============================================================================
# kis_market_api.py 테스트
# ============================================================================

class TestKisMarketApiPrice:
    """시세 조회 API 테스트"""

    @patch('api.kis_market_api.kis._url_fetch')
    def test_get_inquire_price_success(self, mock_fetch):
        """주식현재가 시세 조회 성공"""
        from api.kis_market_api import get_inquire_price

        mock_body = Mock()
        mock_body.output = {
            'stck_prpr': '70000',
            'prdy_vrss': '500',
            'prdy_ctrt': '0.72',
            'acml_vol': '10000000',
            'hts_avls': '4180000'
        }
        mock_resp = Mock()
        mock_resp.isOK.return_value = True
        mock_resp.getBody.return_value = mock_body
        mock_fetch.return_value = mock_resp

        result = get_inquire_price("J", "005930")

        assert result is not None
        assert result.iloc[0]['stck_prpr'] == '70000'
        assert result.iloc[0]['prdy_vrss'] == '500'

    @patch('api.kis_market_api.kis._url_fetch')
    def test_get_inquire_price_failure(self, mock_fetch):
        """주식현재가 시세 조회 실패"""
        from api.kis_market_api import get_inquire_price

        mock_resp = Mock()
        mock_resp.isOK.return_value = False
        mock_fetch.return_value = mock_resp

        result = get_inquire_price("J", "005930")
        assert result is None


class TestKisMarketApiIndex:
    """지수 조회 API 테스트"""

    @patch('api.kis_market_api.kis._url_fetch')
    def test_get_index_data_dict_output(self, mock_fetch):
        """지수 조회 - dict 형태 응답"""
        from api.kis_market_api import get_index_data

        mock_body = Mock()
        mock_body.output = {
            'bstp_nmix_prpr': '2500.05',
            'bstp_nmix_prdy_ctrt': '0.76'
        }
        mock_resp = Mock()
        mock_resp.isOK.return_value = True
        mock_resp.getBody.return_value = mock_body
        mock_fetch.return_value = mock_resp

        result = get_index_data("0001")

        assert result is not None
        assert result['bstp_nmix_prpr'] == '2500.05'

    @patch('api.kis_market_api.kis._url_fetch')
    def test_get_index_data_list_output(self, mock_fetch):
        """지수 조회 - list 형태 응답"""
        from api.kis_market_api import get_index_data

        mock_body = Mock()
        mock_body.output = [{
            'bstp_nmix_prpr': '2500.05',
            'bstp_nmix_prdy_ctrt': '0.76'
        }]
        mock_resp = Mock()
        mock_resp.isOK.return_value = True
        mock_resp.getBody.return_value = mock_body
        mock_fetch.return_value = mock_resp

        result = get_index_data("0001")

        assert result is not None
        assert isinstance(result, dict)

    @patch('api.kis_market_api.kis._url_fetch')
    def test_get_index_data_failure(self, mock_fetch):
        """지수 조회 실패"""
        from api.kis_market_api import get_index_data

        mock_fetch.return_value = None
        result = get_index_data("0001")
        assert result is None

    @patch('api.kis_market_api.kis._url_fetch')
    def test_get_index_data_no_output(self, mock_fetch):
        """지수 조회 - output 없음"""
        from api.kis_market_api import get_index_data

        mock_body = Mock()
        mock_body.output = None
        mock_resp = Mock()
        mock_resp.isOK.return_value = True
        mock_resp.getBody.return_value = mock_body
        mock_fetch.return_value = mock_resp

        result = get_index_data("0001")
        assert result is None


class TestKisMarketApiDailyPrice:
    """일봉 조회 API 테스트"""

    @patch('api.kis_market_api.kis._url_fetch')
    def test_get_inquire_daily_itemchartprice_output2(self, mock_fetch):
        """기간별 시세 조회 - output2 (목록)"""
        from api.kis_market_api import get_inquire_daily_itemchartprice

        mock_body = Mock()
        mock_body.output2 = [
            {'stck_bsop_date': '20240115', 'stck_oprc': '70000', 'stck_clpr': '70500'},
            {'stck_bsop_date': '20240116', 'stck_oprc': '70500', 'stck_clpr': '71000'}
        ]
        mock_resp = Mock()
        mock_resp.isOK.return_value = True
        mock_resp.getBody.return_value = mock_body
        mock_fetch.return_value = mock_resp

        result = get_inquire_daily_itemchartprice(output_dv="2", itm_no="005930")
        assert result is not None
        assert len(result) == 2

    @patch('api.kis_market_api.kis._url_fetch')
    def test_get_inquire_daily_itemchartprice_output1(self, mock_fetch):
        """기간별 시세 조회 - output1 (요약)"""
        from api.kis_market_api import get_inquire_daily_itemchartprice

        mock_body = Mock()
        mock_body.output1 = {
            'stck_bsop_date': '20240115',
            'stck_oprc': '70000',
            'stck_clpr': '70500'
        }
        mock_resp = Mock()
        mock_resp.isOK.return_value = True
        mock_resp.getBody.return_value = mock_body
        mock_fetch.return_value = mock_resp

        result = get_inquire_daily_itemchartprice(output_dv="1", itm_no="005930")
        assert result is not None


class TestKisMarketApiInvestorFlow:
    """투자자별 매매동향 API 테스트"""

    @patch('api.kis_market_api.kis._url_fetch')
    def test_get_investor_flow_data_success(self, mock_fetch):
        """투자자별 매매동향 조회 성공"""
        from api.kis_market_api import get_investor_flow_data

        mock_body = Mock()
        mock_body.output1 = [{'investor_type': 'foreign', 'net_buy': '1000000'}]
        mock_body.output2 = [{'stock_code': '005930', 'net_buy': '500000'}]
        mock_resp = Mock()
        mock_resp.isOK.return_value = True
        mock_resp.getBody.return_value = mock_body
        mock_fetch.return_value = mock_resp

        result = get_investor_flow_data()

        assert result is not None
        assert 'investor_summary' in result
        assert 'stock_details' in result

    @patch('api.kis_market_api.kis._url_fetch')
    def test_get_investor_flow_data_failure(self, mock_fetch):
        """투자자별 매매동향 조회 실패"""
        from api.kis_market_api import get_investor_flow_data

        mock_fetch.return_value = None
        result = get_investor_flow_data()
        assert result is None


class TestKisMarketApiVolumeRank:
    """거래량순위 API 테스트"""

    @patch('api.kis_market_api.kis._url_fetch')
    def test_get_volume_rank_success(self, mock_fetch):
        """거래량순위 조회 성공"""
        from api.kis_market_api import get_volume_rank

        mock_body = Mock()
        mock_body.output = [
            {'mksc_shrn_iscd': '005930', 'hts_kor_isnm': '삼성전자', 'acml_vol': '50000000'},
            {'mksc_shrn_iscd': '000660', 'hts_kor_isnm': 'SK하이닉스', 'acml_vol': '30000000'}
        ]
        mock_resp = Mock()
        mock_resp.isOK.return_value = True
        mock_resp.getBody.return_value = mock_body
        mock_fetch.return_value = mock_resp

        result = get_volume_rank()

        assert result is not None
        assert len(result) == 2

    @patch('api.kis_market_api.kis._url_fetch')
    def test_get_volume_rank_empty(self, mock_fetch):
        """거래량순위 조회 - 데이터 없음"""
        from api.kis_market_api import get_volume_rank

        mock_body = Mock()
        mock_body.output = None
        # output 속성이 없을 수도 있으니 Output도 빈 리스트
        mock_body.Output = []
        mock_resp = Mock()
        mock_resp.isOK.return_value = True
        mock_resp.getBody.return_value = mock_body
        mock_fetch.return_value = mock_resp

        result = get_volume_rank()
        assert result is not None
        assert result.empty


class TestKISAPIManagerEnsureAuthenticated:
    """인증 상태 확인 및 재인증 테스트"""

    @patch('api.kis_api_manager.kis_auth')
    def test_ensure_authenticated_when_not_authenticated(self, mock_auth):
        """미인증 상태에서 자동 인증 시도"""
        from api.kis_api_manager import KISAPIManager

        mock_auth.auth.return_value = True
        manager = KISAPIManager()
        manager.is_authenticated = False

        result = manager._ensure_authenticated()
        assert result is True
        assert manager.is_authenticated is True

    @patch('api.kis_api_manager.now_kst')
    @patch('api.kis_api_manager.kis_auth')
    def test_ensure_authenticated_token_refresh(self, mock_auth, mock_now):
        """토큰 갱신 (1시간 경과)"""
        from api.kis_api_manager import KISAPIManager

        mock_auth.auth.return_value = True

        now = datetime(2024, 1, 15, 10, 0, 0, tzinfo=timezone(timedelta(hours=9)))
        mock_now.return_value = now

        manager = KISAPIManager()
        manager.is_authenticated = True
        manager.last_auth_time = now - timedelta(hours=2)  # 2시간 전

        result = manager._ensure_authenticated()
        assert result is True
        mock_auth.auth.assert_called_once()


class TestOrderResultDataclass:
    """OrderResult 데이터 클래스 테스트"""

    def test_order_result_success(self):
        """성공 OrderResult"""
        from api.kis_api_manager import OrderResult

        result = OrderResult(success=True, order_id="ORD-001", message="주문 성공")
        assert result.success is True
        assert result.order_id == "ORD-001"

    def test_order_result_failure(self):
        """실패 OrderResult"""
        from api.kis_api_manager import OrderResult

        result = OrderResult(success=False, message="잔고 부족", error_code="E001")
        assert result.success is False
        assert result.error_code == "E001"

    def test_order_result_defaults(self):
        """OrderResult 기본값"""
        from api.kis_api_manager import OrderResult

        result = OrderResult(success=True)
        assert result.order_id == ""
        assert result.message == ""
        assert result.error_code == ""
        assert result.data is None


class TestStockPriceDataclass:
    """StockPrice 데이터 클래스 테스트"""

    def test_stock_price_creation(self):
        """StockPrice 생성"""
        from api.kis_api_manager import StockPrice

        now = datetime.now()
        price = StockPrice(
            stock_code="005930",
            current_price=70000.0,
            change_amount=500.0,
            change_rate=0.72,
            volume=10000000,
            timestamp=now
        )
        assert price.stock_code == "005930"
        assert price.current_price == 70000.0
        assert price.volume == 10000000


class TestAccountInfoDataclass:
    """AccountInfo 데이터 클래스 테스트"""

    def test_account_info_creation(self):
        """AccountInfo 생성"""
        from api.kis_api_manager import AccountInfo

        info = AccountInfo(
            account_balance=10000000,
            available_amount=8000000,
            stock_value=2000000,
            total_value=10000000,
            positions=[{'stock_code': '005930'}]
        )
        assert info.available_amount == 8000000
        assert len(info.positions) == 1
