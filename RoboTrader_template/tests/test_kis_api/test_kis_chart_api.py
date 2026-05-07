"""
KIS 일봉 API 60일 요청 파라미터 검증 테스트

조사 결과:
- TR: FHKST03010100 (국내주식기간별시세)
- KIS API 1회 호출 최대 100건 반환 (kis_market_api.py:129 docstring 명시)
- days=60 → estimated_trading_days = int(60 * 0.7) = 42 ≤ 100
- → 단일 호출 경로 사용 (get_inquire_daily_itemchartprice)
- → 분기 A: 60일 요청은 1회 호출로 충분, 분할 로직 불필요

테스트:
1. test_daily_chart_request_60days_params: 60일 요청 시 API 파라미터 검증
2. test_ohlcv_60days_uses_single_call: 60일은 단일 호출 경로 사용 확인
3. test_ohlcv_144days_uses_extended_call: 144일(>100 거래일)은 연속조회 경로 사용 확인
"""

import pytest
import pandas as pd
from datetime import datetime, timedelta
from unittest.mock import patch, MagicMock, call
from typing import Optional


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def _make_ohlcv_rows(n: int, base_date: Optional[datetime] = None) -> list:
    """n개의 가짜 일봉 행 생성 (최신 → 과거 순)"""
    if base_date is None:
        base_date = datetime(2026, 4, 11)
    rows = []
    for i in range(n):
        d = (base_date - timedelta(days=i)).strftime("%Y%m%d")
        rows.append({
            "stck_bsop_date": d,
            "stck_oprc": "70000",
            "stck_hgpr": "71000",
            "stck_lwpr": "69000",
            "stck_clpr": "70500",
            "acml_vol": "10000000",
        })
    return rows


def _make_ohlcv_df(n: int, base_date: Optional[datetime] = None) -> pd.DataFrame:
    return pd.DataFrame(_make_ohlcv_rows(n, base_date))


# ---------------------------------------------------------------------------
# 1. 60일 요청 파라미터 검증
# ---------------------------------------------------------------------------

class TestDailyChartRequest60DaysParams:
    """
    get_ohlcv_data(stock_code, 'D', 60) 호출 시
    API 파라미터(FID_INPUT_DATE_1, FID_INPUT_DATE_2)에 60일 범위가 반영되는지 검증
    """

    @patch("api.kis_api_manager.kis_market_api")
    @patch("api.kis_api_manager.kis_auth")
    def test_daily_chart_request_60days_params(self, mock_auth, mock_market):
        """
        KISAPIManager.get_ohlcv_data("005930", "D", 60) 호출 시
        get_inquire_daily_itemchartprice에 전달되는 start_date/end_date가
        오늘 기준 60일 범위인지 검증
        """
        from api.kis_api_manager import KISAPIManager
        from utils.korean_time import now_kst

        mock_auth.auth.return_value = True
        mock_market.get_inquire_daily_itemchartprice.return_value = _make_ohlcv_df(42)

        manager = KISAPIManager()
        manager.is_authenticated = True
        manager.max_retries = 1

        result = manager.get_ohlcv_data("005930", "D", 60)

        # 단일 조회 경로가 호출됐어야 함
        mock_market.get_inquire_daily_itemchartprice.assert_called_once()
        call_args = mock_market.get_inquire_daily_itemchartprice.call_args

        # positional args: output_dv, div_code, itm_no, inqr_strt_dt, inqr_end_dt, period
        args = call_args[0]
        assert len(args) >= 5, f"예상 인자 수 부족: {args}"

        inqr_strt_dt = args[3]  # start_date
        inqr_end_dt = args[4]   # end_date

        today = now_kst()
        expected_start = (today - timedelta(days=60)).strftime("%Y%m%d")
        expected_end = today.strftime("%Y%m%d")

        assert inqr_strt_dt == expected_start, (
            f"시작일 불일치: {inqr_strt_dt} != {expected_start}"
        )
        assert inqr_end_dt == expected_end, (
            f"종료일 불일치: {inqr_end_dt} != {expected_end}"
        )

        assert result is not None
        # 연속조회 경로는 사용하지 않아야 함
        mock_market.get_inquire_daily_itemchartprice_extended.assert_not_called()

    @patch("api.kis_api_manager.kis_market_api")
    @patch("api.kis_api_manager.kis_auth")
    def test_daily_chart_request_returns_sufficient_rows(self, mock_auth, mock_market):
        """
        60일 요청 시 반환 행 수가 22 이상(SampleStrategy 최소 요구치)인지 검증
        """
        from api.kis_api_manager import KISAPIManager
        from config.constants import CANDIDATE_MIN_DAILY_DATA

        mock_auth.auth.return_value = True
        # API가 42개 영업일 반환한다고 가정 (현실적인 60 달력일 범위)
        mock_market.get_inquire_daily_itemchartprice.return_value = _make_ohlcv_df(42)

        manager = KISAPIManager()
        manager.is_authenticated = True
        manager.max_retries = 1

        result = manager.get_ohlcv_data("005930", "D", 60)

        assert result is not None
        assert len(result) >= CANDIDATE_MIN_DAILY_DATA, (
            f"반환 행 수 {len(result)} < CANDIDATE_MIN_DAILY_DATA={CANDIDATE_MIN_DAILY_DATA}"
        )


# ---------------------------------------------------------------------------
# 2. 단일 호출 vs 연속조회 분기 검증
# ---------------------------------------------------------------------------

class TestOhlcvCallRoutingByDays:
    """
    estimated_trading_days > 100 경계 기준 분기 검증
    60일 → 단일 호출, 144일 이상(101/0.7≈144) → 연속조회
    """

    @patch("api.kis_api_manager.kis_market_api")
    @patch("api.kis_api_manager.kis_auth")
    def test_ohlcv_60days_uses_single_call(self, mock_auth, mock_market):
        """
        days=60 → estimated_trading_days=42 ≤ 100 → 단일 호출 경로
        분할 호출(extended) 사용 안 함
        """
        from api.kis_api_manager import KISAPIManager

        mock_auth.auth.return_value = True
        mock_market.get_inquire_daily_itemchartprice.return_value = _make_ohlcv_df(42)

        manager = KISAPIManager()
        manager.is_authenticated = True
        manager.max_retries = 1

        manager.get_ohlcv_data("005930", "D", 60)

        mock_market.get_inquire_daily_itemchartprice.assert_called_once()
        mock_market.get_inquire_daily_itemchartprice_extended.assert_not_called()

    @patch("api.kis_api_manager.kis_market_api")
    @patch("api.kis_api_manager.kis_auth")
    def test_ohlcv_144days_uses_extended_call(self, mock_auth, mock_market):
        """
        days=144 → estimated_trading_days=int(144*0.7)=100 (경계값, ≤100 → 단일)
        days=145 → estimated_trading_days=int(145*0.7)=101 > 100 → 연속조회
        """
        from api.kis_api_manager import KISAPIManager

        mock_auth.auth.return_value = True
        mock_market.get_inquire_daily_itemchartprice_extended.return_value = _make_ohlcv_df(100)

        manager = KISAPIManager()
        manager.is_authenticated = True
        manager.max_retries = 1

        # 145일: int(145*0.7)=101 > 100 → extended 경로
        manager.get_ohlcv_data("005930", "D", 145)

        mock_market.get_inquire_daily_itemchartprice_extended.assert_called_once()
        mock_market.get_inquire_daily_itemchartprice.assert_not_called()

    @patch("api.kis_api_manager.kis_market_api")
    @patch("api.kis_api_manager.kis_auth")
    def test_ohlcv_boundary_144days_uses_single_call(self, mock_auth, mock_market):
        """
        days=144 → estimated_trading_days=int(144*0.7)=100 = 경계값 → 단일 호출
        (> 100 조건이므로 정확히 100은 단일 경로)
        """
        from api.kis_api_manager import KISAPIManager

        mock_auth.auth.return_value = True
        mock_market.get_inquire_daily_itemchartprice.return_value = _make_ohlcv_df(100)

        manager = KISAPIManager()
        manager.is_authenticated = True
        manager.max_retries = 1

        manager.get_ohlcv_data("005930", "D", 144)

        mock_market.get_inquire_daily_itemchartprice.assert_called_once()
        mock_market.get_inquire_daily_itemchartprice_extended.assert_not_called()


# ---------------------------------------------------------------------------
# 3. KIS API 한도(100건) 이해 확인 — 분기 A 근거 문서화 테스트
# ---------------------------------------------------------------------------

class TestKisApiLimitDocumentation:
    """
    KIS FHKST03010100 API 한도 100건/호출 기반으로
    60일(약 42영업일) 요청이 단일 호출로 충분함을 수치로 검증
    """

    def test_60_calendar_days_is_within_single_call_limit(self):
        """
        60 달력일 → ~42 영업일(×0.7) < 100건 한도
        → 1회 호출로 충분: 분기 A 확인
        """
        KIS_API_MAX_RECORDS_PER_CALL = 100  # kis_market_api.py:129 문서화
        DAYS = 60
        estimated_trading_days = int(DAYS * 0.7)  # kis_api_manager.py:350 로직

        assert estimated_trading_days <= KIS_API_MAX_RECORDS_PER_CALL, (
            f"60일 요청의 예상 영업일({estimated_trading_days})이 "
            f"API 한도({KIS_API_MAX_RECORDS_PER_CALL})를 초과합니다 — 분할 호출 필요"
        )

    def test_ohlcv_lookback_days_within_single_call_limit(self):
        """
        constants.OHLCV_LOOKBACK_DAYS(=60)가 단일 호출 한도 내인지 검증
        """
        from config.constants import OHLCV_LOOKBACK_DAYS

        KIS_API_MAX_RECORDS_PER_CALL = 100
        estimated_trading_days = int(OHLCV_LOOKBACK_DAYS * 0.7)

        assert estimated_trading_days <= KIS_API_MAX_RECORDS_PER_CALL, (
            f"OHLCV_LOOKBACK_DAYS={OHLCV_LOOKBACK_DAYS}일 → "
            f"예상 영업일={estimated_trading_days} > {KIS_API_MAX_RECORDS_PER_CALL} "
            f"→ 분할 호출 구현 필요"
        )
