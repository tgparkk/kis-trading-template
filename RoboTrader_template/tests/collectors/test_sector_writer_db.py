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

TEST_CODES = ("TEST9A", "TEST9B", "TEST9C", "TEST90", "TEST9D", "TEST9F", "TEST9G")
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


def _insert_named(cur, code, ksic, name, ksic_source="dart"):
    cur.execute(
        "INSERT INTO stock_sector_map (stock_code, valid_from, valid_to, ksic_code, "
        "ksic_source, ksic3_name, source) VALUES (%s, %s, NULL, %s, %s, %s, 'eod')",
        (code, date(2021, 1, 4), ksic, ksic_source, name))


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


def test_upsert_stats_is_idempotent(conn):
    """T7-a — 같은 날 두 번 실행해도 행수·값이 그대로여야 한다."""
    rows = [{"date": TEST_STATS_DATE, "taxonomy": "ksic3", "sector_key": "261",
             "n_members": 3, "g_sectors": 2, "ret_median": 0.01, "ret_mean": 0.02,
             "up_count": 1, "pos_ratio": 0.67, "rank_median": 0, "pct_median": 100.0,
             "rank_up": 0, "pct_up": 100.0, "rank_pos": 0, "pct_pos": 100.0},
            {"date": TEST_STATS_DATE, "taxonomy": "ksic2", "sector_key": "26",
             "n_members": 3, "g_sectors": 1, "ret_median": 0.01, "ret_mean": 0.02,
             "up_count": 1, "pos_ratio": 0.67, "rank_median": 0, "pct_median": None,
             "rank_up": 0, "pct_up": None, "rank_pos": 0, "pct_pos": None}]
    assert w.upsert_stats(conn, [dict(r) for r in rows]) == 2
    w.upsert_stats(conn, [dict(r) for r in rows])
    with conn.cursor() as cur:
        cur.execute("SELECT count(*), sum(n_members) FROM sector_daily_stats WHERE date=%s",
                    (TEST_STATS_DATE,))
        assert cur.fetchone() == (2, 6), "재실행이 멱등하지 않다"
    assert w.delete_stats(conn, TEST_STATS_DATE, TEST_STATS_DATE) == 2


def _stats_row(taxonomy, key, n_members):
    return {"date": TEST_STATS_DATE, "taxonomy": taxonomy, "sector_key": key,
            "n_members": n_members, "g_sectors": 2, "ret_median": 0.01, "ret_mean": 0.02,
            "up_count": 1, "pos_ratio": 0.5, "rank_median": 0, "pct_median": 100.0,
            "rank_up": 0, "pct_up": 100.0, "rank_pos": 0, "pct_pos": 100.0}


def _read_stats(conn, taxonomy):
    with conn.cursor() as cur:
        cur.execute("SELECT sector_key, n_members FROM sector_daily_stats "
                    "WHERE date=%s AND taxonomy=%s ORDER BY 1", (TEST_STATS_DATE, taxonomy))
        return cur.fetchall()


def test_upsert_overwrites_the_value_not_just_the_row(conn):
    """🔴 T7-a ① — 충돌 시 DO **UPDATE** 여야 한다. 행수만 세면 DO NOTHING 과 구별되지 않아
    「재계산했는데 옛 값이 남는」 사고를 못 잡는다."""
    assert w.upsert_stats(conn, [_stats_row("ksic3", "261", 3)]) == 1
    assert _read_stats(conn, "ksic3") == [("261", 3)]
    w.upsert_stats(conn, [_stats_row("ksic3", "261", 9)])
    assert _read_stats(conn, "ksic3") == [("261", 9)], "값이 안 바뀌었다(DO NOTHING 인가)"


def test_delete_stale_stats_removes_ghost_rows_only(conn):
    """🔴 T7-a ② — 두 번째 계산에서 사라진 섹터 키의 행은 없어져야 한다(유령 행 제거).
    같은 날 «다른 taxonomy» 는 건드리지 않는다."""
    w.upsert_stats(conn, [_stats_row("ksic3", "261", 3), _stats_row("ksic3", "262", 4),
                          _stats_row("ksic2", "26", 7)])
    # 2회차 계산: ksic3 키 집합이 {261} 로 줄었다
    w.upsert_stats(conn, [_stats_row("ksic3", "261", 5)])
    assert w.delete_stale_stats(conn, TEST_STATS_DATE, "ksic3", {"261"}) == 1
    assert _read_stats(conn, "ksic3") == [("261", 5)], "유령 행이 남았거나 산 행을 지웠다"
    assert _read_stats(conn, "ksic2") == [("26", 7)], "다른 taxonomy 를 건드렸다"
    # 같은 키 집합으로 다시 부르면 0건(멱등)
    assert w.delete_stale_stats(conn, TEST_STATS_DATE, "ksic3", {"261"}) == 0


def test_delete_stale_stats_with_empty_keep_set_is_valid_sql(conn):
    """🔴 빈 키 집합은 «그 taxonomy 전부 삭제»다 — 빈 배열이 SQL 문법 오류가 나지 않는지
    실 DB 로 확인한다(호출자가 스킵 경로에서 부르면 안 되는 이유이기도 하다)."""
    w.upsert_stats(conn, [_stats_row("ksic2", "26", 7)])
    assert w.delete_stale_stats(conn, TEST_STATS_DATE, "ksic2", set()) == 1
    assert _read_stats(conn, "ksic2") == []


def test_rebuild_ksic_names_picks_mode_and_warns_on_low_share(conn):
    """T12 — ksic_code NULL/길이<3/ksic3_name NULL 은 «완전히» 제외(분자·분모 모두 안 셈) ·
    최빈 이름 · 점유율 < 0.8 은 WARNING 목록 · 부모복사 우선주(ksic_source='parent:...')도
    «종목»으로 센다(분자·분모 +1).

    ⚠️ 라이브 표를 쓰므로 합성 코드는 실 데이터와 겹치면 안 된다 — 겹치면 skip 한다
       (부트스트랩 후 재실행 대비)."""
    with conn.cursor() as cur:
        cur.execute("SELECT count(*) FROM stock_sector_map WHERE valid_to IS NULL "
                    "AND left(ksic_code,3) IN ('990','991')")
        if cur.fetchone()[0]:
            pytest.skip("실 데이터에 990/991 코드가 있어 합성 테스트를 격리할 수 없다")
    with conn.cursor() as cur:
        cur.execute("DELETE FROM ksic_code_name WHERE code IN ('990','991','99')")
        # 990: '합성A'(2) vs '합성B'(1) → 최빈 '합성A'
        _insert_named(cur, "TEST9A", "9901", "합성A")
        _insert_named(cur, "TEST9B", "99011", "합성A")
        _insert_named(cur, "TEST9C", "9902", "합성B")
        # 길이 2 코드는 3자리 집계에서 빠진다
        _insert_named(cur, "TEST90", "99", "짧은코드")
        # Fix#2 ① ksic_code NULL(이름은 있음) — 완전히 제외(어느 코드의 분자·분모에도 안 셈)
        _insert_named(cur, "TEST9D", None, "합성A")
        # Fix#2 ② ksic_code 는 990 대(9905) 지만 ksic3_name NULL — 990 «분모»에서도 빠져야 한다
        _insert_named(cur, "TEST9F", "9905", None)
        # Fix#2 ③ 부모복사 우선주(ksic_source='parent:...')도 «종목»으로 센다
        #          → 합성A 분자 2→3, 990 분모 3→4 (share 2/3 → 3/4 = 0.75, 여전히 <0.8)
        _insert_named(cur, "TEST9G", "9903", "합성A", ksic_source="parent:001040")
    conn.commit()
    out = w.rebuild_ksic_names(conn)
    with conn.cursor() as cur:
        cur.execute("SELECT name, n_stocks, share FROM ksic_code_name WHERE code='990'")
        name, n, share = cur.fetchone()
    assert name == "합성A" and n == 3, "부모복사 행(TEST9G)이 종목수에 안 셌다"
    assert abs(share - 3.0 / 4.0) < 1e-9, \
        "분모가 0.75(=3/4) 가 아니다 — TEST9D/TEST9F 가 새어들었거나 부모복사가 안 셌다"
    assert any(c == "990" for c, _n, _s in out["low_share"]), "점유율 0.75 가 경고 목록에 없다"
    with conn.cursor() as cur:
        cur.execute("SELECT count(*) FROM ksic_code_name WHERE code='99'")
        assert cur.fetchone()[0] == 0, "길이 2 코드가 3자리 이름표에 들어왔다"
