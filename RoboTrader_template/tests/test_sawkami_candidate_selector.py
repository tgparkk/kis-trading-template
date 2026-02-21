"""
SawkamiCandidateSelector 유닛 테스트
"""

import asyncio
import json
import tempfile
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List
from unittest.mock import MagicMock, patch

import pytest

# 테스트 대상
from strategies.sawkami.screener import (
    SawkamiCandidateSelector,
    SawkamiFundamentalData,
)
from core.candidate_selector import CandidateStock
from core.models import TradingConfig


# ============================================================================
# Fixtures
# ============================================================================

@pytest.fixture
def trading_config():
    return TradingConfig()


@pytest.fixture
def mock_broker():
    return MagicMock()


@pytest.fixture
def selector(trading_config, mock_broker):
    sel = SawkamiCandidateSelector(
        config=trading_config,
        broker=mock_broker,
        strategy_params={
            "op_income_growth_min": 30.0,
            "pbr_max": 1.5,
            "high52w_drop_pct": -20.0,
            "rsi_oversold": 30,
            "volume_ratio_min": 1.5,
        },
    )
    return sel


@pytest.fixture
def sample_stocks():
    return [
        {"code": "005930", "name": "삼성전자", "market": "KOSPI"},
        {"code": "000660", "name": "SK하이닉스", "market": "KOSPI"},
        {"code": "035420", "name": "NAVER", "market": "KOSDAQ"},
        {"code": "069500", "name": "KODEX 200", "market": "KOSPI"},       # ETF
        {"code": "005935", "name": "삼성전자우", "market": "KOSPI"},       # 우선주
        {"code": "999999", "name": "테스트종목", "market": "KONEX"},       # 제외 시장
    ]


# ============================================================================
# 1차 필터 테스트
# ============================================================================

class TestBasicFilters:
    def test_includes_kospi_and_kosdaq(self, selector, sample_stocks):
        result = selector._apply_basic_filters(sample_stocks)
        codes = [s['code'] for s in result]
        assert "005930" in codes  # KOSPI
        assert "035420" in codes  # KOSDAQ

    def test_excludes_etf(self, selector, sample_stocks):
        result = selector._apply_basic_filters(sample_stocks)
        codes = [s['code'] for s in result]
        assert "069500" not in codes  # KODEX ETF

    def test_excludes_preferred_stock(self, selector, sample_stocks):
        result = selector._apply_basic_filters(sample_stocks)
        codes = [s['code'] for s in result]
        assert "005935" not in codes  # 우선주

    def test_excludes_konex(self, selector, sample_stocks):
        result = selector._apply_basic_filters(sample_stocks)
        codes = [s['code'] for s in result]
        assert "999999" not in codes  # KONEX


# ============================================================================
# 스코어링 테스트
# ============================================================================

class TestScoring:
    def test_score_range(self, selector):
        score = selector._calculate_sawkami_score(
            op_growth=50.0,
            drop_pct=-30.0,
            rsi=15.0,
            pbr=0.8,
            vol_ratio=3.0,
        )
        assert 0 <= score <= 100

    def test_higher_growth_higher_score(self, selector):
        score_low = selector._calculate_sawkami_score(
            op_growth=35.0, drop_pct=-25.0, rsi=20.0, pbr=1.0, vol_ratio=2.0,
        )
        score_high = selector._calculate_sawkami_score(
            op_growth=100.0, drop_pct=-25.0, rsi=20.0, pbr=1.0, vol_ratio=2.0,
        )
        assert score_high > score_low

    def test_deeper_drop_higher_score(self, selector):
        score_shallow = selector._calculate_sawkami_score(
            op_growth=50.0, drop_pct=-22.0, rsi=20.0, pbr=1.0, vol_ratio=2.0,
        )
        score_deep = selector._calculate_sawkami_score(
            op_growth=50.0, drop_pct=-50.0, rsi=20.0, pbr=1.0, vol_ratio=2.0,
        )
        assert score_deep > score_shallow

    def test_lower_rsi_higher_score(self, selector):
        score_high_rsi = selector._calculate_sawkami_score(
            op_growth=50.0, drop_pct=-30.0, rsi=28.0, pbr=1.0, vol_ratio=2.0,
        )
        score_low_rsi = selector._calculate_sawkami_score(
            op_growth=50.0, drop_pct=-30.0, rsi=5.0, pbr=1.0, vol_ratio=2.0,
        )
        assert score_low_rsi > score_high_rsi

    def test_lower_pbr_higher_score(self, selector):
        score_high_pbr = selector._calculate_sawkami_score(
            op_growth=50.0, drop_pct=-30.0, rsi=20.0, pbr=1.4, vol_ratio=2.0,
        )
        score_low_pbr = selector._calculate_sawkami_score(
            op_growth=50.0, drop_pct=-30.0, rsi=20.0, pbr=0.3, vol_ratio=2.0,
        )
        assert score_low_pbr > score_high_pbr

    def test_higher_vol_ratio_higher_score(self, selector):
        score_low = selector._calculate_sawkami_score(
            op_growth=50.0, drop_pct=-30.0, rsi=20.0, pbr=1.0, vol_ratio=1.6,
        )
        score_high = selector._calculate_sawkami_score(
            op_growth=50.0, drop_pct=-30.0, rsi=20.0, pbr=1.0, vol_ratio=4.0,
        )
        assert score_high > score_low

    def test_max_score_components(self, selector):
        """극단적 값으로 최대 점수 확인"""
        score = selector._calculate_sawkami_score(
            op_growth=200.0, drop_pct=-60.0, rsi=0.0, pbr=0.01, vol_ratio=5.0,
        )
        assert score == pytest.approx(100.0, abs=1.0)


# ============================================================================
# RSI 계산 테스트
# ============================================================================

class TestRSI:
    def test_rsi_calculation(self, selector):
        import pandas as pd
        # 연속 상승 → RSI 높음
        prices = pd.Series([float(100 + i) for i in range(30)])
        rsi = selector._calculate_rsi_value(prices)
        assert rsi is not None
        assert rsi > 50

    def test_rsi_oversold(self, selector):
        import pandas as pd
        # 연속 하락 → RSI 낮음
        prices = pd.Series([float(200 - i * 2) for i in range(30)])
        rsi = selector._calculate_rsi_value(prices)
        assert rsi is not None
        assert rsi < 50


# ============================================================================
# 캐시 테스트
# ============================================================================

class TestCache:
    def test_cache_validity(self, selector):
        from utils.korean_time import now_kst
        fund = SawkamiFundamentalData(
            code="005930", name="삼성전자", market="KOSPI",
            op_income_growth=50.0, pbr=0.8, bps=50000.0,
            cached_at=now_kst(),
        )
        assert selector._is_cache_valid(fund) is True

    def test_cache_expired(self, selector):
        from utils.korean_time import now_kst
        fund = SawkamiFundamentalData(
            code="005930", name="삼성전자", market="KOSPI",
            op_income_growth=50.0, pbr=0.8, bps=50000.0,
            cached_at=now_kst() - timedelta(hours=25),
        )
        assert selector._is_cache_valid(fund) is False

    def test_cache_save_load(self, selector, tmp_path):
        from utils.korean_time import now_kst
        selector._fundamental_cache_file = tmp_path / "test_cache.json"
        selector._fundamental_cache["005930"] = SawkamiFundamentalData(
            code="005930", name="삼성전자", market="KOSPI",
            op_income_growth=50.0, pbr=0.8, bps=50000.0,
            cached_at=now_kst(),
        )
        selector._save_fundamental_cache()
        assert selector._fundamental_cache_file.exists()

        selector._fundamental_cache.clear()
        selector._load_fundamental_cache()
        assert "005930" in selector._fundamental_cache


# ============================================================================
# safe_float 테스트
# ============================================================================

class TestSafeFloat:
    def test_normal(self, selector):
        assert selector._safe_float("12345") == 12345.0

    def test_comma(self, selector):
        assert selector._safe_float("1,234,567") == 1234567.0

    def test_none(self, selector):
        assert selector._safe_float(None) == 0.0

    def test_empty(self, selector):
        assert selector._safe_float("") == 0.0

    def test_invalid(self, selector):
        assert selector._safe_float("abc") == 0.0


# ============================================================================
# 통합 테스트 (모킹)
# ============================================================================

class TestIntegration:
    @patch('strategies.sawkami.screener.SawkamiCandidateSelector._load_stock_list')
    def test_select_returns_empty_when_no_stocks(self, mock_load, selector):
        mock_load.return_value = []
        result = selector.select_daily_candidates()
        assert result == []

    @patch('strategies.sawkami.screener.SawkamiCandidateSelector._load_stock_list')
    def test_select_applies_filters_in_order(self, mock_load, selector, sample_stocks):
        mock_load.return_value = sample_stocks
        with patch.object(selector, '_apply_fundamental_filters', return_value=[]):
            result = selector.select_daily_candidates()
            assert result == []
