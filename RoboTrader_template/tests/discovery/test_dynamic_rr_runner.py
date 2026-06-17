"""Task 8: _load_base_params 단위 테스트.

라이브 config.yaml 의 고정 sl/tp/max_hold 를 베이스라인 파라미터로 로드하는지 검증.
이 프로젝트의 config 는 `risk_management:` 키를 사용한다 (scaffold 의 `risk:` 아님).
"""
from scripts.dynamic_rr_multiverse import _load_base_params


def test_load_base_params_elder():
    p = _load_base_params("elder_ema_pullback")
    assert p["stop_loss_pct"] == 0.08
    assert p["take_profit_pct"] == 0.30
    assert p["max_hold_bars"] == 100


def test_load_base_params_book_pullback_ma5():
    # sl 0.03 / tp 0.15 / max_hold 30 — 다른 전략도 동일 키 구조 확인
    p = _load_base_params("book_pullback_ma5")
    assert p["stop_loss_pct"] == 0.03
    assert p["take_profit_pct"] == 0.15
    assert p["max_hold_bars"] == 30
