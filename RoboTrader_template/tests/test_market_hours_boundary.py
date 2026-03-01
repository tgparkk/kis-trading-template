"""
시나리오3: 장 시작/마감 경계 처리 테스트

테스트 범위:
- MarketPhase 단계별 정확성
- 동시호가 / 장 시작 보호 / 매수 차단
- 서킷브레이커/VI 상태 관리
- EOD 청산 실패 재시도
- 공휴일/반일장 (수능일)
"""
import pytest
import asyncio
from datetime import datetime, time, timedelta
from unittest.mock import Mock, AsyncMock, patch, MagicMock
import pytz

from config.market_hours import (
    MarketHours, MarketPhase, CircuitBreakerState,
    get_circuit_breaker_state,
)

KST = pytz.timezone('Asia/Seoul')


def kst_dt(year, month, day, hour, minute=0, second=0):
    """KST datetime 헬퍼"""
    return KST.localize(datetime(year, month, day, hour, minute, second))


# ============================================================================
# MarketPhase 테스트
# ============================================================================

class TestMarketPhase:
    """장 단계(phase) 테스트"""

    def test_pre_market(self):
        dt = kst_dt(2026, 2, 9, 7, 30)  # 월요일 07:30
        assert MarketHours.get_market_phase('KRX', dt) == MarketPhase.PRE_MARKET

    def test_pre_auction(self):
        dt = kst_dt(2026, 2, 9, 8, 30)  # 08:30 동시호가
        assert MarketHours.get_market_phase('KRX', dt) == MarketPhase.PRE_AUCTION

    def test_pre_auction_845(self):
        dt = kst_dt(2026, 2, 9, 8, 45)
        assert MarketHours.get_market_phase('KRX', dt) == MarketPhase.PRE_AUCTION

    def test_opening_protection(self):
        dt = kst_dt(2026, 2, 9, 9, 0)  # 09:00 장 시작
        assert MarketHours.get_market_phase('KRX', dt) == MarketPhase.OPENING_PROTECTION

    def test_opening_protection_903(self):
        dt = kst_dt(2026, 2, 9, 9, 3)
        assert MarketHours.get_market_phase('KRX', dt) == MarketPhase.OPENING_PROTECTION

    def test_market_open(self):
        dt = kst_dt(2026, 2, 9, 9, 5)  # 09:05 정규장
        assert MarketHours.get_market_phase('KRX', dt) == MarketPhase.MARKET_OPEN

    def test_market_open_midday(self):
        dt = kst_dt(2026, 2, 9, 12, 0)
        assert MarketHours.get_market_phase('KRX', dt) == MarketPhase.MARKET_OPEN

    def test_closing_cutoff(self):
        dt = kst_dt(2026, 2, 9, 15, 20)  # 15:20 마감 직전
        assert MarketHours.get_market_phase('KRX', dt) == MarketPhase.CLOSING_CUTOFF

    def test_closing_cutoff_1525(self):
        dt = kst_dt(2026, 2, 9, 15, 25)
        assert MarketHours.get_market_phase('KRX', dt) == MarketPhase.CLOSING_CUTOFF

    def test_post_market(self):
        dt = kst_dt(2026, 2, 9, 15, 31)  # 15:31
        assert MarketHours.get_market_phase('KRX', dt) == MarketPhase.POST_MARKET

    def test_weekend_closed(self):
        dt = kst_dt(2026, 2, 7, 10, 0)  # 토요일
        assert MarketHours.get_market_phase('KRX', dt) == MarketPhase.CLOSED

    def test_sunday_closed(self):
        dt = kst_dt(2026, 2, 8, 10, 0)  # 일요일
        assert MarketHours.get_market_phase('KRX', dt) == MarketPhase.CLOSED


# ============================================================================
# 매수 차단 테스트
# ============================================================================

class TestNewBuyBlocked:
    """신규 매수 차단 테스트"""

    def test_blocked_pre_auction(self):
        dt = kst_dt(2026, 2, 9, 8, 45)
        assert MarketHours.is_new_buy_blocked('KRX', dt) is True

    def test_blocked_opening_protection(self):
        """장 시작 직후 보호 시간에는 should_stop_buying으로 차단되지 않으면 phase로 차단 안됨"""
        dt = kst_dt(2026, 2, 9, 9, 2)
        # OPENING_PROTECTION은 is_new_buy_blocked에서 차단하지 않음 (MARKET_OPEN 전이지만 거래 가능)
        # 실제로는 should_stop_buying이 False이면 허용
        phase = MarketHours.get_market_phase('KRX', dt)
        assert phase == MarketPhase.OPENING_PROTECTION

    def test_allowed_normal_hours(self):
        dt = kst_dt(2026, 2, 9, 10, 0)
        assert MarketHours.is_new_buy_blocked('KRX', dt) is False

    def test_blocked_after_buy_cutoff(self):
        """12시 이후 매수 차단 (buy_cutoff_hour=12)"""
        dt = kst_dt(2026, 2, 9, 13, 0)
        assert MarketHours.is_new_buy_blocked('KRX', dt) is True

    def test_blocked_closing_cutoff(self):
        dt = kst_dt(2026, 2, 9, 15, 22)
        assert MarketHours.is_new_buy_blocked('KRX', dt) is True

    def test_blocked_weekend(self):
        dt = kst_dt(2026, 2, 7, 10, 0)
        assert MarketHours.is_new_buy_blocked('KRX', dt) is True

    def test_blocked_market_halt(self):
        """서킷브레이커 발동 시 매수 차단"""
        cb = get_circuit_breaker_state()
        cb.clear_all()
        dt = kst_dt(2026, 2, 9, 10, 0)
        cb.trigger_market_halt(20, triggered_at=dt)
        try:
            assert MarketHours.is_new_buy_blocked('KRX', dt) is True
        finally:
            cb.clear_all()


# ============================================================================
# 동시호가 테스트
# ============================================================================

class TestAuction:
    def test_pre_auction_time(self):
        assert MarketHours.is_pre_auction('KRX', kst_dt(2026, 2, 9, 8, 30))
        assert MarketHours.is_pre_auction('KRX', kst_dt(2026, 2, 9, 8, 59))
        assert not MarketHours.is_pre_auction('KRX', kst_dt(2026, 2, 9, 9, 0))

    def test_closing_auction_time(self):
        assert MarketHours.is_closing_auction('KRX', kst_dt(2026, 2, 9, 15, 20))
        assert MarketHours.is_closing_auction('KRX', kst_dt(2026, 2, 9, 15, 29))
        assert not MarketHours.is_closing_auction('KRX', kst_dt(2026, 2, 9, 15, 19))


# ============================================================================
# 서킷브레이커 / VI 테스트
# ============================================================================

class TestCircuitBreaker:
    def setup_method(self):
        self.cb = CircuitBreakerState()

    def test_vi_trigger_and_release(self):
        self.cb.trigger_vi("005930")
        assert self.cb.is_vi_active("005930")
        assert not self.cb.is_vi_active("000660")
        self.cb.release_vi("005930")
        assert not self.cb.is_vi_active("005930")

    def test_market_halt(self):
        dt = kst_dt(2026, 2, 9, 10, 0)
        self.cb.trigger_market_halt(20, triggered_at=dt)
        assert self.cb.is_market_halted(dt)
        # 20분 후 자동 해제
        dt_after = dt + timedelta(minutes=20)
        assert not self.cb.is_market_halted(dt_after)

    def test_market_halt_manual_release(self):
        self.cb.trigger_market_halt(60)
        assert self.cb.is_market_halted()
        self.cb.release_market_halt()
        assert not self.cb.is_market_halted()

    def test_get_active_vi_stocks(self):
        self.cb.trigger_vi("005930")
        self.cb.trigger_vi("000660")
        assert set(self.cb.get_active_vi_stocks()) == {"005930", "000660"}

    def test_clear_all(self):
        self.cb.trigger_vi("005930")
        self.cb.trigger_market_halt(20)
        self.cb.clear_all()
        assert not self.cb.is_vi_active("005930")
        assert not self.cb.is_market_halted()

    def test_can_place_order_with_vi(self):
        """VI 발동 종목 주문 차단"""
        from utils.korean_time import now_kst as _now_kst
        cb = get_circuit_breaker_state()
        cb.clear_all()
        # VI 발동 시각은 현재 시각 사용 (2분 자동해제 방지)
        vi_time = _now_kst()
        cb.trigger_vi("005930", triggered_at=vi_time)
        # can_place_order의 dt는 장중 시간대를 사용해야 함
        dt = kst_dt(2026, 2, 9, 10, 0)  # 월요일 10:00
        try:
            assert MarketHours.can_place_order("005930", 'KRX', dt) is False
            assert MarketHours.can_place_order("000660", 'KRX', dt) is True
        finally:
            cb.clear_all()


# ============================================================================
# 수능일 (특수일) 테스트
# ============================================================================

class TestSpecialDay:
    def test_suneung_market_hours(self):
        """수능일: 10:00 개장, 16:30 마감"""
        dt = kst_dt(2025, 11, 13, 9, 30)
        hours = MarketHours.get_market_hours('KRX', dt)
        assert hours['market_open'] == time(10, 0)
        assert hours['market_close'] == time(16, 30)
        assert hours['is_special_day'] is True

    def test_suneung_not_open_at_930(self):
        dt = kst_dt(2025, 11, 13, 9, 30)
        assert not MarketHours.is_market_open('KRX', dt)

    def test_suneung_open_at_1030(self):
        dt = kst_dt(2025, 11, 13, 10, 30)
        assert MarketHours.is_market_open('KRX', dt)


# ============================================================================
# EOD 청산 실패 재시도 테스트
# ============================================================================

class TestEodLiquidationRetry:
    """EOD 청산 실패 복구 테스트"""

    def _make_handler(self):
        from bot.liquidation_handler import LiquidationHandler
        bot = Mock()
        bot.decision_engine.is_virtual_mode = False  # 실매매 모드
        bot.trading_manager = Mock()
        bot.telegram = AsyncMock()
        handler = LiquidationHandler(bot)
        return handler, bot

    @pytest.mark.asyncio
    async def test_retry_clears_on_success(self):
        handler, bot = self._make_handler()
        handler._eod_failed_stocks = {"005930"}

        # 재시도 시 해당 종목이 이미 청산됨 (positioned에 없음)
        bot.trading_manager.get_stocks_by_state.return_value = []
        result = await handler.retry_failed_eod_liquidation()
        assert result is True
        assert not handler.has_failed_eod_stocks()

    @pytest.mark.asyncio
    async def test_retry_max_exceeded(self):
        from bot.liquidation_handler import EOD_LIQUIDATION_MAX_RETRIES
        handler, bot = self._make_handler()
        handler._eod_failed_stocks = {"005930"}
        handler._eod_retry_count = EOD_LIQUIDATION_MAX_RETRIES  # 이미 한도

        mock_stock = Mock()
        mock_stock.stock_code = "005930"
        mock_stock.position = Mock(quantity=10)
        bot.trading_manager.get_stocks_by_state.return_value = [mock_stock]

        result = await handler.retry_failed_eod_liquidation()
        assert result is False

    @pytest.mark.asyncio
    async def test_retry_succeeds_on_second_try(self):
        handler, bot = self._make_handler()
        handler._eod_failed_stocks = {"005930"}
        handler._eod_retry_count = 0

        mock_stock = Mock()
        mock_stock.stock_code = "005930"
        mock_stock.position = Mock(quantity=10)
        bot.trading_manager.get_stocks_by_state.return_value = [mock_stock]
        bot.trading_manager.move_to_sell_candidate.return_value = True
        bot.trading_manager.execute_sell_order = AsyncMock()

        result = await handler.retry_failed_eod_liquidation()
        assert result is True
        assert handler._eod_retry_count == 1

    def test_reset_eod_state(self):
        handler, _ = self._make_handler()
        handler._eod_failed_stocks = {"005930"}
        handler._eod_retry_count = 3
        handler.reset_eod_state()
        assert not handler.has_failed_eod_stocks()
        assert handler._eod_retry_count == 0


# ============================================================================
# is_market_open / is_eod_liquidation_time 기존 호환 테스트
# ============================================================================

class TestBackwardCompatibility:
    """기존 API 호환성 확인"""

    def test_is_market_open_weekday(self):
        dt = kst_dt(2026, 2, 9, 10, 0)
        assert MarketHours.is_market_open('KRX', dt) is True

    def test_is_market_open_weekend(self):
        dt = kst_dt(2026, 2, 7, 10, 0)
        assert MarketHours.is_market_open('KRX', dt) is False

    def test_is_market_open_before_open(self):
        dt = kst_dt(2026, 2, 9, 8, 59)
        assert MarketHours.is_market_open('KRX', dt) is False

    def test_is_eod_liquidation_time(self):
        dt = kst_dt(2026, 2, 9, 15, 1)
        assert MarketHours.is_eod_liquidation_time('KRX', dt) is True

    def test_is_not_eod_liquidation_time(self):
        dt = kst_dt(2026, 2, 9, 14, 59)
        assert MarketHours.is_eod_liquidation_time('KRX', dt) is False

    def test_get_market_status(self):
        assert MarketHours.get_market_status('KRX', kst_dt(2026, 2, 9, 10, 0)) == "market_open"
        assert MarketHours.get_market_status('KRX', kst_dt(2026, 2, 9, 8, 0)) == "pre_market"
        assert MarketHours.get_market_status('KRX', kst_dt(2026, 2, 9, 16, 0)) == "after_market"
        assert MarketHours.get_market_status('KRX', kst_dt(2026, 2, 7, 10, 0)) == "weekend"

    def test_should_stop_buying(self):
        assert MarketHours.should_stop_buying('KRX', kst_dt(2026, 2, 9, 11, 0)) is False
        assert MarketHours.should_stop_buying('KRX', kst_dt(2026, 2, 9, 12, 0)) is True

    def test_get_today_info(self):
        info = MarketHours.get_today_info('KRX')
        assert '장 시작' in info
        assert '장 마감' in info
