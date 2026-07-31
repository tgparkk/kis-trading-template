"""run_once() 의 summaries "ok" 필드 정합성 테스트 (2026-07-31, HIGH 결함).

배경: runners/screener_snapshot_collector.py run_once() 는 non-dry-run 경로에서
DB 저장 성공 여부를 계산해 지역변수 ok 에 담아 print(status) 에만 쓰고,
summaries.append 에는 항상 "ok": True 를 하드코딩했다. 그 결과:
- bot/liquidation_handler.py:620 의 `failed = [... if not s["ok"]]` 가 저장
  실패를 영원히 감지하지 못함(:621 WARNING 이 절대 발화하지 않음)
- liquidation_handler.py:612 텔레그램이 저장 실패에도 "N건 저장 완료" 발송

방금 고친 검증 쿼리(D-1/CURRENT_DATE 날짜 불일치, _verify_screener_snapshot)와
정확히 같은 클래스의 거짓 안심이며 한 층 아래(저장 자체)에 있다.
"""
from datetime import date

from runners import screener_snapshot_collector as ssc


class _FakeCandidate:
    def __init__(self, code="005930", name="삼성전자", score=1.0, reason="test"):
        self.code = code
        self.name = name
        self.score = score
        self.reason = reason


class _FakeAdapter:
    """ScreenerBase 규약만 만족하는 최소 스텁."""

    def __init__(self, candidates):
        self._candidates = list(candidates)

    def default_params(self):
        return {}

    def scan(self, scan_date, params):
        return list(self._candidates)


class _FakeCandidateRepo:
    def __init__(self, save_result=True):
        self.save_result = save_result
        self.save_calls = []

    def save_screener_snapshot(self, **kwargs):
        self.save_calls.append(kwargs)
        return self.save_result


class _FakeDbManager:
    def __init__(self, save_result=True):
        self.candidate_repo = _FakeCandidateRepo(save_result)


def _patch_adapter(monkeypatch, candidates):
    monkeypatch.setattr(
        ssc, "_build_adapter",
        lambda strategy_name, broker=None, db_manager=None, config=None: _FakeAdapter(candidates),
    )


def test_run_once_ok_false_when_save_fails(monkeypatch):
    """save_screener_snapshot() 이 False 를 반환하면 요약도 ok=False 여야 한다.

    현재 결함: 계산된 ok 를 버리고 summaries.append 에 "ok": True 를 하드코딩해
    저장 실패가 소비자(liquidation_handler)에 영원히 전달되지 않는다.
    """
    _patch_adapter(monkeypatch, [_FakeCandidate()])
    db_manager = _FakeDbManager(save_result=False)

    summaries = ssc.run_once(
        strategies=["fake"], scan_date=date(2026, 7, 30), max_candidates=10,
        dry_run=False, db_manager=db_manager,
    )

    assert summaries[0]["count"] == 1
    assert summaries[0]["ok"] is False, f"저장 실패인데 ok={summaries[0]['ok']!r}"


def test_run_once_ok_true_when_save_succeeds(monkeypatch):
    """save_screener_snapshot() 이 True 를 반환하면 요약도 ok=True (정상 경로 유지)."""
    _patch_adapter(monkeypatch, [_FakeCandidate()])
    db_manager = _FakeDbManager(save_result=True)

    summaries = ssc.run_once(
        strategies=["fake"], scan_date=date(2026, 7, 30), max_candidates=10,
        dry_run=False, db_manager=db_manager,
    )

    assert summaries[0]["ok"] is True


def test_run_once_ok_false_when_db_manager_none_and_count_positive(monkeypatch):
    """db_manager 가 None 인데 후보가 있으면 저장 못 한 것이 맞으므로 ok=False (기존 동작 유지)."""
    _patch_adapter(monkeypatch, [_FakeCandidate()])

    summaries = ssc.run_once(
        strategies=["fake"], scan_date=date(2026, 7, 30), max_candidates=10,
        dry_run=False, db_manager=None,
    )

    assert summaries[0]["ok"] is False


def test_run_once_ok_true_when_count_zero(monkeypatch):
    """후보 0건은 DB 저장을 스킵하는 정상 상태이므로 ok=True."""
    _patch_adapter(monkeypatch, [])
    db_manager = _FakeDbManager(save_result=False)  # 호출되면 안 됨(count==0 이라 스킵)

    summaries = ssc.run_once(
        strategies=["fake"], scan_date=date(2026, 7, 30), max_candidates=10,
        dry_run=False, db_manager=db_manager,
    )

    assert summaries[0]["count"] == 0
    assert summaries[0]["ok"] is True
    assert db_manager.candidate_repo.save_calls == [], "count==0 인데 save_screener_snapshot 이 호출됨"


def test_run_once_dry_run_does_not_raise_and_ok_true(monkeypatch):
    """dry_run=True 는 DB 저장을 시도하지 않은 것이므로 실패가 아니다 — ok=True, 예외 없음.

    회귀 방지 핵심: "ok": ok 로 고치면서 dry_run 분기에 ok 를 정의하지 않으면
    UnboundLocalError 가 난다. 이 테스트가 그 회귀를 잡는다.
    """
    _patch_adapter(monkeypatch, [_FakeCandidate()])

    summaries = ssc.run_once(
        strategies=["fake"], scan_date=date(2026, 7, 30), max_candidates=10,
        dry_run=True, db_manager=None,
    )

    assert summaries[0]["ok"] is True


def test_run_once_exception_path_ok_false(monkeypatch):
    """어댑터 scan() 이 예외를 던지면 요약은 ok=False (기존 except 블록 동작 회귀 고정)."""
    class _RaisingAdapter(_FakeAdapter):
        def scan(self, scan_date, params):
            raise RuntimeError("boom")

    monkeypatch.setattr(
        ssc, "_build_adapter",
        lambda strategy_name, broker=None, db_manager=None, config=None: _RaisingAdapter([]),
    )

    summaries = ssc.run_once(
        strategies=["fake"], scan_date=date(2026, 7, 30), max_candidates=10,
        dry_run=False, db_manager=None,
    )

    assert summaries[0]["ok"] is False
