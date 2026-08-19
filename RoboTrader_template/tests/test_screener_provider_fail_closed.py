"""screener_snapshots 조회 «고장» 이 「후보 없음」으로 위장되지 않는지 검증.

## 왜 이 파일이 있나 (2026-08-19)

`68b542f` 가 `core/candidate_selector.py` 에서 「없다」와 「고장」을 갈랐다.
그런데 갈라놓은 `except` 가 **도달 불가**였다 — 한 층 아래
`core/screener_snapshot_provider.py` 가 모든 예외를 삼키고 `[]` 를 돌려줬기 때문이다.

⇒ DB 조회가 고장나면 시스템이 `[E6] ... 조건에 맞는 종목 없음, 금일 미진입` 이라는
   **INFO(정상) 메시지로 보고**했다. 가드의 ERROR 문구가 `screener_snapshots 조회 «실패»`
   인데 정작 그 조회 실패는 여기 도달하지 못했다 —
   ***가드가 자기가 못 잡는 케이스의 이름을 달고 있었다.***

🔑 계열 규칙: ***같은 결함은 「고치는 과정」에서 한 층 아래로 재발한다.***

## 🔴 캡처 장치도 가드다

`utils/logger.py:106` 이 `logger.propagate = False` 를 건다. 그런데 **그 시점이 중요하다** —
실측(2026-08-19): 모듈 import 만으로는 `propagate=True / handlers=0` 이고,
**`CandidateSelector` 인스턴스가 생성될 때**(`__init__` 의 `setup_logger`) 비로소
`propagate=False / handlers=2` 가 된다.

⇒ 🔴 ***caplog 는 「항상 안 보인다」가 아니라 「테스트 순서에 따라 보이기도 한다」다.***
   같은 caplog 단언이 단독 실행에서는 통과하고 전체 실행에서는 무의미해질 수 있다.
   **「항상 무의미」보다 나쁘다** — 무의미해지는 순간이 실행 조건에 숨는다.

그래서 이 파일은 로거에 핸들러를 «직접» 붙이고, **positive control**
(`test_capture_device_actually_sees_error`)로 캡처 장치가 살아 있음을 먼저 증명한다.
그 통제가 통과해야만 「ERROR 0건」 단언이 의미를 갖는다.
"""
import logging
from datetime import date, datetime
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

import core.screener_snapshot_provider as provider_mod
from core.candidate_selector import CandidateSelector
from core.screener_snapshot_provider import make_screener_snapshot_provider

SELECTOR_LOGGER = "core.candidate_selector"


class _Capture(logging.Handler):
    """propagate=False 로거에 «직접» 붙는 캡처 핸들러."""

    def __init__(self):
        super().__init__(level=logging.DEBUG)
        self.records = []

    def emit(self, record):
        self.records.append(record)

    def messages(self, level):
        return [r.getMessage() for r in self.records if r.levelno == level]


@pytest.fixture
def cap():
    logger = logging.getLogger(SELECTOR_LOGGER)
    handler = _Capture()
    prev_level = logger.level
    logger.addHandler(handler)
    logger.setLevel(logging.DEBUG)
    try:
        yield handler
    finally:
        logger.removeHandler(handler)
        logger.setLevel(prev_level)


def _make_selector():
    config = MagicMock()
    config.candidate_filters = None
    return CandidateSelector(config=config, broker=MagicMock(), db_manager=None)


class _DbDown(RuntimeError):
    """테스트 전용 — DB 조회 고장 표식."""


# ────────────────────────────────────────────────────────────────────────
# 0. 캡처 장치 건전성 — 이게 통과해야 아래 「ERROR 0건」 단언이 의미를 갖는다
# ────────────────────────────────────────────────────────────────────────

class TestCaptureDeviceIsItselfAGuard:

    def test_capture_device_actually_sees_error(self, cap):
        """positive control — 알려진 ERROR 를 넣으면 «반드시» 잡혀야 한다."""
        _make_selector()  # 실제 사용과 같은 상태(setup_logger 발효)를 만든 뒤 잰다
        logging.getLogger(SELECTOR_LOGGER).error("PROBE-4711")
        assert "PROBE-4711" in cap.messages(logging.ERROR), (
            "캡처 장치가 죽었다 — 이 파일의 「ERROR 0건」 단언은 전부 무의미해진다"
        )

    def test_caplog_goes_blind_once_selector_constructed(self, cap, caplog):
        """대칭 단언 — 같은 레코드를 우리 장치는 «보고» caplog 는 «못 본다».

        피시험체를 만든 뒤에는 `propagate=False` 라 caplog 가 눈이 먼다.
        ⇒ 이 경로를 caplog 로 검증하려 들면 「ERROR 없다」가 공짜로 참이 된다.

        이 테스트가 «실패»하면 `propagate=False` 전제가 풀린 것이므로
        이 파일의 캡처 전략을 재검토해야 한다.
        """
        _make_selector()
        with caplog.at_level(logging.ERROR):
            logging.getLogger(SELECTOR_LOGGER).error("PROBE-CAPLOG")

        assert "PROBE-CAPLOG" in cap.messages(logging.ERROR), "우리 장치는 봐야 한다"
        assert "PROBE-CAPLOG" not in caplog.text, "caplog 가 보였다 — 전제 재검토"


# ────────────────────────────────────────────────────────────────────────
# 1. provider 계약 — 「없다」는 [] · 「고장」은 예외
# ────────────────────────────────────────────────────────────────────────

class TestProviderSeparatesEmptyFromBroken:

    def test_raises_on_db_error(self):
        """🔴 조회 «고장» 은 삼키지 않고 올려보낸다."""
        with patch.object(provider_mod, "CandidateRepository") as MockRepo:
            MockRepo.side_effect = _DbDown("DB 연결 실패")
            provider = make_screener_snapshot_provider("SampleStrategy")
            with pytest.raises(_DbDown):
                provider("SampleStrategy", "2026-08-18")

    def test_returns_empty_when_no_rows(self):
        """🟢 스냅샷이 «없는» 날은 정상이며 [] 다 — 이건 예외가 아니다."""
        with patch.object(provider_mod, "CandidateRepository") as MockRepo:
            MockRepo.return_value.get_snapshot_date_range.return_value = pd.DataFrame()
            provider = make_screener_snapshot_provider("SampleStrategy")
            assert provider("SampleStrategy", "2026-08-18") == []

    def test_failure_is_not_cached(self):
        """실패를 캐시하면 순간 장애 하나가 그날 하루를 통째로 죽인다."""
        with patch.object(provider_mod, "CandidateRepository") as MockRepo:
            MockRepo.side_effect = _DbDown("DB 연결 실패")
            provider = make_screener_snapshot_provider("SampleStrategy")
            for _ in range(2):
                with pytest.raises(_DbDown):
                    provider("SampleStrategy", "2026-08-18")
            assert MockRepo.call_count == 2, "실패가 캐시됐다 — 재시도가 원천 봉쇄된다"

    def test_success_is_still_cached(self):
        """성공 캐시는 유지 — 회귀 방지."""
        with patch.object(provider_mod, "CandidateRepository") as MockRepo:
            MockRepo.return_value.get_snapshot_date_range.return_value = pd.DataFrame(
                {"stock_code": ["005930"]}
            )
            provider = make_screener_snapshot_provider("SampleStrategy")
            provider("SampleStrategy", "2026-08-18")
            provider("SampleStrategy", "2026-08-18")
            assert MockRepo.return_value.get_snapshot_date_range.call_count == 1


# ────────────────────────────────────────────────────────────────────────
# 2. candidate_selector — 고장이면 ERROR + 매수 중단, 정상 0건이면 INFO
# ────────────────────────────────────────────────────────────────────────

class TestSelectorFailClosedIsReachable:

    def _run(self, cap, provider_impl):
        selector = _make_selector()
        with patch.object(provider_mod, "make_screener_snapshot_provider",
                          return_value=provider_impl), \
             patch("core.candidate_selector.get_previous_trading_day",
                   return_value=datetime(2026, 8, 18)):
            return selector._fetch_candidates_for_strategy("minervini_volume_dryup", 10)

    def test_broken_query_logs_error_and_buys_nothing(self, cap):
        """🔴 이 테스트가 수정 «전» 코드에서 실패한다 = 결함의 재현."""
        def _boom(strategy, scan_date):
            raise _DbDown("DB 연결 실패")

        result = self._run(cap, _boom)

        assert result == [], "고장 시 다른 명단으로 대체하면 안 된다"
        errors = cap.messages(logging.ERROR)
        assert any("fail-closed" in m for m in errors), (
            f"고장이 ERROR 로 안 올라왔다 — 실제 ERROR: {errors}"
        )
        infos = cap.messages(logging.INFO)
        assert not any("조건에 맞는 종목 없음" in m for m in infos), (
            "고장을 「정상 0건」으로 보고했다 — 이게 바로 그 결함이다"
        )

    def test_legitimate_zero_logs_info_and_no_error(self, cap):
        """🟢 진짜 0건은 정상 — INFO 로 남고 ERROR 는 «없어야» 한다.

        (이 「없어야」 단언은 위 positive control 이 통과할 때만 의미가 있다.)
        """
        result = self._run(cap, lambda strategy, scan_date: [])

        assert result == []
        assert any("조건에 맞는 종목 없음" in m for m in cap.messages(logging.INFO))
        assert cap.messages(logging.ERROR) == []


# ────────────────────────────────────────────────────────────────────────
# 3. 통합 — 진짜 provider + 진짜 selector. «여기서만» 원래 결함이 재현된다
# ────────────────────────────────────────────────────────────────────────

class TestEndToEndBrokenQueryIsNotReportedAsEmpty:
    """🔑 §2 는 provider 를 mock 으로 «갈아끼우므로» 원래 결함을 재현하지 못한다.

    결함은 「provider 가 삼킨다」 + 「selector 가 0건을 정상으로 읽는다」의
    «합성»에서만 나타난다. 유닛 테스트 둘 다 통과하는데 합치면 고장나는 자리다.
    ⇒ 경계를 자른 테스트만 있으면 이 결함은 영원히 안 잡힌다.
    """

    def test_db_failure_must_not_surface_as_no_candidates(self, cap):
        selector = _make_selector()

        with patch.object(provider_mod, "CandidateRepository") as MockRepo,              patch("core.candidate_selector.get_previous_trading_day",
                   return_value=datetime(2026, 8, 18)):
            MockRepo.side_effect = _DbDown("DB 연결 실패")
            result = selector._fetch_candidates_for_strategy("minervini_volume_dryup", 10)

        assert result == [], "고장 시 다른 명단으로 대체하면 안 된다"

        infos = cap.messages(logging.INFO)
        assert not any("조건에 맞는 종목 없음" in m for m in infos), (
            "🔴 DB 고장이 「조건에 맞는 종목 없음」(정상)으로 보고됐다 — 이게 그 결함이다"
        )
        errors = cap.messages(logging.ERROR)
        assert any("fail-closed" in m for m in errors), (
            f"고장이 ERROR 로 안 올라왔다 — 실제 ERROR: {errors}"
        )
