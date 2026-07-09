import pandas as pd
from datetime import date
from db.quant_daily_reader import QuantDailyReader


class _FakeCur:
    def __init__(self, rows): self._rows = rows; self.queries = []
    def execute(self, q, params=None): self.queries.append((q, params))
    def fetchall(self): return self._rows
    def close(self): pass
    def __enter__(self): return self
    def __exit__(self, *args): pass


class _FakeConn:
    def __init__(self, rows): self.cur = _FakeCur(rows)
    def cursor(self): return self.cur


def _reader(rows):
    r = QuantDailyReader()
    import contextlib
    @contextlib.contextmanager
    def _conn():
        yield _FakeConn(rows)
    r._conn = _conn
    return r


def test_get_universe_snapshot_maps_rows():
    rows = [("005930", 4.5e14, 900000000000), ("000660", 1.0e14, 0)]
    r = _reader(rows)
    out = r.get_universe_snapshot(date(2026, 6, 2))
    assert out[0] == {"stock_code": "005930", "market_cap": 4.5e14, "trading_value": 9.0e11}
    assert out[1]["stock_code"] == "000660"


class _DateAwareCur:
    """date 별 행을 가진 daily_prices 시뮬레이션 커서.

    - 정확매칭 쿼리(``date = %s``, 서브쿼리 없음): param 날짜가 있을 때만 행 반환.
    - 'scan_date 이하 최신일' 쿼리(``max(date)`` / ``<=`` 포함): param 이하 최대 날짜의 행 반환.
    이로써 '없는 당일' 조회 시 직전 거래일로 폴백하는지를 행동으로 검증한다.
    """

    def __init__(self, table):
        self._table = table  # {date_str: [rows]}
        self._result = []
        self.queries = []

    def execute(self, q, params=None):
        self.queries.append((q, params))
        ql = " ".join(q.lower().split())
        param_date = params[0] if params else None
        if "max(date)" in ql or "<=" in ql:
            avail = sorted(d for d in self._table if d <= param_date)
            eff = avail[-1] if avail else None
            self._result = self._table.get(eff, []) if eff else []
        else:
            self._result = self._table.get(param_date, [])

    def fetchall(self):
        return self._result

    def close(self):
        pass

    def __enter__(self):
        return self

    def __exit__(self, *args):
        pass


class _DateAwareConn:
    def __init__(self, table):
        self.cur = _DateAwareCur(table)

    def cursor(self):
        return self.cur


def _date_aware_reader(table):
    r = QuantDailyReader()
    import contextlib

    @contextlib.contextmanager
    def _conn():
        yield _DateAwareConn(table)

    r._conn = _conn
    return r


def test_get_universe_snapshot_uses_latest_on_or_before():
    """scan_date(06-08)에 데이터가 없으면 직전 거래일(06-05) 유니버스로 폴백한다.

    EOD 스크리너가 quant 적재(15:35) 전에 돌아도 빈 유니버스가 되지 않도록 하는 방어.
    """
    table = {
        "2026-06-05": [("005930", 4.5e14, 9.0e11), ("000660", 1.0e14, 5.0e11)],
        # 2026-06-08 은 아직 적재되지 않은 상태(키 없음)
    }
    r = _date_aware_reader(table)
    out = r.get_universe_snapshot(date(2026, 6, 8))
    assert len(out) == 2, "06-08 미적재 시 직전 거래일(06-05) 유니버스로 폴백해야 함"
    assert {o["stock_code"] for o in out} == {"005930", "000660"}


def test_get_daily_prices_returns_sorted_df():
    rows = [
        ("2026-06-02", 100.0, 110.0, 95.0, 105.0, 1000),
        ("2026-06-01", 90.0, 95.0, 88.0, 92.0, 800),
    ]
    r = _reader(rows)
    df = r.get_daily_prices("005930", end_date="2026-06-02", days=120)
    assert list(df.columns) == ["date", "open", "high", "low", "close", "volume"]
    assert df["date"].iloc[0] < df["date"].iloc[1]   # 오름차순 정렬
    assert df["close"].iloc[-1] == 105.0


# =============================================================================
# 운영/퀀트 병합 오염 방어 (DB 컷오버 KIS_DATA_SOURCE=new)
#   운영 현재가 쓰기(save_daily_prices_batch)는 OHLCV만 채우고 market_cap 은 NULL로 남긴다.
#   퀀트 유니버스 행(수집기/이관분)만 market_cap 이 채워져 있다.
#   따라서 '가장 최신 일자'가 소수 운영행(부분 유니버스)뿐이면 그 날을 건너뛰고
#   완전한 퀀트 유니버스가 있는 직전 일자를 사용해야 한다.
# =============================================================================
class _UniverseCur:
    """market_cap 판별을 모델링하는 daily_prices 시뮬레이션 커서.

    table: {date_str: [(stock_code, market_cap|None, trading_value|None), ...]}
    운영 전용 행은 market_cap=None(=None → NULL), 퀀트 유니버스 행은 값이 있음.
    실제 SQL 의 ``market_cap IS NOT NULL`` 절 유무를 파싱해 DB 동작을 재현한다:
      - 절이 있으면(수정 후 코드): market_cap 채워진 행이 있는 최신 일자 선택 + 그 날의
        market_cap 채워진 행만 반환.
      - 절이 없으면(수정 전 코드): market_cap 무시하고 max(date) 선택 → 부분일자 오염.
    """

    def __init__(self, table):
        self._table = table
        self._result = []
        self.queries = []

    def execute(self, q, params=None):
        self.queries.append((q, params))
        ql = " ".join(q.lower().split())
        param_date = params[0] if params else None
        require_mc = "market_cap is not null" in ql

        def _rows_for(d):
            rows = self._table.get(d, [])
            if require_mc:
                return [r for r in rows if r[1] is not None]
            return list(rows)

        eligible = [
            d for d in self._table
            if d <= param_date and (not require_mc or any(r[1] is not None for r in self._table[d]))
        ]
        eff = max(eligible) if eligible else None
        self._result = _rows_for(eff) if eff else []

    def fetchall(self):
        return self._result

    def close(self):
        pass

    def __enter__(self):
        return self

    def __exit__(self, *args):
        pass


class _UniverseConn:
    def __init__(self, table):
        self.cur = _UniverseCur(table)

    def cursor(self):
        return self.cur


def _universe_reader(table):
    r = QuantDailyReader()
    import contextlib

    @contextlib.contextmanager
    def _conn():
        yield _UniverseConn(table)

    r._conn = _conn
    return r


def test_universe_skips_partial_operational_latest_day():
    """최신 일자가 소수 운영행(market_cap NULL)뿐이면 직전 완전 퀀트일로 폴백한다.

    운영 현재가 쓰기가 보유 종목 몇 개만 오늘자로 UPSERT 하면 max(date)=오늘이 되어
    유니버스가 그 몇 종목으로 붕괴하던 버그(DB 컷오버) 방어.
    """
    table = {
        "2026-07-07": [
            ("005930", 4.5e14, 9.0e11),
            ("000660", 1.0e14, 5.0e11),
            ("035720", 2.0e13, 3.0e11),
        ],
        # 07-08: 운영 전용 부분 유니버스(오늘자 UPSERT, market_cap NULL)
        "2026-07-08": [("005930", None, None), ("000660", None, None)],
    }
    r = _universe_reader(table)
    out = r.get_universe_snapshot(date(2026, 7, 8))
    assert len(out) == 3, "부분 운영일(07-08)은 건너뛰고 완전 퀀트일(07-07) 유니버스를 써야 함"
    assert {o["stock_code"] for o in out} == {"005930", "000660", "035720"}


def test_universe_uses_latest_complete_day():
    """최신 일자가 완전한 퀀트 유니버스면 그 날을 사용한다."""
    table = {
        "2026-07-07": [("005930", 4.5e14, 9.0e11)],
        "2026-07-08": [("005930", 4.6e14, 9.0e11), ("000660", 1.0e14, 5.0e11)],
    }
    r = _universe_reader(table)
    out = r.get_universe_snapshot(date(2026, 7, 8))
    assert {o["stock_code"] for o in out} == {"005930", "000660"}


def test_universe_excludes_operational_straggler_on_selected_day():
    """선택된 완전일에 섞인 운영 전용 행(market_cap NULL)은 유니버스에서 제외한다.

    레거시(분리 DB) 시절엔 퀀트 유니버스에 운영행이 전혀 없었음 → 그 순수성 복원.
    (KOSPI/KOSDAQ 지수 유사행도 market_cap NULL 이라 자연히 제외됨.)
    """
    table = {
        "2026-07-08": [
            ("005930", 4.5e14, 9.0e11),
            ("000660", 1.0e14, 5.0e11),
            ("111111", None, None),   # 보유 종목 운영 전용 스트래글러
        ],
    }
    r = _universe_reader(table)
    out = r.get_universe_snapshot(date(2026, 7, 8))
    assert {o["stock_code"] for o in out} == {"005930", "000660"}


def test_universe_pit_excludes_future_date():
    """PIT: scan_date 이후 미래 일자는 선택되지 않는다(룩어헤드 금지)."""
    table = {
        "2026-07-07": [("005930", 4.5e14, 9.0e11)],
        "2026-07-09": [("005930", 4.7e14, 9.0e11), ("000660", 1.0e14, 5.0e11)],
    }
    r = _universe_reader(table)
    out = r.get_universe_snapshot(date(2026, 7, 8))
    assert {o["stock_code"] for o in out} == {"005930"}, "미래일(07-09) 유니버스를 참조하면 안 됨"


def test_universe_returns_empty_when_no_complete_day_exists():
    """market_cap 채워진 행이 전무한 DB(신규 DB/초기 부팅 극단)에서는 빈 유니버스([])를 반환한다.

    모든 날짜가 운영 전용 행(market_cap NULL)뿐이면 완전한 퀀트일이 존재하지 않으므로
    eff=None → [] (조용히 빈 유니버스, 예외 아님). 코드리뷰 MINOR#1.
    """
    table = {
        "2026-07-07": [("005930", None, None), ("000660", None, None)],
        "2026-07-08": [("005930", None, None)],
    }
    r = _universe_reader(table)
    out = r.get_universe_snapshot(date(2026, 7, 8))
    assert out == []


# =============================================================================
# 부분 운영일 스킵 debug 로그 (코드리뷰 MINOR#2, 관측성 하드닝)
#   선택된 유니버스 일자가 scan_date보다 과거인데(=부분일자 스킵 발생) scan_date 당일에
#   행이 존재하는 경우(=market_cap 없는 운영 부분일자를 건너뛴 상황)만 logger.debug 로 남긴다.
#   정상 경로(당일이 완전 유니버스) 및 scan_date 자체에 행이 아예 없는 휴장일 정상 폴백은
#   로그를 남기지 않는다(잡음 방지). 메인 조회는 (main_query, meta_query) 호출 순서로
#   실행되므로, 호출 순서 기반의 경량 fake로 각 시나리오의 메타(eff_date, scan_has_rows)를
#   직접 주입해 로그 유무·내용을 검증한다.
# =============================================================================
class _CallSeqCur:
    """1번째 execute=메인 유니버스 조회(rows 고정), 2번째=메타 조회(eff_date, scan_has_rows 고정)."""

    def __init__(self, rows, meta):
        self._rows = rows
        self._meta = meta
        self.queries = []

    def execute(self, q, params=None):
        self.queries.append((q, params))

    def fetchall(self):
        return self._rows

    def fetchone(self):
        return self._meta

    def close(self):
        pass

    def __enter__(self):
        return self

    def __exit__(self, *args):
        pass


class _CallSeqConn:
    def __init__(self, rows, meta):
        self.cur = _CallSeqCur(rows, meta)

    def cursor(self):
        return self.cur


def _callseq_reader(rows, meta):
    r = QuantDailyReader()
    import contextlib

    @contextlib.contextmanager
    def _conn():
        yield _CallSeqConn(rows, meta)

    r._conn = _conn
    return r


def test_universe_logs_debug_on_partial_day_skip(monkeypatch):
    """scan_date 당일에 행이 있는데(market_cap 미충전) 건너뛰고 과거 완전일로 폴백하면
    logger.debug 로 선택된 date 와 scan_date 를 모두 남긴다."""
    from db import quant_daily_reader as qdr_module

    calls = []
    monkeypatch.setattr(qdr_module.logger, "debug", lambda *a, **k: calls.append(a))

    rows = [("005930", 4.5e14, 9.0e11)]
    meta = ("2026-07-07", True)  # eff_date=07-07(<scan_date), scan_date(07-08) 당일 행 존재(부분운영)
    r = _callseq_reader(rows, meta)
    r.get_universe_snapshot("2026-07-08")

    assert len(calls) == 1, "부분 운영일 스킵 시 debug 로그가 정확히 1회 남아야 함"
    logged_args = calls[0]
    assert "2026-07-08" in logged_args, "로그에 scan_date 포함"
    assert "2026-07-07" in logged_args, "로그에 선택된(폴백) date 포함"


def test_universe_no_debug_log_when_selected_day_is_scan_date():
    """당일(scan_date)이 완전 유니버스라 그대로 선택되면(정상 경로) 로그가 없다."""
    import unittest.mock as mock
    from db import quant_daily_reader as qdr_module

    rows = [("005930", 4.5e14, 9.0e11)]
    meta = ("2026-07-08", True)  # eff_date == scan_date → 정상 경로
    r = _callseq_reader(rows, meta)
    with mock.patch.object(qdr_module.logger, "debug") as mock_debug:
        r.get_universe_snapshot("2026-07-08")
        mock_debug.assert_not_called()


def test_universe_no_debug_log_when_scan_date_has_no_rows_at_all():
    """scan_date 자체가 휴장일이라 행이 아예 없으면(통상적 다일 폴백) 로그가 없다.

    market_cap 미충전 스킵과 구분: 휴장일 정상 폴백은 매일 발생할 수 있는 흔한 경로라
    로그 잡음이 되므로, scan_date 에 행 자체가 없는 경우는 제외한다.
    """
    import unittest.mock as mock
    from db import quant_daily_reader as qdr_module

    rows = [("005930", 4.5e14, 9.0e11)]
    meta = ("2026-07-07", False)  # eff_date < scan_date, scan_date 당일엔 행 자체가 없음(휴장)
    r = _callseq_reader(rows, meta)
    with mock.patch.object(qdr_module.logger, "debug") as mock_debug:
        r.get_universe_snapshot("2026-07-08")
        mock_debug.assert_not_called()
