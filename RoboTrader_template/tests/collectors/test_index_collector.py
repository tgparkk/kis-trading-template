# tests/collectors/test_index_collector.py
"""지수 수집기 테스트.

🔴 2026-08-17 — `reconcile_index` 4개 테스트 삭제:
   「새 DB index_daily vs 레거시 robotrader_quant.daily_prices(KS11/KQ11)」 대조였고,
   그 함수가 레거시 DB 폐기와 함께 제거되면서 같이 사라졌다.
   **없어진 함수를 계속 시험할 수는 없다.**
   (삭제: exact_match_pass · no_new_data_fail · provisional_within_1pct_pass ·
    large_discrepancy_fail · 그리고 오직 그 4개만 쓰던 DB mock 헬퍼 일체)

   ⚠️ 잃어버린 커버리지 자기신고: (b) 「FDR 미설치로 index_daily 가 조용히 비는」
      실패를 잡던 가드가 이 삭제로 사라진다. 다만 그 가드는 **레거시 DB 가 살아
      있어야** 작동했고(비교 대상이 없으면 EMPTY 로 빠진다) 지금은 legacy 게이트가
      꺼져 있어 이미 휴면이었다. 대체 감시는 `bot/system_monitor.py` 의 EOD 로그
      (`지수 {…}`)와 `core/regime/index_refresh.py` 쪽 신선도 점검이 담당한다.
"""
import collectors.index_collector as ic
from collectors.index_collector import INDEX_TICKERS


def test_index_tickers_map():
    assert INDEX_TICKERS == {"KOSPI": "KS11", "KOSDAQ": "KQ11"}


def test_legacy_reconcile_helpers_are_gone():
    """레거시 대조 심볼 재유입 방지 — 죽은 DB 에 직접 붙던 코드다."""
    for nm in ("reconcile_index", "reconcile_verdict", "_LEGACY_CODE_MAP"):
        assert not hasattr(ic, nm), f"제거된 심볼이 되살아났다: {nm}"


def test_collect_index_is_still_exported():
    """수집 자체(kis_template.index_daily 적재)는 그대로 남아야 한다."""
    assert callable(ic.collect_index)
