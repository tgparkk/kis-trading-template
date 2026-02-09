"""
P3-3: 비정상 상황 시뮬레이션

a. API 장애: 연속 3회 실패 → CircuitBreaker open → 복구
b. 부분 체결: 100주 주문 → 60주 체결 → 나머지 40주 미체결 처리
c. 주문 거부: 잔고 부족, 호가 제한 등
d. 네트워크 타임아웃: 주문 후 응답 없음 → 미체결 확인 루프
e. 장중 VI 발동: 매수 차단, 매도 허용 확인
"""
import sys
import unittest
from pathlib import Path
from datetime import datetime, timedelta
from unittest.mock import MagicMock

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

if 'psycopg2' not in sys.modules:
    _mock_pg = MagicMock()
    _mock_pg.extensions = MagicMock()
    _mock_pg.extras = MagicMock()
    _mock_pg.IntegrityError = type('IntegrityError', (Exception,), {})
    sys.modules['psycopg2'] = _mock_pg
    sys.modules['psycopg2.extensions'] = _mock_pg.extensions
    sys.modules['psycopg2.extras'] = _mock_pg.extras

import pytz

# api 패키지 import 시 OpenSSL 문제 방지: api 모듈을 mock한 후 직접 import
import importlib
import types
if 'api' not in sys.modules:
    _api_mock = types.ModuleType('api')
    _api_mock.__path__ = [str(PROJECT_ROOT / "api")]  # 패키지로 인식되도록 __path__ 설정
    _api_mock.__package__ = 'api'
    sys.modules['api'] = _api_mock
elif not hasattr(sys.modules['api'], '__path__'):
    # 이미 로드되었지만 패키지가 아닌 경우 __path__ 추가
    sys.modules['api'].__path__ = [str(PROJECT_ROOT / "api")]
# circuit_breaker는 독립적이므로 직접 로드
_cb_spec = importlib.util.spec_from_file_location(
    "api.circuit_breaker",
    str(PROJECT_ROOT / "api" / "circuit_breaker.py")
)
_cb_mod = importlib.util.module_from_spec(_cb_spec)
sys.modules['api.circuit_breaker'] = _cb_mod
_cb_spec.loader.exec_module(_cb_mod)

from tests.dryrun.dryrun_broker import DryRunBroker, DryRunConfig
from api.circuit_breaker import CircuitBreaker, CircuitBreakerConfig, CircuitState
from config.market_hours import CircuitBreakerState, MarketHours

KST = pytz.timezone('Asia/Seoul')


# ============================================================================
# a. API 장애 → CircuitBreaker
# ============================================================================

class TestAPIFailureCircuitBreaker(unittest.TestCase):
    """API 연속 실패 → CircuitBreaker open → 복구"""

    def test_consecutive_failures_open_circuit(self):
        """연속 3회 실패 → OPEN"""
        cb = CircuitBreaker(
            name="test",
            config=CircuitBreakerConfig(
                failure_threshold=3,
                recovery_timeout=1.0,
                success_threshold=1,
            )
        )
        self.assertEqual(cb.state, CircuitState.CLOSED)

        # 3회 실패
        for _ in range(3):
            cb.record_failure()

        self.assertEqual(cb.state, CircuitState.OPEN)
        self.assertFalse(cb.can_execute())

    def test_circuit_recovery_after_timeout(self):
        """OPEN → 타임아웃 후 HALF_OPEN → 성공 → CLOSED"""
        cb = CircuitBreaker(
            name="test_recovery",
            config=CircuitBreakerConfig(
                failure_threshold=3,
                recovery_timeout=0.1,  # 100ms
                success_threshold=1,
            )
        )

        for _ in range(3):
            cb.record_failure()
        self.assertEqual(cb.state, CircuitState.OPEN)

        # 타임아웃 대기
        import time
        time.sleep(0.15)

        # HALF_OPEN으로 전환
        self.assertEqual(cb.state, CircuitState.HALF_OPEN)
        self.assertTrue(cb.can_execute())

        # 성공 → CLOSED
        cb.record_success()
        self.assertEqual(cb.state, CircuitState.CLOSED)
        self.assertTrue(cb.can_execute())

    def test_half_open_failure_reopens(self):
        """HALF_OPEN에서 실패 → 다시 OPEN"""
        cb = CircuitBreaker(
            name="test_reopen",
            config=CircuitBreakerConfig(
                failure_threshold=3,
                recovery_timeout=0.1,
                success_threshold=2,
            )
        )

        for _ in range(3):
            cb.record_failure()

        import time
        time.sleep(0.15)
        self.assertEqual(cb.state, CircuitState.HALF_OPEN)

        cb.record_failure()
        self.assertEqual(cb.state, CircuitState.OPEN)

    def test_circuit_breaker_stats(self):
        """통계 추적"""
        cb = CircuitBreaker(name="test_stats")
        cb.record_success()
        cb.record_success()
        cb.record_failure()

        stats = cb.get_status()
        self.assertEqual(stats['total_calls'], 3)
        self.assertEqual(stats['total_failures'], 1)

    def test_state_change_callback(self):
        """상태 변경 콜백"""
        changes = []
        cb = CircuitBreaker(
            name="test_cb",
            config=CircuitBreakerConfig(failure_threshold=2)
        )
        cb.on_state_change(lambda name, old, new: changes.append((old, new)))

        cb.record_failure()
        cb.record_failure()  # → OPEN

        self.assertEqual(len(changes), 1)
        self.assertEqual(changes[0], (CircuitState.CLOSED, CircuitState.OPEN))


# ============================================================================
# b. 부분 체결
# ============================================================================

class TestPartialFill(unittest.TestCase):
    """부분 체결 시나리오"""

    def test_manual_partial_fill(self):
        """100주 주문 → 60주 체결 → 40주 미체결"""
        broker = DryRunBroker(DryRunConfig(initial_cash=10_000_000))
        broker.set_price('005930', 70000)

        # 대기 주문 생성 (자동 체결 안 됨)
        order_id = broker.create_pending_order("buy", "005930", 100, 70000)

        # 60주만 체결
        ok = broker.force_fill_order(order_id, fill_qty=60)
        self.assertTrue(ok)

        status = broker.get_order_status(order_id)
        self.assertEqual(status['filled_quantity'], 60)
        self.assertEqual(status['status'], 'partial')

        # 포지션 60주
        holdings = broker.get_holdings()
        self.assertEqual(holdings[0]['quantity'], 60)

        # 나머지 40주 미체결 → 취소
        cancel_result = broker.cancel_order(order_id)
        self.assertTrue(cancel_result['success'])

        status = broker.get_order_status(order_id)
        self.assertEqual(status['status'], 'cancelled')

    def test_partial_fill_then_complete(self):
        """부분 체결 → 추가 체결로 완료"""
        broker = DryRunBroker(DryRunConfig(initial_cash=10_000_000))
        broker.set_price('005930', 70000)

        order_id = broker.create_pending_order("buy", "005930", 100, 70000)

        # 60주 체결
        broker.force_fill_order(order_id, fill_qty=60)
        self.assertEqual(broker.get_order_status(order_id)['status'], 'partial')

        # 나머지 40주 체결
        broker.force_fill_order(order_id, fill_qty=40)
        self.assertEqual(broker.get_order_status(order_id)['status'], 'filled')
        self.assertEqual(broker.get_order_status(order_id)['filled_quantity'], 100)

    def test_partial_fill_sell(self):
        """매도 부분 체결"""
        broker = DryRunBroker(DryRunConfig(initial_cash=10_000_000))
        broker.set_price('005930', 70000)

        # 먼저 100주 매수
        broker.place_buy_order('005930', 100, 70000)

        # 매도 대기 주문
        order_id = broker.create_pending_order("sell", "005930", 100, 72000)

        # 60주만 매도 체결
        broker.set_price('005930', 72000)
        ok = broker.force_fill_order(order_id, fill_qty=60, fill_price=72000)
        self.assertTrue(ok)

        # 40주 남음
        holdings = broker.get_holdings()
        self.assertEqual(holdings[0]['quantity'], 40)


# ============================================================================
# c. 주문 거부
# ============================================================================

class TestOrderRejection(unittest.TestCase):
    """주문 거부 시나리오"""

    def test_insufficient_funds(self):
        """잔고 부족으로 매수 거부"""
        broker = DryRunBroker(DryRunConfig(initial_cash=100_000))  # 10만원
        broker.set_price('005930', 70000)

        # 70000 * 10 = 700,000 > 100,000
        result = broker.place_buy_order('005930', 10, 70000)
        self.assertFalse(result['success'])
        self.assertIn('잔고 부족', result['message'])

    def test_insufficient_holdings_for_sell(self):
        """보유 수량 부족으로 매도 거부"""
        broker = DryRunBroker(DryRunConfig(initial_cash=10_000_000))

        result = broker.place_sell_order('005930', 10, 70000)
        self.assertFalse(result['success'])
        self.assertIn('보유 수량 부족', result['message'])

    def test_random_rejection(self):
        """랜덤 거부 모드"""
        broker = DryRunBroker(DryRunConfig(
            initial_cash=10_000_000,
            enable_rejection=True,
            rejection_rate=1.0,  # 100% 거부
        ))
        broker.set_price('005930', 70000)

        result = broker.place_buy_order('005930', 1, 70000)
        self.assertFalse(result['success'])
        self.assertIn('거부', result['message'])

    def test_sell_more_than_held(self):
        """보유보다 많은 수량 매도 시도"""
        broker = DryRunBroker(DryRunConfig(initial_cash=10_000_000))
        broker.set_price('005930', 70000)
        broker.place_buy_order('005930', 5, 70000)

        result = broker.place_sell_order('005930', 10, 70000)
        self.assertFalse(result['success'])


# ============================================================================
# d. 네트워크 타임아웃 → 미체결 확인 루프
# ============================================================================

class TestNetworkTimeout(unittest.TestCase):
    """네트워크 타임아웃 시나리오"""

    def test_pending_order_monitoring_loop(self):
        """주문 후 미체결 상태 → 확인 루프 → 체결"""
        broker = DryRunBroker(DryRunConfig(initial_cash=10_000_000))
        broker.set_price('005930', 70000)

        # 대기 주문 (미체결 상태)
        order_id = broker.create_pending_order("buy", "005930", 50, 70000)

        # 미체결 확인 루프 시뮬레이션
        max_retries = 5
        filled = False
        for attempt in range(max_retries):
            status = broker.get_order_status(order_id)
            if status['status'] == 'filled':
                filled = True
                break
            # 3번째 시도에서 체결 처리
            if attempt == 2:
                broker.force_fill_order(order_id)

        self.assertTrue(filled)
        self.assertEqual(broker.get_order_status(order_id)['filled_quantity'], 50)

    def test_timeout_then_cancel(self):
        """타임아웃 후 미체결 주문 취소"""
        broker = DryRunBroker(DryRunConfig(initial_cash=10_000_000))
        broker.set_price('005930', 70000)

        order_id = broker.create_pending_order("buy", "005930", 30, 70000)

        # 타임아웃 (체결되지 않음)
        pending = broker.get_pending_orders()
        self.assertEqual(len(pending), 1)

        # 취소
        result = broker.cancel_order(order_id)
        self.assertTrue(result['success'])

        pending = broker.get_pending_orders()
        self.assertEqual(len(pending), 0)

    def test_unfilled_orders_query(self):
        """미체결 주문 조회"""
        broker = DryRunBroker(DryRunConfig(initial_cash=10_000_000))
        broker.set_price('005930', 70000)
        broker.set_price('000660', 150000)

        id1 = broker.create_pending_order("buy", "005930", 10, 70000)
        id2 = broker.create_pending_order("buy", "000660", 5, 150000)

        # 하나만 체결
        broker.force_fill_order(id1)

        unfilled = broker.get_unfilled_orders()
        self.assertEqual(len(unfilled), 1)
        self.assertEqual(unfilled[0]['order_id'], id2)


# ============================================================================
# e. 장중 VI 발동: 매수 차단, 매도 허용
# ============================================================================

class TestVIActivation(unittest.TestCase):
    """VI(Volatility Interruption) 발동 시나리오"""

    def setUp(self):
        self.cb_state = CircuitBreakerState()

    def tearDown(self):
        self.cb_state.clear_all()

    def test_vi_blocks_buy(self):
        """VI 발동 종목 매수 차단"""
        self.cb_state.trigger_vi('005930')
        self.assertTrue(self.cb_state.is_vi_active('005930'))

        # can_place_order는 VI 종목 차단
        dt = KST.localize(datetime(2026, 2, 10, 10, 0))
        with unittest.mock.patch(
            'config.market_hours.get_circuit_breaker_state',
            return_value=self.cb_state
        ):
            can_order = MarketHours.can_place_order('005930', 'KRX', dt)
            self.assertFalse(can_order)

    def test_vi_allows_sell(self):
        """VI 발동 종목이라도 매도는 허용 (포지션 청산 기회)

        Note: can_place_order는 VI 시 False를 반환하지만,
        실전에서는 place_sell_order 레벨에서 VI 시 매도를 허용합니다.
        여기서는 DryRunBroker가 VI 무관하게 매도 가능한지 테스트.
        """
        broker = DryRunBroker(DryRunConfig(initial_cash=10_000_000))
        broker.set_price('005930', 70000)
        broker.place_buy_order('005930', 10, 70000)

        # VI 발동 상태에서도 DryRunBroker는 매도 가능
        self.cb_state.trigger_vi('005930')
        result = broker.place_sell_order('005930', 10, 70000)
        self.assertTrue(result['success'])

    def test_vi_release(self):
        """VI 해제 후 매수 가능"""
        self.cb_state.trigger_vi('005930')
        self.assertTrue(self.cb_state.is_vi_active('005930'))

        self.cb_state.release_vi('005930')
        self.assertFalse(self.cb_state.is_vi_active('005930'))

    def test_market_wide_halt(self):
        """시장 전체 서킷브레이커"""
        dt = KST.localize(datetime(2026, 2, 10, 10, 30))
        self.cb_state.trigger_market_halt(20, dt)
        self.assertTrue(self.cb_state.is_market_halted(dt))

        # 20분 후 해제
        dt_after = dt + timedelta(minutes=20)
        self.assertFalse(self.cb_state.is_market_halted(dt_after))

    def test_vi_multiple_stocks(self):
        """복수 종목 VI"""
        self.cb_state.trigger_vi('005930')
        self.cb_state.trigger_vi('000660')

        active = self.cb_state.get_active_vi_stocks()
        self.assertEqual(len(active), 2)
        self.assertIn('005930', active)
        self.assertIn('000660', active)

    def test_clear_all_vi(self):
        """일일 리셋"""
        self.cb_state.trigger_vi('005930')
        self.cb_state.trigger_market_halt(20)
        self.cb_state.clear_all()

        self.assertFalse(self.cb_state.is_vi_active('005930'))
        self.assertFalse(self.cb_state.is_market_halted())


# ============================================================================
# 복합 시나리오
# ============================================================================

class TestCombinedAbnormalScenarios(unittest.TestCase):
    """복합 비정상 시나리오"""

    def test_partial_fill_then_vi_then_cancel(self):
        """부분 체결 → VI 발동 → 미체결분 취소"""
        broker = DryRunBroker(DryRunConfig(initial_cash=10_000_000))
        broker.set_price('005930', 70000)

        order_id = broker.create_pending_order("buy", "005930", 100, 70000)
        broker.force_fill_order(order_id, fill_qty=40)

        # VI 발동 (추가 체결 불가 가정) → 미체결 취소
        result = broker.cancel_order(order_id)
        self.assertTrue(result['success'])

        holdings = broker.get_holdings()
        self.assertEqual(holdings[0]['quantity'], 40)

    def test_circuit_breaker_blocks_then_recovers_order(self):
        """CB open → 주문 차단 → 복구 → 주문 성공"""
        cb = CircuitBreaker(
            name="test_block_recover",
            config=CircuitBreakerConfig(failure_threshold=2, recovery_timeout=0.1, success_threshold=1)
        )

        cb.record_failure()
        cb.record_failure()
        self.assertFalse(cb.can_execute())

        import time
        time.sleep(0.15)
        self.assertTrue(cb.can_execute())

        # 복구 후 주문
        broker = DryRunBroker(DryRunConfig(initial_cash=10_000_000))
        broker.set_price('005930', 70000)
        result = broker.place_buy_order('005930', 10, 70000)
        self.assertTrue(result['success'])

        cb.record_success()
        self.assertEqual(cb.state, CircuitState.CLOSED)

    def test_insufficient_funds_after_partial_invest(self):
        """투자 후 잔고 부족으로 추가 매수 거부"""
        broker = DryRunBroker(DryRunConfig(initial_cash=1_000_000))
        broker.set_price('005930', 70000)
        broker.set_price('000660', 150000)

        # 70000 * 10 = 700,000
        result = broker.place_buy_order('005930', 10, 70000)
        self.assertTrue(result['success'])

        # 잔여 300,000 < 150,000 * 5 = 750,000
        result = broker.place_buy_order('000660', 5, 150000)
        self.assertFalse(result['success'])


if __name__ == '__main__':
    unittest.main()
