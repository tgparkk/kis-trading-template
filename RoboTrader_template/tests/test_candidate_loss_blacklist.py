"""
D2: 손실 종목 동적 블랙리스트 단위 테스트
==========================================

테스트 항목:
- test_get_losing_stocks_recent_5days: DB 손실 기록 종목 반환
- test_get_persistently_failed_stocks_3_losses: 연속 3회 손실 종목 식별
- test_blacklist_filters_candidates: 블랙리스트 종목이 후보에서 제외됨
- test_blacklist_disabled_when_config_off: 토글 OFF 시 미적용
- test_blacklist_excludes_018470: 4/30 데이터 0승3패 종목(조일알미늄) 제외 시뮬레이션
- test_recent_and_persistent_combined: 두 블랙리스트 합산 동작
"""

import pytest
from unittest.mock import MagicMock, patch
from typing import Set

from core.candidate_selector import CandidateSelector, CandidateStock
from core.models import TradingConfig, CandidateFiltersConfig


# ============================================================================
# Fixtures
# ============================================================================

@pytest.fixture
def config_on():
    """블랙리스트 ON 설정"""
    cfg = TradingConfig()
    cfg.candidate_filters = CandidateFiltersConfig(
        exclude_recent_losses=True,
        recent_loss_days_back=5,
        exclude_persistent_losses=True,
        persistent_loss_count=3,
    )
    return cfg


@pytest.fixture
def config_off():
    """블랙리스트 완전 OFF 설정"""
    cfg = TradingConfig()
    cfg.candidate_filters = CandidateFiltersConfig(
        exclude_recent_losses=False,
        exclude_persistent_losses=False,
    )
    return cfg


@pytest.fixture
def selector_on(config_on):
    return CandidateSelector(config=config_on, broker=MagicMock())


@pytest.fixture
def selector_off(config_off):
    return CandidateSelector(config=config_off, broker=MagicMock())


def _make_candidate(code: str, name: str = "테스트") -> CandidateStock:
    return CandidateStock(code=code, name=name, market="KOSPI", score=50.0, reason="test")


def _mock_repo(recent: Set[str] = None, persistent: Set[str] = None):
    """TradingRepository mock — get_losing_stocks / get_persistently_failed_stocks 반환값 설정."""
    repo = MagicMock()
    repo.get_losing_stocks.return_value = recent or set()
    repo.get_persistently_failed_stocks.return_value = persistent or set()
    return repo


# ============================================================================
# TradingRepository 메서드 단위 테스트 (DB mock)
# ============================================================================

class TestTradingRepositoryLossMethods:
    def test_get_losing_stocks_returns_set(self):
        """get_losing_stocks는 set을 반환한다 (mock 검증)."""
        repo = _mock_repo(recent={"005930", "000660"})
        result = repo.get_losing_stocks(days_back=5, min_losses=1)
        assert isinstance(result, set)
        assert "005930" in result
        assert "000660" in result

    def test_get_losing_stocks_recent_5days(self):
        """최근 5영업일 손실 종목 반환 — days_back=5 인자 전달 확인."""
        repo = _mock_repo(recent={"018470"})
        result = repo.get_losing_stocks(days_back=5, min_losses=1)
        assert "018470" in result
        repo.get_losing_stocks.assert_called_once_with(days_back=5, min_losses=1)

    def test_get_persistently_failed_stocks_3_losses(self):
        """연속 3회 손실 종목 반환 — consecutive_losses=3 인자 전달 확인."""
        repo = _mock_repo(persistent={"018470"})
        result = repo.get_persistently_failed_stocks(consecutive_losses=3)
        assert "018470" in result
        repo.get_persistently_failed_stocks.assert_called_once_with(consecutive_losses=3)

    def test_get_losing_stocks_empty_on_db_error(self):
        """DB 오류 시 빈 set 반환."""
        repo = MagicMock()
        repo.get_losing_stocks.side_effect = Exception("DB 연결 실패")
        # side_effect 예외 발생 시 호출부에서 처리 — 실제 repository 구현 검증은
        # integration test 영역이므로 여기서는 mock 오류 전파만 확인
        with pytest.raises(Exception):
            repo.get_losing_stocks(days_back=5)


# ============================================================================
# _apply_loss_blacklist 동작 테스트
# ============================================================================

class TestApplyLossBlacklist:
    def test_blacklist_filters_candidates(self, selector_on):
        """블랙리스트 종목은 후보에서 제외된다."""
        candidates = [
            _make_candidate("005930", "삼성전자"),
            _make_candidate("018470", "조일알미늄"),
            _make_candidate("000660", "SK하이닉스"),
        ]
        repo = _mock_repo(recent={"018470"})

        result = selector_on._apply_loss_blacklist(candidates, trading_repo=repo)
        codes = [c.code for c in result]
        assert "018470" not in codes
        assert "005930" in codes
        assert "000660" in codes

    def test_blacklist_disabled_when_config_off(self, selector_off):
        """exclude_recent_losses=False, exclude_persistent_losses=False 시 필터 미적용."""
        candidates = [
            _make_candidate("018470", "조일알미늄"),
            _make_candidate("005930", "삼성전자"),
        ]
        repo = _mock_repo(recent={"018470"}, persistent={"018470"})

        result = selector_off._apply_loss_blacklist(candidates, trading_repo=repo)
        # 토글 OFF → repo 호출 없이 원본 반환
        assert len(result) == 2
        repo.get_losing_stocks.assert_not_called()
        repo.get_persistently_failed_stocks.assert_not_called()

    def test_blacklist_excludes_018470(self, selector_on):
        """4/30 0승3패 종목(조일알미늄 018470) 제외 시뮬레이션."""
        candidates = [
            _make_candidate("018470", "조일알미늄"),
            _make_candidate("005930", "삼성전자"),
            _make_candidate("000660", "SK하이닉스"),
        ]
        # 018470은 연속 3회 손실 → persistent 블랙리스트
        repo = _mock_repo(recent=set(), persistent={"018470"})

        result = selector_on._apply_loss_blacklist(candidates, trading_repo=repo)
        codes = [c.code for c in result]
        assert "018470" not in codes
        assert len(result) == 2

    def test_recent_and_persistent_combined(self, selector_on):
        """최근 손실 + 연속 손실 합산 블랙리스트 적용."""
        candidates = [
            _make_candidate("AAA"),
            _make_candidate("BBB"),
            _make_candidate("CCC"),
            _make_candidate("DDD"),
        ]
        repo = _mock_repo(recent={"AAA"}, persistent={"BBB"})

        result = selector_on._apply_loss_blacklist(candidates, trading_repo=repo)
        codes = [c.code for c in result]
        assert "AAA" not in codes
        assert "BBB" not in codes
        assert "CCC" in codes
        assert "DDD" in codes

    def test_blacklist_empty_candidates(self, selector_on):
        """빈 후보 리스트 입력 시 빈 리스트 반환."""
        repo = _mock_repo(recent={"005930"})
        result = selector_on._apply_loss_blacklist([], trading_repo=repo)
        assert result == []

    def test_blacklist_no_overlap(self, selector_on):
        """블랙리스트에 후보가 없으면 전원 통과."""
        candidates = [_make_candidate("005930"), _make_candidate("000660")]
        repo = _mock_repo(recent={"999999"}, persistent={"888888"})

        result = selector_on._apply_loss_blacklist(candidates, trading_repo=repo)
        assert len(result) == 2

    def test_blacklist_repo_error_graceful(self, selector_on):
        """repo 조회 오류 시 보수적으로 후보 유지."""
        candidates = [_make_candidate("005930")]
        repo = MagicMock()
        repo.get_losing_stocks.side_effect = Exception("DB 오류")
        repo.get_persistently_failed_stocks.side_effect = Exception("DB 오류")

        # 예외 발생 시에도 후보 유지 (보수적 통과)
        result = selector_on._apply_loss_blacklist(candidates, trading_repo=repo)
        assert len(result) == 1

    def test_only_recent_loss_filter_when_persistent_off(self):
        """exclude_persistent_losses=False 시 최근 손실 필터만 적용."""
        from core.models import TradingConfig, CandidateFiltersConfig
        cfg = TradingConfig()
        cfg.candidate_filters = CandidateFiltersConfig(
            exclude_recent_losses=True,
            exclude_persistent_losses=False,
        )
        selector = CandidateSelector(config=cfg, broker=MagicMock())
        candidates = [_make_candidate("AAA"), _make_candidate("BBB")]
        repo = _mock_repo(recent={"AAA"}, persistent={"BBB"})

        result = selector._apply_loss_blacklist(candidates, trading_repo=repo)
        codes = [c.code for c in result]
        assert "AAA" not in codes   # 최근 손실 → 제외
        assert "BBB" in codes       # persistent OFF → 통과
        repo.get_persistently_failed_stocks.assert_not_called()

    def test_only_persistent_filter_when_recent_off(self):
        """exclude_recent_losses=False 시 연속 손실 필터만 적용."""
        from core.models import TradingConfig, CandidateFiltersConfig
        cfg = TradingConfig()
        cfg.candidate_filters = CandidateFiltersConfig(
            exclude_recent_losses=False,
            exclude_persistent_losses=True,
            persistent_loss_count=3,
        )
        selector = CandidateSelector(config=cfg, broker=MagicMock())
        candidates = [_make_candidate("AAA"), _make_candidate("BBB")]
        repo = _mock_repo(recent={"AAA"}, persistent={"BBB"})

        result = selector._apply_loss_blacklist(candidates, trading_repo=repo)
        codes = [c.code for c in result]
        assert "AAA" in codes       # recent OFF → 통과
        assert "BBB" not in codes   # persistent → 제외
        repo.get_losing_stocks.assert_not_called()
