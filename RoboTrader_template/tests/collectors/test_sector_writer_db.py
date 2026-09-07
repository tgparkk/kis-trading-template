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
# T13 recon 행(Task 9). 🔴 실 이력(2026-06~)과 겹칠 수 없는 1999 날짜 «한 줄»만 지운다.
TEST_RECON_DATE = "1999-01-04"


def _cleanup(c):
    try:
        with c.cursor() as cur:
            cur.execute("DELETE FROM stock_sector_map WHERE stock_code IN %s", (TEST_CODES,))
            cur.execute("DELETE FROM sector_daily_stats WHERE date=%s", (TEST_STATS_DATE,))
            # T12 합성 코드(Task 7). 실 데이터와 겹치지 않는 990/991/99 만 지운다.
            cur.execute("DELETE FROM ksic_code_name WHERE code IN ('990','991','99')")
            cur.execute("DELETE FROM collection_reconciliation "
                        "WHERE dataset='sector' AND trade_date=%s", (TEST_RECON_DATE,))
        c.commit()
    except Exception:
        c.rollback()
        raise


def _conn_fixture():
    """`conn` 픽스처의 본체 — 정리 계약을 «직접» 드라이브해서 재려고 이름을 준다.

    🔴 뒤 정리는 `finally` 다. `yield` 뒤 본문에 두면 제너레이터가 «재개되지 않고»
       닫히거나(throw/close) 하는 경로에서 정리가 통째로 건너뛰어져 실 kis_template 에
       합성 행(TEST9A~G · ksic 990/991 · 1999-01-04)이 남는다. 그러면 다음 EOD 의
       `rebuild_ksic_names` 가 코드 990 에 '합성A' 이름표를 «영구» 발급한다.
    """
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
    finally:
        try:
            _cleanup(c)
        except Exception as e:  # noqa: BLE001 — 정리 실패가 «테스트 실패»를 가리면 안 된다
            print("[test] conn 픽스처 뒤 정리 실패(수동 확인 필요): %s" % e)
        cm.__exit__(None, None, None)


conn = pytest.fixture(name="conn")(_conn_fixture)


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


def test_coverage_numerator_is_limited_to_u_market(conn):
    """§8-1 — 커버리지 분자·분모는 «U_market 소속 열린 줄»만 센다.

    🔴 U_all 에만 있는 상폐 23 종목이 분자에 섞이면 커버리지가 부풀어 98% 게이트를
       «거짓으로» 통과한다. stock_market 에 없는 코드로 열린 줄을 하나 만들어 두고
       분자·분모가 «둘 다» 안 움직이는지 본다.
    """
    from collectors import sector_collector as sc2
    with conn.cursor() as cur:
        cur.execute("SELECT count(*) FROM stock_market WHERE stock_code='TEST9C'")
        assert cur.fetchone()[0] == 0, "합성 코드가 실제 상장목록에 있다 - 다른 코드를 쓸 것"
        cur.execute("SELECT count(*) FROM stock_market WHERE " + sc2.SQL_STOCK_ONLY)
        den_before = int(cur.fetchone()[0])
        cur.execute(sc2._FACTS_COVERAGE_SQL)
        num_before = cur.fetchone()

    with conn.cursor() as cur:
        _insert_named(cur, "TEST9C", "2611", "합성")
    conn.commit()

    with conn.cursor() as cur:
        cur.execute("SELECT count(*) FROM stock_market WHERE " + sc2.SQL_STOCK_ONLY)
        den_after = int(cur.fetchone()[0])
        cur.execute(sc2._FACTS_COVERAGE_SQL)
        num_after = cur.fetchone()
    assert num_after == num_before, "U_market 밖 종목이 커버리지 «분자»에 들어갔다"
    assert den_after == den_before, "U_market 밖 종목이 커버리지 «분모»를 움직였다"


def test_upsert_reconciliation_updates_row_and_keeps_the_two_ratios_apart(conn):
    """T13 recon 행 — 실 스키마 왕복. 🔴 합성 `_facts()` 로 도는 T13 은 이 SQL 을 안 탄다.

    ① 두 번째 호출이 «갱신»이라야 한다(재실행이 행을 늘리면 PK 계약이 깨진 것).
    ② `coverage` 와 `value_match_rate` 는 «서로 다른 값»으로 넣고 «열별로» 읽는다 —
       `_UPSERT_RECON` 은 인자 순서와 컬럼 순서가 일부러 어긋나 있어(coverage 가 뒤)
       한 자리만 밀려도 두 값이 조용히 뒤바뀐다.
    """
    with conn.cursor() as cur:
        cur.execute("SELECT count(*) FROM collection_reconciliation "
                    "WHERE dataset='sector' AND trade_date=%s", (TEST_RECON_DATE,))
        assert cur.fetchone()[0] == 0, "픽스처 정리가 안 됐다"

    w.upsert_reconciliation(conn, TEST_RECON_DATE, real_rows=547, new_rows=3, overlap=5,
                            coverage=0.5001, value_match_rate=0.9002, verdict="WARN")
    w.upsert_reconciliation(conn, TEST_RECON_DATE, real_rows=548, new_rows=4, overlap=6,
                            coverage=0.5003, value_match_rate=0.9004, verdict="PASS")

    with conn.cursor() as cur:
        cur.execute("SELECT count(*) FROM collection_reconciliation "
                    "WHERE dataset='sector' AND trade_date=%s", (TEST_RECON_DATE,))
        assert cur.fetchone()[0] == 1, "두 번째 호출이 «새 행»을 만들었다(UPSERT 가 아니다)"
        cur.execute("SELECT real_rows, new_rows, overlap, coverage, value_match_rate, verdict "
                    "FROM collection_reconciliation WHERE dataset='sector' AND trade_date=%s",
                    (TEST_RECON_DATE,))
        rr, nr, ov, cov, vmr, verdict = cur.fetchone()
    assert (rr, nr, ov, verdict) == (548, 4, 6, "PASS"), "두 번째 값으로 «갱신»이 안 됐다"
    assert abs(cov - 0.5003) < 1e-9, "coverage 열에 다른 값이 들어갔다"
    assert abs(vmr - 0.9004) < 1e-9, "value_match_rate 열에 다른 값이 들어갔다(coverage 와 swap)"


# ── I1 — 픽스처 정리 계약(실 DB 불필요 · 접속·정리를 가짜로 바꿔 «호출 여부»만 본다) ──
class _FakeCursor:
    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def execute(self, *a, **kw):
        return None


class _FakeConn:
    def cursor(self):
        return _FakeCursor()


def test_conn_fixture_cleans_up_even_when_the_test_body_raises(monkeypatch):
    """🔴 I1 — 본문이 raise 해서 제너레이터가 «재개되지 않고» 닫혀도 정리는 돈다.

    `yield` 뒤 «본문»에 정리를 두면 이 경로에서 통째로 건너뛰어져 실 kis_template 에
    합성 행이 남고, 다음 EOD 의 `rebuild_ksic_names` 가 그 코드에 이름표를 영구 발급한다.
    정리는 `finally` 라야 한다.
    """
    calls = []
    fake = _FakeConn()

    class _FakeCM:
        def __enter__(self):
            return fake

        def __exit__(self, *a):
            calls.append("exit")
            return False

    monkeypatch.setattr(KisDbConnection, "get_connection", lambda: _FakeCM())
    monkeypatch.setattr(w, "ensure_tables", lambda c: calls.append("ensure"))
    monkeypatch.setitem(globals(), "_cleanup", lambda c: calls.append("cleanup"))

    gen = _conn_fixture()
    assert next(gen) is fake
    assert calls == ["ensure", "cleanup"], "앞 정리가 안 돌았다: %s" % calls

    with pytest.raises(RuntimeError):
        gen.throw(RuntimeError("테스트 본문 실패"))
    assert calls == ["ensure", "cleanup", "cleanup", "exit"], (
        "본문이 raise 했을 때 뒤 정리가 건너뛰어졌다(실 DB 에 합성 행이 남는다): %s" % calls)


def test_conn_fixture_cleanup_failure_does_not_mask_the_test_failure(monkeypatch):
    """🔴 I1 — 정리가 터져도 «원래» 예외가 올라간다(정리 예외가 실패를 갈아치우면 안 된다).
    연결 반납(`cm.__exit__`)도 그대로 돈다."""
    calls = []
    fake = _FakeConn()

    class _FakeCM:
        def __enter__(self):
            return fake

        def __exit__(self, *a):
            calls.append("exit")
            return False

    def _boom(c):
        calls.append("cleanup")
        if len(calls) > 1:          # 앞 정리는 통과 · 뒤 정리만 터뜨린다
            raise RuntimeError("정리 실패")

    monkeypatch.setattr(KisDbConnection, "get_connection", lambda: _FakeCM())
    monkeypatch.setattr(w, "ensure_tables", lambda c: None)
    monkeypatch.setitem(globals(), "_cleanup", _boom)

    gen = _conn_fixture()
    next(gen)
    with pytest.raises(RuntimeError) as e:
        gen.throw(RuntimeError("테스트 본문 실패"))
    assert "테스트 본문 실패" in str(e.value), "정리 예외가 본문 실패를 가렸다"
    assert calls[-1] == "exit", "정리가 터지면 연결이 반납되지 않는다: %s" % calls
