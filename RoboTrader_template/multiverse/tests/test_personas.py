"""4 페르소나 ComposableStrategy 회귀 테스트 — 4건."""
from __future__ import annotations

from unittest.mock import MagicMock

import pandas as pd
import pytest

from RoboTrader_template.multiverse.composable import (
    ComposableStrategy,
    build_intraday_strategy,
    build_long_term_strategy,
    build_quant_strategy,
    build_swing_strategy,
)


def _mock_ctx() -> MagicMock:
    """DB 없이 동작하는 PITContext 모의 객체."""
    ctx = MagicMock()
    ctx.as_of_date = MagicMock()
    # read_daily: 빈 DataFrame 반환 → 신호 생성 조건 미충족 → HOLD
    ctx.read_daily.return_value = pd.DataFrame()
    ctx.read_financial_ratio.return_value = None
    ctx.read_minute.return_value = pd.DataFrame()
    return ctx


def test_quant_strategy_builds(valid_paramset):
    """퀀트 페르소나가 ComposableStrategy를 반환하고 signal_fn이 호출 가능."""
    s = build_quant_strategy(valid_paramset, ["005930", "000660"])
    assert isinstance(s, ComposableStrategy)

    sig = s.signal_fn(_mock_ctx(), symbol="005930", position=None, capital=10_000_000)
    assert sig.action in {"BUY", "SELL", "HOLD"}


def test_swing_strategy_builds(valid_paramset):
    """스윙 페르소나가 ComposableStrategy를 반환하고 signal_fn이 호출 가능."""
    s = build_swing_strategy(valid_paramset, ["005930"])
    assert isinstance(s, ComposableStrategy)

    sig = s.signal_fn(_mock_ctx(), symbol="005930", position=None, capital=10_000_000)
    assert sig.action in {"BUY", "SELL", "HOLD"}


def test_long_term_strategy_builds(valid_paramset):
    """중장기 페르소나가 ComposableStrategy를 반환하고 signal_fn이 호출 가능."""
    s = build_long_term_strategy(valid_paramset, ["005930"])
    assert isinstance(s, ComposableStrategy)

    sig = s.signal_fn(_mock_ctx(), symbol="005930", position=None, capital=10_000_000)
    assert sig.action in {"BUY", "SELL", "HOLD"}


def test_intraday_strategy_builds(valid_paramset):
    """단타 페르소나가 ComposableStrategy를 반환하고 signal_fn이 호출 가능."""
    s = build_intraday_strategy(valid_paramset, ["005930"])
    assert isinstance(s, ComposableStrategy)

    sig = s.signal_fn(_mock_ctx(), symbol="005930", position=None, capital=10_000_000)
    assert sig.action in {"BUY", "SELL", "HOLD"}
