"""
전략별 시장 방향성 필터 — regime_index 분기 검증.

목적: 각 전략의 regime_index(KOSPI/KOSDAQ/both)가 실제로
      해당 지수만 조회·판정하는지(전략별 장 파악 로직 독립성) 증명.

검증 포인트 (core/trading_decision_engine.py:check_market_direction):
  - "KOSPI"  -> get_index_data("0001") 만 호출
  - "KOSDAQ" -> get_index_data("1001") 만 호출
  - "both"   -> "0001", "1001" 둘 다
  - 독립성: KOSPI 급락 시 KOSPI 전략은 차단되지만 KOSDAQ 전략은 통과
            (= 2026-06-04 실거래 시나리오: KOSPI -2.5%, daytrading=KOSDAQ)
"""
from unittest.mock import Mock, patch

import pytest

import api.kis_market_api as kis_market_api
from core.trading_decision_engine import TradingDecisionEngine


def _make_engine():
    """check_market_direction 검사에 필요한 최소 엔진."""
    engine = TradingDecisionEngine.__new__(TradingDecisionEngine)
    engine.logger = Mock()
    engine._market_direction_cache = {}
    engine._market_direction_cache_time = {}
    engine._MARKET_DIRECTION_CACHE_TTL = 60
    return engine


def _index_stub(changes_by_code):
    """code -> 등락률(%) 매핑으로 get_index_data 흉내. 호출 코드 기록."""
    called = []

    def _fn(code):
        called.append(code)
        if code not in changes_by_code:
            return None
        return {"bstp_nmix_prdy_ctrt": str(changes_by_code[code])}

    return _fn, called


class TestPerStrategyIndexRouting:
    """regime_index 별로 조회되는 지수 코드가 분기되는지."""

    def test_kospi_queries_only_0001(self):
        engine = _make_engine()
        fn, called = _index_stub({"0001": -0.5, "1001": -9.9})
        with patch.object(kis_market_api, "get_index_data", fn):
            is_crash, reason = engine.check_market_direction(regime_index="KOSPI")
        assert called == ["0001"]            # KOSDAQ(1001) 미조회
        assert is_crash is False             # -0.5% > -2.5%

    def test_kosdaq_queries_only_1001(self):
        engine = _make_engine()
        fn, called = _index_stub({"0001": -9.9, "1001": -0.5})
        with patch.object(kis_market_api, "get_index_data", fn):
            is_crash, reason = engine.check_market_direction(regime_index="KOSDAQ")
        assert called == ["1001"]            # KOSPI(0001) 미조회 — KOSPI가 -9.9%여도 무관
        assert is_crash is False             # -0.5% > -3.0%

    def test_both_queries_both_indices(self):
        engine = _make_engine()
        fn, called = _index_stub({"0001": -0.1, "1001": -0.1})
        with patch.object(kis_market_api, "get_index_data", fn):
            engine.check_market_direction(regime_index="both")
        assert set(called) == {"0001", "1001"}


class TestPerStrategyIndependence:
    """2026-06-04 재현: KOSPI 급락이 KOSDAQ 전략을 막지 않아야 한다."""

    def test_kospi_crash_blocks_kospi_strategy(self):
        engine = _make_engine()
        fn, _ = _index_stub({"0001": -2.6, "1001": -0.3})
        with patch.object(kis_market_api, "get_index_data", fn):
            is_crash, reason = engine.check_market_direction(regime_index="KOSPI")
        assert is_crash is True
        assert "KOSPI" in reason

    def test_kospi_crash_does_not_block_kosdaq_strategy(self):
        engine = _make_engine()
        # KOSPI -2.6%(급락) 이지만 KOSDAQ -0.3% (임계 -3.0% 미달)
        fn, called = _index_stub({"0001": -2.6, "1001": -0.3})
        with patch.object(kis_market_api, "get_index_data", fn):
            is_crash, reason = engine.check_market_direction(regime_index="KOSDAQ")
        assert is_crash is False             # KOSDAQ 전략은 통과
        assert called == ["1001"]            # KOSPI 급락값을 아예 보지 않음

    def test_kosdaq_threshold_is_independent(self):
        """KOSDAQ 전용 임계(-3.0%)로 차단되는지."""
        engine = _make_engine()
        fn, _ = _index_stub({"1001": -3.5})
        with patch.object(kis_market_api, "get_index_data", fn):
            is_crash, reason = engine.check_market_direction(regime_index="KOSDAQ")
        assert is_crash is True
        assert "KOSDAQ" in reason


class TestNoneIsExempt:
    def test_none_skips_all_queries(self):
        engine = _make_engine()
        fn, called = _index_stub({"0001": -9.9, "1001": -9.9})
        with patch.object(kis_market_api, "get_index_data", fn):
            is_crash, _ = engine.check_market_direction(regime_index="none")
        assert is_crash is False
        assert called == []                  # 면제 → 지수 조회 자체 없음
