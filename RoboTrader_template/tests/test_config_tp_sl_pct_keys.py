"""
회귀 버그: 전략 config tp/sl이 실시간 청산에 도달하지 못함 (커밋 5c17f56 회귀)
=====================================================================

배경:
  execute_virtual_buy()의 tp/sl 3순위(전략 config) 블록이 `take_profit_ratio`/
  `stop_loss_ratio` 키만 읽는다. 그러나 8개 활성 전략 config.yaml은 전부
  `take_profit_pct`/`stop_loss_pct` 키만 가진다 → 3순위 항상 None →
  4순위 글로벌 DEFAULT(tp 0.15 / sl 0.10)로 낙하 → 전 전략 청산률 고정.

추가:
  3순위가 `self.strategy`(멀티전략 모드 고정 참조)를 읽어 소유 전략이 아닌
  config(예: Elder)로 오염될 수 있음. strategy_name(폴더키)으로 소유 전략을
  self.strategies_by_key에서 해소해야 한다(라인 605 owner 해소와 동일 원칙).

검증:
  1. config `_pct` 키가 저장 rate에 도달
  2. 소유 전략 해소: self.strategy != owner여도 strategy_name으로 owner config 사용
  3. 레거시 `_ratio` 키 fallback 유지
  4. config 없음 → 4순위 DEFAULT 0.15/0.10
  5. config `_pct`가 FLOOR(0.03) 미만 → clamp 유지
"""
import asyncio
from unittest.mock import Mock

import pytest

from core.trading_decision_engine import TradingDecisionEngine
from core.models import TradingStock, StockState


def _make_engine(strategy=None, strategies_by_key=None):
    """execute_virtual_buy 경로를 태우기 위한 최소 의존성 엔진."""
    engine = TradingDecisionEngine.__new__(TradingDecisionEngine)
    engine.logger = Mock()
    engine.strategy = strategy
    engine.intraday_manager = None
    engine.broker = None
    engine.config = Mock(risk_management=None)
    engine.strategies_by_key = strategies_by_key or {}

    vtm = Mock()
    vtm.get_max_quantity.return_value = 10
    vtm.execute_virtual_buy.return_value = 123
    engine.virtual_trading = vtm

    engine._notify_strategy_order_filled = Mock()
    return engine


def _make_trading_stock():
    return TradingStock(
        stock_code="005930",
        stock_name="삼성전자",
        state=StockState.SELECTED,
        selected_time=__import__('datetime').datetime.now(),
    )


def _strategy(name, tp_key, tp_val, sl_key, sl_val):
    s = Mock()
    s.name = name
    s.config = {"risk_management": {tp_key: tp_val, sl_key: sl_val}}
    return s


def _run(engine, strategy_name, buy_price=100_000):
    stock = _make_trading_stock()
    result = asyncio.new_event_loop().run_until_complete(
        engine.execute_virtual_buy(
            trading_stock=stock,
            combined_data=None,
            buy_reason="test",
            buy_price=buy_price,
            strategy_name=strategy_name,
        )
    )
    return result, stock


def test_config_pct_keys_reach_stored_rate():
    """config의 take_profit_pct/stop_loss_pct가 저장 rate에 도달 (회귀 재현 → 수정 후 green).

    elder 예: tp_pct=0.30 / sl_pct=0.08 → 저장 rate = 0.30 / 0.08.
    수정 전: 3순위가 _ratio만 읽어 None → DEFAULT 0.15/0.10으로 낙하(실패).
    """
    strategy = _strategy("elder_ema_pullback",
                         "take_profit_pct", 0.30, "stop_loss_pct", 0.08)
    engine = _make_engine(strategy=strategy,
                          strategies_by_key={"elder_ema_pullback": strategy})

    result, stock = _run(engine, "elder_ema_pullback")
    assert result is True
    assert stock.target_profit_rate == pytest.approx(0.30)
    assert stock.stop_loss_rate == pytest.approx(0.08)


def test_owner_strategy_resolved_by_strategy_name_not_self_strategy():
    """self.strategy가 elder여도 strategy_name='book_pullback_ma5'면 ma5 config 사용.

    멀티전략 모드 self.strategy 고정 참조 오염 방어.
    ma5: tp_pct=0.15 / sl_pct=0.03.
    """
    elder = _strategy("elder_ema_pullback",
                      "take_profit_pct", 0.30, "stop_loss_pct", 0.08)
    ma5 = _strategy("book_pullback_ma5",
                    "take_profit_pct", 0.15, "stop_loss_pct", 0.03)

    # self.strategy는 elder(고정), 소유 전략은 strategy_name으로 해소
    engine = _make_engine(strategy=elder,
                          strategies_by_key={"book_pullback_ma5": ma5,
                                             "elder_ema_pullback": elder})

    result, stock = _run(engine, "book_pullback_ma5")
    assert result is True
    assert stock.target_profit_rate == pytest.approx(0.15)
    assert stock.stop_loss_rate == pytest.approx(0.03)  # FLOOR 0.03 경계 — 미발동


def test_legacy_ratio_keys_still_work():
    """레거시 take_profit_ratio/stop_loss_ratio 키 fallback 유지."""
    strategy = _strategy("legacy",
                         "take_profit_ratio", 0.12, "stop_loss_ratio", 0.07)
    engine = _make_engine(strategy=strategy,
                          strategies_by_key={"legacy": strategy})

    result, stock = _run(engine, "legacy")
    assert result is True
    assert stock.target_profit_rate == pytest.approx(0.12)
    assert stock.stop_loss_rate == pytest.approx(0.07)


def test_no_config_falls_to_default():
    """전략 config 없음 → 4순위 DEFAULT 0.15 / 0.10."""
    engine = _make_engine(strategy=None, strategies_by_key={})

    result, stock = _run(engine, "unknown_strategy")
    assert result is True
    assert stock.target_profit_rate == pytest.approx(0.15)
    assert stock.stop_loss_rate == pytest.approx(0.10)


def test_config_pct_below_floor_clamped():
    """config stop_loss_pct=0.02 (3% 미만) → FLOOR 0.03으로 clamp."""
    strategy = _strategy("tight",
                         "take_profit_pct", 0.15, "stop_loss_pct", 0.02)
    engine = _make_engine(strategy=strategy,
                          strategies_by_key={"tight": strategy})

    result, stock = _run(engine, "tight")
    assert result is True
    assert stock.target_profit_rate == pytest.approx(0.15)
    assert stock.stop_loss_rate == pytest.approx(0.03)


# ---------------------------------------------------------------------------
# L2 (관찰성): config tp/sl 누락 → 4순위 DEFAULT 폴백 발동 시 WARNING 로그
#   동작은 불변(여전히 0.15/0.10 적용). 사일런트 디폴트를 로그로 표면화만 한다.
# ---------------------------------------------------------------------------

def _default_warning_logged(engine) -> bool:
    """logger.warning 호출 중 tp/sl DEFAULT 폴백 경고가 있는지."""
    for c in engine.logger.warning.call_args_list:
        msg = c.args[0] if c.args else ""
        if "DEFAULT" in str(msg) and ("tp" in str(msg) or "sl" in str(msg) or "손익절" in str(msg)):
            return True
    return False


def test_default_fallback_emits_warning():
    """config risk_management 누락 → DEFAULT 0.15/0.10 폴백 발동 시 WARNING 로그."""
    engine = _make_engine(strategy=None, strategies_by_key={})

    result, stock = _run(engine, "unknown_strategy")
    assert result is True
    # 동작 불변: 여전히 DEFAULT 적용
    assert stock.target_profit_rate == pytest.approx(0.15)
    assert stock.stop_loss_rate == pytest.approx(0.10)
    # 관찰성: 사일런트 디폴트를 경고로 표면화
    assert _default_warning_logged(engine), "DEFAULT 폴백 발동 시 WARNING 로그가 있어야 합니다."


def test_config_present_emits_no_default_warning():
    """config tp/sl 존재 → DEFAULT 미발동 → 경고 없음."""
    strategy = _strategy("elder_ema_pullback",
                         "take_profit_pct", 0.30, "stop_loss_pct", 0.08)
    engine = _make_engine(strategy=strategy,
                          strategies_by_key={"elder_ema_pullback": strategy})

    result, stock = _run(engine, "elder_ema_pullback")
    assert result is True
    assert not _default_warning_logged(engine), "config 존재 시 DEFAULT 경고가 없어야 합니다."
