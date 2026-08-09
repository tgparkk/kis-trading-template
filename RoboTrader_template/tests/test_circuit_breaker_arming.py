"""런타임 CircuitBreakerState 를 라이브 KIS 종목정보로 arm 하는 회귀.

배경 (사전-실전 감사 BLOCKER #6, 2026-06-24):
  VI/거래정지 매수 가드(trading_context.is_vi_active 등)는 런타임
  CircuitBreakerState 싱글톤을 보지만, 프로덕션에서 그 상태를 arm 하는
  프로듀서가 전무했다(trigger_vi/trigger_market_halt 는 테스트에서만 호출).
  → is_vi_active() 가 항상 False → 실전에서 VI/거래정지 종목에도 매수 진행.

  candidate_selector 가 vi_cls_code 를 읽지만 후보 선정 시점이라, 선정 후
  매수 시점에 VI 진입한 종목은 무방비였다.

2026-08-09 정정 — 프로듀서를 붙였어도 가드는 여전히 no-op 이었다:
  1. 프로듀서가 부르는 api.kis_market_api.get_stock_basic_info 가 **존재하지
     않았다**. 호출부 try/except 가 ImportError 를 삼켜 arm 이 한 번도 안 됐다.
  2. 이 헬퍼의 **값 계약이 틀렸다**. 전 유니버스 2,574종목 실측 결과
     vi_cls_code 의 값 도메인은 'Y'/'N' 이고(❌ '1'/'2'/'3' 아님),
     거래정지는 iscd_stat_cls_code=='58' 이다(❌ '09' 는 존재하지 않는 값).
     옛 테스트는 그 틀린 계약을 그대로 베껴 초록불이었다.

검증 (실측 계약 기준):
  1. VI(vi_cls_code 'Y') → arm, is_vi_active True.
  2. 거래정지(iscd_stat_cls_code '58') / 임시정지(temp_stop_yn 'Y') → arm.
  3. 정상 종목(vi_cls_code 'N', iscd '55'/'57') → arm 안 함 (대칭 주장).
  4. 옛 계약값('1'/'2'/'3', '09')로는 arm 되지 않는다(계약 되돌림 방지).
  5. info 없음/None → arm 안 함(조회 실패가 매수를 막지 않도록).
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import pytest

from config.market_hours import arm_circuit_breaker_from_info, CircuitBreakerState

# 실응답 채록본(2026-08-09, 전 유니버스 2,574종목) — 손으로 만든 dict 금지.
FIXTURE_PATH = ROOT / "tests" / "fixtures" / "kis_stock_basic_info_recorded.json"
with open(FIXTURE_PATH, "r", encoding="utf-8") as _f:
    GROUPS = json.load(_f)["groups"]

NORMAL = GROUPS["정상_신용가능"][0]
MARGIN100 = GROUPS["정상_증거금100"][0]
HALTED = GROUPS["거래정지_58"][0]


class TestArmCircuitBreakerFromInfo:
    def test_arms_on_vi(self):
        """VI 발동은 vi_cls_code=='Y' 다."""
        cb = CircuitBreakerState()
        info = dict(NORMAL, vi_cls_code="Y")  # 채록 행의 VI 한 칸만 도메인 내 값으로 파생
        assert arm_circuit_breaker_from_info("005930", info, cb) is True
        assert cb.is_vi_active("005930") is True

    def test_arms_on_trading_halt(self):
        """거래정지는 iscd_stat_cls_code=='58' (채록 실응답)."""
        cb = CircuitBreakerState()
        assert HALTED["iscd_stat_cls_code"] == "58"
        assert arm_circuit_breaker_from_info(HALTED["code"], HALTED, cb) is True
        assert cb.is_vi_active(HALTED["code"]) is True

    def test_arms_on_temp_stop(self):
        cb = CircuitBreakerState()
        info = dict(NORMAL, temp_stop_yn="Y")
        assert arm_circuit_breaker_from_info("005930", info, cb) is True

    def test_no_arm_on_clean_stock(self):
        """대칭 주장: 채록된 정상 종목은 arm 되면 안 된다."""
        cb = CircuitBreakerState()
        for info in (NORMAL, MARGIN100):
            assert arm_circuit_breaker_from_info(info["code"], info, cb) is False
            assert cb.is_vi_active(info["code"]) is False

    def test_margin100_status_is_not_a_halt(self):
        """함정: iscd_stat_cls_code != '55' 를 이상으로 보면 안 된다.

        '57'(증거금100%)이 유니버스 최다(1,584종목)이며 정상 거래된다.
        """
        cb = CircuitBreakerState()
        assert MARGIN100["iscd_stat_cls_code"] == "57"
        assert arm_circuit_breaker_from_info(MARGIN100["code"], MARGIN100, cb) is False

    @pytest.mark.parametrize("legacy_vi", ["1", "2", "3"])
    def test_legacy_numeric_vi_codes_do_not_arm(self, legacy_vi):
        """옛 계약('1'/'2'/'3')은 실응답 값 도메인에 없다 — 되돌림 방지."""
        cb = CircuitBreakerState()
        info = dict(NORMAL, vi_cls_code=legacy_vi)
        assert arm_circuit_breaker_from_info("005930", info, cb) is False

    def test_legacy_halt_code_09_does_not_arm(self):
        """옛 계약('09')은 전 유니버스에서 관측되지 않는 값이다."""
        cb = CircuitBreakerState()
        info = dict(NORMAL, iscd_stat_cls_code="09")
        assert arm_circuit_breaker_from_info("005930", info, cb) is False

    def test_no_arm_on_empty_or_none_info(self):
        cb = CircuitBreakerState()
        assert arm_circuit_breaker_from_info("005930", None, cb) is False
        assert arm_circuit_breaker_from_info("005930", {}, cb) is False
        assert cb.is_vi_active("005930") is False
