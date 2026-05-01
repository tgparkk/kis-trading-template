"""
Phase E1 — Strategy Registry + 다중 로딩 단위 테스트

검증 항목:
  - load_strategies(): 3개 spec → 3개 인스턴스
  - enabled=False 전략 제외
  - max_capital_pct 인스턴스에 설정됨
  - 합계 > 100% 시 WARNING 로그
  - DayTradingBot.strategies가 dict
  - config.strategy.name만 있어도 self.strategies 1개 dict (backward compat)
  - self.strategy가 첫 전략 인스턴스 (backward compat)
"""

import logging
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from strategies.config import StrategyLoader
from strategies.base import BaseStrategy


# ---------------------------------------------------------------------------
# 헬퍼: 전략 스펙 (실제 전략 폴더 sample/momentum/mean_reversion 사용)
# ---------------------------------------------------------------------------

SPEC_3 = [
    {"name": "sample",        "enabled": True,  "max_capital_pct": 0.4},
    {"name": "momentum",      "enabled": True,  "max_capital_pct": 0.3},
    {"name": "mean_reversion","enabled": True,  "max_capital_pct": 0.3},
]

SPEC_WITH_DISABLED = [
    {"name": "sample",   "enabled": True,  "max_capital_pct": 0.5},
    {"name": "momentum", "enabled": False, "max_capital_pct": 0.5},
]

SPEC_OVER_100 = [
    {"name": "sample",   "enabled": True, "max_capital_pct": 0.7},
    {"name": "momentum", "enabled": True, "max_capital_pct": 0.7},
]


# ---------------------------------------------------------------------------
# 1. load_strategies: 3개 spec → 3개 인스턴스
# ---------------------------------------------------------------------------

def test_load_strategies_3_specs():
    result = StrategyLoader.load_strategies(SPEC_3)
    assert len(result) == 3
    assert "sample" in result
    assert "momentum" in result
    assert "mean_reversion" in result
    for instance in result.values():
        assert isinstance(instance, BaseStrategy)


# ---------------------------------------------------------------------------
# 2. enabled=False 전략 제외
# ---------------------------------------------------------------------------

def test_load_strategies_disabled_skipped():
    result = StrategyLoader.load_strategies(SPEC_WITH_DISABLED)
    assert len(result) == 1
    assert "sample" in result
    assert "momentum" not in result


# ---------------------------------------------------------------------------
# 3. max_capital_pct 인스턴스에 설정됨
# ---------------------------------------------------------------------------

def test_load_strategies_max_capital_pct_set():
    result = StrategyLoader.load_strategies(SPEC_3)
    assert abs(result["sample"].max_capital_pct - 0.4) < 1e-9
    assert abs(result["momentum"].max_capital_pct - 0.3) < 1e-9
    assert abs(result["mean_reversion"].max_capital_pct - 0.3) < 1e-9


# ---------------------------------------------------------------------------
# 4. 합계 > 100% 시 WARNING 로그
# ---------------------------------------------------------------------------

def test_load_strategies_warning_over_100pct(caplog):
    with caplog.at_level(logging.WARNING, logger="strategies.config"):
        StrategyLoader.load_strategies(SPEC_OVER_100)
    assert any("100%" in r.message or "> 100" in r.message or "1.40" in r.message
               for r in caplog.records if r.levelno >= logging.WARNING), \
        f"WARNING 로그 미발생. 기록된 로그: {[r.message for r in caplog.records]}"


# ---------------------------------------------------------------------------
# 5~7. DayTradingBot 통합 (핵심 의존성 mock)
# ---------------------------------------------------------------------------

def _make_mock_bot(config_overrides: dict):
    """DayTradingBot.__init__ 핵심 의존성 전체 mock."""
    config = SimpleNamespace(
        strategy=SimpleNamespace(name="sample", enabled=True),
        strategies=None,
        risk_management=SimpleNamespace(max_daily_loss=0.1),
        **config_overrides,
    )

    patches = [
        patch("main.check_duplicate_process"),
        patch("main.load_config", return_value=config),
        patch("main.KISBroker", return_value=MagicMock()),
        patch("main.DatabaseManager", return_value=MagicMock()),
        patch("main.TelegramIntegration", return_value=MagicMock()),
        patch("main.RealTimeDataCollector", return_value=MagicMock()),
        patch("main.OrderManager", return_value=MagicMock()),
        patch("main.IntradayStockManager", return_value=MagicMock()),
        patch("main.TradingStockManager", return_value=MagicMock()),
        patch("main.TradingDecisionEngine", return_value=MagicMock(
            virtual_trading=MagicMock(), is_virtual_mode=False
        )),
        patch("main.FundManager", return_value=MagicMock()),
        patch("main.BotInitializer", return_value=MagicMock()),
        patch("main.TradingAnalyzer", return_value=MagicMock()),
        patch("main.SystemMonitor", return_value=MagicMock()),
        patch("main.LiquidationHandler", return_value=MagicMock()),
        patch("main.PositionSyncManager", return_value=MagicMock()),
        patch("main.StateRestorer", return_value=MagicMock()),
        patch("main.CandidateSelector", return_value=MagicMock()),
        patch("main.signal.signal"),
    ]
    return patches, config


def test_strategies_dict_in_bot():
    """DayTradingBot.strategies가 dict 타입."""
    patches, _ = _make_mock_bot({})
    started = [p.start() for p in patches]
    try:
        from main import DayTradingBot
        bot = DayTradingBot()
        assert isinstance(bot.strategies, dict)
    finally:
        for p in patches:
            p.stop()
        import importlib, main as m
        importlib.reload(m)


def test_backward_compat_single_strategy():
    """config.strategy.name만 있을 때 self.strategies가 1개 dict."""
    patches, _ = _make_mock_bot({})
    started = [p.start() for p in patches]
    try:
        from main import DayTradingBot
        bot = DayTradingBot()
        assert len(bot.strategies) == 1
        assert "sample" in bot.strategies
    finally:
        for p in patches:
            p.stop()
        import importlib, main as m
        importlib.reload(m)


def test_backward_compat_self_strategy():
    """self.strategy가 첫 전략 인스턴스 (backward compat)."""
    patches, _ = _make_mock_bot({})
    started = [p.start() for p in patches]
    try:
        from main import DayTradingBot
        bot = DayTradingBot()
        assert bot.strategy is not None
        assert isinstance(bot.strategy, BaseStrategy)
        # self.strategy == self.strategies의 첫 값
        first_val = next(iter(bot.strategies.values()))
        assert bot.strategy is first_val
    finally:
        for p in patches:
            p.stop()
        import importlib, main as m
        importlib.reload(m)
