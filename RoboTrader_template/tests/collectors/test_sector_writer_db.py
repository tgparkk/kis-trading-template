"""섹터 스키마 DB 테스트 (T11 · T12 · T7-a).

🔴 실 DB(kis_template)가 있어야 한다. 없으면 전부 skip — 워크트리·CI 에서 스위트를
   깨뜨리지 않는다(재무 test_financial_writer_db.py 규약 + 접속 프로브 추가).
🔴 `@pytest.mark.db` — 기준선 실패 집합 비교에서 제외한다(스펙 T9 규정 승계).
"""
import os
import sys
from datetime import date

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from db.kis_db_connection import KisDbConnection  # noqa: E402
from collectors import sector_writer as w  # noqa: E402


# 🔴 접속 프로브를 «모듈 최상위»에 두지 않는다 — 수집 단계에 DB 를 두드리게 되고
#    `-m "not db"` 로도 못 막는다. 픽스처 안에서만 붙고, 실패하면 skip 한다.
pytestmark = [pytest.mark.db]

TEST_CODES = ("TEST9A", "TEST9B", "TEST9C", "TEST90")
TEST_STATS_DATE = date(1999, 1, 4)


def _cleanup(c):
    try:
        with c.cursor() as cur:
            cur.execute("DELETE FROM stock_sector_map WHERE stock_code IN %s", (TEST_CODES,))
            cur.execute("DELETE FROM sector_daily_stats WHERE date=%s", (TEST_STATS_DATE,))
            # T12 합성 코드(Task 7). 실 데이터와 겹치지 않는 990/991/99 만 지운다.
            cur.execute("DELETE FROM ksic_code_name WHERE code IN ('990','991','99')")
        c.commit()
    except Exception:
        c.rollback()
        raise


@pytest.fixture
def conn():
    try:
        cm = KisDbConnection.get_connection()
        c = cm.__enter__()
        with c.cursor() as cur:
            cur.execute("SELECT 1")
    except Exception as e:  # noqa: BLE001 — 접속 실패는 skip 사유지 테스트 실패가 아니다
        pytest.skip("kis_template DB 접속 불가: %s" % e)
    try:
        w.ensure_tables(c)
        _cleanup(c)
        yield c
        _cleanup(c)
    finally:
        cm.__exit__(None, None, None)


def test_ensure_tables_is_idempotent(conn):
    """두 번 돌려도 안 죽어야 한다 — EOD 가 매일 부른다."""
    w.ensure_tables(conn)
    w.ensure_tables(conn)
    with conn.cursor() as cur:
        for t in ("stock_sector_map", "sector_daily_stats",
                  "sector_ksic_nodata", "ksic_code_name"):
            cur.execute("SELECT to_regclass(%s)", ("public." + t,))
            assert cur.fetchone()[0] is not None, t + " 이 안 만들어졌다"


def test_stats_check_rejects_key_length_mismatch(conn):
    """taxonomy 와 sector_key 자릿수가 어긋나면 «저장이 안 돼야» 한다.
    4자리 KSIC 가 ksic5 키로 들어오는 경로를 스키마가 막는다 — T5 와 한 쌍."""
    import psycopg2
    with pytest.raises(psycopg2.errors.CheckViolation):
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO sector_daily_stats (date, taxonomy, sector_key, n_members, g_sectors) "
                "VALUES (%s, 'ksic5', '2611', 1, 1)", (TEST_STATS_DATE,))
    conn.rollback()


def test_map_check_rejects_reversed_validity(conn):
    """valid_to < valid_from 인 역전 줄은 스키마가 막는다(§3.1 과거 날짜 재실행 사고 방지)."""
    import psycopg2
    with pytest.raises(psycopg2.errors.CheckViolation):
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO stock_sector_map (stock_code, valid_from, valid_to, source) "
                "VALUES ('TEST9A', %s, %s, 'eod')", (date(2026, 2, 10), date(2026, 2, 9)))
    conn.rollback()


def _insert_row(cur, code, vf, vt, ksic, source="eod"):
    cur.execute(
        "INSERT INTO stock_sector_map (stock_code, valid_from, valid_to, ksic_code, "
        "ksic_source, ksic3_name, source) VALUES (%s,%s,%s,%s,'dart','이름',%s)",
        (code, vf, vt, ksic, source))


def test_fn_sector_map_as_of_roundtrip_and_boundaries(conn):
    """`SELECT * FROM fn_sector_map_as_of(d)` 왕복 + 경계 3개.
    valid_from 당일 포함 · valid_to 당일 포함 · 그 다음날 제외."""
    with conn.cursor() as cur:
        _insert_row(cur, "TEST9A", date(2026, 1, 10), date(2026, 2, 9), "2611")
        _insert_row(cur, "TEST9A", date(2026, 2, 10), None, "2612")
    conn.commit()

    def _codes(d):
        with conn.cursor() as cur:
            cur.execute("SELECT * FROM fn_sector_map_as_of(%s)", (d,))
            return {r[0]: r[1] for r in cur.fetchall() if r[0] == "TEST9A"}

    assert _codes(date(2026, 1, 9)) == {}, "valid_from 이전이 보인다"
    assert _codes(date(2026, 1, 10)) == {"TEST9A": "2611"}, "valid_from 당일이 안 보인다"
    assert _codes(date(2026, 2, 9)) == {"TEST9A": "2611"}, "valid_to 당일이 안 보인다"
    assert _codes(date(2026, 2, 10)) == {"TEST9A": "2612"}
    assert _codes(date(2030, 1, 1)) == {"TEST9A": "2612"}, "열린 줄이 미래에 안 보인다"

    with conn.cursor() as cur:
        cur.execute("SELECT * FROM fn_sector_map_as_of(%s)", (date(2026, 2, 10),))
        assert [d[0] for d in cur.description] == [
            "stock_code", "ksic_code", "ksic_source", "ksic3_name", "valid_from", "source"], \
            "소비자 계약(§3.6)의 컬럼 순서가 바뀌었다"

    rows = {r[0]: r[1] for r in w.map_as_of(conn, date(2026, 2, 10))}
    assert rows.get("TEST9A") == "2612", "writer API 왕복이 함수와 다르다"


def test_no_duplicate_stock_rows_on_sample_dates(conn):
    """🔴 겹치는 유효기간 = n_members 이중 계산. 표본 날짜 10개에서 종목당 ≤ 1행."""
    with conn.cursor() as cur:
        _insert_row(cur, "TEST9B", date(2021, 1, 4), date(2026, 3, 31), "2611")
        _insert_row(cur, "TEST9B", date(2026, 4, 1), None, "2612")
    conn.commit()
    sample = [date(2021, 1, 4), date(2022, 6, 30), date(2023, 12, 29), date(2024, 3, 12),
              date(2025, 1, 2), date(2026, 3, 31), date(2026, 4, 1), date(2026, 8, 5),
              date(2026, 9, 4), date(2026, 9, 30)]
    for d in sample:
        with conn.cursor() as cur:
            cur.execute("SELECT stock_code, count(*) FROM fn_sector_map_as_of(%s) "
                        "GROUP BY 1 HAVING count(*) > 1", (d,))
            dup = cur.fetchall()
        assert dup == [], "%s 에 중복 유효기간이 있다: %s" % (d, dup[:5])
