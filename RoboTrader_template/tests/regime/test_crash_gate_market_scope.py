"""급락게이트 호출부 배선 검증.

이 파일은 두 층을 검증한다.

1) `resolve_regime_index`(해석 함수) 자체의 판정 규칙
   — `TestResolveRegimeIndexAgainst20260803Crash`.
   이것은 해석 함수의 단위 테스트이며 실제 게이트 호출부
   (TradingContext.buy / TradingDecisionEngine.analyze_buy_decision)를
   거치지 않는다 — 원본 호출부가 깨져도 이 클래스는 통과할 수 있다.

2) 실제 배선 — `TestWiringPassesResolvedIndexToGate`.
   `TradingContext.buy()`·`TradingDecisionEngine.analyze_buy_decision()`를
   직접 호출해 `check_market_direction`에 **실제로 전달된 kwarg 값**을
   단언한다. grep으로만 확인됐던 배선(2026-08-03 리뷰 발견 2)의 회귀 가드다.
   `test_two_markets_do_not_share_gate_cache_slot`은 목이 아닌 진짜
   `check_market_direction`(캐시 포함)을 사용해 캐시 오염 여부를 확인한다.
"""
import asyncio
from unittest.mock import AsyncMock, Mock, patch

import pytest

import core.regime.market_classifier as market_classifier
from core.regime.market_classifier import resolve_regime_index


# 2026-08-03 실측: KOSPI -5.29% / KOSDAQ +2.45%
INDEX_CHANGE = {"KOSPI": -5.29, "KOSDAQ": +2.45}
THRESHOLD = {"KOSPI": -2.5, "KOSDAQ": -3.0}
MARKET_OF = {"005930": "KOSPI", "035720": "KOSDAQ"}


def _is_crashing(regime_index: str) -> bool:
    """check_market_direction 의 판정 규칙(:186-188)을 그대로 옮긴 것.

    ⚠️ 이것은 실제 게이트를 호출하지 않는 거울 함수다 — 원본이 바뀌어도
    이 함수는 조용히 낡아진다(2026-08-03 리뷰 발견 2). 배선 자체의 회귀
    가드는 `TestWiringPassesResolvedIndexToGate` 를 참조할 것.
    """
    if regime_index == "none":
        return False
    checks = []
    if regime_index in ("both", "KOSPI"):
        checks.append("KOSPI")
    if regime_index in ("both", "KOSDAQ"):
        checks.append("KOSDAQ")
    return any(INDEX_CHANGE[n] <= THRESHOLD[n] for n in checks)


class TestResolveRegimeIndexAgainst20260803Crash:
    """`resolve_regime_index`(해석 함수) 단위 테스트 — 배선 테스트가 아니다."""

    def test_auto_blocks_kospi_stock_and_allows_kosdaq_on_2026_08_03(self):
        """같은 날·같은 설정에서 시장에 따라 판정이 갈려야 한다."""
        kospi = resolve_regime_index("auto", "005930", market_lookup=MARKET_OF.get)
        kosdaq = resolve_regime_index("auto", "035720", market_lookup=MARKET_OF.get)

        assert kospi == "KOSPI" and _is_crashing(kospi) is True
        assert kosdaq == "KOSDAQ" and _is_crashing(kosdaq) is False

    def test_resolve_is_stateless_across_consecutive_calls(self):
        """서로 다른 시장 종목을 연속 조회해도 각자 지수로 해석돼야 한다.

        ⚠️ 이름 정정(2026-08-03 리뷰 발견 2): `resolve_regime_index` 자체는
        캐시를 갖지 않으므로 이 테스트는 게이트 캐시 오염 여부를 증명하지
        않는다. 실제 게이트 캐시가 종목코드로 오염되지 않는지는
        `TestWiringPassesResolvedIndexToGate.test_two_markets_do_not_share_gate_cache_slot`
        이 진짜 `check_market_direction` 으로 검증한다.
        """
        seq = ["005930", "035720", "005930", "035720"]
        resolved = [resolve_regime_index("auto", c, market_lookup=MARKET_OF.get) for c in seq]
        assert resolved == ["KOSPI", "KOSDAQ", "KOSPI", "KOSDAQ"]

    def test_unmapped_stock_is_blocked_on_2026_08_03(self):
        """결측 → both → KOSPI 급락에 걸려 차단(보호 과잉 쪽)."""
        resolved = resolve_regime_index("auto", "999999", market_lookup=lambda c: None)
        assert resolved == "both"
        assert _is_crashing(resolved) is True

    @pytest.mark.parametrize("configured,expected", [
        ("KOSPI", "KOSPI"), ("KOSDAQ", "KOSDAQ"), ("both", "both"), ("none", "none"),
    ])
    def test_legacy_config_values_unchanged(self, configured, expected):
        """config 를 되돌리면 코드를 되돌리지 않아도 변경 전 동작이 복원된다(롤백 경로)."""
        assert resolve_regime_index(configured, "035720", market_lookup=MARKET_OF.get) == expected


class TestWiringPassesResolvedIndexToGate:
    """실제 호출부가 `resolve_regime_index` 결과를 게이트에 넘기는지(2026-08-03 리뷰 발견 2).

    grep은 "그 줄이 존재한다"만 보여준다 — 여기서는 런타임에 실제로
    전달된 kwarg 값을 단언한다.
    """

    # ---- TradingDecisionEngine.analyze_buy_decision ------------------------

    def _make_engine(self):
        from core.trading_decision_engine import TradingDecisionEngine
        engine = TradingDecisionEngine.__new__(TradingDecisionEngine)
        engine.logger = Mock()
        engine.check_market_direction = Mock(return_value=(False, ""))
        return engine

    def test_engine_auto_kospi_stock_resolves_to_kospi(self):
        engine = self._make_engine()
        stock = Mock(stock_code="005930")
        with patch.object(market_classifier, "get_stock_market", return_value="KOSPI"):
            asyncio.get_event_loop().run_until_complete(
                engine.analyze_buy_decision(stock, None, regime_index="auto")
            )
        engine.check_market_direction.assert_called_once_with(regime_index="KOSPI")

    def test_engine_auto_unmapped_stock_resolves_to_both(self):
        engine = self._make_engine()
        stock = Mock(stock_code="999999")
        with patch.object(market_classifier, "get_stock_market", return_value=None):
            asyncio.get_event_loop().run_until_complete(
                engine.analyze_buy_decision(stock, None, regime_index="auto")
            )
        engine.check_market_direction.assert_called_once_with(regime_index="both")

    def test_engine_non_auto_passes_through_unchanged(self):
        """기존 동작 보존: non-auto 는 매핑 조회 없이 그대로 통과해야 한다."""
        engine = self._make_engine()
        stock = Mock(stock_code="005930")

        def boom(_code):
            raise AssertionError("non-auto 에서 매핑을 조회하면 안 된다")

        with patch.object(market_classifier, "get_stock_market", boom):
            asyncio.get_event_loop().run_until_complete(
                engine.analyze_buy_decision(stock, None, regime_index="KOSPI")
            )
        engine.check_market_direction.assert_called_once_with(regime_index="KOSPI")

    # ---- TradingContext.buy -------------------------------------------------

    def _make_ctx(self, configured_regime_index):
        from core.trading_context import TradingContext

        strategy = Mock(regime_index=configured_regime_index, regime_gate="none")
        decision_engine = Mock()
        # check_market_direction 은 통과(False)시켜 check_regime_gate 까지 도달하게 하고,
        # check_regime_gate 를 차단(True)시켜 그 직후 buy()를 종료시킨다 — 두 호출부의
        # kwarg 를 모두 관찰하면서도, 배선 검증에 불필요한 하위 경로(주문 실행 등)를
        # 위한 mock 준비를 피한다.
        decision_engine.check_market_direction.return_value = (False, "")
        decision_engine.check_regime_gate.return_value = (True, "테스트국면차단")

        ctx = TradingContext(
            trading_manager=Mock(),
            decision_engine=decision_engine,
            fund_manager=Mock(),
            data_collector=Mock(),
            intraday_manager=Mock(),
            trading_analyzer=AsyncMock(),
            db_manager=Mock(),
            broker=Mock(),
            strategy_name="my_strategy",
            strategies_dict={"my_strategy": strategy},
        )
        return ctx, decision_engine

    def test_ctx_buy_auto_kospi_stock_resolves_to_kospi(self):
        ctx, decision_engine = self._make_ctx("auto")
        cb_state = Mock()
        cb_state.is_market_halted.return_value = False
        with patch('config.market_hours.get_circuit_breaker_state', return_value=cb_state), \
             patch.object(market_classifier, "get_stock_market", return_value="KOSPI"):
            asyncio.get_event_loop().run_until_complete(ctx.buy("005930"))
        decision_engine.check_market_direction.assert_called_once_with(regime_index="KOSPI")
        # check_regime_gate 는 원본("auto")을 그대로 받아야 한다 — resolved_index 가 아니다.
        decision_engine.check_regime_gate.assert_called_once_with(
            regime_index="auto", regime_gate="none"
        )

    def test_ctx_buy_auto_kosdaq_stock_resolves_to_kosdaq(self):
        ctx, decision_engine = self._make_ctx("auto")
        cb_state = Mock()
        cb_state.is_market_halted.return_value = False
        with patch('config.market_hours.get_circuit_breaker_state', return_value=cb_state), \
             patch.object(market_classifier, "get_stock_market", return_value="KOSDAQ"):
            asyncio.get_event_loop().run_until_complete(ctx.buy("035720"))
        decision_engine.check_market_direction.assert_called_once_with(regime_index="KOSDAQ")

    def test_ctx_buy_non_auto_passes_through_unchanged(self):
        """기존 동작 보존: config 가 아직 non-auto 인 8전략은 변경 전과 동일해야 한다."""
        ctx, decision_engine = self._make_ctx("KOSPI")
        cb_state = Mock()
        cb_state.is_market_halted.return_value = False

        def boom(_code):
            raise AssertionError("non-auto 에서 매핑을 조회하면 안 된다")

        with patch('config.market_hours.get_circuit_breaker_state', return_value=cb_state), \
             patch.object(market_classifier, "get_stock_market", boom):
            asyncio.get_event_loop().run_until_complete(ctx.buy("005930"))
        decision_engine.check_market_direction.assert_called_once_with(regime_index="KOSPI")

    def test_two_markets_do_not_share_gate_cache_slot(self):
        """`check_market_direction`(엔진 실물)의 캐시 키가 regime_index 문자열이다
        (TTL 60초). 서로 다른 시장 종목을 연속 해석해 넣어도 지수별 슬롯에
        각각 쌓이고, 종목코드가 캐시 키로 새어 들어가지 않는지 확인한다
        — mock 이 아니라 진짜 check_market_direction 으로 검증한다.
        """
        from core.trading_decision_engine import TradingDecisionEngine

        engine = TradingDecisionEngine.__new__(TradingDecisionEngine)
        engine.logger = Mock()
        engine._market_direction_cache = {}
        engine._market_direction_cache_time = {}
        engine._MARKET_DIRECTION_CACHE_TTL = 60

        import api.kis_market_api as kis_market_api
        called = []

        def _index_fn(code):
            called.append(code)
            return {"bstp_nmix_prdy_ctrt": {"0001": "-0.1", "1001": "-0.1"}[code]}

        with patch.object(kis_market_api, "get_index_data", _index_fn):
            for code, market in [("005930", "KOSPI"), ("035720", "KOSDAQ")]:
                with patch.object(market_classifier, "get_stock_market", return_value=market):
                    resolved = resolve_regime_index("auto", code)
                engine.check_market_direction(regime_index=resolved)

        # 두 지수 모두 조회됐다 — 캐시 키가 종목코드로 오염돼 한쪽이 스킵되지 않았다.
        assert set(called) == {"0001", "1001"}
        # 캐시 슬롯은 지수명뿐이다 — 종목코드(005930/035720)가 새어 들어가지 않았다.
        assert set(engine._market_direction_cache.keys()) == {"KOSPI", "KOSDAQ"}
