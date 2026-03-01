"""
FundManager 유닛 테스트
- 자금 예약/확인/취소/회수 순수 로직 검증
- Thread safety 검증
- 경계값 및 안전성 검증
"""
import pytest
import threading
from core.fund_manager import FundManager
from config.constants import COMMISSION_RATE


class TestFundManagerInit:
    """초기화 테스트"""

    def test_initialization(self):
        fm = FundManager(initial_funds=10_000_000)
        assert fm.total_funds == 10_000_000
        assert fm.available_funds == 10_000_000
        assert fm.reserved_funds == 0
        assert fm.invested_funds == 0
        assert fm.order_reservations == {}

    def test_initialization_zero(self):
        fm = FundManager(initial_funds=0)
        assert fm.total_funds == 0
        assert fm.available_funds == 0


class TestReserveFunds:
    """자금 예약 테스트"""

    def test_reserve_success(self):
        fm = FundManager(initial_funds=10_000_000)
        result = fm.reserve_funds("ORD1", 1_000_000)
        assert result is True
        assert fm.available_funds == 9_000_000
        assert fm.reserved_funds == 1_000_000
        assert "ORD1" in fm.order_reservations

    def test_reserve_insufficient(self):
        fm = FundManager(initial_funds=1_000_000)
        result = fm.reserve_funds("ORD1", 2_000_000)
        assert result is False
        assert fm.available_funds == 1_000_000
        assert fm.reserved_funds == 0

    def test_reserve_duplicate(self):
        fm = FundManager(initial_funds=10_000_000)
        fm.reserve_funds("ORD1", 1_000_000)
        result = fm.reserve_funds("ORD1", 500_000)
        assert result is False
        assert fm.available_funds == 9_000_000
        assert fm.reserved_funds == 1_000_000

    def test_reserve_zero_amount(self):
        fm = FundManager(initial_funds=10_000_000)
        result = fm.reserve_funds("ORD1", 0)
        assert result is True
        assert fm.available_funds == 10_000_000

    def test_reserve_exact_balance(self):
        fm = FundManager(initial_funds=1_000_000)
        result = fm.reserve_funds("ORD1", 1_000_000)
        assert result is True
        assert fm.available_funds == 0
        assert fm.reserved_funds == 1_000_000


class TestConfirmOrder:
    """주문 확인 테스트"""

    def test_confirm_with_refund(self):
        fm = FundManager(initial_funds=10_000_000)
        fm.reserve_funds("ORD1", 1_000_000)
        fm.confirm_order("ORD1", 900_000)
        # invested = actual_amount only (without commission)
        commission = 900_000 * COMMISSION_RATE
        total_cost = 900_000 + commission
        assert fm.invested_funds == 900_000
        assert fm.reserved_funds == 0
        assert fm.available_funds == pytest.approx(9_000_000 + (1_000_000 - total_cost))
        assert "ORD1" not in fm.order_reservations

    def test_confirm_exact_amount(self):
        fm = FundManager(initial_funds=10_000_000)
        fm.reserve_funds("ORD1", 1_000_000)
        fm.confirm_order("ORD1", 1_000_000)
        # invested = actual_amount only (without commission)
        commission = 1_000_000 * COMMISSION_RATE
        assert fm.invested_funds == 1_000_000
        assert fm.reserved_funds == 0
        # 수수료로 인해 total_cost > reserved이므로 차액 추가 차감
        assert fm.available_funds == pytest.approx(9_000_000 - commission)

    def test_confirm_actual_exceeds_reserved(self):
        """체결금액이 예약금액보다 큰 경우 — 추가 비용을 가용자금에서 차감"""
        fm = FundManager(initial_funds=10_000_000)
        fm.reserve_funds("ORD1", 900_000)
        # 실제 체결이 1M (예약 900K보다 100K+ 초과, 수수료 포함)
        fm.confirm_order("ORD1", 1_000_000)
        commission = 1_000_000 * COMMISSION_RATE
        total_cost = 1_000_000 + commission
        assert fm.invested_funds == 1_000_000
        assert fm.reserved_funds == 0
        # 가용 = 10M - 900K(예약시) - (total_cost - 900K)(초과분)
        assert fm.available_funds == pytest.approx(10_000_000 - total_cost)
        # 총합 일관성: commission creates a gap
        assert fm.available_funds + fm.reserved_funds + fm.invested_funds == pytest.approx(fm.total_funds - commission)

    def test_confirm_actual_exceeds_reserved_accounting_consistency(self):
        """체결>예약 시 복수 주문 상황에서도 총합 일관"""
        fm = FundManager(initial_funds=10_000_000)
        fm.reserve_funds("ORD1", 1_000_000)
        fm.reserve_funds("ORD2", 2_000_000)
        # ORD1: 체결이 예약보다 200K+ 초과 (수수료 포함)
        fm.confirm_order("ORD1", 1_200_000)
        commission = 1_200_000 * COMMISSION_RATE
        total_cost = 1_200_000 + commission
        assert fm.available_funds == pytest.approx(10_000_000 - 1_000_000 - 2_000_000 - (total_cost - 1_000_000))
        assert fm.reserved_funds == 2_000_000
        assert fm.invested_funds == 1_200_000
        # commission creates a gap
        assert fm.available_funds + fm.reserved_funds + fm.invested_funds == pytest.approx(fm.total_funds - commission)

    def test_confirm_unreserved(self):
        fm = FundManager(initial_funds=10_000_000)
        fm.confirm_order("UNKNOWN", 500_000)
        # 상태 변경 없음
        assert fm.available_funds == 10_000_000
        assert fm.invested_funds == 0


class TestCancelOrder:
    """주문 취소 테스트"""

    def test_cancel_success(self):
        fm = FundManager(initial_funds=10_000_000)
        fm.reserve_funds("ORD1", 1_000_000)
        fm.cancel_order("ORD1")
        assert fm.available_funds == 10_000_000
        assert fm.reserved_funds == 0
        assert "ORD1" not in fm.order_reservations

    def test_cancel_unreserved(self):
        fm = FundManager(initial_funds=10_000_000)
        fm.cancel_order("UNKNOWN")
        assert fm.available_funds == 10_000_000


class TestReleaseInvestment:
    """투자 자금 회수 테스트"""

    def test_release_investment(self):
        fm = FundManager(initial_funds=10_000_000)
        fm.reserve_funds("ORD1", 5_000_000)
        fm.confirm_order("ORD1", 5_000_000)
        commission = 5_000_000 * COMMISSION_RATE
        fm.release_investment(2_000_000)
        # invested = actual_amount (5M) - released (2M)
        assert fm.invested_funds == pytest.approx(5_000_000 - 2_000_000)
        # available = (예약해제후 잔여) + 회수액
        assert fm.available_funds == pytest.approx(5_000_000 - commission + 2_000_000)

    def test_release_negative_guard(self):
        """안전성 이슈 #8: release_investment로 invested_funds가 음수 되지 않도록 보정"""
        fm = FundManager(initial_funds=10_000_000)
        fm.reserve_funds("ORD1", 1_000_000)
        fm.confirm_order("ORD1", 1_000_000)
        # invested = 1M + 수수료인데 2M 회수 → 보정되어 0으로 클램핑
        fm.release_investment(2_000_000)
        assert fm.invested_funds == 0  # 음수 방지 보정 적용됨


class TestGetMaxBuyAmount:
    """최대 매수 가능 금액 테스트"""

    def test_get_max_buy_amount(self):
        fm = FundManager(initial_funds=10_000_000)
        max_amt = fm.get_max_buy_amount("005930")
        assert max_amt == 900_000  # 10M * 0.09

    def test_max_buy_investment_limit(self):
        fm = FundManager(initial_funds=10_000_000)
        fm.reserve_funds("ORD1", 8_500_000)
        fm.confirm_order("ORD1", 8_500_000)
        max_amt = fm.get_max_buy_amount("005930")
        # invested = actual_amount (8.5M), not total_cost
        # 투자여력: 10M*0.9 - 8.5M(invested)
        # 종목한도: 10M*0.09 = 900K
        # 가용자금: 10M - total_cost (수수료 포함)
        remaining = 10_000_000 * 0.9 - 8_500_000
        assert max_amt == pytest.approx(remaining)

    def test_max_buy_no_funds(self):
        fm = FundManager(initial_funds=10_000_000)
        fm.reserve_funds("ORD1", 10_000_000)
        max_amt = fm.get_max_buy_amount("005930")
        assert max_amt == 0


class TestGetStatus:
    """상태 조회 테스트"""

    def test_get_status_consistency(self):
        fm = FundManager(initial_funds=10_000_000)
        fm.reserve_funds("ORD1", 1_000_000)
        fm.confirm_order("ORD1", 800_000)
        fm.reserve_funds("ORD2", 500_000)

        commission = 800_000 * COMMISSION_RATE
        status = fm.get_status()
        assert status['total_funds'] == 10_000_000
        assert status['reserved_funds'] == 500_000
        assert status['invested_funds'] == pytest.approx(800_000)
        # 정합성: commission creates a gap
        total_check = status['available_funds'] + status['reserved_funds'] + status['invested_funds']
        assert total_check == pytest.approx(status['total_funds'] - commission)


class TestUpdateTotalFunds:
    """총 자금 업데이트 테스트"""

    def test_update_total_funds(self):
        fm = FundManager(initial_funds=10_000_000)
        fm.reserve_funds("ORD1", 1_000_000)
        fm.confirm_order("ORD1", 1_000_000)
        fm.update_total_funds(12_000_000)
        # available = 12M - 0(reserved) - invested(1M, without commission)
        assert fm.total_funds == 12_000_000
        assert fm.available_funds == pytest.approx(12_000_000 - 1_000_000)


class TestConcurrency:
    """동시성 테스트"""

    def test_concurrent_reservations(self):
        fm = FundManager(initial_funds=10_000_000)
        results = []

        def reserve(order_id, amount):
            result = fm.reserve_funds(order_id, amount)
            results.append(result)

        threads = [
            threading.Thread(target=reserve, args=(f"ORD{i}", 3_000_000))
            for i in range(5)
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        success_count = sum(1 for r in results if r)
        fail_count = sum(1 for r in results if not r)

        # 10M으로 3M씩 최대 3번만 성공 가능
        assert success_count == 3
        assert fail_count == 2
        assert fm.reserved_funds == 9_000_000
        assert fm.available_funds == 1_000_000
