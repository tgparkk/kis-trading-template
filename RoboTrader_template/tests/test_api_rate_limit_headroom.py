"""
KIS API 호출 간격 헤드룸 회귀 테스트
====================================

2026-06-09: API_CALL_INTERVAL=0.06초(초당 16-17회)가 KIS 상한 20/s에
헤드룸 없이 붙어 서버측 롤링윈도우 계산·지터만으로 EGW00201(속도제한)이
하루 2,689회 발생 → 각 오류의 2.2~3초 백오프 sleep이 전역 API 락 위에서
일어나 메인 트레이딩 루프 전체를 정지시킴(on_tick ~70초 주기로 마비).

기본 호출 간격은 KIS 20/s 상한 대비 충분한 헤드룸(≥0.08초, 즉 ≤12.5/s)을
유지해야 한다.
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def test_api_call_interval_has_headroom_under_kis_limit():
    """기본 API 호출 간격은 KIS 20/s 상한 대비 헤드룸이 있어야 한다."""
    from config.constants import API_CALL_INTERVAL

    assert API_CALL_INTERVAL >= 0.08, (
        f"API_CALL_INTERVAL={API_CALL_INTERVAL}초 → 약 {1 / API_CALL_INTERVAL:.1f}/s. "
        f"KIS 20/s 상한에 헤드룸이 없어 EGW00201 폭주를 유발한다 (≥0.08초 필요)."
    )
