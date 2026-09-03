# -*- coding: utf-8 -*-
"""(E′) 과거 행 INSERT-only — `W1` 장전 일봉 쓰기 가드.

사전등록: docs/prereg_2026-09-03_write_path_rawprice_upsert.md (D-1)

고정하는 계약 세 가지 (§3-(E′) 정의):
  1. **과거 행이 이미 있으면 건드리지 않는다** — 과거 행에 쓰는 문장은
     `ON CONFLICT ... DO NOTHING` 이고 `DO UPDATE` 가 «없다».
  2. **과거 행이 없으면 넣는다** — 같은 문장이 `INSERT INTO daily_prices` 다
     (빈 칸 채우기는 (E′) 가 잃지 않는 기능 · §3-(E′) 「잃지 않는 것」 ②).
  3. **당일(KST) 행은 기존대로 UPSERT** — 얼리면 최신 봉이 안 들어온다(§4-3 J2 실패행).

🔴 이 테스트는 DB 에 붙지 않는다. 커서를 가로채 「어느 행이 어느 문장으로 갔는가」를
   검사한다 — 판정 대상이 «쓰기 의미»이지 DB 상태가 아니기 때문이다.
🔴 §4-4-1 대칭: 가드가 «켜지지 않은» 경로(W3 regime 지수 등)는 의미가 안 바뀌어야 한다.
"""
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from unittest.mock import Mock, patch

import pandas as pd
import pytest

from db.repositories.price import (
    DAILY_INSERT_ONLY_SQL,
    DAILY_UPSERT_SQL,
    PriceRepository,
)

KST = timezone(timedelta(hours=9))
_NOW = datetime(2026, 9, 3, 7, 40, 11, tzinfo=KST)
_TODAY = "2026-09-03"


class _FakeCursor:
    """executemany 호출을 (sql, rows) 로 기록만 하는 커서."""

    def __init__(self):
        self.calls = []
        self.rowcount = 0

    def executemany(self, sql, rows):
        self.calls.append((sql, list(rows)))
        self.rowcount = len(rows)

    def execute(self, sql, params=None):  # pragma: no cover - 이 경로는 안 쓴다
        self.calls.append((sql, [params]))


def _repo_with(cursor):
    repo = PriceRepository.__new__(PriceRepository)
    repo.logger = Mock()

    conn = Mock()
    conn.cursor = Mock(return_value=cursor)

    @contextmanager
    def _conn():
        yield conn

    repo._get_connection = _conn
    return repo


def _df(dates):
    return pd.DataFrame({
        "date": list(dates),
        "open": [100.0] * len(dates),
        "high": [110.0] * len(dates),
        "low": [90.0] * len(dates),
        "close": [105.0] * len(dates),
        "volume": [1000] * len(dates),
    })


def _rows_of(calls, sql):
    for got_sql, rows in calls:
        if got_sql == sql:
            return rows
    return None


# ---------------------------------------------------------------------------
# SQL 계약 — 두 문장의 «의미»를 문자열로 고정한다
# ---------------------------------------------------------------------------

def test_insert_only_sql_never_updates_an_existing_row():
    """과거 행 문장에 DO UPDATE 가 섞이면 (E′) 는 이름만 남는다."""
    upper = DAILY_INSERT_ONLY_SQL.upper()
    assert "INSERT INTO DAILY_PRICES" in upper
    assert "ON CONFLICT (STOCK_CODE, DATE) DO NOTHING" in upper
    assert "DO UPDATE" not in upper


def test_upsert_sql_still_overwrites_ohlcv():
    upper = DAILY_UPSERT_SQL.upper()
    assert "ON CONFLICT (STOCK_CODE, DATE) DO UPDATE" in upper
    for col in ("OPEN", "HIGH", "LOW", "CLOSE", "VOLUME"):
        assert f"{col} = EXCLUDED.{col}" in upper


def test_both_statements_write_the_same_columns():
    """컬럼 목록이 갈리면 두 경로가 «다른 행»을 쓰게 된다."""
    head = "INSERT INTO daily_prices\n                    (stock_code, date, open, high, low, close, volume)"
    assert head in DAILY_INSERT_ONLY_SQL
    assert head in DAILY_UPSERT_SQL


# ---------------------------------------------------------------------------
# 라우팅 — 어느 행이 어느 문장으로 가는가
# ---------------------------------------------------------------------------

@patch("db.repositories.price.now_kst", return_value=_NOW)
def test_past_rows_go_to_insert_only_and_today_row_is_upserted(_now):
    cur = _FakeCursor()
    repo = _repo_with(cur)

    df = _df(["2026-08-31", "2026-09-01", "2026-09-02", _TODAY])
    assert repo.save_daily_prices_batch("001210", df, past_rows_insert_only=True) is True

    past = _rows_of(cur.calls, DAILY_INSERT_ONLY_SQL)
    today = _rows_of(cur.calls, DAILY_UPSERT_SQL)

    assert [r[1] for r in past] == ["2026-08-31", "2026-09-01", "2026-09-02"]
    assert [r[1] for r in today] == [_TODAY]
    # 어떤 과거 행도 UPSERT 문장으로 새지 않았다(= 원복 채널이 닫혔다).
    assert all(r[1] >= _TODAY for r in today)


@patch("db.repositories.price.now_kst", return_value=_NOW)
def test_absent_past_row_is_still_inserted(_now):
    """과거 행이 «없을» 때 넣는 경로는 살아 있다 — 빈 칸 채우기 보존(J5)."""
    cur = _FakeCursor()
    repo = _repo_with(cur)

    df = _df(["2026-04-06", "2026-04-07"])
    assert repo.save_daily_prices_batch("900300", df, past_rows_insert_only=True) is True

    past = _rows_of(cur.calls, DAILY_INSERT_ONLY_SQL)
    assert [r[1] for r in past] == ["2026-04-06", "2026-04-07"]
    assert past[0][0] == "900300"
    # INSERT 문장이므로 DB 에 없는 날짜는 그대로 들어간다.
    assert DAILY_INSERT_ONLY_SQL.strip().startswith("INSERT INTO daily_prices")
    # UPSERT 문장은 아예 실행되지 않았다(당일 행이 없으므로).
    assert _rows_of(cur.calls, DAILY_UPSERT_SQL) is None


@patch("db.repositories.price.now_kst", return_value=_NOW)
def test_today_only_batch_keeps_upsert_semantics(_now):
    """장중 재선정 시 당일 «부분봉»은 갱신돼야 한다(§3-(E′) 실패 모드)."""
    cur = _FakeCursor()
    repo = _repo_with(cur)

    assert repo.save_daily_prices_batch("005930", _df([_TODAY]),
                                        past_rows_insert_only=True) is True
    assert _rows_of(cur.calls, DAILY_INSERT_ONLY_SQL) is None
    assert [r[1] for r in _rows_of(cur.calls, DAILY_UPSERT_SQL)] == [_TODAY]


@patch("db.repositories.price.now_kst", return_value=_NOW)
def test_kis_yyyymmdd_dates_are_normalized_before_the_boundary_compare(_now):
    """KIS 'YYYYMMDD' 도 같은 경계로 갈린다 — 타입 함정(§4-3 첫 행) 회귀 고정."""
    cur = _FakeCursor()
    repo = _repo_with(cur)

    df = pd.DataFrame({
        "stck_bsop_date": ["20260902", "20260903"],
        "stck_oprc": [100, 100], "stck_hgpr": [110, 110],
        "stck_lwpr": [90, 90], "stck_clpr": [105, 105], "acml_vol": [10, 10],
    })
    assert repo.save_daily_prices_batch("950220", df, past_rows_insert_only=True) is True

    assert [r[1] for r in _rows_of(cur.calls, DAILY_INSERT_ONLY_SQL)] == ["2026-09-02"]
    assert [r[1] for r in _rows_of(cur.calls, DAILY_UPSERT_SQL)] == ["2026-09-03"]


@patch("db.repositories.price.now_kst", return_value=_NOW)
def test_future_dated_row_is_not_frozen(_now):
    """미래 날짜 행(있어선 안 되지만)이 INSERT-only 로 얼면 조용히 못 고친다."""
    cur = _FakeCursor()
    repo = _repo_with(cur)

    repo.save_daily_prices_batch("000660", _df(["2026-09-04"]), past_rows_insert_only=True)
    assert [r[1] for r in _rows_of(cur.calls, DAILY_UPSERT_SQL)] == ["2026-09-04"]


# ---------------------------------------------------------------------------
# 대칭 — 가드가 «안 켜진» 경로는 그대로다
# ---------------------------------------------------------------------------

@patch("db.repositories.price.now_kst", return_value=_NOW)
def test_default_is_unchanged_upsert_for_every_other_caller(_now):
    """기본값이 True 로 바뀌면 W3(regime 지수)·보정 도구가 조용히 얼어붙는다."""
    cur = _FakeCursor()
    repo = _repo_with(cur)

    df = _df(["2026-08-31", _TODAY])
    assert repo.save_daily_prices_batch("KOSPI", df) is True

    assert len(cur.calls) == 1
    sql, rows = cur.calls[0]
    assert sql == DAILY_UPSERT_SQL
    assert [r[1] for r in rows] == ["2026-08-31", _TODAY]


def test_empty_frame_writes_nothing():
    cur = _FakeCursor()
    repo = _repo_with(cur)
    assert repo.save_daily_prices_batch("001210", pd.DataFrame(),
                                        past_rows_insert_only=True) is True
    assert cur.calls == []


# ---------------------------------------------------------------------------
# 배선 — W1 만 가드를 켠다
# ---------------------------------------------------------------------------

def test_w1_flag_is_on_by_default_in_constants():
    from config import constants
    assert constants.W1_PAST_ROWS_INSERT_ONLY is True


@pytest.mark.asyncio
async def test_w1_write_path_passes_the_flag():
    """`_save_daily_to_db` = W1 의 쓰기 경로. 여기서 안 넘기면 가드는 죽은 코드다."""
    from core.intraday import data_collector as dc

    collector = dc.IntradayDataCollector.__new__(dc.IntradayDataCollector)
    collector.logger = Mock()

    repo = Mock()
    repo.save_daily_prices_batch = Mock(return_value=True)

    with patch("db.repositories.price.PriceRepository", return_value=repo):
        assert await collector._save_daily_to_db("001210", _df([_TODAY])) is True

    kwargs = repo.save_daily_prices_batch.call_args.kwargs
    assert kwargs["past_rows_insert_only"] is dc.W1_PAST_ROWS_INSERT_ONLY
    assert kwargs["past_rows_insert_only"] is True


@pytest.mark.asyncio
async def test_w3_regime_index_refresh_does_not_enable_the_guard():
    """지수엔 기업행위가 없다 — W3 는 최근 10일 정정을 계속 받아야 한다(§0-2 범위 밖)."""
    from core.regime import index_refresh

    repo = Mock()
    repo.save_daily_prices_batch = Mock(return_value=True)

    fake_fdr = Mock()
    fake_fdr.DataReader = Mock(return_value=pd.DataFrame({
        "Open": [1.0], "High": [1.0], "Low": [1.0], "Close": [1.0], "Volume": [1],
    }, index=pd.to_datetime(["2026-09-02"])))

    index_refresh.refresh_regime_indices(repo, fdr=fake_fdr)

    for call in repo.save_daily_prices_batch.call_args_list:
        assert "past_rows_insert_only" not in call.kwargs
        assert len(call.args) == 2
