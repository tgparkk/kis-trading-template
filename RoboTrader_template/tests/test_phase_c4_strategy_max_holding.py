"""
Phase C4: 스윙 전략 max_holding_days config.yaml 표준화 테스트
==============================================================

각 스윙 전략이 config에서 max_holding_days를 읽어
BaseStrategy.max_holding_days 속성으로 설정하는지 검증.

테스트 목록:
- test_momentum_max_holding_from_config: Momentum 10일 (기본)
- test_momentum_max_holding_custom: 커스텀 값 반영
- test_bb_reversion_max_holding_from_config: BBReversion 15일
- test_mean_reversion_max_holding_from_config: MeanReversion 7일
- test_lynch_max_holding_from_config: Lynch 120일
- test_sawkami_max_holding_from_config: Sawkami 40일
- test_all_strategies_max_holding_is_int_or_none: 모두 int 또는 None
"""
import pytest
from unittest.mock import MagicMock


def _broker():
    return MagicMock()


def _dp():
    return MagicMock()


def _exec():
    return MagicMock()


# ============================================================================
# Momentum
# ============================================================================

class TestMomentumMaxHolding:
    def test_momentum_max_holding_from_config(self):
        from strategies.momentum.strategy import MomentumStrategy
        s = MomentumStrategy(config={"parameters": {"max_holding_days": 10}})
        s.on_init(_broker(), _dp(), _exec())
        assert s.max_holding_days == 10

    def test_momentum_max_holding_custom(self):
        from strategies.momentum.strategy import MomentumStrategy
        s = MomentumStrategy(config={"parameters": {"max_holding_days": 7}})
        s.on_init(_broker(), _dp(), _exec())
        assert s.max_holding_days == 7

    def test_momentum_max_holding_default(self):
        from strategies.momentum.strategy import MomentumStrategy
        s = MomentumStrategy()
        s.on_init(_broker(), _dp(), _exec())
        assert s.max_holding_days == 10  # 기본값


# ============================================================================
# BBReversion
# ============================================================================

class TestBBReversionMaxHolding:
    def test_bb_reversion_max_holding_from_config(self):
        from strategies.bb_reversion.strategy import BBReversionStrategy
        cfg = {
            "parameters": {"max_holding_days": 15},
            "risk_management": {"max_holding_days": 15},
        }
        s = BBReversionStrategy(config=cfg)
        s.on_init(_broker(), _dp(), _exec())
        assert s.max_holding_days == 15

    def test_bb_reversion_max_holding_custom(self):
        from strategies.bb_reversion.strategy import BBReversionStrategy
        cfg = {
            "parameters": {"max_holding_days": 20},
            "risk_management": {"max_holding_days": 15},
        }
        s = BBReversionStrategy(config=cfg)
        s.on_init(_broker(), _dp(), _exec())
        # parameters 섹션이 우선
        assert s.max_holding_days == 20

    def test_bb_reversion_max_holding_fallback_risk(self):
        """parameters에 max_holding_days 없으면 risk_management 폴백."""
        from strategies.bb_reversion.strategy import BBReversionStrategy
        cfg = {
            "parameters": {},
            "risk_management": {"max_holding_days": 12},
        }
        s = BBReversionStrategy(config=cfg)
        s.on_init(_broker(), _dp(), _exec())
        assert s.max_holding_days == 12


# ============================================================================
# MeanReversion
# ============================================================================

class TestMeanReversionMaxHolding:
    def test_mean_reversion_max_holding_from_config(self):
        from strategies.mean_reversion.strategy import MeanReversionStrategy
        cfg = {"parameters": {"max_holding_days": 7}, "risk_management": {}}
        s = MeanReversionStrategy(config=cfg)
        s.on_init(_broker(), _dp(), _exec())
        assert s.max_holding_days == 7

    def test_mean_reversion_max_holding_default(self):
        from strategies.mean_reversion.strategy import MeanReversionStrategy
        s = MeanReversionStrategy()
        s.on_init(_broker(), _dp(), _exec())
        assert s.max_holding_days == 7  # 기본값


# ============================================================================
# Lynch
# ============================================================================

class TestLynchMaxHolding:
    def test_lynch_max_holding_from_config(self):
        from strategies.lynch.strategy import LynchStrategy
        cfg = {
            "parameters": {"max_holding_days": 120},
            "risk_management": {"max_hold_days": 120},
            "paper_trading": True,
        }
        s = LynchStrategy(config=cfg)
        try:
            s.on_init(_broker(), _dp(), _exec())
        except Exception:
            pass
        assert s.max_holding_days == 120

    def test_lynch_max_holding_fallback_risk(self):
        """parameters에 없으면 risk_management.max_hold_days 사용."""
        from strategies.lynch.strategy import LynchStrategy
        cfg = {
            "parameters": {},
            "risk_management": {"max_hold_days": 90},
            "paper_trading": True,
        }
        s = LynchStrategy(config=cfg)
        try:
            s.on_init(_broker(), _dp(), _exec())
        except Exception:
            pass
        assert s.max_holding_days == 90

    def test_lynch_max_holding_default(self):
        """config 없을 때 기본값 120."""
        from strategies.lynch.strategy import LynchStrategy
        s = LynchStrategy()
        try:
            s.on_init(_broker(), _dp(), _exec())
        except Exception:
            pass
        assert s.max_holding_days == 120


# ============================================================================
# Sawkami
# ============================================================================

class TestSawkamiMaxHolding:
    def test_sawkami_max_holding_from_config(self):
        from strategies.sawkami.strategy import SawkamiStrategy
        cfg = {
            "parameters": {"max_holding_days": 40},
            "risk_management": {"max_hold_days": 40},
            "paper_trading": True,
        }
        s = SawkamiStrategy(config=cfg)
        try:
            s.on_init(_broker(), _dp(), _exec())
        except Exception:
            pass
        assert s.max_holding_days == 40

    def test_sawkami_max_holding_fallback_risk(self):
        from strategies.sawkami.strategy import SawkamiStrategy
        cfg = {
            "parameters": {},
            "risk_management": {"max_hold_days": 30},
            "paper_trading": True,
        }
        s = SawkamiStrategy(config=cfg)
        try:
            s.on_init(_broker(), _dp(), _exec())
        except Exception:
            pass
        assert s.max_holding_days == 30

    def test_sawkami_max_holding_default(self):
        from strategies.sawkami.strategy import SawkamiStrategy
        s = SawkamiStrategy()
        try:
            s.on_init(_broker(), _dp(), _exec())
        except Exception:
            pass
        assert s.max_holding_days == 40


# ============================================================================
# 전략별 타입 검증
# ============================================================================

class TestAllStrategiesMaxHoldingType:
    """모든 스윙 전략의 max_holding_days가 int (또는 None)인지."""

    def _get_max_holding(self, strategy_cls, config):
        s = strategy_cls(config=config)
        try:
            s.on_init(_broker(), _dp(), _exec())
        except Exception:
            pass
        return s.max_holding_days

    def test_momentum_type(self):
        from strategies.momentum.strategy import MomentumStrategy
        v = self._get_max_holding(MomentumStrategy, {})
        assert v is None or isinstance(v, int)

    def test_bb_reversion_type(self):
        from strategies.bb_reversion.strategy import BBReversionStrategy
        v = self._get_max_holding(BBReversionStrategy, {})
        assert v is None or isinstance(v, int)

    def test_mean_reversion_type(self):
        from strategies.mean_reversion.strategy import MeanReversionStrategy
        v = self._get_max_holding(MeanReversionStrategy, {})
        assert v is None or isinstance(v, int)

    def test_lynch_type(self):
        from strategies.lynch.strategy import LynchStrategy
        v = self._get_max_holding(LynchStrategy, {"paper_trading": True})
        assert v is None or isinstance(v, int)

    def test_sawkami_type(self):
        from strategies.sawkami.strategy import SawkamiStrategy
        v = self._get_max_holding(SawkamiStrategy, {"paper_trading": True})
        assert v is None or isinstance(v, int)
