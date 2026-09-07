"""_fetch_candidates_for_strategy 의 섹터 뉴스 재정렬 배선 — off/shadow/live · 안전필터 앞 · fail-open 전 경로 (스펙 B §5.1·§5.5)."""
import sys
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import MagicMock

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import tests._mock_modules  # noqa: F401,E402
import config.constants as C  # noqa: E402
import core.candidate_selector as cs  # noqa: E402
from core.candidate_selector import CandidateSelector, CandidateStock  # noqa: E402

NOW = datetime(2026, 9, 8, 9, 0)      # 화 09:00
CODES = ["A1", "A2", "A3", "A4", "A5", "A6"]


class UndefinedFunction(Exception):
    pass


class UndefinedTable(Exception):
    pass


class FakeRepo:
    def __init__(self, scores=None, asof=None, sector_map=None, exc_scores=None, exc_map=None, exc_save=None):
        self.scores, self.asof, self.sector_map = scores or {}, asof, sector_map or {}
        self.exc_scores, self.exc_map, self.exc_save = exc_scores, exc_map, exc_save
        self.saved, self.calls = [], []

    def get_scores(self, trade_date):
        self.calls.append("get_scores")
        if self.exc_scores:
            raise self.exc_scores
        return dict(self.scores), self.asof

    def get_sector_map(self, as_of, codes):
        self.calls.append("get_sector_map")
        if self.exc_map:
            raise self.exc_map
        return {c: s for c, s in self.sector_map.items() if c in codes}

    def save_rerank_log(self, rows):
        self.calls.append("save")
        if self.exc_save:
            raise self.exc_save
        self.saved.extend(rows)
        return len(rows)


GOOD = dict(scores={"261": 1.0, "641": -1.0}, asof=NOW - timedelta(minutes=5), sector_map={"A5": "261", "A2": "641"})


@pytest.fixture
def selector(monkeypatch):
    sel = CandidateSelector(config=MagicMock(), broker=MagicMock(), db_manager=MagicMock())
    monkeypatch.setattr(cs, "now_kst", lambda: NOW)
    monkeypatch.setattr(cs, "get_previous_trading_day", lambda dt=None, market="KRX": datetime(2026, 9, 7))
    monkeypatch.setattr("core.screener_snapshot_provider.make_screener_snapshot_provider",
                        lambda strategy_name, params_hash=None: (lambda s, d: list(CODES)))
    monkeypatch.setattr(sel, "_filter_unsafe_stocks", lambda pool, limit=None: pool[:limit] if limit else pool)
    for name, val in (("SECTOR_NEWS_MAX_SHIFT", 3), ("SECTOR_NEWS_MIN_ABS", 0.2),
                      ("SECTOR_NEWS_STALE_MINUTES", 60), ("SECTOR_NEWS_EXCLUDE_STRATEGIES", frozenset())):
        monkeypatch.setattr(C, name, val)
    return sel


def _run(sel, repo, mode, monkeypatch, strategy="s1", limit=20):
    monkeypatch.setattr(C, "SECTOR_NEWS_BOOST_MODE", mode)
    sel.db_manager.sector_news_repo = repo
    return sel._fetch_candidates_for_strategy(strategy, limit)


def _codes(cands):
    return [c.code for c in cands]


def test_candidate_stock_has_default_sector_note():
    assert CandidateStock(code="x", name="x", market="KRX", score=1.0, reason="r").sector_note == ""


def test_off_touches_nothing(selector, monkeypatch):
    repo = FakeRepo(**GOOD)
    assert _codes(_run(selector, repo, "off", monkeypatch)) == CODES
    assert repo.calls == []


def test_shadow_keeps_order_but_records_would_be_ranks(selector, monkeypatch):
    repo = FakeRepo(**GOOD)
    cands = _run(selector, repo, "shadow", monkeypatch)
    assert _codes(cands) == CODES and all(c.sector_note == "" for c in cands)
    assert repo.calls == ["get_scores", "get_sector_map", "save"]
    by = {r["stock_code"]: r for r in repo.saved}
    assert len(by) == 6
    assert all(r["mode"] == "shadow" and r["reason"] == "ok" and r["applied"] is False
               and r["strategy"] == "s1" and r["trade_date"] == NOW.date() for r in by.values())
    assert by["A5"] == dict(by["A5"], new_rank=2, orig_rank=5, sector_key="261", sector_score=1.0)
    assert by["A2"]["new_rank"] == 5 and by["A1"]["new_rank"] == 1 and by["A1"]["sector_key"] is None
    assert by["A1"]["score_asof"] == NOW - timedelta(minutes=5)


def test_live_applies_new_order_and_notes(selector, monkeypatch):
    repo = FakeRepo(**GOOD)
    cands = _run(selector, repo, "live", monkeypatch)
    assert _codes(cands) == ["A1", "A5", "A3", "A4", "A2", "A6"]
    assert all(r["applied"] is True and r["mode"] == "live" for r in repo.saved)
    notes = {c.code: c.sector_note for c in cands}
    assert notes["A5"] == " (↑3 261 +1.0)" and notes["A2"] == " (↓3 641 -1.0)" and notes["A1"] == ""


def test_live_rerank_happens_before_limit_cut(selector, monkeypatch):
    repo = FakeRepo(scores={"261": 1.0}, asof=NOW, sector_map={"A6": "261"})
    assert _codes(_run(selector, repo, "live", monkeypatch, limit=3)) == ["A1", "A2", "A6"]


@pytest.mark.parametrize("repo_kwargs,reason", [
    (dict(scores={}, asof=None), "no_score_rows"),
    (dict(scores={"261": 1.0}, asof=NOW - timedelta(minutes=61), sector_map={"A5": "261"}), "stale"),
    (dict(exc_scores=UndefinedTable("relation sector_news_score does not exist")), "table_missing"),
    (dict(scores={"261": 1.0}, asof=NOW, exc_map=UndefinedFunction("fn_sector_map_as_of")), "fn_missing"),
    (dict(scores={"261": 1.0}, asof=NOW, exc_map=RuntimeError("boom")), "error:RuntimeError"),
])
def test_fail_open_paths_keep_order_and_record_reason(selector, monkeypatch, repo_kwargs, reason):
    repo = FakeRepo(**repo_kwargs)
    assert _codes(_run(selector, repo, "live", monkeypatch)) == CODES
    assert len(repo.saved) == 6
    assert all(r["reason"] == reason and r["new_rank"] == r["orig_rank"] and r["applied"] is False
               and r["sector_score"] is None for r in repo.saved)


def test_stale_boundary_exactly_60_minutes_is_fresh(selector, monkeypatch):
    repo = FakeRepo(scores={"261": 1.0}, asof=NOW - timedelta(minutes=60), sector_map={"A5": "261"})
    assert _codes(_run(selector, repo, "live", monkeypatch)) == ["A1", "A5", "A2", "A3", "A4", "A6"]


def test_save_failure_does_not_change_order(selector, monkeypatch):
    repo = FakeRepo(exc_save=RuntimeError("db down"), **GOOD)
    assert _codes(_run(selector, repo, "live", monkeypatch)) == ["A1", "A5", "A3", "A4", "A2", "A6"]
    assert repo.calls[-1] == "save"


def test_excluded_strategy_records_and_keeps_order(selector, monkeypatch):
    monkeypatch.setattr(C, "SECTOR_NEWS_EXCLUDE_STRATEGIES", frozenset({"deep_mr_dev20"}))
    repo = FakeRepo(**GOOD)
    assert _codes(_run(selector, repo, "live", monkeypatch, strategy="deep_mr_dev20")) == CODES
    assert repo.calls == ["save"] and all(r["reason"] == "excluded_strategy" for r in repo.saved)


def test_missing_repo_attribute_is_fail_open(selector, monkeypatch):
    monkeypatch.setattr(C, "SECTOR_NEWS_BOOST_MODE", "live")
    selector.db_manager = object()    # sector_news_repo 없음
    assert _codes(selector._fetch_candidates_for_strategy("s1", 20)) == CODES


def test_exception_inside_rerank_never_escapes(selector, monkeypatch):
    repo = FakeRepo(**GOOD)

    def _boom(*a, **k):
        raise RuntimeError("bug")
    monkeypatch.setattr("core.sector_news_rerank.rerank", _boom)
    assert _codes(_run(selector, repo, "live", monkeypatch)) == CODES


def test_apply_method_direct_contract(selector, monkeypatch):
    monkeypatch.setattr(C, "SECTOR_NEWS_BOOST_MODE", "shadow")
    selector.db_manager.sector_news_repo = FakeRepo(**GOOD)
    codes, notes = selector._apply_sector_news_rerank("s1", list(CODES), "2026-09-07")
    assert codes == CODES and notes == {}
    monkeypatch.setattr(C, "SECTOR_NEWS_BOOST_MODE", "live")
    codes, notes = selector._apply_sector_news_rerank("s1", list(CODES), "2026-09-07")
    assert codes == ["A1", "A5", "A3", "A4", "A2", "A6"] and set(notes) == {"A5", "A2"}
