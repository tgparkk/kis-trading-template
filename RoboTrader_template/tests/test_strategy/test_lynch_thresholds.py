"""
Lynch Strategy 임계값 완화 회귀 테스트 (2026-05-14)

배경: 8영업일 연속 후보 0건 → PEG≤0.3, 영업이익 YoY≥70% 두 임계값을
PEG≤1.3, YoY≥30%로 완화. 기존 임계값에서 탈락하던 종목이 새 임계값으로
통과하는지 evaluate_buy_conditions 정적 메서드로 검증.
"""

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from strategies.lynch.strategy import LynchStrategy
from strategies.lynch.screener import LynchCandidateSelector, LynchScreenerAdapter


# ============================================================================
# 1. 기본값 회귀 검증
# ============================================================================

class TestLynchDefaultsRelaxed_2026_05_14:
    """Lynch 임계값 완화 시점의 default 값이 모든 경로에서 일관되게 적용되는지 검증."""

    def test_evaluate_buy_conditions_defaults(self):
        """evaluate_buy_conditions의 keyword 기본값이 완화 후 값과 일치"""
        import inspect

        sig = inspect.signature(LynchStrategy.evaluate_buy_conditions)
        peg_default = sig.parameters["peg_max"].default
        op_default = sig.parameters["op_growth_min"].default

        assert peg_default == 1.3, f"peg_max default 1.3 기대, 실제 {peg_default}"
        assert op_default == 30.0, f"op_growth_min default 30.0 기대, 실제 {op_default}"

    def test_screener_default_params(self):
        """LynchScreenerAdapter.default_params()도 동일한 완화 임계값"""
        # broker/config 주입 없이 default_params만 호출 (의존성 우회)
        adapter = LynchScreenerAdapter.__new__(LynchScreenerAdapter)
        params = adapter.default_params()

        assert params["peg_max"] == 1.3
        assert params["op_income_growth_min"] == 30.0


# ============================================================================
# 2. 통과/탈락 케이스 — PEG 1.0 종목 (기존 0.3 탈락, 새 1.3 통과)
# ============================================================================

class TestLynchBuyConditionsRelaxed:
    """완화된 임계값 기준 buy 조건 통과/탈락 회귀 케이스."""

    def _base_fundamentals(self):
        """PEG=1.0 (per=40 / op_growth=40), 부채/ROE 통과 구성"""
        return {
            "per": 40.0,           # PER 40
            "op_income_growth": 40.0,  # YoY 40%  → PEG = 40/40 = 1.0
            "debt_ratio": 100.0,   # 부채비율 100% (200% 한도 통과)
            "roe": 10.0,           # ROE 10% (5% 한도 통과)
        }

    def test_peg_1_0_passes_with_new_threshold(self):
        """PEG=1.0인 종목이 새 임계값 peg_max=1.3 으로 통과해야 한다."""
        should_buy, reasons = LynchStrategy.evaluate_buy_conditions(
            current_price=10000,
            rsi_value=25.0,
            fundamentals=self._base_fundamentals(),
            # defaults 사용 (peg_max=1.3, op_growth_min=30.0)
        )
        assert should_buy is True, f"통과 실패. reasons={reasons}"
        # 이유 라벨에 PEG/영업이익 성장이 포함되어 있어야 함
        joined = " ".join(reasons)
        assert "PEG" in joined and "1.000" in joined
        assert "40.0%" in joined  # 영업이익 YoY +40.0%

    def test_peg_1_0_fails_with_old_threshold(self):
        """PEG=1.0은 기존 임계값 peg_max=0.3 으로는 탈락해야 한다 (회귀 보장)."""
        should_buy, reasons = LynchStrategy.evaluate_buy_conditions(
            current_price=10000,
            rsi_value=25.0,
            fundamentals=self._base_fundamentals(),
            peg_max=0.3,           # 기존 임계값 명시
            op_growth_min=70.0,    # 기존 임계값 명시
        )
        assert should_buy is False
        # PEG 또는 영업이익성장 둘 중 하나로 reject
        joined = " ".join(reasons)
        assert ("PEG" in joined and ">" in joined) or "영업이익성장" in joined

    def test_op_growth_40_passes_with_new_threshold(self):
        """영업이익 YoY 40% 종목이 새 임계값 30% 로 통과 (PEG 별도 조정)."""
        fund = {
            "per": 10.0,
            "op_income_growth": 40.0,  # YoY 40% → PEG=10/40=0.25
            "debt_ratio": 100.0,
            "roe": 10.0,
        }
        should_buy, reasons = LynchStrategy.evaluate_buy_conditions(
            current_price=10000,
            rsi_value=25.0,
            fundamentals=fund,
        )
        assert should_buy is True, f"통과 실패. reasons={reasons}"

    def test_op_growth_40_fails_with_old_threshold(self):
        """영업이익 YoY 40% 는 기존 임계값 70% 로는 탈락해야 한다."""
        fund = {
            "per": 10.0,
            "op_income_growth": 40.0,
            "debt_ratio": 100.0,
            "roe": 10.0,
        }
        should_buy, reasons = LynchStrategy.evaluate_buy_conditions(
            current_price=10000,
            rsi_value=25.0,
            fundamentals=fund,
            peg_max=0.3,
            op_growth_min=70.0,
        )
        assert should_buy is False
        assert any("영업이익성장" in r for r in reasons)

    def test_peg_1_5_still_rejected(self):
        """PEG=1.5는 새 임계값 1.3 으로도 탈락해야 한다 (상한선 명확화)."""
        fund = {
            "per": 60.0,
            "op_income_growth": 40.0,  # PEG = 60/40 = 1.5
            "debt_ratio": 100.0,
            "roe": 10.0,
        }
        should_buy, reasons = LynchStrategy.evaluate_buy_conditions(
            current_price=10000,
            rsi_value=25.0,
            fundamentals=fund,
        )
        assert should_buy is False
        assert any("PEG" in r and ">" in r for r in reasons)
