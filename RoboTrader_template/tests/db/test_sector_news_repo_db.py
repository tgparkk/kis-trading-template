"""SectorNewsRepository 실 DB 왕복. DB 없으면 skip. 쓰기는 센티널(1999-01-04, _test_sector_news)만."""
from datetime import date, datetime

import pytest

pytestmark = pytest.mark.db

TD = date(1999, 1, 4)
STRAT = "_test_sector_news"


@pytest.fixture(scope="module")
def repo():
    try:
        from db.connection import DatabaseConnection
        DatabaseConnection.initialize()
        with DatabaseConnection.get_connection() as conn:
            cur = conn.cursor()
            cur.execute("SELECT 1")
            cur.close()
    except Exception as e:
        pytest.skip(f"실 DB 없음: {type(e).__name__}: {e}")
    from db.repositories.sector_news import SectorNewsRepository
    r = SectorNewsRepository()
    r.ensure_table()
    return r


@pytest.fixture
def clean(repo):
    yield
    from db.connection import DatabaseConnection
    with DatabaseConnection.get_connection() as conn:
        cur = conn.cursor()
        cur.execute("DELETE FROM sector_news_rerank_log WHERE trade_date = %s AND strategy = %s", (TD, STRAT))
        conn.commit()
        cur.close()


def _row(**kw):
    base = dict(trade_date=TD, strategy=STRAT, stock_code="000001", sector_key="261", sector_score=0.5,
                orig_rank=5, new_rank=2, applied=False, mode="shadow", reason="ok",
                score_asof=datetime(1999, 1, 4, 8, 50))
    base.update(kw)
    return base


def test_ensure_table_idempotent(repo):
    repo.ensure_table()
    repo.ensure_table()


def test_get_scores_empty_day(repo):
    try:
        scores, asof = repo.get_scores(date(1998, 1, 1))
    except Exception as e:
        assert type(e).__name__ == "UndefinedTable"     # NewsQuant 측 미배포 — 호출자가 table_missing 으로 분류
        return
    assert scores == {} and asof is None


def test_get_sector_map_roundtrip(repo):
    try:
        m = repo.get_sector_map("2026-09-04", ["005930", "000660"])
    except Exception as e:
        assert type(e).__name__ == "UndefinedFunction"  # 스펙 A 미배포
        return
    assert isinstance(m, dict) and all(len(k) == 6 and len(v) == 3 for k, v in m.items())
    assert repo.get_sector_map("2026-09-04", []) == {}


def test_save_rerank_log_upsert(repo, clean):
    assert repo.save_rerank_log([_row()]) == 1
    assert repo.save_rerank_log([_row(new_rank=3, reason="stale", sector_score=None)]) == 1
    from db.connection import DatabaseConnection
    with DatabaseConnection.get_connection() as conn:
        cur = conn.cursor()
        cur.execute("SELECT new_rank, reason, sector_score, applied FROM sector_news_rerank_log "
                    "WHERE trade_date = %s AND strategy = %s", (TD, STRAT))
        rows = cur.fetchall()
        cur.close()
    assert rows == [(3, "stale", None, False)]
    assert repo.save_rerank_log([]) == 0
