# tests/collectors/test_minute_collector.py
"""분봉 수집기 테스트.

🔴 2026-08-17 — `minute_match_rate` 2개 테스트 삭제:
   그 함수는 「새 DB vs 레거시 robotrader」 분봉 바 일치율 계산기였고,
   유일한 소비자 `reconcile_minute` 가 레거시 DB 폐기와 함께 제거되면서 같이
   사라졌다. **없어진 함수를 계속 시험할 수는 없다.**
   (삭제된 테스트: test_minute_match_rate_on_intersection · _no_overlap)
   대신 「되살아나지 않는다」를 아래에서 고정한다.
"""
import collectors.minute_collector as mc


def test_legacy_reconcile_helpers_are_gone():
    """레거시 대조 심볼 재유입 방지 — 죽은 DB(robotrader)에 직접 붙던 코드다."""
    for nm in ("reconcile_minute", "minute_match_rate", "_load_bars"):
        assert not hasattr(mc, nm), f"제거된 심볼이 되살아났다: {nm}"


def test_collect_minute_is_still_exported():
    """수집 자체(kis_template 적재)는 그대로 남아야 한다 — 제거 범위 오버런 가드."""
    assert callable(mc.collect_minute)
