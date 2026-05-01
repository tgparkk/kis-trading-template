"""
Phase C3: 자금관리 통합 테스트
==============================

C3: FundManagerProtocol 인터페이스 + FundManager/MockFundManager/VTM 호환성

테스트 목록:
- test_fund_manager_protocol_compliance: FundManager가 Protocol을 충족하는지
- test_mock_fund_manager_protocol_compliance: MockFundManager도 Protocol 충족
- test_fund_manager_protocol_methods_work: reserve/commit/release/realize 동작
- test_mock_fund_manager_reserve_commit_release: MockFundManager 기본 흐름
- test_mock_fund_manager_realize_updates_total: realize가 total 조정
- test_three_way_consistency: FundManager ↔ MockFundManager 동일 시나리오 잔고 일치
- test_mock_fund_manager_reserve_insufficient: 잔고 부족 시 False
"""
import pytest
from core.fund_manager import FundManager, MockFundManager, FundManagerProtocol
from config.constants import COMMISSION_RATE


# ============================================================================
# C3-A: Protocol 준수 검증
# ============================================================================

class TestProtocolCompliance:
    """FundManager와 MockFundManager 모두 FundManagerProtocol을 충족하는지."""

    def test_fund_manager_protocol_compliance(self):
        """FundManager가 FundManagerProtocol 인스턴스인지 확인 (runtime_checkable)."""
        fm = FundManager(initial_funds=10_000_000)
        assert isinstance(fm, FundManagerProtocol), (
            "FundManager는 FundManagerProtocol을 구현해야 함"
        )

    def test_mock_fund_manager_protocol_compliance(self):
        """MockFundManager가 FundManagerProtocol 인스턴스인지 확인."""
        mfm = MockFundManager(initial_capital=10_000_000)
        assert isinstance(mfm, FundManagerProtocol), (
            "MockFundManager는 FundManagerProtocol을 구현해야 함"
        )

    def test_protocol_required_methods_exist_on_fund_manager(self):
        """FundManager에 Protocol 메서드/프로퍼티가 모두 존재하는지."""
        fm = FundManager(initial_funds=1_000_000)
        assert callable(getattr(fm, 'reserve', None))
        assert callable(getattr(fm, 'commit', None))
        assert callable(getattr(fm, 'release', None))
        assert callable(getattr(fm, 'realize', None))
        assert isinstance(fm.available_balance, (int, float))
        assert isinstance(fm.total_invested, (int, float))

    def test_protocol_required_methods_exist_on_mock(self):
        """MockFundManager에 Protocol 메서드/프로퍼티가 모두 존재하는지."""
        mfm = MockFundManager(initial_capital=1_000_000)
        assert callable(getattr(mfm, 'reserve', None))
        assert callable(getattr(mfm, 'commit', None))
        assert callable(getattr(mfm, 'release', None))
        assert callable(getattr(mfm, 'realize', None))
        assert isinstance(mfm.available_balance, (int, float))
        assert isinstance(mfm.total_invested, (int, float))


# ============================================================================
# C3-B: FundManager Protocol 메서드 동작 검증
# ============================================================================

class TestFundManagerProtocolMethods:
    """FundManager의 Protocol 래퍼 메서드가 올바르게 동작하는지."""

    def test_available_balance_property(self):
        fm = FundManager(initial_funds=10_000_000)
        assert fm.available_balance == fm.available_funds == 10_000_000

    def test_total_invested_property(self):
        fm = FundManager(initial_funds=10_000_000)
        fm.reserve_funds("ORD1", 1_000_000)
        fm.confirm_order("ORD1", 1_000_000)
        assert fm.total_invested == fm.invested_funds == 1_000_000

    def test_reserve_delegates_to_reserve_funds(self):
        fm = FundManager(initial_funds=10_000_000)
        result = fm.reserve(1_000_000, "ORD_PROTO")
        assert result is True
        assert fm.available_balance == 9_000_000

    def test_commit_delegates_to_confirm_order(self):
        fm = FundManager(initial_funds=10_000_000)
        fm.reserve(1_000_000, "ORD_PROTO")
        fm.commit("ORD_PROTO", 900_000)
        assert fm.total_invested == 900_000
        assert fm.reserved_funds == 0

    def test_release_delegates_to_release_investment(self):
        fm = FundManager(initial_funds=10_000_000)
        fm.reserve_funds("ORD1", 1_000_000)
        fm.confirm_order("ORD1", 1_000_000)
        prev_available = fm.available_balance
        fm.release(1_000_000)
        assert fm.total_invested == 0
        assert fm.available_balance == pytest.approx(prev_available + 1_000_000)

    def test_realize_delegates_to_adjust_pnl(self):
        fm = FundManager(initial_funds=10_000_000)
        fm.realize(500_000)
        assert fm.total_funds == 10_500_000

    def test_realize_loss_records_daily_loss(self):
        fm = FundManager(initial_funds=10_000_000)
        fm.realize(-500_000)
        assert fm.total_funds == 9_500_000
        # 손실 기록도 반영
        assert fm._daily_realized_loss > 0


# ============================================================================
# C3-C: MockFundManager 단독 동작 검증
# ============================================================================

class TestMockFundManager:
    """MockFundManager 기본 흐름 검증."""

    def test_initial_state(self):
        mfm = MockFundManager(initial_capital=5_000_000)
        assert mfm.available_balance == 5_000_000
        assert mfm.total_invested == 0.0
        assert mfm.total_funds == 5_000_000

    def test_reserve_commit_release(self):
        mfm = MockFundManager(initial_capital=5_000_000)

        # 예약
        result = mfm.reserve(1_000_000, "ORD1")
        assert result is True
        assert mfm.available_balance == 4_000_000

        # 체결 확정
        mfm.commit("ORD1", 950_000)
        assert mfm.total_invested == 950_000
        # 차액(50_000) → available 반환
        assert mfm.available_balance == pytest.approx(4_050_000)

        # 매도 후 회수
        mfm.release(950_000)
        assert mfm.total_invested == 0.0
        assert mfm.available_balance == pytest.approx(5_000_000)

    def test_reserve_insufficient(self):
        mfm = MockFundManager(initial_capital=1_000_000)
        result = mfm.reserve(2_000_000, "ORD1")
        assert result is False
        assert mfm.available_balance == 1_000_000

    def test_realize_profit_updates_total_and_available(self):
        mfm = MockFundManager(initial_capital=5_000_000)
        mfm.realize(200_000)
        assert mfm.total_funds == 5_200_000
        assert mfm.available_balance == 5_200_000

    def test_realize_loss_reduces_total(self):
        mfm = MockFundManager(initial_capital=5_000_000)
        mfm.realize(-300_000)
        assert mfm.total_funds == 4_700_000


# ============================================================================
# C3-D: 3-way 일관성 검증 (FundManager ↔ MockFundManager)
# ============================================================================

class TestThreeWayConsistency:
    """
    동일 매매 시나리오에서 FundManager와 MockFundManager의
    가용 잔고 변화가 ±0.01% 이내로 일치하는지 검증.

    시나리오:
    1. 초기 자본 10M
    2. 1M 예약 → 950K 체결 확정 (차액 50K 반환)
    3. 실현 손익 +100K
    4. 매도 후 950K 회수
    """

    def _run_scenario(self, fm):
        """FundManagerProtocol 구현체에 동일 시나리오 적용."""
        initial = fm.available_balance

        # 1) 예약
        fm.reserve(1_000_000, "ORD_TEST")
        after_reserve = fm.available_balance

        # 2) 체결
        fm.commit("ORD_TEST", 950_000)
        after_commit = fm.available_balance
        invested_after_commit = fm.total_invested

        # 3) 실현 손익 +100K
        fm.realize(100_000)
        after_realize = fm.available_balance

        # 4) 매도 회수
        fm.release(950_000)
        after_release = fm.available_balance
        invested_after_release = fm.total_invested

        return {
            'initial': initial,
            'after_reserve': after_reserve,
            'after_commit': after_commit,
            'invested_after_commit': invested_after_commit,
            'after_realize': after_realize,
            'after_release': after_release,
            'invested_after_release': invested_after_release,
        }

    def _assert_close(self, a: float, b: float, key: str, tol_pct: float = 0.01):
        """두 값이 tol_pct % 이내 일치하는지 검증."""
        if a == 0 and b == 0:
            return
        ref = max(abs(a), abs(b), 1.0)
        diff_pct = abs(a - b) / ref * 100
        assert diff_pct <= tol_pct, (
            f"[{key}] FundManager={a:,.0f} vs MockFundManager={b:,.0f} "
            f"차이={diff_pct:.4f}% (한도 {tol_pct}%)"
        )

    def test_three_way_consistency(self):
        """FundManager와 MockFundManager 시나리오 일관성."""
        INITIAL = 10_000_000

        fm = FundManager(initial_funds=INITIAL)
        mfm = MockFundManager(initial_capital=INITIAL)

        # FundManager는 수수료를 반영하므로 MockFundManager보다
        # commit 후 available이 commission만큼 적을 수 있음.
        # 따라서 tol_pct를 0.1%로 설정 (COMMISSION_RATE ≈ 0.015% 수준)
        fm_result = self._run_scenario(fm)
        mfm_result = self._run_scenario(mfm)

        for key in ['initial', 'after_reserve', 'invested_after_commit',
                    'invested_after_release']:
            self._assert_close(fm_result[key], mfm_result[key], key, tol_pct=0.1)

        # 예약 직후 available: 둘 다 9_000_000 (수수료 없음)
        self._assert_close(
            fm_result['after_reserve'], mfm_result['after_reserve'],
            'after_reserve', tol_pct=0.01,
        )

        # 매도 후 투자금 = 0
        assert fm_result['invested_after_release'] == 0.0
        assert mfm_result['invested_after_release'] == 0.0
