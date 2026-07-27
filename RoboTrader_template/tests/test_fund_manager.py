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
        assert fm.invested_funds == 900_000
        assert fm.reserved_funds == 0
        # 미체결분 100K 전액 환불 (매수 수수료는 매도 시 실현손익에 반영)
        assert fm.available_funds == pytest.approx(9_000_000 + 100_000)
        assert "ORD1" not in fm.order_reservations

    def test_confirm_exact_amount(self):
        fm = FundManager(initial_funds=10_000_000)
        fm.reserve_funds("ORD1", 1_000_000)
        fm.confirm_order("ORD1", 1_000_000)
        # invested = actual_amount only (without commission)
        assert fm.invested_funds == 1_000_000
        assert fm.reserved_funds == 0
        # 예약=체결이므로 정산 차액 0 (수수료는 체결 시점에 차감하지 않는다)
        assert fm.available_funds == pytest.approx(9_000_000)

    def test_confirm_actual_exceeds_reserved(self):
        """체결금액이 예약금액보다 큰 경우 — 초과 체결분을 가용자금에서 차감"""
        fm = FundManager(initial_funds=10_000_000)
        fm.reserve_funds("ORD1", 900_000)
        # 실제 체결이 1M (예약 900K보다 100K 초과)
        fm.confirm_order("ORD1", 1_000_000)
        assert fm.invested_funds == 1_000_000
        assert fm.reserved_funds == 0
        # 가용 = 10M - 900K(예약시) - 100K(초과분)
        assert fm.available_funds == pytest.approx(10_000_000 - 1_000_000)
        # 총합 일관성: 체결은 계정 간 이동이므로 갭이 생기지 않는다
        assert fm.available_funds + fm.reserved_funds + fm.invested_funds == pytest.approx(fm.total_funds)
        assert fm.verify_fund_integrity()['is_valid'] is True

    def test_confirm_actual_exceeds_reserved_accounting_consistency(self):
        """체결>예약 시 복수 주문 상황에서도 총합 일관

        미체결 예약(ORD2)이 남아 있어도 정합성 등식이 성립해야 한다.
        """
        fm = FundManager(initial_funds=10_000_000)
        fm.reserve_funds("ORD1", 1_000_000)
        fm.reserve_funds("ORD2", 2_000_000)
        # ORD1: 체결이 예약보다 200K 초과
        fm.confirm_order("ORD1", 1_200_000)
        assert fm.available_funds == pytest.approx(10_000_000 - 1_000_000 - 2_000_000 - 200_000)
        assert fm.reserved_funds == 2_000_000
        assert fm.invested_funds == 1_200_000
        # 갭 없음 (예전에는 수수료만큼 어긋났고, 그 상태를 테스트가 고정하고 있었다)
        assert fm.available_funds + fm.reserved_funds + fm.invested_funds == pytest.approx(fm.total_funds)
        assert fm.verify_fund_integrity()['is_valid'] is True

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
        fm.release_investment(2_000_000)
        # invested = actual_amount (5M) - released (2M)
        assert fm.invested_funds == pytest.approx(5_000_000 - 2_000_000)
        # available = (예약해제후 잔여) + 회수액
        assert fm.available_funds == pytest.approx(5_000_000 + 2_000_000)
        assert fm.verify_fund_integrity()['is_valid'] is True

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

        status = fm.get_status()
        assert status['total_funds'] == 10_000_000
        assert status['reserved_funds'] == 500_000
        assert status['invested_funds'] == pytest.approx(800_000)
        # 정합성: 매수 체결은 계정 간 이동이므로 총합이 보존된다
        total_check = status['available_funds'] + status['reserved_funds'] + status['invested_funds']
        assert total_check == pytest.approx(status['total_funds'])


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


class TestFundIntegrityInvariant:
    """자금 정합성 등식 회귀 테스트

    등식: total_funds == available_funds + reserved_funds + invested_funds

    매수 체결(confirm_order)은 자금을 계정 간 *이동*시킬 뿐이므로 이 등식을
    깨뜨려서는 안 된다. 매수 수수료는 매도 시 실현손익(adjust_pnl)에 이미
    포함되어 있으므로(order_monitor.py:389, order_timeout.py:229,
    trading_decision_engine.py:876) 체결 시점에 available_funds에서 또 한 번
    차감하면 이중계상이 되고, 그 갭은 다음 매도의 adjust_pnl 재계산으로
    조용히 지워진다. 그 결과 EOD 정합성 CRITICAL 알람이 "당일 마지막 자금
    이벤트가 매수였는지 매도였는지"에 따라 비결정적으로 발화한다.
    (실증: 2026-07-27 갭 329원 = 마지막 매도 이후 매수 2건의 수수료 합,
     2026-07-21 갭 69원 = 마지막 매도 이후 매수 1건의 수수료)
    """

    def test_invariant_holds_after_buy_fill_exact(self):
        """매도 없는 단일 매수 체결 후 정합성 유지 (라이브 실패 재현)"""
        fm = FundManager(initial_funds=10_000_000)
        fm.reserve_funds("ORD1", 1_000_000)
        fm.confirm_order("ORD1", 1_000_000)

        result = fm.verify_fund_integrity()
        assert result['is_valid'] is True, (
            f"매수 체결만으로 정합성이 깨졌다: 차이={result['discrepancy']:,.2f}원"
        )
        assert result['discrepancy'] == pytest.approx(0.0, abs=1e-6)
        # 자금은 available → invested 로 이동만 했을 뿐이다
        assert fm.invested_funds == pytest.approx(1_000_000)
        assert fm.reserved_funds == pytest.approx(0)
        assert fm.available_funds == pytest.approx(9_000_000)

    def test_invariant_holds_when_fill_below_reservation(self):
        """diff>0 분기(체결<예약, 차액 환불) — 정합성 유지"""
        fm = FundManager(initial_funds=10_000_000)
        fm.reserve_funds("ORD1", 1_000_000)
        fm.confirm_order("ORD1", 900_000)

        result = fm.verify_fund_integrity()
        assert result['is_valid'] is True, (
            f"체결<예약 분기에서 정합성이 깨졌다: 차이={result['discrepancy']:,.2f}원"
        )
        assert fm.invested_funds == pytest.approx(900_000)
        # 미체결분 100_000 전액이 환불되어야 한다
        assert fm.available_funds == pytest.approx(9_100_000)

    def test_invariant_holds_when_fill_above_reservation(self):
        """diff<0 분기(체결>예약, 추가 차감) — 정합성 유지"""
        fm = FundManager(initial_funds=10_000_000)
        fm.reserve_funds("ORD1", 900_000)
        fm.confirm_order("ORD1", 1_000_000)

        result = fm.verify_fund_integrity()
        assert result['is_valid'] is True, (
            f"체결>예약 분기에서 정합성이 깨졌다: 차이={result['discrepancy']:,.2f}원"
        )
        assert fm.invested_funds == pytest.approx(1_000_000)
        # 초과 체결분 100_000 만 추가 차감
        assert fm.available_funds == pytest.approx(9_000_000)

    def test_invariant_gap_does_not_accumulate_over_sequential_buys(self):
        """매도 없이 매수만 연속 — 갭이 누적되지 않는다"""
        fm = FundManager(initial_funds=10_000_000)
        fills = [(1_000_000, 1_000_000), (800_000, 750_000), (500_000, 560_000)]
        for i, (reserved, actual) in enumerate(fills):
            oid = f"ORD{i}"
            assert fm.reserve_funds(oid, reserved) is True
            fm.confirm_order(oid, actual)
            result = fm.verify_fund_integrity()
            assert result['is_valid'] is True, (
                f"{i+1}번째 매수 후 정합성 붕괴: 차이={result['discrepancy']:,.2f}원"
            )

        # 3건 누적 후에도 갭 0 (수수료 3건분이 쌓이지 않았음)
        assert fm.verify_fund_integrity()['discrepancy'] == pytest.approx(0.0, abs=1e-6)
        assert fm.invested_funds == pytest.approx(750_000 + 1_000_000 + 560_000)
        assert fm.available_funds == pytest.approx(10_000_000 - 2_310_000)

    def test_invariant_holds_through_buy_sell_buy_and_pnl_not_double_charged(self):
        """매수→매도→매수 전 구간 정합성 + total_funds 의미 불변(수수료 이중계상 없음)

        매도 산식은 프로덕션 경로(order_monitor._handle_full_fill,
        trading_decision_engine 가상매도)와 동일하게 buy_commission을 포함한다.
        """
        from config.constants import SECURITIES_TAX_RATE

        initial = 10_000_000
        fm = FundManager(initial_funds=initial)

        # --- 1차 매수 ---
        buy_cost = 1_000_000
        fm.reserve_funds("B1", buy_cost)
        fm.confirm_order("B1", buy_cost)
        assert fm.verify_fund_integrity()['is_valid'] is True, "1차 매수 후 정합성 붕괴"

        # --- 매도 (프로덕션 산식: 매수/매도 수수료 + 거래세 전부 pnl에 반영) ---
        sell_amount = 1_100_000
        buy_commission = buy_cost * COMMISSION_RATE
        sell_commission = sell_amount * COMMISSION_RATE
        sell_tax = sell_amount * SECURITIES_TAX_RATE
        pnl = sell_amount - buy_cost - buy_commission - sell_commission - sell_tax

        fm.release_investment(buy_cost, stock_code="005930")
        assert fm.verify_fund_integrity()['is_valid'] is True, "회수 직후 정합성 붕괴"
        fm.adjust_pnl(pnl)
        assert fm.verify_fund_integrity()['is_valid'] is True, "손익 반영 후 정합성 붕괴"

        # total_funds 의미 불변: 초기자금 + 실현손익(수수료 1회만 포함)
        assert fm.total_funds == pytest.approx(initial + pnl)
        # 포지션 청산 상태이므로 전액 가용
        assert fm.invested_funds == pytest.approx(0)
        assert fm.available_funds == pytest.approx(initial + pnl)

        # --- 2차 매수 (매도 이후 매수 = 라이브 EOD 갭이 관측된 상황) ---
        fm.reserve_funds("B2", 2_000_000)
        fm.confirm_order("B2", 2_000_000)
        result = fm.verify_fund_integrity()
        assert result['is_valid'] is True, (
            f"매도 이후 매수에서 정합성 붕괴(라이브 EOD 갭): "
            f"차이={result['discrepancy']:,.2f}원"
        )
        # total_funds는 매수로 변하지 않는다
        assert fm.total_funds == pytest.approx(initial + pnl)
        assert fm.available_funds == pytest.approx(initial + pnl - 2_000_000)

    def test_buy_commission_not_deducted_from_available_at_fill(self):
        """체결 시점에 수수료가 available에서 빠지지 않는다 (이중계상 방지 명시)"""
        fm = FundManager(initial_funds=10_000_000)
        fm.reserve_funds("ORD1", 1_000_000)
        fm.confirm_order("ORD1", 1_000_000)
        commission = 1_000_000 * COMMISSION_RATE
        assert commission > 0  # 상수가 0이면 이 테스트는 무의미
        # 수수료가 1원어치라도 차감되면 실패하도록 절대오차로 고정한다.
        # (기본 상대오차 approx는 9M 기준 ±9원 밴드라 작은 수수료를 놓칠 수 있다)
        assert fm.available_funds == pytest.approx(9_000_000, abs=1e-6)


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
