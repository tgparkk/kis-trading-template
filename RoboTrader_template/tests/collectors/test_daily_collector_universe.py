# tests/collectors/test_daily_collector_universe.py
"""`daily_collector.load_universe` 유니버스 술어 회귀 가드.

🔴 무엇을 막는가 (2026-08-12 실측 결함 2건):

  ① 자기참조 — 유니버스를 `daily_prices` 자기 자신에서 읽으면, 일봉이 없는 종목은
     수집 대상에 못 들어가고 그래서 계속 일봉이 없다. 한 번 빠지면 스스로 복구되지
     않는다. 실측: FDR 상장목록 2,764 중 **185종목이 일봉 0행**.

  ② 정규식 `^[0-9]{6}$` — KRX 단축코드는 「숫자 5자리 + 영숫자 1자리」다.
     숫자 6자리만 받으면 신형우선주(`00088K` 등 10종)와 신형 코드(`0001A0` 등)가
     **구조적으로 영구 배제**된다. 실측: 그 10종의 마지막 일봉이 전부 `2024-02-29`
     (774행에서 정지, 2년 5개월 미수집).

⚠️ 이 함수는 `collectors/foreign_flow_collector.py` 도 import 한다 — 수집기 2개 공유.

🔑 대칭 단언 규칙: "신형우선주가 들어온다"만 단언하면 판별력이 없다(전부 통과시켜도
   참이 된다). "지수 의사행은 안 들어온다"를 같이 단언해야 술어가 검증된다.
"""
import os

import pytest

import collectors.daily_collector as dc
from collectors.daily_collector import load_universe


# --------------------------------------------------------------------------- #
# fake cursor — SQL 텍스트 단언 (DB 불필요)
# --------------------------------------------------------------------------- #
class _FakeCursor:
    def __init__(self, rows):
        self._rows = rows
        self.sql = None

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def execute(self, sql, params=None):
        self.sql = sql

    def fetchall(self):
        return self._rows


class _FakeConn:
    def __init__(self, rows=()):
        self.cur = _FakeCursor(list(rows))

    def cursor(self):
        return self.cur


def _captured_sql(rows=()):
    conn = _FakeConn(rows)
    load_universe(conn)
    return conn.cur.sql


def test_universe_sql_reads_listing_table_not_only_daily_prices():
    """자기참조 탈출 — 상장목록(stock_market)을 소스에 포함해야 한다."""
    sql = _captured_sql()
    assert "stock_market" in sql, (
        "유니버스가 daily_prices 자기 자신만 읽고 있다 — 일봉 없는 상장 종목이 "
        "영원히 수집되지 않는다(실측 185종목)"
    )


def test_universe_sql_keeps_daily_prices_as_source():
    """상장목록에서 빠진 종목(상폐 등, 실측 27종목)을 잃지 않도록 합집합이어야 한다."""
    sql = _captured_sql()
    assert "daily_prices" in sql
    assert "UNION" in sql.upper()


def test_universe_sql_uses_krx_shortcode_predicate():
    """술어는 「첫 글자 숫자 + 영숫자 6자리」.

    KRX 코드 체계가 두 번 넓어졌다. 술어도 그만큼 넓어야 한다:
      005930  보통주                    숫자 6자리
      00088K  신형우선주                끝자리가 영문
      0001A0  신형 상장코드(덕양에너젠)   **중간이 영문** ← [0-9]{5}[0-9A-Z] 로는 못 잡는다
    """
    sql = _captured_sql()
    assert "[0-9][0-9A-Z]{5}" in sql, (
        "KRX 단축코드 술어가 아니다 — 0001A0(덕양에너젠) 형태 54종목이 배제된다"
    )


def test_universe_sql_does_not_use_digits_only_predicate():
    """대칭 단언 — 옛 술어가 남아 있으면 안 된다(둘 다 있으면 좁은 쪽이 이긴다)."""
    sql = _captured_sql()
    assert "[0-9]{6}" not in sql, (
        "숫자 6자리 술어가 남아 있다 — 신형우선주 10종이 계속 배제된다"
    )
    assert "[0-9]{5}[0-9A-Z]" not in sql, (
        "숫자5+영숫자1 술어가 남아 있다 — 신형 상장코드 54종목이 계속 배제된다"
    )


def test_universe_returns_codes_from_rows():
    codes = load_universe(_FakeConn([("000020",), ("00088K",)]))
    assert codes == ["000020", "00088K"]


# --------------------------------------------------------------------------- #
# 실 DB 통합 — 읽기 전용
# --------------------------------------------------------------------------- #
_INDEX_PSEUDO_CODES = ("KOSPI", "KOSDAQ", "KS11", "KQ11")


@pytest.fixture(scope="module")
def live_universe():
    if os.getenv("SKIP_DB_TESTS"):
        pytest.skip("SKIP_DB_TESTS 설정됨")
    try:
        with dc.KisDbConnection.get_connection() as conn:
            return load_universe(conn)
    except Exception as e:  # noqa: BLE001 — DB 미가동 환경에서는 스킵
        pytest.skip(f"DB 연결 불가: {e}")


def test_live_universe_includes_new_style_preferred_shares(live_universe):
    """신형우선주 10종이 유니버스에 들어와야 한다 (2024-02-29 이후 미수집분)."""
    missing = [c for c in ("00088K", "37550L") if c not in live_universe]
    assert missing == [], f"신형우선주가 유니버스에서 빠졌다: {missing}"


def test_live_universe_includes_new_format_listing_codes(live_universe):
    """KRX 신형 상장코드(중간이 영문)도 실제 상장 종목이다.

    0001A0=덕양에너젠 · 0007C0=아크릴 · 0030R0=대신밸류리츠(KOSPI).
    FDR 상장목록에 이름과 함께 존재한다 — 배제하면 신규 상장을 통째로 놓친다.
    """
    missing = [c for c in ("0001A0", "0007C0", "0030R0") if c not in live_universe]
    assert missing == [], f"신형 상장코드가 유니버스에서 빠졌다: {missing}"


def test_live_universe_excludes_index_pseudo_rows(live_universe):
    """대칭 단언 — 지수 의사행은 종목이 아니므로 배제돼야 한다."""
    leaked = [c for c in _INDEX_PSEUDO_CODES if c in live_universe]
    assert leaked == [], f"지수 행이 종목 유니버스에 섞였다: {leaked}"


def test_live_universe_covers_listed_stocks_without_daily_rows(live_universe):
    """상장목록에 있는데 일봉이 0행인 종목도 대상에 들어와야 한다."""
    with dc.KisDbConnection.get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT m.stock_code FROM stock_market m "
                "WHERE m.stock_code ~ '^[0-9]{5}[0-9A-Z]$' "
                "AND NOT EXISTS (SELECT 1 FROM daily_prices d "
                "                WHERE d.stock_code = m.stock_code) "
                "ORDER BY 1 LIMIT 5"
            )
            orphans = [r[0] for r in cur.fetchall()]
    if not orphans:
        pytest.skip("일봉 0행인 상장 종목이 없다 — 이 회귀는 이미 해소됨")
    missing = [c for c in orphans if c not in live_universe]
    assert missing == [], f"상장목록에만 있는 종목이 수집 대상에서 빠졌다: {missing}"


def test_live_universe_is_sorted_and_unique(live_universe):
    assert live_universe == sorted(set(live_universe))
