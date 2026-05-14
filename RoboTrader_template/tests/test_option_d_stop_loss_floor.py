"""
옵션 D-A: 손절률 하한 -3.0% 강제 적용 검증
=========================================

사장님 결재 2026-05-14 — scientist 분석 결과에 따라
일부 종목 동적 손절률이 -1.95% ~ -2.99%로 비정상적으로 좁게
산출되는 케이스(예: 5/14 한온시스템) 방지 목적.

검증 지점: core/trading_decision_engine.py
  execute_virtual_buy()의 4단계 우선순위 종료 직후
  stop_loss_rate = max(stop_loss_rate, 0.03) 강제 적용

검증 시나리오:
  1. 동적 산출값 -1.95% → 적용값 -3.0% (하한 발동)
  2. 동적 산출값 -2.99% → 적용값 -3.0% (하한 발동 경계)
  3. 동적 산출값 -3.0% → 적용값 -3.0% (경계 — 발동 안 함)
  4. 동적 산출값 -5.0% → 적용값 -5.0% (하한 미발동, 그대로 유지)
  5. Signal 경로(2순위)에서 산출된 좁은 손절도 하한 적용
"""
import asyncio
import sys
from pathlib import Path
from unittest.mock import Mock, MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))


# ============================================================================
# Helpers
# ============================================================================

def _build_engine_with_mocks():
    """TradingDecisionEngine + 가상매매 의존성 mock 구성."""
    with patch('core.trading_decision_engine.setup_logger'), \
         patch('core.virtual_trading_manager.setup_logger'):
        from core.trading_decision_engine import TradingDecisionEngine
        engine = TradingDecisionEngine(
            db_manager=Mock(),
            telegram_integration=None,
            trading_manager=None,
            broker=None,
            config=Mock(paper_trading=True),
        )

    # virtual_trading.execute_virtual_buy: 호출 시 받은 stop_loss_rate를 캡처
    captured = {}

    def _capture(*, stock_code, stock_name, price, quantity,
                 strategy, reason, target_profit_rate, stop_loss_rate):
        captured['stop_loss_rate'] = stop_loss_rate
        captured['target_profit_rate'] = target_profit_rate
        return 12345  # virtual record id

    engine.virtual_trading.execute_virtual_buy = Mock(side_effect=_capture)
    engine.virtual_trading.get_max_quantity = Mock(return_value=10)

    # 전략 콜백 통보는 본 테스트와 무관 — no-op
    engine._notify_strategy_order_filled = Mock()

    return engine, captured


def _build_trading_stock(stock_code="005930", stock_name="삼성전자"):
    """최소 TradingStock 객체."""
    from core.models import TradingStock, StockState
    from datetime import datetime
    return TradingStock(
        stock_code=stock_code,
        stock_name=stock_name,
        state=StockState.SELECTED,
        selected_time=datetime.now(),
    )


def _run_virtual_buy(engine, *, stock_loss_rate=None, target_rate=None,
                     buy_price=10000.0, signal=None):
    """가상매수 실행 헬퍼 — combined_data=None, buy_price=고정."""
    ts = _build_trading_stock()
    coro = engine.execute_virtual_buy(
        trading_stock=ts,
        combined_data=None,
        buy_reason="test",
        buy_price=buy_price,
        quantity=10,
        target_profit_rate=target_rate,
        stop_loss_rate=stock_loss_rate,
        signal=signal,
    )
    asyncio.get_event_loop().run_until_complete(coro)
    return ts


# ============================================================================
# Test: 옵션 D-A 손절 하한 강제 적용
# ============================================================================

class TestStopLossFloor:
    """동적 산출된 손절률에 하한 -3.0% (0.03)이 강제 적용되는지 검증."""

    def test_narrow_dynamic_stop_loss_floored_to_3pct(self):
        """동적 -1.95% → 강제 -3.0% (5/14 한온시스템 케이스 재현)."""
        engine, captured = _build_engine_with_mocks()
        _run_virtual_buy(engine, stock_loss_rate=0.0195, target_rate=0.05)
        assert captured['stop_loss_rate'] == pytest.approx(0.03), \
            f"손절 하한 미적용: 1.95% 입력 → {captured['stop_loss_rate']*100:.2f}% 출력"

    def test_boundary_2_99pct_floored_to_3pct(self):
        """동적 -2.99% → 강제 -3.0% (경계 케이스)."""
        engine, captured = _build_engine_with_mocks()
        _run_virtual_buy(engine, stock_loss_rate=0.0299, target_rate=0.05)
        assert captured['stop_loss_rate'] == pytest.approx(0.03)

    def test_exact_3pct_unchanged(self):
        """동적 -3.0% → 그대로 -3.0% (경계 — 발동 안 함)."""
        engine, captured = _build_engine_with_mocks()
        _run_virtual_buy(engine, stock_loss_rate=0.03, target_rate=0.05)
        assert captured['stop_loss_rate'] == pytest.approx(0.03)

    def test_wide_5pct_unchanged(self):
        """동적 -5.0% → 그대로 -5.0% (하한보다 넓으므로 미발동)."""
        engine, captured = _build_engine_with_mocks()
        _run_virtual_buy(engine, stock_loss_rate=0.05, target_rate=0.10)
        assert captured['stop_loss_rate'] == pytest.approx(0.05)

    def test_signal_path_narrow_stop_floored(self):
        """Signal.stop_loss로 좁게 산출돼도 하한 적용 (2순위 경로 검증)."""
        engine, captured = _build_engine_with_mocks()

        # Signal: target_price=10300 (3%), stop_loss=9805 (-1.95%)
        signal = MagicMock()
        signal.target_price = 10300.0
        signal.stop_loss = 9805.0  # buy_price 10000 대비 -1.95%

        # 호출자는 명시값을 안 줘서 2순위(Signal) → 비율 변환 → 하한 적용
        _run_virtual_buy(
            engine,
            stock_loss_rate=None,
            target_rate=None,
            buy_price=10000.0,
            signal=signal,
        )
        assert captured['stop_loss_rate'] == pytest.approx(0.03), \
            f"Signal 경로 하한 미적용: 환산 -1.95% → {captured['stop_loss_rate']*100:.2f}%"

    def test_trading_stock_attribute_floored(self):
        """trading_stock.stop_loss_rate에도 하한 적용된 값이 기록되는지 (DB 일관성)."""
        engine, _ = _build_engine_with_mocks()
        ts = _run_virtual_buy(engine, stock_loss_rate=0.02, target_rate=0.05)
        assert ts.stop_loss_rate == pytest.approx(0.03), \
            f"trading_stock 속성 하한 미반영: {ts.stop_loss_rate}"
