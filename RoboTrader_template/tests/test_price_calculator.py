"""
PriceCalculator 유닛 테스트
- 손절가 계산
- 익절가 계산
- 신호 강도별 목표 수익률
"""
import pytest
from core.price_calculator import PriceCalculator


class TestStopLossPrice:
    def test_default_rate(self):
        # 기본 target_profit_rate=0.03, stop_loss = 0.03/2 = 0.015
        result = PriceCalculator.calculate_stop_loss_price(100000)
        assert result == pytest.approx(100000 * (1 - 0.015), rel=1e-6)

    def test_custom_rate(self):
        result = PriceCalculator.calculate_stop_loss_price(50000, 0.04)
        assert result == pytest.approx(50000 * (1 - 0.02), rel=1e-6)

    def test_zero_price(self):
        result = PriceCalculator.calculate_stop_loss_price(0, 0.03)
        assert result == 0.0


class TestProfitPrice:
    def test_default_rate(self):
        result = PriceCalculator.calculate_profit_price(100000)
        assert result == pytest.approx(103000, rel=1e-6)

    def test_custom_rate(self):
        result = PriceCalculator.calculate_profit_price(50000, 0.05)
        assert result == pytest.approx(52500, rel=1e-6)


class TestTargetProfitFromSignal:
    def test_strong_signal(self):
        assert PriceCalculator.get_target_profit_rate_from_signal("Strong buy") == 0.025

    def test_cautious_signal(self):
        assert PriceCalculator.get_target_profit_rate_from_signal("Cautious entry") == 0.02

    def test_default_signal(self):
        assert PriceCalculator.get_target_profit_rate_from_signal("normal buy") == 0.015

    def test_empty_signal(self):
        assert PriceCalculator.get_target_profit_rate_from_signal("") == 0.015
