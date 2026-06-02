"""전략별 KOSPI/KOSDAQ 급락필터 분리(A) + PIT 일봉 국면 게이트(B) — 라이브 검증.

★실거래 로직. 하위호환·룩어헤드·미확정봉 절대조건.

A. check_market_direction(regime_index): 전략 인자화
   ① KOSDAQ 전략은 KOSPI 급락에 안 막히고 KOSDAQ 급락에만 막힘
   ② regime_index=both/none 하위호환
B. check_regime_gate(regime_index, regime_gate): PIT 일봉 국면 게이트
   ③ exclude_bear = 국면 BEAR일 때 차단·아닐 때 허용
   ④ bull_only = BULL만 허용
   ⑤ 미설정(none) 전략 기존 동작 불변
   ⑥ 일봉 국면계산에 미확정 당일봉 미사용
"""
from __future__ import annotations

from datetime import date
from unittest.mock import MagicMock, Mock, patch

import pandas as pd
import pytest

from core.trading_decision_engine import TradingDecisionEngine


def _make_engine():
    engine = TradingDecisionEngine.__new__(TradingDecisionEngine)
    engine.logger = Mock()
    engine.strategy = None
    engine._market_direction_cache = {}
    engine._market_direction_cache_time = {}
    engine._MARKET_DIRECTION_CACHE_TTL = 60
    engine._regime_gate = None
    engine.db_manager = None
    return engine


# ============================================================================
# A. 전략별 급락필터 분리
# ============================================================================

def _index_payload(kospi_change: float, kosdaq_change: float):
    def _fake_get_index_data(code: str):
        if code == "0001":
            return {"bstp_nmix_prdy_ctrt": str(kospi_change)}
        if code == "1001":
            return {"bstp_nmix_prdy_ctrt": str(kosdaq_change)}
        return None
    return _fake_get_index_data


@patch("core.trading_decision_engine.MARKET_DIRECTION_FILTER_ENABLED", True)
@patch("core.trading_decision_engine.KOSPI_DECLINE_THRESHOLD", -3.0)
@patch("core.trading_decision_engine.KOSDAQ_DECLINE_THRESHOLD", -3.0)
def test_kosdaq_strategy_not_blocked_by_kospi_crash():
    """① KOSDAQ 전략: KOSPI -5% 급락이어도 KOSDAQ 정상이면 안 막힘."""
    engine = _make_engine()
    with patch("api.kis_market_api.get_index_data",
               _index_payload(kospi_change=-5.0, kosdaq_change=+0.5)):
        crashing, _ = engine.check_market_direction(regime_index="KOSDAQ")
    assert crashing is False


@patch("core.trading_decision_engine.MARKET_DIRECTION_FILTER_ENABLED", True)
@patch("core.trading_decision_engine.KOSPI_DECLINE_THRESHOLD", -3.0)
@patch("core.trading_decision_engine.KOSDAQ_DECLINE_THRESHOLD", -3.0)
def test_kosdaq_strategy_blocked_by_kosdaq_crash():
    """① KOSDAQ 전략: KOSDAQ 급락이면 막힘."""
    engine = _make_engine()
    with patch("api.kis_market_api.get_index_data",
               _index_payload(kospi_change=+0.5, kosdaq_change=-5.0)):
        crashing, reason = engine.check_market_direction(regime_index="KOSDAQ")
    assert crashing is True
    assert "KOSDAQ" in reason


@patch("core.trading_decision_engine.MARKET_DIRECTION_FILTER_ENABLED", True)
@patch("core.trading_decision_engine.KOSPI_DECLINE_THRESHOLD", -3.0)
@patch("core.trading_decision_engine.KOSDAQ_DECLINE_THRESHOLD", -3.0)
def test_kospi_strategy_not_blocked_by_kosdaq_crash():
    """KOSPI 전략: KOSDAQ만 급락이면 안 막힘."""
    engine = _make_engine()
    with patch("api.kis_market_api.get_index_data",
               _index_payload(kospi_change=+0.2, kosdaq_change=-5.0)):
        crashing, _ = engine.check_market_direction(regime_index="KOSPI")
    assert crashing is False


@patch("core.trading_decision_engine.MARKET_DIRECTION_FILTER_ENABLED", True)
@patch("core.trading_decision_engine.KOSPI_DECLINE_THRESHOLD", -3.0)
@patch("core.trading_decision_engine.KOSDAQ_DECLINE_THRESHOLD", -3.0)
def test_both_default_backward_compat():
    """② regime_index=both(기본)는 KOSPI 또는 KOSDAQ 둘 중 하나만 급락해도 막힘(현 동작)."""
    engine = _make_engine()
    with patch("api.kis_market_api.get_index_data",
               _index_payload(kospi_change=+0.2, kosdaq_change=-5.0)):
        crashing, reason = engine.check_market_direction(regime_index="both")
    assert crashing is True
    assert "KOSDAQ" in reason

    engine2 = _make_engine()
    with patch("api.kis_market_api.get_index_data",
               _index_payload(kospi_change=-5.0, kosdaq_change=+0.2)):
        crashing2, reason2 = engine2.check_market_direction(regime_index="both")
    assert crashing2 is True
    assert "KOSPI" in reason2


@patch("core.trading_decision_engine.MARKET_DIRECTION_FILTER_ENABLED", True)
@patch("core.trading_decision_engine.KOSPI_DECLINE_THRESHOLD", -3.0)
@patch("core.trading_decision_engine.KOSDAQ_DECLINE_THRESHOLD", -3.0)
def test_none_exempts_filter():
    """② regime_index=none: 어떤 급락이어도 면제."""
    engine = _make_engine()
    with patch("api.kis_market_api.get_index_data",
               _index_payload(kospi_change=-9.0, kosdaq_change=-9.0)):
        crashing, _ = engine.check_market_direction(regime_index="none")
    assert crashing is False


@patch("core.trading_decision_engine.MARKET_DIRECTION_FILTER_ENABLED", True)
@patch("core.trading_decision_engine.KOSPI_DECLINE_THRESHOLD", -3.0)
@patch("core.trading_decision_engine.KOSDAQ_DECLINE_THRESHOLD", -3.0)
def test_default_arg_is_both():
    """인자 미지정 호출은 both와 동일(완전 하위호환)."""
    engine = _make_engine()
    with patch("api.kis_market_api.get_index_data",
               _index_payload(kospi_change=-5.0, kosdaq_change=+0.2)):
        crashing, _ = engine.check_market_direction()
    assert crashing is True


@patch("core.trading_decision_engine.MARKET_DIRECTION_FILTER_ENABLED", True)
@patch("core.trading_decision_engine.KOSPI_DECLINE_THRESHOLD", -3.0)
@patch("core.trading_decision_engine.KOSDAQ_DECLINE_THRESHOLD", -3.0)
def test_market_direction_cache_is_per_index():
    """캐시가 지수별 — KOSPI 캐시가 KOSDAQ 결과를 오염시키지 않음."""
    engine = _make_engine()
    fake = _index_payload(kospi_change=-5.0, kosdaq_change=+0.5)
    with patch("api.kis_market_api.get_index_data", fake) as m:
        k1, _ = engine.check_market_direction(regime_index="KOSPI")
        d1, _ = engine.check_market_direction(regime_index="KOSDAQ")
    assert k1 is True
    assert d1 is False


# ============================================================================
# B. PIT 일봉 국면 게이트
# ============================================================================

def _bull_close():
    dates = pd.bdate_range("2021-01-04", periods=400)
    import numpy as np
    rng = np.random.default_rng(3)
    logret = 0.002 + rng.normal(0, 0.003, 400)
    return pd.Series(2000 * np.exp(np.cumsum(logret)), index=dates)


def _bear_close():
    dates = pd.bdate_range("2021-01-04", periods=400)
    import numpy as np
    rng = np.random.default_rng(5)
    logret = -0.002 + rng.normal(0, 0.003, 400)
    return pd.Series(2000 * np.exp(np.cumsum(logret)), index=dates)


def test_regime_gate_none_always_allows():
    """⑤ regime_gate=none: 게이트 없음(항상 허용), 데이터 조회조차 안 함."""
    engine = _make_engine()
    blocked, _ = engine.check_regime_gate(regime_index="KOSPI", regime_gate="none")
    assert blocked is False


def test_exclude_bear_blocks_in_bear():
    """③ exclude_bear: 현재 국면이 BEAR면 차단."""
    engine = _make_engine()
    with patch("core.regime.regime_gate.RegimeGate.current_regime",
               return_value="bear") as m:
        engine._regime_gate = __import__(
            "core.regime.regime_gate", fromlist=["RegimeGate"]
        ).RegimeGate(db_manager=None)
        blocked, reason = engine.check_regime_gate(
            regime_index="KOSPI", regime_gate="exclude_bear")
    assert blocked is True
    assert "bear" in reason.lower()


def test_exclude_bear_allows_in_bull():
    """③ exclude_bear: BEAR가 아니면 허용."""
    engine = _make_engine()
    with patch("core.regime.regime_gate.RegimeGate.current_regime",
               return_value="bull"):
        engine._regime_gate = __import__(
            "core.regime.regime_gate", fromlist=["RegimeGate"]
        ).RegimeGate(db_manager=None)
        blocked, _ = engine.check_regime_gate(
            regime_index="KOSPI", regime_gate="exclude_bear")
    assert blocked is False


def test_exclude_bear_allows_in_sideways():
    """③ exclude_bear: SIDEWAYS도 허용."""
    engine = _make_engine()
    with patch("core.regime.regime_gate.RegimeGate.current_regime",
               return_value="sideways"):
        engine._regime_gate = __import__(
            "core.regime.regime_gate", fromlist=["RegimeGate"]
        ).RegimeGate(db_manager=None)
        blocked, _ = engine.check_regime_gate(
            regime_index="KOSPI", regime_gate="exclude_bear")
    assert blocked is False


def test_bull_only_blocks_non_bull():
    """④ bull_only: BULL만 허용 — SIDEWAYS 차단."""
    engine = _make_engine()
    with patch("core.regime.regime_gate.RegimeGate.current_regime",
               return_value="sideways"):
        engine._regime_gate = __import__(
            "core.regime.regime_gate", fromlist=["RegimeGate"]
        ).RegimeGate(db_manager=None)
        blocked, _ = engine.check_regime_gate(
            regime_index="KOSPI", regime_gate="bull_only")
    assert blocked is True


def test_bull_only_allows_bull():
    """④ bull_only: BULL이면 허용."""
    engine = _make_engine()
    with patch("core.regime.regime_gate.RegimeGate.current_regime",
               return_value="bull"):
        engine._regime_gate = __import__(
            "core.regime.regime_gate", fromlist=["RegimeGate"]
        ).RegimeGate(db_manager=None)
        blocked, _ = engine.check_regime_gate(
            regime_index="KOSPI", regime_gate="bull_only")
    assert blocked is False


def test_gate_safe_default_when_no_data():
    """데이터 부족시 안전 디폴트(차단 안 함) — fail-open."""
    engine = _make_engine()
    from core.regime.regime_gate import RegimeGate
    gate = RegimeGate(db_manager=None)  # db 없음 → 데이터 없음
    # current_regime이 None(불명) → 게이트는 허용해야 함
    with patch.object(gate, "current_regime", return_value=None):
        engine._regime_gate = gate
        blocked, _ = engine.check_regime_gate(
            regime_index="KOSPI", regime_gate="exclude_bear")
    assert blocked is False


# ============================================================================
# ⑥ 미확정 당일봉 미사용 — RegimeGate가 _drop_unconfirmed_today_bar SSOT를 탄다
# ============================================================================

def test_regime_gate_drops_unconfirmed_today_bar():
    """⑥ 일봉 국면 계산에 KST 오늘(미확정) 봉이 들어가지 않음."""
    from core.regime.regime_gate import RegimeGate
    from utils.korean_time import now_kst

    bull = _bull_close()
    today = now_kst().date()
    # daily_prices 모킹: 마지막 행이 '오늘'(미확정) 인 DataFrame 구성
    df = pd.DataFrame({
        "date": list(bull.index) + [pd.Timestamp(today)],
        "close": list(bull.values) + [bull.values[-1] * 0.5],  # 미확정 봉(왜곡)
    })

    class _Repo:
        def get_daily_prices(self, stock_code, days=30):
            return df.copy()

    class _DB:
        price_repo = _Repo()

    gate = RegimeGate(db_manager=_DB())
    # 내부에서 close_series를 만들 때 오늘 봉이 제외돼야 함
    cs = gate._load_index_close("KOSPI")
    assert cs is not None
    last_date = pd.Timestamp(cs.index[-1]).date()
    assert last_date != today, "미확정 당일봉이 국면계산 close_series에 포함됨"


# ============================================================================
# config 필드 — 하위호환 (StrategyLoader 미설정 전략)
# ============================================================================

def test_basestrategy_regime_defaults():
    """미설정 전략은 regime_index=both / regime_gate=none 기본값(기존 동작 불변)."""
    from strategies.base import BaseStrategy
    assert BaseStrategy.regime_index == "both"
    assert BaseStrategy.regime_gate == "none"


def test_loader_sets_regime_fields():
    """StrategyLoader.load_strategies가 spec의 regime_index/regime_gate를 인스턴스에 반영."""
    from strategies.config import StrategyLoader

    fake = MagicMock()
    fake.max_capital_pct = 1.0
    fake.regime_index = "both"
    fake.regime_gate = "none"
    specs = [{
        "name": "x", "enabled": True, "max_capital_pct": 0.2,
        "regime_index": "KOSDAQ", "regime_gate": "exclude_bear",
    }]
    with patch.object(StrategyLoader, "load_strategy", return_value=fake):
        out = StrategyLoader.load_strategies(specs)
    assert out["x"].regime_index == "KOSDAQ"
    assert out["x"].regime_gate == "exclude_bear"
