"""EOD 스크리너 스냅샷 「룰 통과 전수 저장」 — 사전등록 §5-1 (a)~(d).

근거: docs/prereg_2026-09-24_screener_fullpass_snapshot.md
  (a) 어댑터 `max_candidates=None` = 룰 통과 전부 · `scan(None)[:20] == scan(20)`(안정 정렬)
  (b) `run_once(None)` 이 전부 저장 · params_json 의 max_candidates = null · 한도 20 해시 = 골든
  (c) EOD 훅이 `bot.liquidation_handler.SCREENER_SNAPSHOT_MAX_ROWS` 를 그대로 넘긴다
  (d) 소비자 불변 가드 — 상위 20 중 11개가 제외돼도 21위 이하는 조회·선정되지 않는다

DB·네트워크 접근 0 — 유니버스·일봉·저장 연결·안전정보 조회는 전부 가짜다.
"""
import json
import logging
from contextlib import contextmanager
from datetime import date, datetime
from pathlib import Path
from types import SimpleNamespace
from typing import List
from unittest.mock import MagicMock, Mock, patch

import pandas as pd
import pytest

from core.candidate_selector import CandidateSelector
from core.models import TradingConfig
from strategies._rule_screener_base import RuleScreenerBase

SCAN_DATE = date(2026, 9, 22)

# 변경 전 골든 해시 — DB `screener_snapshots` (book_pullback_ma20, scan_date 2026-09-22) 의 유일 params_hash.
# params_json = {"max_candidates": 20, "max_market_cap": 3000000000000, "min_trading_value": 1000000000}
GOLDEN_MA20_HASH_MAX20 = "9f2ad26d81357cee7c8044c55f910bba04fb7ead"


def _frame(volume: int, n: int = 30) -> pd.DataFrame:
    """평탄한 종가(불가능봉 없음) + 거래량으로 종목을 식별하는 가짜 일봉."""
    return pd.DataFrame({
        "date": pd.bdate_range(end="2026-09-22", periods=n),
        "open": [10000.0] * n, "high": [10000.0] * n, "low": [10000.0] * n,
        "close": [10000.0] * n, "volume": [volume] * n,
    })


@contextmanager
def _capture_logs(logger, level=logging.INFO):
    """프로젝트 로거는 propagate=False 라 caplog 로 안 잡힌다 → 핸들러를 직접 붙인다."""
    records: List[logging.LogRecord] = []

    class _Collector(logging.Handler):
        def emit(self, record):
            records.append(record)

    handler = _Collector(level=level)
    prev_level = logger.level
    logger.setLevel(level)
    logger.addHandler(handler)
    try:
        yield records
    finally:
        logger.removeHandler(handler)
        logger.setLevel(prev_level)


# ---------------------------------------------------------------------------
# (a) 어댑터 — None = 전부 · 앞 20 은 한도 20 과 항등
# ---------------------------------------------------------------------------

class _TiedScreener(RuleScreenerBase):
    """점수 4종(동점 묶음) · 7의 배수 코드는 룰 탈락인 가짜 어댑터."""
    strategy_name = "fake_tied"

    def __init__(self, n_codes: int):
        super().__init__()
        self._codes = [f"{i:06d}" for i in range(1, n_codes + 1)]
        self.diags = []

    def base_filter(self, universe):
        return universe

    def match(self, df, params):
        tag = int(df["volume"].iloc[-1])
        if tag % 7 == 0:
            return None
        return (float(tag % 4), "fake")

    def finalize_scan(self, diag):
        self.diags.append(diag)

    def _load_universe(self, scan_date):
        return [{"code": c, "name": c, "market_cap": 1, "trading_value": 1} for c in self._codes]

    def _load_daily(self, code, scan_date):
        return _frame(volume=int(code))


def test_adapter_none_returns_every_match_and_prefix_equals_cap20():
    s = _TiedScreener(45)
    matched = [c for c in s._codes if int(c) % 7 != 0]
    expected = sorted(matched, key=lambda c: int(c) % 4, reverse=True)   # 안정 정렬 = 동점은 유니버스 순서
    assert len(matched) == 39

    full = s.scan(SCAN_DATE, {"max_candidates": None})
    assert [c.code for c in full] == expected
    assert s.diags[-1]["n_matched"] == s.diags[-1]["n_selected"] == 39

    top20 = s.scan(SCAN_DATE, {"max_candidates": 20})
    assert len(top20) == 20
    # 19~22위는 점수 1 동점 묶음이다 — 동점이 20위 경계를 가로지른다.
    assert {c.score for c in full[18:22]} == {1.0}
    assert [(c.code, c.score) for c in full[:20]] == [(c.code, c.score) for c in top20]
    assert (s.diags[-1]["n_matched"], s.diags[-1]["n_selected"]) == (39, 20)

    # 정수 한도는 그대로 — 0 은 [] · 미지정은 default_params 의 10.
    assert s.scan(SCAN_DATE, {"max_candidates": 0}) == []
    assert len(s.scan(SCAN_DATE, {})) == 10


def test_adapter_logs_one_diag_line_with_matched_and_saved_counts():
    import strategies._rule_screener_base as base_mod
    s = _TiedScreener(45)
    with _capture_logs(base_mod.logger) as records:
        s.scan(SCAN_DATE, {"max_candidates": None})
    lines = [r.getMessage() for r in records if r.getMessage().startswith("[스크리너]")]
    assert lines == ["[스크리너] fake_tied scan_date=2026-09-22 유니버스 45 · 평가 45 · 룰 통과 39 · 저장 39"]


# ---------------------------------------------------------------------------
# (b) run_once(None) — 전부 저장 · null · 한도 20 해시 = 골든
# ---------------------------------------------------------------------------

def test_run_once_none_saves_every_match_and_cap20_hash_is_golden(monkeypatch):
    from runners import screener_snapshot_collector as ssc
    from strategies.book_pullback_ma20.screener import BookPullbackMa20ScreenerAdapter as Ma20
    from db.repositories.candidate import CandidateRepository

    codes = [f"{i:06d}" for i in range(1, 31)]
    monkeypatch.setattr(Ma20, "_load_universe", lambda self, d: [
        {"code": c, "name": c, "market_cap": 1_000_000_000_000, "trading_value": 2_000_000_000}
        for c in codes
    ])
    monkeypatch.setattr(Ma20, "_load_daily", lambda self, code, d: _frame(volume=int(code)))
    monkeypatch.setattr(Ma20, "match", lambda self, df, params: (float(df["volume"].iloc[-1]), "fake"))

    executed = []

    @contextmanager
    def _fake_connection(self):
        conn = MagicMock()
        conn.cursor.return_value.executemany.side_effect = lambda sql, rows: executed.append(list(rows))
        yield conn

    monkeypatch.setattr(CandidateRepository, "_get_connection", _fake_connection)
    db_manager = SimpleNamespace(candidate_repo=CandidateRepository())

    s_none = ssc.run_once(["book_pullback_ma20"], SCAN_DATE, None, dry_run=False, db_manager=db_manager)
    s_20 = ssc.run_once(["book_pullback_ma20"], SCAN_DATE, 20, dry_run=False, db_manager=db_manager)

    assert s_none[0]["ok"] is True and s_none[0]["count"] == 30
    rows_none = executed[0]
    assert [r[6] for r in rows_none] == list(range(1, 31))          # rank_in_snapshot 1..30
    assert json.loads(rows_none[0][3])["max_candidates"] is None
    assert '"max_candidates": null' in rows_none[0][3]

    assert s_20[0]["ok"] is True and s_20[0]["count"] == 20
    assert s_20[0]["params_hash"] == GOLDEN_MA20_HASH_MAX20
    assert s_none[0]["params_hash"] != GOLDEN_MA20_HASH_MAX20
    assert s_none[0]["params_hash"].startswith("292fc1ffbadd")      # 사전등록 §4-3 실측값
    assert [r[4] for r in executed[1]] == [r[4] for r in rows_none[:20]]


# ---------------------------------------------------------------------------
# (c) 훅 — 모듈 상수를 그대로 넘긴다
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_hook_passes_module_level_max_rows_through():
    from bot.liquidation_handler import LiquidationHandler

    bot = Mock()
    bot.config = None
    handler = LiquidationHandler(bot)
    captured = {}

    def _fake_run_once(strategies, scan_date, max_candidates, dry_run,
                       broker=None, db_manager=None, config=None):
        captured["max_candidates"] = max_candidates
        captured["scan_date"] = scan_date
        return []

    with patch("bot.liquidation_handler.SCREENER_SNAPSHOT_ENABLED", True), \
         patch("bot.liquidation_handler.SCREENER_SNAPSHOT_MAX_ROWS", 37), \
         patch("bot.liquidation_handler.now_kst", return_value=datetime(2026, 9, 28, 7, 40)), \
         patch("runners.screener_snapshot_collector.run_once", side_effect=_fake_run_once):
        await handler.run_screener_snapshot_hook()

    assert captured["max_candidates"] == 37
    assert captured["scan_date"] == date(2026, 9, 23)                # 사전등록 §1-3 (추석 9/24·25 휴장)


# ---------------------------------------------------------------------------
# (d) 소비자 불변 가드 — 21위 이하는 안 본다
# ---------------------------------------------------------------------------

_FIXTURE = json.loads(
    (Path(__file__).resolve().parent / "fixtures" / "kis_stock_basic_info_recorded.json").read_text(encoding="utf-8")
)
_HALTED_ROW = _FIXTURE["groups"]["거래정지_58"][0]
_NORMAL_ROW = _FIXTURE["groups"]["정상_신용가능"][0]


def test_consumer_reads_only_top20_when_11_of_top20_are_excluded(monkeypatch):
    import core.screener_snapshot_provider as provider_mod

    selector = CandidateSelector(config=TradingConfig(), broker=MagicMock())
    codes = [f"{i:06d}" for i in range(1, 31)]                        # 스냅샷 30행 = 순위 1..30
    top20 = codes[:20]
    excluded = set(codes[:11])                                        # 상위 20 중 11개 제외
    monkeypatch.setattr(provider_mod, "make_screener_snapshot_provider",
                        lambda strategy_name: (lambda name, day: list(codes)))

    rerank_inputs = []
    real_rerank = selector._apply_sector_news_rerank

    def _spy_rerank(strategy_name, cs, prev_day_str):
        rerank_inputs.append(list(cs))
        return real_rerank(strategy_name, cs, prev_day_str)

    monkeypatch.setattr(selector, "_apply_sector_news_rerank", _spy_rerank)

    queried = []

    def _lookup(code):
        queried.append(code)
        return dict(_HALTED_ROW if code in excluded else _NORMAL_ROW)

    monkeypatch.setattr(selector, "_get_stock_safety_info", _lookup)

    out = selector._fetch_candidates_for_strategy("test_strategy", 10)

    assert rerank_inputs == [top20]                                   # 재정렬 입력 = 1~20위
    assert queried == top20                                           # 안전정보 조회 20건 · 21위 이하 0건
    assert [c.code for c in out] == codes[11:20]                      # 안전 9건 — 21위로 채우지 않는다
    assert not set(queried) & set(codes[20:])
