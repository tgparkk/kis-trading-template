"""
FinancialRatioEntry 단위 테스트

수정 내용:
- per 필드 추가 (per_pbr_rate / per / eps_per_rto / stk_per 키 폴백)
- roe 프로퍼티 추가 (roe_value 별칭)
- debt_ratio 프로퍼티 추가 (liability_ratio 별칭)
"""

import os
import sys
from datetime import datetime

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from api.kis_financial_api import FinancialRatioEntry


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def _make_entry(**overrides) -> FinancialRatioEntry:
    base = {
        "stck_cd": "005930",
        "stac_yymm": "202312",
        "grs": "10.5",
        "bsop_prfi_inrt": "75.0",
        "ntin_inrt": "20.0",
        "roe_val": "12.5",
        "eps": "5000",
        "sps": "30000",
        "bps": "50000",
        "rsrv_rate": "50.0",
        "lblt_rate": "80.0",
    }
    base.update(overrides)
    return FinancialRatioEntry.from_api_output(base)


# ---------------------------------------------------------------------------
# from_api_output — per 파싱
# ---------------------------------------------------------------------------

class TestFromApiOutputPer:
    def test_per_from_per_pbr_rate_key(self):
        entry = _make_entry(per_pbr_rate="15.3")
        assert entry.per == pytest.approx(15.3)

    def test_per_from_per_key_fallback(self):
        """per_pbr_rate 없을 때 per 키 사용"""
        entry = _make_entry(per="20.0")
        assert entry.per == pytest.approx(20.0)

    def test_per_from_eps_per_rto_fallback(self):
        entry = _make_entry(eps_per_rto="18.5")
        assert entry.per == pytest.approx(18.5)

    def test_per_from_stk_per_fallback(self):
        entry = _make_entry(stk_per="22.1")
        assert entry.per == pytest.approx(22.1)

    def test_per_defaults_to_zero_when_missing(self):
        """PER 키가 전혀 없으면 0.0"""
        entry = _make_entry()
        assert entry.per == pytest.approx(0.0)

    def test_per_defaults_to_zero_on_empty_string(self):
        entry = _make_entry(per="")
        assert entry.per == pytest.approx(0.0)

    def test_per_defaults_to_zero_on_none(self):
        entry = _make_entry(per_pbr_rate=None)
        assert entry.per == pytest.approx(0.0)

    def test_per_priority_per_pbr_rate_over_per(self):
        """per_pbr_rate가 있으면 per 키보다 우선"""
        entry = _make_entry(per_pbr_rate="10.0", per="99.9")
        assert entry.per == pytest.approx(10.0)

    def test_per_with_comma_formatted_value(self):
        entry = _make_entry(per_pbr_rate="1,234.5")
        assert entry.per == pytest.approx(1234.5)

    def test_per_with_invalid_string(self):
        entry = _make_entry(per_pbr_rate="N/A")
        assert entry.per == pytest.approx(0.0)


# ---------------------------------------------------------------------------
# roe / debt_ratio 프로퍼티
# ---------------------------------------------------------------------------

class TestProperties:
    def test_roe_equals_roe_value(self):
        entry = _make_entry(roe_val="12.5")
        assert entry.roe == pytest.approx(12.5)
        assert entry.roe == entry.roe_value

    def test_debt_ratio_equals_liability_ratio(self):
        entry = _make_entry(lblt_rate="80.0")
        assert entry.debt_ratio == pytest.approx(80.0)
        assert entry.debt_ratio == entry.liability_ratio

    def test_roe_zero_when_missing(self):
        entry = _make_entry(roe_val="")
        assert entry.roe == pytest.approx(0.0)

    def test_debt_ratio_zero_when_missing(self):
        entry = _make_entry(lblt_rate=None)
        assert entry.debt_ratio == pytest.approx(0.0)


# ---------------------------------------------------------------------------
# Lynch screener 호환 — evaluate_buy_conditions
# ---------------------------------------------------------------------------

class TestLynchBuyConditionsCompat:
    """
    per=0.0 종목은 Lynch의 evaluate_buy_conditions에서 탈락해야 한다.
    (PER≤0 → False 반환)
    """

    def test_per_zero_rejected_by_lynch(self):
        from strategies.lynch.strategy import LynchStrategy
        entry = _make_entry()  # per=0.0
        fund = {
            "per": entry.per,
            "op_income_growth": entry.operating_income_growth,
            "debt_ratio": entry.debt_ratio,
            "roe": entry.roe,
        }
        ok, reasons = LynchStrategy.evaluate_buy_conditions(
            current_price=10000,
            rsi_value=30.0,
            fundamentals=fund,
        )
        assert ok is False
        assert any("PER" in r or "적자" in r for r in reasons)

    def test_per_positive_passes_peg_check(self):
        from strategies.lynch.strategy import LynchStrategy
        # PEG = per / op_growth = 6.0 / 80.0 = 0.075 <= 0.3
        entry = _make_entry(per_pbr_rate="6.0", bsop_prfi_inrt="80.0",
                            lblt_rate="100.0", roe_val="10.0")
        fund = {
            "per": entry.per,
            "op_income_growth": entry.operating_income_growth,
            "debt_ratio": entry.debt_ratio,
            "roe": entry.roe,
        }
        ok, reasons = LynchStrategy.evaluate_buy_conditions(
            current_price=10000,
            rsi_value=30.0,
            fundamentals=fund,
            peg_max=0.3,
            op_growth_min=70.0,
            debt_ratio_max=200.0,
            roe_min=5.0,
            rsi_oversold=35.0,
        )
        assert ok is True
