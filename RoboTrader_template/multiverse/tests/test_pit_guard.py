"""Phase 1 PIT 가드 — pit_reader가 미래 데이터 노출을 모두 차단."""
import sys
from pathlib import Path

import pytest
import psycopg2
from datetime import date, time, datetime
from RoboTrader_template.multiverse.data import pit_reader

_TEMPLATE_ROOT = Path(__file__).resolve().parents[2]
if str(_TEMPLATE_ROOT) not in sys.path:
    sys.path.insert(0, str(_TEMPLATE_ROOT))

from config.constants import resolve_minute_source_db  # noqa: E402

# 분봉 가드 기준 종목/일자 — kis_template.minute_candles 에 실데이터가 있는 구간.
_MINUTE_SYMBOL = "005930"
_MINUTE_DATE = date(2026, 4, 1)


def _minute_conn():
    """분봉 소스 직결 — read_minute 이 거른 것을 원본과 대조하기 위한 검증용 연결.

    read_minute 과 동일하게 resolve_minute_source_db() 를 따른다.
    """
    import os
    return psycopg2.connect(
        host=os.getenv("TIMESCALE_HOST", "127.0.0.1"),
        port=int(os.getenv("TIMESCALE_PORT", "5433")),
        user=os.getenv("TIMESCALE_USER", "robotrader"),
        password=os.getenv("TIMESCALE_PASSWORD", "1234"),
        database=resolve_minute_source_db(),
    )


def test_read_daily_requires_as_of_date():
    """as_of_date 미입력 시 TypeError raise."""
    with pytest.raises(TypeError):
        pit_reader.read_daily(symbol="005930")  # as_of_date 누락


def test_read_daily_excludes_as_of_date_close():
    """as_of_date 당일 종가는 절대 반환 금지."""
    df = pit_reader.read_daily(symbol="005930", as_of_date=date(2026, 4, 1))
    if not df.empty:
        assert df["date"].max() < date(2026, 4, 1)


def test_read_minute_respects_as_of_time():
    """as_of_time 직전 분봉까지.

    ★ 비어 있으면 통과하던 vacuous 가드였다 — 실데이터가 실제로 돌아오는지
      먼저 못박고(assert not df.empty) 그 위에서 경계를 검증한다.
    """
    df = pit_reader.read_minute(
        symbol=_MINUTE_SYMBOL, as_of_date=_MINUTE_DATE, as_of_time=time(9, 1)
    )
    assert not df.empty, (
        f"{_MINUTE_SYMBOL} {_MINUTE_DATE} 분봉이 비었다 — 가드가 vacuous 하게 통과 중"
    )
    latest = df.iloc[-1]
    # 09:00 분봉까지 OK, 09:01은 금지
    assert (latest["date"] < _MINUTE_DATE) or (
        latest["date"] == _MINUTE_DATE and latest["time"] < time(9, 1)
    )


def test_read_minute_excludes_bar_stamped_at_as_of_time():
    """★ look-ahead 가드 비-vacuous 증명 — 경계 봉이 원본에 **실재하는데도** 배제되는가.

    minute_candles 분봉은 open-stamp(봉 라벨 = 시작 분)다. 09:01 봉은
    [09:01, 09:02) 구간이라 09:01:00 시점엔 아직 시작조차 안 했다 =
    그 시점에 관측 불가능 → 배제가 정답(경계 배제, 엄격 부등호 <).

    이 테스트는 "원본에 09:01 봉이 있다"를 **전제로 못박고**(assert) 시작하므로,
    필터가 <= 로 느슨해지면 반드시 실패한다 = 미래 봉 주입 검출 능력 증명.
    """
    as_of = time(9, 1)
    boundary_dt = datetime.combine(_MINUTE_DATE, as_of)

    # 전제: 경계 봉(09:01)이 원본에 실재해야 이 가드가 의미를 갖는다.
    conn = _minute_conn()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT count(*) FROM minute_candles "
                "WHERE stock_code = %s AND datetime = %s",
                (_MINUTE_SYMBOL, boundary_dt),
            )
            boundary_exists = cur.fetchone()[0]
    finally:
        conn.close()

    assert boundary_exists > 0, (
        f"전제 불성립: 원본에 {boundary_dt} 봉이 없다 — 이 가드는 아무것도 증명 못 함"
    )

    df = pit_reader.read_minute(
        symbol=_MINUTE_SYMBOL, as_of_date=_MINUTE_DATE, as_of_time=as_of
    )
    assert not df.empty

    # 실재하는 09:01 봉이 결과에 없어야 한다.
    same_day = df[df["date"] == _MINUTE_DATE]
    assert not (same_day["time"] == as_of).any(), (
        "as_of_time 과 같은 분의 봉이 새어나왔다 = look-ahead"
    )
    # 그리고 바로 직전 봉(09:00)은 관측 가능하므로 포함돼야 한다(과잉 배제 방지).
    assert (same_day["time"] == time(9, 0)).any(), (
        "09:00 봉까지 배제됐다 — 경계가 한 칸 과하게 잘렸다"
    )


def test_read_minute_dedupes_bars_sharing_timestamp():
    """같은 분(datetime)에 중복 봉이 있어도 분당 1봉만 반환.

    minute_candles PK 는 (stock_code, trade_date, idx) 인데 trade_date 는 **수집일**
    이라 같은 봉이 서로 다른 trade_date 파티션에 중복 적재된다(실측 8,806 키).
    dedupe 없이 읽으면 lookback_minutes=390 이 실제로는 195 분만 덮는다
    (실측: 010170 → 390행 중 distinct 195).
    """
    conn = _minute_conn()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT stock_code, datetime
                FROM minute_candles
                GROUP BY stock_code, datetime
                HAVING count(*) > 1
                LIMIT 1
                """
            )
            dup = cur.fetchone()
    finally:
        conn.close()

    if dup is None:
        pytest.skip("중복 봉이 없다 — dedupe 가드 전제 불성립(별건 이슈 해소됨?)")

    symbol, bar_dt = dup
    df = pit_reader.read_minute(
        symbol=symbol,
        as_of_date=bar_dt.date(),
        as_of_time=time(23, 59),
        lookback_minutes=390,
    )
    assert not df.empty
    dupes = df[df.duplicated(subset=["date", "time"], keep=False)]
    assert dupes.empty, f"중복 봉이 그대로 새어나왔다:\n{dupes}"


class _ConnectSpy(Exception):
    """connect() 인자만 낚아채고 실제 접속은 막기 위한 sentinel."""


def test_read_minute_uses_minute_source_resolver(monkeypatch):
    """소스 DB 는 반드시 resolve_minute_source_db() 경유 — 하드코딩 금지 회귀 가드.

    resolver 를 가짜 DB명으로 갈아끼우면 connect(database=...) 가 그 이름이어야 한다.
    (기본값이 legacy 였을 때 연구만 조용히 동결 DB 를 읽던 사고의 재발 방지)
    """
    captured = {}

    def _spy(**kwargs):
        captured.update(kwargs)
        raise _ConnectSpy()

    monkeypatch.setattr(
        pit_reader, "resolve_minute_source_db", lambda: "__sentinel_minute_db__"
    )
    monkeypatch.setattr(pit_reader.psycopg2, "connect", _spy)

    with pytest.raises(_ConnectSpy):
        pit_reader.read_minute(
            symbol=_MINUTE_SYMBOL, as_of_date=_MINUTE_DATE, as_of_time=time(9, 1)
        )
    assert captured["database"] == "__sentinel_minute_db__"


def test_read_financial_ratio_applies_disclosure_lag():
    """공시 lag 60일 적용."""
    ratio = pit_reader.read_financial_ratio(
        symbol="005930", as_of_date=date(2026, 4, 1)
    )
    # 데이터 없으면 None OK. 있으면 60일 이전 공시분.
    if ratio is not None:
        assert "disclosure_date" not in ratio or \
               ratio["disclosure_date"] <= date(2026, 4, 1).replace(month=2, day=1)
