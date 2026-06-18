"""BaseStrategy exit_timeframe 정합성 가드 (2026-06-18 whipsaw 재발방지).

스윙 전략이 exit_timeframe 미설정으로 분봉('intraday') 청산을 상속하면
매수 직후 분봉 노이즈로 청산되는 whipsaw 발생. 6개 전략이 이 함정에 빠졌었음.
구조적 방지: 미설정 시 holding_period에서 유도 + 모순 조합 거부(fail-fast).
"""
import pytest

from strategies.base import BaseStrategy


class _SwingNoExit(BaseStrategy):
    name = "_SwingNoExit"
    holding_period = "swing"

    def generate_signal(self, stock_code, data, timeframe="daily"):
        return None


class _IntradayNoExit(BaseStrategy):
    name = "_IntradayNoExit"
    holding_period = "intraday"

    def generate_signal(self, stock_code, data, timeframe="daily"):
        return None


class _SwingExplicitIntraday(BaseStrategy):
    name = "_SwingExplicitIntraday"
    holding_period = "swing"
    exit_timeframe = "intraday"

    def generate_signal(self, stock_code, data, timeframe="daily"):
        return None


def test_swing_defaults_to_daily():
    # 미설정 스윙 전략 → 자동으로 일봉 청산
    assert _SwingNoExit().exit_timeframe == "daily"


def test_intraday_defaults_to_intraday():
    # 미설정 단타 전략 → 분봉 청산 유지 (하위호환)
    assert _IntradayNoExit().exit_timeframe == "intraday"


def test_swing_with_intraday_exit_rejected():
    # 명시적 모순(스윙+분봉청산) → 생성 시점 거부
    with pytest.raises(ValueError):
        _SwingExplicitIntraday()
