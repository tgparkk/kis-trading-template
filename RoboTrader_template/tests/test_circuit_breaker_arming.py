"""런타임 CircuitBreakerState 를 라이브 KIS 종목정보로 arm 하는 회귀.

배경 (사전-실전 감사 BLOCKER #6, 2026-06-24):
  VI/거래정지 매수 가드(trading_context.is_vi_active 등)는 런타임
  CircuitBreakerState 싱글톤을 보지만, 프로덕션에서 그 상태를 arm 하는
  프로듀서가 전무했다(trigger_vi/trigger_market_halt 는 테스트에서만 호출).
  → is_vi_active() 가 항상 False → 실전에서 VI/거래정지 종목에도 매수 진행.

  candidate_selector 가 vi_cls_code 를 읽지만 후보 선정 시점이라, 선정 후
  매수 시점에 VI 진입한 종목은 무방비였다.

수정:
  매수 시점에 라이브 KIS 종목정보(vi_cls_code/iscd_stat_cls_code)로 런타임
  VI 상태를 arm 하는 순수 헬퍼 arm_circuit_breaker_from_info 를 추가하고
  trading_context.buy() 의 is_vi_active 가드 직전에 호출한다.

검증:
  1. 정적/동적 VI(vi_cls_code 1/2/3) → arm, is_vi_active True.
  2. 거래정지(iscd_stat_cls_code '09') → arm.
  3. 정상 종목(vi_cls_code '0') → arm 안 함.
  4. info 없음/None → arm 안 함(조회 실패가 매수를 막지 않도록).
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import pytest

from config.market_hours import arm_circuit_breaker_from_info, CircuitBreakerState


class TestArmCircuitBreakerFromInfo:
    @pytest.mark.parametrize("vi_code", ["1", "2", "3"])
    def test_arms_on_vi(self, vi_code):
        cb = CircuitBreakerState()
        armed = arm_circuit_breaker_from_info("005930", {"vi_cls_code": vi_code}, cb)
        assert armed is True
        assert cb.is_vi_active("005930") is True

    def test_arms_on_trading_halt(self):
        cb = CircuitBreakerState()
        armed = arm_circuit_breaker_from_info("005930", {"iscd_stat_cls_code": "09"}, cb)
        assert armed is True
        assert cb.is_vi_active("005930") is True

    def test_no_arm_on_clean_stock(self):
        cb = CircuitBreakerState()
        armed = arm_circuit_breaker_from_info("005930", {"vi_cls_code": "0"}, cb)
        assert armed is False
        assert cb.is_vi_active("005930") is False

    def test_no_arm_on_empty_or_none_info(self):
        cb = CircuitBreakerState()
        assert arm_circuit_breaker_from_info("005930", None, cb) is False
        assert arm_circuit_breaker_from_info("005930", {}, cb) is False
        assert cb.is_vi_active("005930") is False
