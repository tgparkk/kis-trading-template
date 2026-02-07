"""
Framework Utils Tests
=====================

Tests for framework/utils.py

Test Requirements:
- test_now_kst(): Korean time return test
- test_is_market_open(): Market hours determination test
- test_round_to_tick(): Tick size rounding test
- test_format_price(): Price formatting test
"""

import pytest
from datetime import datetime, timezone, timedelta, time

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from framework.utils import (
    KST,
    now_kst,
    is_market_open,
    get_market_status,
    get_market_open_time,
    get_market_close_time,
    get_tick_size,
    round_to_tick,
    validate_tick,
    format_price,
    format_quantity,
    format_currency,
    format_percentage,
    calculate_change_rate,
)


# ============================================================================
# Test: test_now_kst()
# ============================================================================

class TestNowKst:
    """Tests for now_kst() function - Korean time return test."""

    def test_now_kst_returns_datetime(self):
        """Test that now_kst returns a datetime object."""
        result = now_kst()
        assert isinstance(result, datetime)

    def test_now_kst_has_kst_timezone(self):
        """Test that now_kst returns datetime with KST timezone."""
        result = now_kst()
        assert result.tzinfo == KST

    def test_kst_timezone_offset_is_9_hours(self):
        """Test KST timezone offset is +9 hours."""
        assert KST.utcoffset(None) == timedelta(hours=9)

    def test_now_kst_returns_current_time(self):
        """Test now_kst returns approximately current time."""
        before = datetime.now(KST)
        result = now_kst()
        after = datetime.now(KST)

        assert before <= result <= after

    def test_now_kst_timezone_aware(self):
        """Test now_kst returns timezone-aware datetime."""
        result = now_kst()
        assert result.tzinfo is not None


# ============================================================================
# Test: test_is_market_open()
# ============================================================================

class TestIsMarketOpen:
    """Tests for is_market_open() function - Market hours determination test."""

    def test_is_market_open_weekday_trading_hours(self):
        """Test market is open during trading hours on weekday (09:00-15:30)."""
        # Monday 10:00 KST
        dt = datetime(2024, 1, 15, 10, 0, 0, tzinfo=KST)  # Monday
        assert is_market_open(dt) is True

    def test_is_market_open_at_market_open(self):
        """Test market is open at exactly 09:00."""
        dt = datetime(2024, 1, 15, 9, 0, 0, tzinfo=KST)  # Monday
        assert is_market_open(dt) is True

    def test_is_market_open_at_market_close(self):
        """Test market is open at exactly 15:30."""
        dt = datetime(2024, 1, 15, 15, 30, 0, tzinfo=KST)  # Monday
        assert is_market_open(dt) is True

    def test_is_market_open_weekend_saturday(self):
        """Test market is closed on Saturday."""
        dt = datetime(2024, 1, 13, 10, 0, 0, tzinfo=KST)  # Saturday
        assert is_market_open(dt) is False

    def test_is_market_open_weekend_sunday(self):
        """Test market is closed on Sunday."""
        dt = datetime(2024, 1, 14, 10, 0, 0, tzinfo=KST)  # Sunday
        assert is_market_open(dt) is False

    def test_is_market_open_before_open(self):
        """Test market is closed before 09:00."""
        dt = datetime(2024, 1, 15, 8, 59, 59, tzinfo=KST)
        assert is_market_open(dt) is False

    def test_is_market_open_after_close(self):
        """Test market is closed after 15:30."""
        dt = datetime(2024, 1, 15, 15, 30, 1, tzinfo=KST)
        assert is_market_open(dt) is False

    def test_is_market_open_default_current_time(self):
        """Test is_market_open uses current time if none provided."""
        # This just verifies it doesn't raise an error
        result = is_market_open()
        assert isinstance(result, bool)

    def test_is_market_open_noon(self):
        """Test market is open at noon."""
        dt = datetime(2024, 1, 15, 12, 0, 0, tzinfo=KST)  # Monday noon
        assert is_market_open(dt) is True

    def test_get_market_status_returns_correct_status(self):
        """Test get_market_status returns correct status strings."""
        # Market open
        dt_open = datetime(2024, 1, 15, 10, 0, 0, tzinfo=KST)
        assert get_market_status(dt_open) == 'OPEN'

        # Pre-market
        dt_pre = datetime(2024, 1, 15, 8, 30, 0, tzinfo=KST)
        assert get_market_status(dt_pre) == 'PRE_MARKET'

        # Post-market
        dt_post = datetime(2024, 1, 15, 16, 0, 0, tzinfo=KST)
        assert get_market_status(dt_post) == 'POST_MARKET'

        # Weekend
        dt_weekend = datetime(2024, 1, 13, 10, 0, 0, tzinfo=KST)
        assert get_market_status(dt_weekend) == 'CLOSED'

    def test_get_market_open_time(self):
        """Test get_market_open_time returns 09:00."""
        result = get_market_open_time()
        assert result == time(9, 0)

    def test_get_market_close_time(self):
        """Test get_market_close_time returns 15:30."""
        result = get_market_close_time()
        assert result == time(15, 30)


# ============================================================================
# Test: test_round_to_tick()
# ============================================================================

class TestRoundToTick:
    """Tests for round_to_tick() function - Tick size rounding test."""

    def test_round_to_tick_under_1000(self):
        """Test tick size of 1 won for prices under 1000."""
        assert round_to_tick(500) == 500
        assert round_to_tick(500.4) == 500
        assert round_to_tick(500.5) == 501
        assert round_to_tick(500.6) == 501
        assert round_to_tick(999) == 999
        assert round_to_tick(1) == 1

    def test_round_to_tick_1000_to_5000(self):
        """Test tick size of 5 won for prices 1000-4999."""
        assert round_to_tick(1000) == 1000
        assert round_to_tick(1002) == 1000
        assert round_to_tick(1003) == 1005
        assert round_to_tick(1005) == 1005
        assert round_to_tick(4997) == 4995
        assert round_to_tick(4998) == 5000

    def test_round_to_tick_5000_to_10000(self):
        """Test tick size of 10 won for prices 5000-9999."""
        assert round_to_tick(5000) == 5000
        assert round_to_tick(5004) == 5000
        assert round_to_tick(5005) == 5010
        assert round_to_tick(9995) == 10000
        assert round_to_tick(9990) == 9990

    def test_round_to_tick_10000_to_50000(self):
        """Test tick size of 50 won for prices 10000-49999."""
        assert round_to_tick(10000) == 10000
        assert round_to_tick(10024) == 10000
        assert round_to_tick(10025) == 10050
        assert round_to_tick(10050) == 10050
        assert round_to_tick(49975) == 50000

    def test_round_to_tick_50000_to_100000(self):
        """Test tick size of 100 won for prices 50000-99999."""
        assert round_to_tick(50000) == 50000
        assert round_to_tick(50049) == 50000
        assert round_to_tick(50050) == 50100
        assert round_to_tick(99950) == 100000

    def test_round_to_tick_100000_to_500000(self):
        """Test tick size of 500 won for prices 100000-499999."""
        assert round_to_tick(100000) == 100000
        assert round_to_tick(100249) == 100000
        assert round_to_tick(100250) == 100500
        assert round_to_tick(499750) == 500000

    def test_round_to_tick_over_500000(self):
        """Test tick size of 1000 won for prices >= 500000."""
        assert round_to_tick(500000) == 500000
        assert round_to_tick(500499) == 500000
        assert round_to_tick(500500) == 501000
        assert round_to_tick(999500) == 1000000

    def test_round_to_tick_zero(self):
        """Test rounding zero returns zero."""
        assert round_to_tick(0) == 0

    def test_round_to_tick_negative(self):
        """Test rounding negative returns zero."""
        assert round_to_tick(-100) == 0
        assert round_to_tick(-50000) == 0

    def test_get_tick_size_function(self):
        """Test get_tick_size returns correct tick sizes."""
        assert get_tick_size(500) == 1
        assert get_tick_size(1500) == 5
        assert get_tick_size(7000) == 10
        assert get_tick_size(25000) == 50
        assert get_tick_size(75000) == 100
        assert get_tick_size(200000) == 500
        assert get_tick_size(600000) == 1000

    def test_validate_tick_valid(self):
        """Test validate_tick for valid prices aligned to tick size."""
        assert validate_tick(1000) is True
        assert validate_tick(1005) is True
        assert validate_tick(5010) is True
        assert validate_tick(50100) is True
        assert validate_tick(100500) is True
        assert validate_tick(501000) is True

    def test_validate_tick_invalid(self):
        """Test validate_tick for invalid prices not aligned to tick size."""
        assert validate_tick(1001) is False  # Should be 1000 or 1005
        assert validate_tick(5003) is False  # Should be multiple of 10
        assert validate_tick(10025) is False  # Should be multiple of 50
        assert validate_tick(50050) is False  # Should be multiple of 100


# ============================================================================
# Test: test_format_price()
# ============================================================================

class TestFormatPrice:
    """Tests for format_price() function - Price formatting test."""

    def test_format_price_basic(self):
        """Test basic price formatting with comma separator."""
        assert format_price(1000) == "1,000"
        assert format_price(50000) == "50,000"
        assert format_price(1234567) == "1,234,567"

    def test_format_price_small_number(self):
        """Test formatting small numbers."""
        assert format_price(1) == "1"
        assert format_price(100) == "100"
        assert format_price(999) == "999"

    def test_format_price_large_number(self):
        """Test formatting large numbers."""
        assert format_price(10000000) == "10,000,000"
        assert format_price(123456789) == "123,456,789"

    def test_format_price_zero(self):
        """Test formatting zero."""
        assert format_price(0) == "0"

    def test_format_price_float(self):
        """Test formatting float (should truncate to int)."""
        assert format_price(1234.56) == "1,234"
        assert format_price(50000.99) == "50,000"

    def test_format_quantity(self):
        """Test format_quantity function."""
        assert format_quantity(100) == "100"
        assert format_quantity(1000) == "1,000"
        assert format_quantity(10000) == "10,000"


class TestFormattingUtilities:
    """Tests for other formatting utility functions."""

    def test_format_currency_without_symbol(self):
        """Test currency formatting without symbol."""
        assert format_currency(1000000) == "1,000,000"
        assert format_currency(50000) == "50,000"

    def test_format_currency_with_symbol(self):
        """Test currency formatting with symbol."""
        assert format_currency(1000000, 'won') == "1,000,000won"
        assert format_currency(50000, 'KRW') == "50,000KRW"

    def test_format_percentage_default(self):
        """Test percentage formatting with default decimals."""
        assert format_percentage(0.05) == "5.00%"
        assert format_percentage(0.123) == "12.30%"
        assert format_percentage(-0.02) == "-2.00%"

    def test_format_percentage_custom_decimals(self):
        """Test percentage formatting with custom decimals."""
        assert format_percentage(0.05, 1) == "5.0%"
        assert format_percentage(0.05, 0) == "5%"
        assert format_percentage(0.123456, 4) == "12.3456%"

    def test_format_percentage_zero(self):
        """Test formatting zero percentage."""
        assert format_percentage(0) == "0.00%"

    def test_calculate_change_rate(self):
        """Test calculate_change_rate function."""
        assert calculate_change_rate(105, 100) == pytest.approx(0.05, rel=1e-6)
        assert calculate_change_rate(95, 100) == pytest.approx(-0.05, rel=1e-6)
        assert calculate_change_rate(100, 100) == 0.0
        assert calculate_change_rate(100, 0) == 0.0  # Division by zero protection


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
