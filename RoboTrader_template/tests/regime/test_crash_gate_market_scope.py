"""급락게이트가 종목 소속 시장으로 판정하는지 — 대칭 단언.

한쪽만 단언하면 판별력이 없다. "KOSPI 종목이 차단된다"만 보면
게이트가 전부 차단해도 통과하기 때문에, 같은 조건에서
"KOSDAQ 종목은 통과한다"를 함께 단언한다.
"""
import pytest

from core.regime.market_classifier import resolve_regime_index


# 2026-08-03 실측: KOSPI -5.29% / KOSDAQ +2.45%
INDEX_CHANGE = {"KOSPI": -5.29, "KOSDAQ": +2.45}
THRESHOLD = {"KOSPI": -2.5, "KOSDAQ": -3.0}
MARKET_OF = {"005930": "KOSPI", "035720": "KOSDAQ"}


def _is_crashing(regime_index: str) -> bool:
    """check_market_direction 의 판정 규칙(:165-168, :186)을 그대로 옮긴 것."""
    if regime_index == "none":
        return False
    checks = []
    if regime_index in ("both", "KOSPI"):
        checks.append("KOSPI")
    if regime_index in ("both", "KOSDAQ"):
        checks.append("KOSDAQ")
    return any(INDEX_CHANGE[n] <= THRESHOLD[n] for n in checks)


def test_auto_blocks_kospi_stock_and_allows_kosdaq_on_2026_08_03():
    """같은 날·같은 설정에서 시장에 따라 판정이 갈려야 한다."""
    kospi = resolve_regime_index("auto", "005930", market_lookup=MARKET_OF.get)
    kosdaq = resolve_regime_index("auto", "035720", market_lookup=MARKET_OF.get)

    assert kospi == "KOSPI" and _is_crashing(kospi) is True
    assert kosdaq == "KOSDAQ" and _is_crashing(kosdaq) is False


def test_cache_key_is_the_resolved_index_not_the_stock():
    """서로 다른 시장 종목을 연속 조회해도 각자 지수로 해석돼야 한다.

    캐시 키가 종목코드로 오염되면 이 단언이 깨진다.
    """
    seq = ["005930", "035720", "005930", "035720"]
    resolved = [resolve_regime_index("auto", c, market_lookup=MARKET_OF.get) for c in seq]
    assert resolved == ["KOSPI", "KOSDAQ", "KOSPI", "KOSDAQ"]
    assert {r for r in resolved} <= {"KOSPI", "KOSDAQ", "both", "none"}


def test_unmapped_stock_is_blocked_on_2026_08_03():
    """결측 → both → KOSPI 급락에 걸려 차단(보호 과잉 쪽)."""
    resolved = resolve_regime_index("auto", "999999", market_lookup=lambda c: None)
    assert resolved == "both"
    assert _is_crashing(resolved) is True


@pytest.mark.parametrize("configured,expected", [
    ("KOSPI", "KOSPI"), ("KOSDAQ", "KOSDAQ"), ("both", "both"), ("none", "none"),
])
def test_legacy_config_values_unchanged(configured, expected):
    """config 를 되돌리면 코드를 되돌리지 않아도 변경 전 동작이 복원된다(롤백 경로)."""
    assert resolve_regime_index(configured, "035720", market_lookup=MARKET_OF.get) == expected
