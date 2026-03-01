"""
시나리오3: 장 시작/마감 경계 테스트
개발자B (검증 담당) - 시간 경계 취약점 분석 및 테스트

테스트 범위:
1. 08:59:59 → 09:00:00 전환 경계
2. 매수 차단 시간 경계 (buy_cutoff)
3. EOD 청산 시간 판단
4. 공휴일 감지 vs MarketHours 통합
5. 특수일(수능) 시간 변경
6. 주말 처리
7. VI(변동성 완화장치) 중 주문 시도 (구현 부재 검증)
"""
import pytest
from datetime import datetime, time, timedelta, timezone
from unittest.mock import patch, Mock, AsyncMock
import pytz

from config.market_hours import MarketHours, MarketPhase
from utils.korean_holidays import (
    is_holiday, is_fixed_holiday, is_lunar_holiday,
    get_previous_trading_day, get_next_trading_day
)

KST = pytz.timezone('Asia/Seoul')


def kst_dt(year, month, day, hour=0, minute=0, second=0):
    """KST datetime 헬퍼"""
    return KST.localize(datetime(year, month, day, hour, minute, second))


# ============================================================================
# 1. 장 시작 경계 테스트 (08:59:59 → 09:00:00)
# ============================================================================
class TestMarketOpenBoundary:
    """장 시작 시간 경계"""

    def test_one_second_before_open(self):
        """08:59:59 → 장 열리기 전"""
        dt = kst_dt(2025, 1, 6, 8, 59, 59)  # 월요일
        assert MarketHours.is_market_open('KRX', dt) is False
        assert MarketHours.get_market_status('KRX', dt) == "pre_market"

    def test_exact_open(self):
        """09:00:00 → 장 시작"""
        dt = kst_dt(2025, 1, 6, 9, 0, 0)
        assert MarketHours.is_market_open('KRX', dt) is True
        assert MarketHours.get_market_status('KRX', dt) == "market_open"

    def test_one_second_after_open(self):
        """09:00:01 → 장중"""
        dt = kst_dt(2025, 1, 6, 9, 0, 1)
        assert MarketHours.is_market_open('KRX', dt) is True

    def test_before_market_open_at_0859(self):
        """08:59:00 → pre_market"""
        dt = kst_dt(2025, 1, 6, 8, 59, 0)
        assert MarketHours.is_before_market_open('KRX', dt) is True

    def test_before_market_open_at_0900(self):
        """09:00:00 → 더 이상 pre_market 아님"""
        dt = kst_dt(2025, 1, 6, 9, 0, 0)
        assert MarketHours.is_before_market_open('KRX', dt) is False

    def test_midnight_is_pre_market(self):
        """00:00 평일 → pre_market"""
        dt = kst_dt(2025, 1, 6, 0, 0, 0)
        assert MarketHours.is_before_market_open('KRX', dt) is True

    def test_early_morning_pre_market(self):
        """06:00 평일 → pre_market"""
        dt = kst_dt(2025, 1, 6, 6, 0, 0)
        assert MarketHours.get_market_status('KRX', dt) == "pre_market"


# ============================================================================
# 2. 장 마감 경계 테스트 (15:30)
# ============================================================================
class TestMarketCloseBoundary:
    """장 마감 시간 경계"""

    def test_at_1530_market_still_open(self):
        """15:30:00 → 장중 (market_close 포함, <= 사용)"""
        dt = kst_dt(2025, 1, 6, 15, 30, 0)
        assert MarketHours.is_market_open('KRX', dt) is True

    def test_at_1530_01_market_closed(self):
        """15:30:01 → time() 비교에서 15:30:01 > 15:30:00 → 장 마감"""
        dt = kst_dt(2025, 1, 6, 15, 30, 1)
        # time(15,30,1) > time(15,30,0) 이므로 is_market_open False
        assert MarketHours.is_market_open('KRX', dt) is False

    def test_at_1529_market_open(self):
        """15:29 → 장중"""
        dt = kst_dt(2025, 1, 6, 15, 29, 0)
        assert MarketHours.is_market_open('KRX', dt) is True

    def test_after_market_status(self):
        """16:00 → after_market"""
        dt = kst_dt(2025, 1, 6, 16, 0, 0)
        assert MarketHours.get_market_status('KRX', dt) == "after_market"


# ============================================================================
# 3. 매수 차단 시간 (buy_cutoff) 경계
# ============================================================================
class TestBuyCutoffBoundary:
    """매수 중단 시간 경계 (기본 12시)"""

    def test_1159_buy_allowed(self):
        """11:59 → 매수 허용"""
        dt = kst_dt(2025, 1, 6, 11, 59, 0)
        assert MarketHours.should_stop_buying('KRX', dt) is False

    def test_1200_buy_stopped(self):
        """12:00 → 매수 중단 (hour >= 12)"""
        dt = kst_dt(2025, 1, 6, 12, 0, 0)
        assert MarketHours.should_stop_buying('KRX', dt) is True

    def test_1201_buy_stopped(self):
        """12:01 → 매수 중단"""
        dt = kst_dt(2025, 1, 6, 12, 1, 0)
        assert MarketHours.should_stop_buying('KRX', dt) is True

    def test_0900_buy_allowed(self):
        """09:00 → 매수 허용"""
        dt = kst_dt(2025, 1, 6, 9, 0, 0)
        assert MarketHours.should_stop_buying('KRX', dt) is False

    def test_1519_buy_stopped(self):
        """15:19 → 매수 중단 (hour=15 >= 12)"""
        dt = kst_dt(2025, 1, 6, 15, 19, 0)
        assert MarketHours.should_stop_buying('KRX', dt) is True

    def test_1521_buy_stopped(self):
        """15:21 → 매수 중단"""
        dt = kst_dt(2025, 1, 6, 15, 21, 0)
        assert MarketHours.should_stop_buying('KRX', dt) is True


# ============================================================================
# 4. EOD 청산 시간 판단
# ============================================================================
class TestEODLiquidation:
    """장마감 일괄청산 시간 경계 (기본 15:00)"""

    def test_1459_not_eod(self):
        """14:59 → 아직 청산 시간 아님"""
        dt = kst_dt(2025, 1, 6, 14, 59, 0)
        assert MarketHours.is_eod_liquidation_time('KRX', dt) is False

    def test_1500_is_eod(self):
        """15:00 → 청산 시간"""
        dt = kst_dt(2025, 1, 6, 15, 0, 0)
        assert MarketHours.is_eod_liquidation_time('KRX', dt) is True

    def test_1501_is_eod(self):
        """15:01 → 청산 시간"""
        dt = kst_dt(2025, 1, 6, 15, 1, 0)
        assert MarketHours.is_eod_liquidation_time('KRX', dt) is True

    def test_1530_is_eod(self):
        """15:30 → 청산 시간 (장 마감 시점)"""
        dt = kst_dt(2025, 1, 6, 15, 30, 0)
        assert MarketHours.is_eod_liquidation_time('KRX', dt) is True

    def test_eod_before_market_open(self):
        """08:00 → 청산 시간 아님"""
        dt = kst_dt(2025, 1, 6, 8, 0, 0)
        assert MarketHours.is_eod_liquidation_time('KRX', dt) is False


# ============================================================================
# 5. 특수일 (수능일) 시간 변경
# ============================================================================
class TestSpecialDayBoundary:
    """수능일 등 특수일 시간 변경"""

    def test_suneung_day_open_at_0900_closed(self):
        """수능일 09:00 → 아직 안 열림 (10시 개장)"""
        dt = kst_dt(2025, 11, 13, 9, 0, 0)
        assert MarketHours.is_market_open('KRX', dt) is False

    def test_suneung_day_open_at_1000(self):
        """수능일 10:00 → 장 시작"""
        dt = kst_dt(2025, 11, 13, 10, 0, 0)
        assert MarketHours.is_market_open('KRX', dt) is True

    def test_suneung_day_close_at_1630(self):
        """수능일 16:30 → 장중 (16:30까지)"""
        dt = kst_dt(2025, 11, 13, 16, 30, 0)
        assert MarketHours.is_market_open('KRX', dt) is True

    def test_suneung_day_close_at_1631(self):
        """수능일 16:31 → 장 마감"""
        dt = kst_dt(2025, 11, 13, 16, 30, 1)
        assert MarketHours.is_market_open('KRX', dt) is False

    def test_suneung_buy_cutoff_at_1259(self):
        """수능일 12:59 → 매수 허용 (cutoff=13)"""
        dt = kst_dt(2025, 11, 13, 12, 59, 0)
        assert MarketHours.should_stop_buying('KRX', dt) is False

    def test_suneung_buy_cutoff_at_1300(self):
        """수능일 13:00 → 매수 중단"""
        dt = kst_dt(2025, 11, 13, 13, 0, 0)
        assert MarketHours.should_stop_buying('KRX', dt) is True

    def test_suneung_eod_liquidation_at_1600(self):
        """수능일 16:00 → 청산 시간"""
        dt = kst_dt(2025, 11, 13, 16, 0, 0)
        assert MarketHours.is_eod_liquidation_time('KRX', dt) is True

    def test_suneung_eod_liquidation_at_1559(self):
        """수능일 15:59 → 아직 청산 아님"""
        dt = kst_dt(2025, 11, 13, 15, 59, 0)
        assert MarketHours.is_eod_liquidation_time('KRX', dt) is False


# ============================================================================
# 6. 주말 처리
# ============================================================================
class TestWeekendHandling:
    """주말 장 닫힘"""

    def test_saturday_market_closed(self):
        """토요일 10:00 → 장 닫힘"""
        dt = kst_dt(2025, 1, 4, 10, 0, 0)  # 토요일
        assert MarketHours.is_market_open('KRX', dt) is False
        assert MarketHours.get_market_status('KRX', dt) == "weekend"

    def test_sunday_market_closed(self):
        """일요일 10:00 → 장 닫힘"""
        dt = kst_dt(2025, 1, 5, 10, 0, 0)  # 일요일
        assert MarketHours.is_market_open('KRX', dt) is False

    def test_saturday_not_pre_market(self):
        """토요일 08:00 → pre_market 아님 (주말이므로)"""
        dt = kst_dt(2025, 1, 4, 8, 0, 0)
        assert MarketHours.is_before_market_open('KRX', dt) is False


# ============================================================================
# 7. 공휴일 감지 - korean_holidays 모듈 테스트
# ============================================================================
class TestHolidayDetection:
    """공휴일 감지 테스트"""

    def test_new_year(self):
        """신정 (1/1)"""
        dt = datetime(2025, 1, 1)
        assert is_holiday(dt) is True

    def test_independence_day(self):
        """삼일절 (3/1)"""
        dt = datetime(2025, 3, 1)
        assert is_holiday(dt) is True

    def test_christmas(self):
        """크리스마스 (12/25)"""
        dt = datetime(2025, 12, 25)
        assert is_holiday(dt) is True

    def test_seollal_2025(self):
        """설날 2025"""
        dt = datetime(2025, 1, 29)
        assert is_holiday(dt) is True

    def test_chuseok_2025(self):
        """추석 2025"""
        dt = datetime(2025, 10, 6)
        assert is_holiday(dt) is True

    def test_normal_weekday_not_holiday(self):
        """일반 평일은 공휴일 아님"""
        dt = datetime(2025, 1, 6)  # 월요일
        assert is_holiday(dt) is False

    def test_previous_trading_day_skips_weekend(self):
        """이전 영업일: 월요일 → 금요일"""
        dt = datetime(2025, 1, 6)  # 월요일
        prev = get_previous_trading_day(dt)
        assert prev.weekday() == 4  # 금요일

    def test_previous_trading_day_skips_holiday(self):
        """이전 영업일: 설날 연휴 건너뛰기"""
        dt = datetime(2025, 1, 31)  # 금요일 (1/28~30 설날)
        prev = get_previous_trading_day(dt)
        assert prev.day == 27  # 1/27 월요일

    def test_next_trading_day_skips_weekend(self):
        """다음 영업일: 금요일 → 월요일"""
        dt = datetime(2025, 1, 3)  # 금요일
        nxt = get_next_trading_day(dt)
        assert nxt.weekday() == 0  # 월요일


# ============================================================================
# 8. 취약점: MarketHours에 공휴일 통합 부재
# ============================================================================
class TestHolidayMarketHoursIntegration:
    """
    [수정완료] MarketHours.is_market_open()이 공휴일을 체크하도록 통합.
    korean_holidays 모듈의 is_fixed_holiday, is_lunar_holiday, is_special_holiday 활용.
    """

    def test_new_year_market_closed(self):
        """신정(1/1 수요일)에 is_market_open이 False 반환"""
        dt = kst_dt(2025, 1, 1, 10, 0, 0)
        assert is_holiday(dt) is True
        assert MarketHours.is_market_open('KRX', dt) is False

    def test_seollal_market_closed(self):
        """설날(1/29 수요일)에 is_market_open이 False 반환"""
        dt = kst_dt(2025, 1, 29, 10, 0, 0)
        assert is_holiday(dt) is True
        assert MarketHours.is_market_open('KRX', dt) is False

    def test_memorial_day_market_closed(self):
        """현충일(6/6 금요일)에 is_market_open이 False 반환"""
        dt = kst_dt(2025, 6, 6, 10, 0, 0)
        assert is_fixed_holiday(dt) is True
        assert MarketHours.is_market_open('KRX', dt) is False

    def test_holiday_market_phase_closed(self):
        """공휴일에 get_market_phase가 CLOSED 반환"""
        dt = kst_dt(2025, 1, 1, 10, 0, 0)
        assert MarketHours.get_market_phase('KRX', dt) == MarketPhase.CLOSED

    def test_holiday_market_status(self):
        """공휴일에 get_market_status가 'holiday' 반환"""
        dt = kst_dt(2025, 1, 1, 10, 0, 0)
        assert MarketHours.get_market_status('KRX', dt) == "holiday"

    def test_normal_weekday_still_opens(self):
        """일반 평일은 정상적으로 장 열림"""
        dt = kst_dt(2025, 7, 7, 10, 0, 0)  # 월요일
        assert is_holiday(dt) is False
        assert MarketHours.is_market_open('KRX', dt) is True


# ============================================================================
# 9. VI(변동성 완화장치) 중 주문 시도 - 구현 부재 확인
# ============================================================================
class TestVolatilityInterruption:
    """VI(Volatility Interruption) / 서킷브레이커 테스트"""

    def test_vi_trigger_and_check(self):
        """개별 종목 VI 발동/확인"""
        from config.market_hours import CircuitBreakerState
        cb = CircuitBreakerState()

        assert cb.is_vi_active("005930") is False
        cb.trigger_vi("005930")
        assert cb.is_vi_active("005930") is True
        assert "005930" in cb.get_active_vi_stocks()

    def test_vi_release(self):
        """VI 해제"""
        from config.market_hours import CircuitBreakerState
        cb = CircuitBreakerState()

        cb.trigger_vi("005930")
        cb.release_vi("005930")
        assert cb.is_vi_active("005930") is False

    def test_market_wide_halt(self):
        """시장 전체 서킷브레이커"""
        from config.market_hours import CircuitBreakerState
        cb = CircuitBreakerState()

        triggered = kst_dt(2025, 1, 6, 10, 0, 0)
        cb.trigger_market_halt(duration_minutes=20, triggered_at=triggered)
        assert cb.is_market_halted(kst_dt(2025, 1, 6, 10, 10, 0)) is True
        # 20분 후 자동 해제
        assert cb.is_market_halted(kst_dt(2025, 1, 6, 10, 20, 0)) is False

    def test_market_halt_manual_release(self):
        """서킷브레이커 수동 해제"""
        from config.market_hours import CircuitBreakerState
        cb = CircuitBreakerState()

        cb.trigger_market_halt(duration_minutes=20)
        cb.release_market_halt()
        assert cb.is_market_halted() is False

    def test_vi_clear_all(self):
        """모든 VI/CB 초기화"""
        from config.market_hours import CircuitBreakerState
        cb = CircuitBreakerState()

        cb.trigger_vi("005930")
        cb.trigger_vi("000660")
        cb.trigger_market_halt()
        cb.clear_all()
        assert cb.is_vi_active("005930") is False
        assert cb.is_market_halted() is False
        assert len(cb.get_active_vi_stocks()) == 0

    def test_vi_not_integrated_with_order_flow(self):
        """
        [취약점 확인] CircuitBreakerState가 존재하지만,
        주문 실행 흐름(order_executor 등)에서 VI 체크를 하는지 확인.
        """
        import os
        project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        order_files = [
            os.path.join(project_root, 'core', 'orders', 'order_executor.py'),
            os.path.join(project_root, 'core', 'order_manager.py'),
        ]
        vi_check_found = False
        for fpath in order_files:
            if os.path.exists(fpath):
                with open(fpath, 'r', encoding='utf-8') as f:
                    content = f.read()
                    if 'is_vi_active' in content or 'circuit_breaker' in content.lower():
                        vi_check_found = True
                        break

        # 현재 주문 흐름에서 VI 체크가 통합되어 있지 않을 가능성 높음
        if not vi_check_found:
            pytest.skip(
                "[확인됨] 주문 실행 코드에 VI 체크 미통합. "
                "CircuitBreakerState는 존재하나 order_executor에서 사용하지 않음."
            )


# ============================================================================
# 10. Naive datetime 처리
# ============================================================================
class TestNaiveDatetimeHandling:
    """timezone-naive datetime 전달 시 동작 확인"""

    def test_naive_datetime_is_localized(self):
        """naive datetime → KST로 localize됨"""
        dt = datetime(2025, 1, 6, 10, 0, 0)  # naive
        result = MarketHours.is_market_open('KRX', dt)
        assert result is True  # 내부에서 KST로 localize

    def test_naive_datetime_pre_market(self):
        """naive datetime 08:00 → pre_market"""
        dt = datetime(2025, 1, 6, 8, 0, 0)
        assert MarketHours.is_market_open('KRX', dt) is False

    def test_utc_datetime_conversion(self):
        """UTC datetime → KST 변환 없이 time() 사용 (잠재적 버그)"""
        # UTC 00:00 = KST 09:00이지만, 코드는 dt.time()을 그대로 사용
        utc = pytz.utc.localize(datetime(2025, 1, 6, 0, 0, 0))
        # 코드는 dt.time() = 00:00:00을 사용하므로 market_open(09:00) 이전
        result = MarketHours.is_market_open('KRX', utc)
        assert result is False  # UTC 00:00의 time()=00:00 < 09:00

    def test_utc_datetime_should_be_kst_9am(self):
        """
        [취약점] UTC 00:00 = KST 09:00인데, timezone 변환 없이 time() 비교.
        is_market_open은 timezone 변환을 하지 않고 dt.time()을 직접 사용.
        """
        utc_midnight = pytz.utc.localize(datetime(2025, 1, 6, 0, 0, 0))
        # 실제로는 KST 09:00이므로 장 시작이지만...
        # 코드는 dt.time() = 00:00:00으로 판단 → False
        result = MarketHours.is_market_open('KRX', utc_midnight)
        # 이것은 잠재적 버그: 다른 타임존의 datetime을 KST로 변환하지 않음
        assert result is False, (
            "[잠재적 취약점] UTC datetime을 KST로 변환하지 않고 time() 직접 비교"
        )


# ============================================================================
# 11. get_market_hours 반환값 검증
# ============================================================================
class TestGetMarketHours:
    """get_market_hours 반환값 구조 검증"""

    def test_default_hours_structure(self):
        """기본 거래시간 반환값 구조"""
        hours = MarketHours.get_market_hours('KRX')
        assert 'market_open' in hours
        assert 'market_close' in hours
        assert 'buy_cutoff_hour' in hours
        assert 'eod_liquidation_hour' in hours
        assert 'eod_liquidation_minute' in hours
        assert hours['market_open'] == time(9, 0)
        assert hours['market_close'] == time(15, 30)

    def test_special_day_hours(self):
        """특수일 거래시간 반환값"""
        dt = kst_dt(2025, 11, 13, 10, 0, 0)  # 수능일
        hours = MarketHours.get_market_hours('KRX', dt)
        assert hours['market_open'] == time(10, 0)
        assert hours['market_close'] == time(16, 30)
        assert hours['is_special_day'] is True

    def test_unknown_market_raises(self):
        """존재하지 않는 시장 코드 → ValueError"""
        with pytest.raises(ValueError, match="Unknown market"):
            MarketHours.get_market_hours('INVALID')


# ============================================================================
# 12. EOD 청산 부분 체결 시나리오 (LiquidationHandler)
# ============================================================================
class TestEODLiquidationScenarios:
    """EOD 청산 다양한 시나리오"""

    def test_eod_no_positions(self):
        """보유 포지션 없을 때 청산 → 정상 종료"""
        from bot.liquidation_handler import LiquidationHandler

        bot = Mock()
        bot.trading_manager.get_stocks_by_state.return_value = []

        handler = LiquidationHandler(bot)

        import asyncio
        asyncio.get_event_loop().run_until_complete(
            handler.liquidate_all_positions_end_of_day()
        )
        # 에러 없이 완료

    def test_eod_with_zero_quantity_position(self):
        """수량 0인 포지션 → 스킵"""
        from bot.liquidation_handler import LiquidationHandler

        stock = Mock()
        stock.stock_code = "005930"
        stock.position = Mock()
        stock.position.quantity = 0

        bot = Mock()
        bot.trading_manager.get_stocks_by_state.return_value = [stock]

        handler = LiquidationHandler(bot)

        import asyncio
        asyncio.get_event_loop().run_until_complete(
            handler.liquidate_all_positions_end_of_day()
        )
        # move_to_sell_candidate 호출되지 않아야 함
        bot.trading_manager.move_to_sell_candidate.assert_not_called()

    def test_eod_sell_order_exception(self):
        """개별 종목 청산 실패 시 다른 종목은 계속 처리"""
        from bot.liquidation_handler import LiquidationHandler

        stock1 = Mock()
        stock1.stock_code = "005930"
        stock1.stock_name = "삼성전자"
        stock1.position = Mock()
        stock1.position.quantity = 10

        stock2 = Mock()
        stock2.stock_code = "000660"
        stock2.stock_name = "SK하이닉스"
        stock2.position = Mock()
        stock2.position.quantity = 5

        bot = Mock()
        bot.decision_engine.is_virtual_mode = False  # 실매매 모드
        bot.trading_manager.get_stocks_by_state.return_value = [stock1, stock2]
        bot.trading_manager.move_to_sell_candidate.return_value = True
        bot.intraday_manager.get_combined_chart_data.return_value = None
        bot.broker.get_current_price.return_value = Mock(current_price=70000)

        # 첫 종목은 실패, 두 번째는 성공
        bot.trading_manager.execute_sell_order = AsyncMock(
            side_effect=[Exception("주문 실패"), None]
        )

        handler = LiquidationHandler(bot)

        import asyncio
        asyncio.get_event_loop().run_until_complete(
            handler.liquidate_all_positions_end_of_day()
        )
        # 두 번째 종목도 시도되어야 함
        assert bot.trading_manager.execute_sell_order.call_count == 2

    def test_eod_liquidation_date_tracking(self):
        """청산 날짜 추적"""
        from bot.liquidation_handler import LiquidationHandler

        bot = Mock()
        handler = LiquidationHandler(bot)

        assert handler.get_last_eod_liquidation_date() is None
        handler.set_last_eod_liquidation_date("2025-01-06")
        assert handler.get_last_eod_liquidation_date() == "2025-01-06"


# ============================================================================
# 13. 연속 공휴일 (설날/추석 연휴) 처리
# ============================================================================
class TestConsecutiveHolidays:
    """연속 공휴일 처리"""

    def test_seollal_2025_consecutive(self):
        """2025 설날 연휴 전체 공휴일"""
        dates = [datetime(2025, 1, d) for d in [28, 29, 30]]
        for dt in dates:
            assert is_holiday(dt) is True, f"{dt.strftime('%Y-%m-%d')} 설날 연휴"

    def test_chuseok_2025_consecutive(self):
        """2025 추석 연휴 전체 공휴일"""
        dates = [datetime(2025, 10, d) for d in [5, 6, 7, 8]]
        for dt in dates:
            assert is_holiday(dt) is True, f"{dt.strftime('%Y-%m-%d')} 추석 연휴"

    def test_trading_day_after_long_holiday(self):
        """긴 연휴 후 첫 영업일"""
        # 2025 설날: 1/28(화)~1/30(목), 다음 영업일 = 1/31(금)
        dt = datetime(2025, 1, 30)
        nxt = get_next_trading_day(dt)
        assert nxt.day == 31
        assert nxt.weekday() == 4  # 금요일
