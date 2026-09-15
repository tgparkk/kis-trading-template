"""급락게이트 차단 로그의 «맥락» — 종목·전략·해석지수.

닫으려는 결함(2026-09-15 결정 패널 §F-5 ②): 09-14·09-15 EOD 에서
「daytrading 이 KOSPI 종목 2개를 KOSDAQ 임계로 통과시켰다」를 판정하는 데
하루가 걸렸다. 차단 줄이 `매수 판단 스킵: 시장급락 (KOSDAQ -2.1% ...)` 뿐이라
**어느 종목을 어느 전략이 어느 해석지수로 막았는지**가 줄에 없었기 때문이다.

이 파일이 단언하는 것:
  ① 차단 줄에 `종목=`·`전략=`·`해석지수=` 세 필드가 붙는다
  ② 해석지수는 `resolve_regime_index` 가 돌려준 값(설정값이 아니라 «해석» 결과)
  ③ 반환값은 그대로 None — 로그 계층이 판단을 바꾸지 않는다

⚠️ logger 는 `utils/logger.py:106` 에서 `propagate = False` 라 caplog 로 안
   잡힌다. Mock 로거를 꽂아 호출을 직접 본다.
"""
from unittest.mock import Mock

import pytest

from core.trading_context import TradingContext


def _make_ctx(strategy_key="daytrading_3methods_breakout"):
    strat = Mock()
    strat.name = "DayTrading3MethodsBreakoutStrategy"
    strat.regime_index = "auto"
    strat.regime_gate = "none"

    ctx = TradingContext(
        trading_manager=Mock(),
        decision_engine=Mock(),
        fund_manager=Mock(),
        data_collector=Mock(),
        intraday_manager=Mock(),
        trading_analyzer=Mock(),
        db_manager=Mock(),
        strategy_name=strategy_key,
        strategies_dict={strategy_key: strat},
    )
    ctx.logger = Mock()
    return ctx


@pytest.mark.asyncio
async def test_crash_skip_log_carries_stock_strategy_and_resolved_index(monkeypatch):
    ctx = _make_ctx()
    # 종목 소속 시장 매핑을 KOSPI 로 고정 → auto 해석 결과 = KOSPI
    monkeypatch.setattr(
        "core.regime.market_classifier.get_stock_market",
        lambda code: "KOSPI",
    )
    ctx._decision_engine.check_market_direction.return_value = (
        True,
        "KOSPI -3.20% (임계값: -3.0%)",
    )

    result = await ctx.buy("005930")

    assert result is None  # 판단 불변
    lines = [
        c.args[0]
        for c in ctx.logger.info.call_args_list
        if c.args and isinstance(c.args[0], str) and "시장급락" in c.args[0]
    ]
    assert len(lines) == 1, lines
    assert "종목=005930" in lines[0]
    assert "전략=daytrading_3methods_breakout" in lines[0]
    assert "해석지수=KOSPI" in lines[0]


@pytest.mark.asyncio
async def test_resolved_index_is_resolution_not_config(monkeypatch):
    """매핑이 없으면 해석지수는 both — 설정값 `auto` 가 그대로 찍히면 안 된다."""
    ctx = _make_ctx()
    monkeypatch.setattr(
        "core.regime.market_classifier.get_stock_market",
        lambda code: None,
    )
    ctx._decision_engine.check_market_direction.return_value = (True, "KOSDAQ -2.5%")

    assert await ctx.buy("999999") is None

    line = [
        c.args[0]
        for c in ctx.logger.info.call_args_list
        if c.args and isinstance(c.args[0], str) and "시장급락" in c.args[0]
    ][0]
    assert "해석지수=both" in line
    assert "해석지수=auto" not in line
