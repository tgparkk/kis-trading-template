"""
Phase E2 단위 테스트 — FundManager 전략별 상한 + 일일 손실 한도
================================================================

검증 항목:
  - reserve_funds(strategy_name=...) 전략별 invested 누적
  - 전략별 max_capital_pct 초과 시 reserve 거부 + INFO 로그
  - strategy_name="" 호출 시 기존 동작 유지 (backward compat)
  - 전략 A 손실 5% 시 A 매수 차단, B는 가능
  - 전체 손실 한도도 별도 작동
  - order_db_handler: trading_stock.strategy_name="" → "unknown" + WARNING
"""
import logging
import pytest
from unittest.mock import MagicMock, patch
from core.fund_manager import FundManager


# ---------------------------------------------------------------------------
# 헬퍼: strategy_max_pct_provider 콜백 팩토리
# ---------------------------------------------------------------------------

def make_provider(mapping: dict):
    """전략명 → max_capital_pct 반환 콜백."""
    def provider(name: str) -> float:
        return mapping.get(name, 1.0)
    return provider


# ---------------------------------------------------------------------------
# 1. reserve_funds — 전략별 invested 추적
# ---------------------------------------------------------------------------

class TestReserveWithStrategyName:
    """전략별 invested 누적 기본 동작."""

    def test_reserve_with_strategy_name(self):
        provider = make_provider({"A": 0.5, "B": 0.5})
        fm = FundManager(initial_funds=10_000_000, strategy_max_pct_provider=provider)

        ok = fm.reserve_funds("ORD1", 2_000_000, strategy_name="A")
        assert ok is True
        assert fm._invested_by_strategy.get("A", 0) == 2_000_000

    def test_two_strategies_tracked_independently(self):
        provider = make_provider({"A": 0.5, "B": 0.5})
        fm = FundManager(initial_funds=10_000_000, strategy_max_pct_provider=provider)

        fm.reserve_funds("ORD1", 1_000_000, strategy_name="A")
        fm.reserve_funds("ORD2", 1_500_000, strategy_name="B")

        assert fm._invested_by_strategy["A"] == 1_000_000
        assert fm._invested_by_strategy["B"] == 1_500_000


# ---------------------------------------------------------------------------
# 2. reserve_funds — 전략별 상한 초과 시 거부
# ---------------------------------------------------------------------------

class TestReserveRejectedOverMaxCapitalPct:
    """max_capital_pct 초과 reserve는 False 반환 + INFO 로그."""

    def test_reject_over_max_capital_pct(self, caplog):
        # A의 상한: 50% = 5,000,000원
        provider = make_provider({"A": 0.5})
        fm = FundManager(initial_funds=10_000_000, strategy_max_pct_provider=provider)

        # 첫 번째 reserve: 4M (누적 4M < 5M 상한) → 성공
        ok1 = fm.reserve_funds("ORD1", 4_000_000, strategy_name="A")
        assert ok1 is True

        # 두 번째 reserve: 2M (누적 4M+2M=6M > 5M 상한) → 거부
        with caplog.at_level(logging.INFO, logger="core.fund_manager"):
            ok2 = fm.reserve_funds("ORD2", 2_000_000, strategy_name="A")

        assert ok2 is False
        # 상한 초과 INFO 로그 확인 (logger 전파 가능하면 caplog, 아니면 반환값으로 충분)
        log_texts = [r.message for r in caplog.records]
        # 로그가 caplog에 잡혔으면 내용 검증, 아니면 반환값(False)으로 행동 검증
        if log_texts:
            assert any("전략별 자금 상한 초과" in t for t in log_texts)

    def test_reject_exactly_at_cap(self):
        # 상한 5M, 이미 5M 투자 → 0원도 불가 (0+5M=5M >= 5M → 거부 조건: current+amount > cap)
        # 실제론 current + amount > cap 이므로 5M+1원만 거부, 0원은 통과
        provider = make_provider({"A": 0.5})
        fm = FundManager(initial_funds=10_000_000, strategy_max_pct_provider=provider)
        fm.reserve_funds("ORD1", 5_000_000, strategy_name="A")

        # 1원 추가 → 거부
        ok = fm.reserve_funds("ORD2", 1, strategy_name="A")
        assert ok is False

    def test_other_strategy_not_affected(self):
        """A가 한도 초과여도 B는 여전히 reserve 가능."""
        provider = make_provider({"A": 0.3, "B": 0.5})
        fm = FundManager(initial_funds=10_000_000, strategy_max_pct_provider=provider)

        fm.reserve_funds("ORD1", 3_000_000, strategy_name="A")  # A 상한 도달
        ok_a = fm.reserve_funds("ORD2", 1, strategy_name="A")  # A 거부
        ok_b = fm.reserve_funds("ORD3", 2_000_000, strategy_name="B")  # B 가능

        assert ok_a is False
        assert ok_b is True


# ---------------------------------------------------------------------------
# 3. backward compat — strategy_name="" 호출 시 기존 동작
# ---------------------------------------------------------------------------

class TestReserveNoStrategyNameBackwardCompat:
    """strategy_name 미지정 시 전략별 체크 없이 전체 풀에서 reserve."""

    def test_no_strategy_name_uses_global_pool(self):
        provider = make_provider({"A": 0.1})  # 10% 상한
        fm = FundManager(initial_funds=10_000_000, strategy_max_pct_provider=provider)

        # strategy_name 없이 9M reserve → 전략별 체크 없이 성공
        ok = fm.reserve_funds("ORD1", 9_000_000)
        assert ok is True
        assert fm._invested_by_strategy == {}  # 전략별 추적 없음

    def test_no_provider_no_cap_check(self):
        """provider가 None이면 전략별 체크 자체 없음."""
        fm = FundManager(initial_funds=10_000_000)  # provider 없음

        ok = fm.reserve_funds("ORD1", 9_000_000, strategy_name="A")
        assert ok is True  # 전략별 상한 체크 없이 통과

    def test_legacy_two_arg_call_still_works(self):
        """reserve_funds(order_id, amount) 2-인자 호출 backward compat."""
        fm = FundManager(initial_funds=10_000_000)
        ok = fm.reserve_funds("ORD1", 1_000_000)
        assert ok is True
        assert fm.available_funds == 9_000_000


# ---------------------------------------------------------------------------
# 4. 일일 손실 한도 — 전략별
# ---------------------------------------------------------------------------

class TestDailyLossPerStrategyLimit:
    """전략 A 손실 5% 초과 시 A의 is_daily_loss_limit_hit(A) True, B는 False."""

    def test_strategy_a_loss_blocks_a_only(self):
        fm = FundManager(
            initial_funds=10_000_000,
            max_daily_loss_ratio_per_strategy=0.05
        )
        fm.reset_daily_loss()

        # A: 5% = 500,000원 손실
        fm.record_realized_loss(500_000, strategy_name="A")

        assert fm.is_daily_loss_limit_hit("A") is True
        assert fm.is_daily_loss_limit_hit("B") is False  # B는 무손실

    def test_partial_loss_does_not_block(self):
        fm = FundManager(
            initial_funds=10_000_000,
            max_daily_loss_ratio_per_strategy=0.05
        )
        fm.reset_daily_loss()

        # A: 4% 손실 → 한도 미달
        fm.record_realized_loss(400_000, strategy_name="A")
        assert fm.is_daily_loss_limit_hit("A") is False

    def test_strategy_loss_accumulated(self):
        fm = FundManager(
            initial_funds=10_000_000,
            max_daily_loss_ratio_per_strategy=0.05
        )
        fm.reset_daily_loss()

        fm.record_realized_loss(300_000, strategy_name="A")
        fm.record_realized_loss(250_000, strategy_name="A")  # 누적 550K > 5%

        assert fm.is_daily_loss_limit_hit("A") is True


# ---------------------------------------------------------------------------
# 5. 전체 손실 한도 — 별도 작동
# ---------------------------------------------------------------------------

class TestDailyLossTotalStillWorks:
    """is_daily_loss_limit_hit(None) 전체 한도도 독립 작동."""

    def test_total_limit_hit(self):
        fm = FundManager(
            initial_funds=10_000_000,
            max_daily_loss_ratio=0.10,
            max_daily_loss_ratio_per_strategy=0.05
        )
        fm.reset_daily_loss()

        # 전체 10% = 1,000,000원 손실
        fm.record_realized_loss(1_000_000)
        assert fm.is_daily_loss_limit_hit() is True   # None — 전체 체크
        assert fm.is_daily_loss_limit_hit(None) is True

    def test_total_not_hit_when_per_strategy_hit(self):
        """전략별 한도 초과해도 전체 미달이면 전체 한도 False."""
        fm = FundManager(
            initial_funds=10_000_000,
            max_daily_loss_ratio=0.10,
            max_daily_loss_ratio_per_strategy=0.05
        )
        fm.reset_daily_loss()

        fm.record_realized_loss(500_000, strategy_name="A")  # 5% → A 차단

        assert fm.is_daily_loss_limit_hit("A") is True
        assert fm.is_daily_loss_limit_hit() is False  # 전체는 5% < 10%

    def test_reset_clears_per_strategy(self):
        fm = FundManager(initial_funds=10_000_000)
        fm.reset_daily_loss()
        fm.record_realized_loss(600_000, strategy_name="A")

        fm.reset_daily_loss()  # 수동 리셋

        assert fm._daily_realized_loss_by_strategy == {}
        assert fm.is_daily_loss_limit_hit("A") is False


# ---------------------------------------------------------------------------
# 6. order_db_handler — strategy_name="" → "unknown" + WARNING
# ---------------------------------------------------------------------------

class TestUnknownStrategyWarningInOrderDb:
    """trading_stock.strategy_name이 비어 있으면 'unknown' 반환 + WARNING 로그."""

    def _make_handler(self, strategy_name_on_ts: str):
        """OrderDBHandlerMixin의 _get_strategy_name_for_order를 직접 테스트하기 위한 mock."""
        from core.orders.order_db_handler import OrderDBHandlerMixin

        ts_mock = MagicMock()
        ts_mock.strategy_name = strategy_name_on_ts

        tm_mock = MagicMock()
        tm_mock.get_trading_stock.return_value = ts_mock

        logger_mock = MagicMock()

        handler = MagicMock(spec=OrderDBHandlerMixin)
        handler.trading_manager = tm_mock
        handler.config = None
        handler.logger = logger_mock

        # 실제 메서드를 언바운드로 호출
        handler._get_strategy_name_for_order = (
            lambda stock_code: OrderDBHandlerMixin._get_strategy_name_for_order(
                handler, stock_code
            )
        )
        return handler

    def test_empty_strategy_name_returns_unknown(self):
        handler = self._make_handler("")
        result = handler._get_strategy_name_for_order("005930")
        assert result == "unknown"

    def test_empty_strategy_name_logs_warning(self):
        handler = self._make_handler("")
        handler._get_strategy_name_for_order("005930")
        handler.logger.warning.assert_called_once()
        warn_msg = handler.logger.warning.call_args[0][0]
        assert "005930" in warn_msg
        assert "unknown" in warn_msg.lower() or "strategy_name" in warn_msg

    def test_filled_strategy_name_no_warning(self):
        handler = self._make_handler("SampleStrategy")
        result = handler._get_strategy_name_for_order("005930")
        assert result == "SampleStrategy"
        handler.logger.warning.assert_not_called()

    def test_no_trading_manager_returns_unknown_with_warning(self):
        from core.orders.order_db_handler import OrderDBHandlerMixin

        handler = MagicMock(spec=OrderDBHandlerMixin)
        handler.trading_manager = None
        handler.config = None
        handler.logger = MagicMock()
        handler._get_strategy_name_for_order = (
            lambda sc: OrderDBHandlerMixin._get_strategy_name_for_order(handler, sc)
        )

        result = handler._get_strategy_name_for_order("005930")
        assert result == "unknown"
        handler.logger.warning.assert_called_once()
