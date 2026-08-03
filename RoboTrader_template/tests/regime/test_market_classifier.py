from core.regime.market_classifier import resolve_regime_index


def test_non_auto_passes_through_without_lookup():
    """configured != "auto" 면 매핑을 조회조차 하지 않는다 — 기존 동작 100% 보존."""
    def boom(_code):
        raise AssertionError("non-auto 에서 매핑을 조회하면 안 된다")

    assert resolve_regime_index("KOSPI", "005930", market_lookup=boom) == "KOSPI"
    assert resolve_regime_index("KOSDAQ", "035720", market_lookup=boom) == "KOSDAQ"
    assert resolve_regime_index("both", "005930", market_lookup=boom) == "both"
    assert resolve_regime_index("none", "005930", market_lookup=boom) == "none"


def test_auto_resolves_to_stock_market():
    lookup = {"005930": "KOSPI", "035720": "KOSDAQ"}.get
    assert resolve_regime_index("auto", "005930", market_lookup=lookup) == "KOSPI"
    assert resolve_regime_index("auto", "035720", market_lookup=lookup) == "KOSDAQ"


def test_auto_falls_back_to_both_when_unmapped():
    """결측은 보호 과잉 쪽으로만 실패한다 — both 는 두 지수를 모두 검사한다."""
    assert resolve_regime_index("auto", "999999", market_lookup=lambda c: None) == "both"


def test_auto_falls_back_to_both_on_garbage_label():
    """FDR 이 예상 밖 라벨을 주면 그대로 흘리지 않고 both 로 막는다."""
    assert resolve_regime_index("auto", "005930", market_lookup=lambda c: "KONEX") == "both"


def test_auto_falls_back_to_both_when_lookup_raises():
    """DB 장애로 조회가 터져도 매수 경로를 죽이지 않는다."""
    def boom(_code):
        raise RuntimeError("db down")

    assert resolve_regime_index("auto", "005930", market_lookup=boom) == "both"


def test_empty_configured_is_treated_as_both():
    """기존 _get_strategy_regime_settings 의 기본값 규약(None/"" → both)과 일치."""
    assert resolve_regime_index("", "005930", market_lookup=lambda c: "KOSPI") == "both"
    assert resolve_regime_index(None, "005930", market_lookup=lambda c: "KOSPI") == "both"
