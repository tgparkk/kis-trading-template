"""
KIS chk-holiday 휴장일 동기화 테스트
====================================
- get_chk_holiday 파싱(kis._url_fetch mock) → list 반환 / 실패 시 None
- sync_today with fetch_fn 주입 → is_kis_closed_day 판정
- 하루 1회 가드(fetch_fn call count) + force 재호출
- fallback(None/[]/예외) → False, 기존 셋 보존, 예외 미전파
- 게이트 통합: 런타임셋 주입 후 is_holiday / market_hours._is_holiday 반영

네트워크 호출 금지: fetch_fn 주입 또는 api.kis_auth._url_fetch 패치.
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest
from datetime import datetime, date
from unittest.mock import patch, MagicMock


# ---------------------------------------------------------------------------
# 헬퍼: chk-holiday output 샘플 행 생성
# ---------------------------------------------------------------------------
def _row(bass_dt: str, opnd_yn: str) -> dict:
    return {
        "bass_dt": bass_dt,
        "wday_dvsn_cd": "01",
        "bzdy_yn": "Y" if opnd_yn == "Y" else "N",
        "tr_day_yn": "Y" if opnd_yn == "Y" else "N",
        "opnd_yn": opnd_yn,
        "sttl_day_yn": "Y" if opnd_yn == "Y" else "N",
    }


def _sample_rows() -> list:
    """20261231=N(휴장), 20260603=N(지방선거), 20260604=Y(개장) 포함 샘플."""
    return [
        _row("20261229", "Y"),
        _row("20261230", "Y"),
        _row("20261231", "N"),  # KRX 연말휴장
        _row("20260603", "N"),  # 지방선거(휴장)
        _row("20260604", "Y"),  # 개장일
    ]


@pytest.fixture(autouse=True)
def _reset_sync_module():
    """각 테스트마다 holiday_kis_sync 런타임 상태 초기화 + 캐시 디스크쓰기 차단."""
    import utils.holiday_kis_sync as hks
    hks._runtime_closed = set()
    hks._synced_date = None
    # 테스트가 cwd에 실제 캐시파일을 만들지 않도록 _save_cache no-op 패치
    with patch.object(hks, "_save_cache", lambda: None):
        yield
    hks._runtime_closed = set()
    hks._synced_date = None


# ---------------------------------------------------------------------------
# 1. get_chk_holiday 파싱
# ---------------------------------------------------------------------------
class TestGetChkHoliday:
    def test_parse_list_output(self):
        from api import kis_market_api

        rows = _sample_rows()
        mock_body = MagicMock()
        mock_body.output = rows
        mock_res = MagicMock()
        mock_res.isOK.return_value = True
        mock_res.getBody.return_value = mock_body

        with patch("api.kis_auth._url_fetch", return_value=mock_res):
            result = kis_market_api.get_chk_holiday("20261231")

        assert isinstance(result, list)
        assert result == rows

    def test_returns_none_on_failure(self):
        from api import kis_market_api

        mock_res = MagicMock()
        mock_res.isOK.return_value = False

        with patch("api.kis_auth._url_fetch", return_value=mock_res):
            result = kis_market_api.get_chk_holiday("20261231")

        assert result is None

    def test_returns_none_when_fetch_none(self):
        from api import kis_market_api

        with patch("api.kis_auth._url_fetch", return_value=None):
            result = kis_market_api.get_chk_holiday("20261231")

        assert result is None

    def test_wraps_dict_output_in_list(self):
        from api import kis_market_api

        single = _row("20261231", "N")
        mock_body = MagicMock()
        mock_body.output = single
        mock_res = MagicMock()
        mock_res.isOK.return_value = True
        mock_res.getBody.return_value = mock_body

        with patch("api.kis_auth._url_fetch", return_value=mock_res):
            result = kis_market_api.get_chk_holiday("20261231")

        assert result == [single]


# ---------------------------------------------------------------------------
# 2. sync_today + is_kis_closed_day
# ---------------------------------------------------------------------------
class TestSyncToday:
    def test_sync_marks_closed_days(self):
        import utils.holiday_kis_sync as hks

        fetch = MagicMock(return_value=_sample_rows())
        ok = hks.sync_today(today=date(2026, 6, 3), fetch_fn=fetch)

        assert ok is True
        assert hks.is_kis_closed_day(date(2026, 12, 31)) is True
        assert hks.is_kis_closed_day(date(2026, 6, 3)) is True
        assert hks.is_kis_closed_day(date(2026, 6, 4)) is False

    def test_is_kis_closed_day_accepts_datetime(self):
        import utils.holiday_kis_sync as hks

        fetch = MagicMock(return_value=_sample_rows())
        hks.sync_today(today=date(2026, 6, 3), fetch_fn=fetch)

        assert hks.is_kis_closed_day(datetime(2026, 12, 31, 10, 30)) is True
        assert hks.is_kis_closed_day(datetime(2026, 6, 4, 10, 30)) is False

    def test_default_today_uses_now(self):
        import utils.holiday_kis_sync as hks

        fetch = MagicMock(return_value=_sample_rows())
        ok = hks.sync_today(fetch_fn=fetch)

        assert ok is True
        # 페이지네이션으로 _DEFAULT_PAGES 회 호출됨
        assert fetch.call_count == hks._DEFAULT_PAGES


# ---------------------------------------------------------------------------
# 3. 하루 1회 가드 + 페이지네이션
# ---------------------------------------------------------------------------
class TestOncePerDayGuard:
    def test_second_call_same_day_skips_fetch(self):
        """첫 호출은 pages회 fetch, 같은 날 2번째 호출은 ZERO fetch."""
        import utils.holiday_kis_sync as hks

        pages = 3
        fetch = MagicMock(return_value=_sample_rows())
        today = date(2026, 6, 3)

        assert hks.sync_today(today=today, fetch_fn=fetch, pages=pages) is True
        first_count = fetch.call_count
        assert first_count == pages  # 첫 호출: pages회 fetch

        assert hks.sync_today(today=today, fetch_fn=fetch, pages=pages) is True
        assert fetch.call_count == first_count  # 2번째 호출: ZERO fetch (가드)

    def test_force_refetches(self):
        import utils.holiday_kis_sync as hks

        pages = 2
        fetch = MagicMock(return_value=_sample_rows())
        today = date(2026, 6, 3)

        hks.sync_today(today=today, fetch_fn=fetch, pages=pages)
        hks.sync_today(today=today, fetch_fn=fetch, pages=pages, force=True)

        assert fetch.call_count == pages * 2

    def test_different_day_refetches(self):
        import utils.holiday_kis_sync as hks

        pages = 1
        fetch = MagicMock(return_value=_sample_rows())

        hks.sync_today(today=date(2026, 6, 3), fetch_fn=fetch, pages=pages)
        hks.sync_today(today=date(2026, 6, 4), fetch_fn=fetch, pages=pages)

        assert fetch.call_count == 2  # 각 날짜마다 pages=1회씩

    def test_pagination_accumulates_both_pages(self):
        """pages=2 시 BASS_DT 전진으로 두 페이지 opnd_yn==N이 모두 누적된다."""
        import utils.holiday_kis_sync as hks

        # 페이지 1: 20260603~20260626 (24행), 20260603=N 포함
        page1 = [_row(f"2026060{d}" if d < 10 else f"202606{d}", "Y")
                 for d in range(4, 27)]
        page1.insert(0, _row("20260603", "N"))  # 첫 행 N
        # bass_dt 마지막값 = "20260626" → 다음 BASS_DT = 20260627

        # 페이지 2: BASS_DT=20260627, 20261231=N 포함
        page2 = [_row("20261231", "N"), _row("20261230", "Y")]

        call_args = []

        def _paged_fetch(bass_dt: str):
            call_args.append(bass_dt)
            if bass_dt == "20260603":
                return page1
            if bass_dt == "20260627":
                return page2
            return []

        ok = hks.sync_today(today=date(2026, 6, 3), pages=2, fetch_fn=_paged_fetch)

        assert ok is True
        assert hks.is_kis_closed_day(date(2026, 6, 3)) is True   # 페이지1
        assert hks.is_kis_closed_day(date(2026, 12, 31)) is True  # 페이지2
        assert len(call_args) == 2
        assert call_args[0] == "20260603"
        assert call_args[1] == "20260627"

    def test_pagination_stops_on_none_preserves_got(self):
        """fetch_fn이 첫 페이지에서 None 반환 → False, 런타임셋 변경 없음."""
        import utils.holiday_kis_sync as hks

        hks._runtime_closed = {"20261231"}
        fetch = MagicMock(return_value=None)

        ok = hks.sync_today(today=date(2026, 6, 3), pages=3, fetch_fn=fetch)

        assert ok is False
        assert hks._runtime_closed == {"20261231"}  # 기존 보존
        assert fetch.call_count == 1  # None 반환 즉시 break


# ---------------------------------------------------------------------------
# 4. fallback (None / [] / 예외)
# ---------------------------------------------------------------------------
class TestFallback:
    def test_none_response_returns_false_and_preserves(self):
        import utils.holiday_kis_sync as hks

        hks._runtime_closed = {"20261231"}
        fetch = MagicMock(return_value=None)

        ok = hks.sync_today(today=date(2026, 6, 3), fetch_fn=fetch)

        assert ok is False
        assert hks._runtime_closed == {"20261231"}  # 기존 보존

    def test_empty_list_returns_false(self):
        import utils.holiday_kis_sync as hks

        hks._runtime_closed = {"20261231"}
        fetch = MagicMock(return_value=[])

        ok = hks.sync_today(today=date(2026, 6, 3), fetch_fn=fetch)

        assert ok is False
        assert hks._runtime_closed == {"20261231"}

    def test_exception_swallowed_returns_false(self):
        import utils.holiday_kis_sync as hks

        hks._runtime_closed = {"20261231"}

        def _boom(_):
            raise RuntimeError("network down")

        # 예외 전파되지 않아야 함
        ok = hks.sync_today(today=date(2026, 6, 3), fetch_fn=_boom)

        assert ok is False
        assert hks._runtime_closed == {"20261231"}


# ---------------------------------------------------------------------------
# 5. 게이트 통합
# ---------------------------------------------------------------------------
class TestGateIntegration:
    def test_baseline_unchanged_without_sync(self):
        """동기화 전: 기존 특수휴일(2026-06-03)은 True, 갭(2026-12-31)은 False."""
        from utils.korean_holidays import is_holiday

        # 2026-06-03 = 지방선거 (기존 _SPECIAL_HOLIDAYS)
        assert is_holiday(datetime(2026, 6, 3)) is True
        # 2026-12-31 = KRX 연말휴장이지만 수동 캘린더에 없음 (갭)
        assert is_holiday(datetime(2026, 12, 31)) is False

    def test_injected_closed_day_becomes_holiday(self):
        import utils.holiday_kis_sync as hks
        from utils.korean_holidays import is_holiday

        hks._runtime_closed = {"20261231"}

        assert is_holiday(datetime(2026, 12, 31)) is True

    def test_normal_day_stays_open(self):
        import utils.holiday_kis_sync as hks
        from utils.korean_holidays import is_holiday

        hks._runtime_closed = {"20261231"}

        # 2026-12-30 (수요일)은 휴장 아님
        assert is_holiday(datetime(2026, 12, 30)) is False

    def test_market_hours_path_reflects_injection(self):
        """MarketHours._is_holiday도 is_special_holiday 경유로 반영되어야 함."""
        import utils.holiday_kis_sync as hks
        from config.market_hours import MarketHours

        hks._runtime_closed = {"20261231"}

        assert MarketHours._is_holiday('KRX', datetime(2026, 12, 31)) is True
        assert MarketHours._is_holiday('KRX', datetime(2026, 12, 30)) is False
