"""daily_trading_summary 의 text date 컬럼 회귀 테스트.

배경(2026-07-10 라이브 로그): DB 컷오버로 kis_template.daily_prices.date 컬럼이
text('YYYY-MM-DD')다 (레거시 robotrader.daily_prices.date 는 date 타입이었음).
``WHERE date = %s::date`` 로 파라미터를 date 로 캐스팅해 비교하면 kis_template
에서 "연산자 없음: text = date" 로 실패해 일일 매매 리포트 생성 전체가 죽는다.

DB 접속 없이 cursor 를 mock 하여, text date 컬럼 스키마에서 쿼리가 예외 없이
종목수를 반환하는지 검증한다. virtual_trading_records 계열 쿼리는 진짜
timestamptz 컬럼(``(timestamp AT TIME ZONE 'Asia/Seoul')::date = %s::date``)이라
이 버그와 무관하므로 빈 결과로 통과시켜 daily_prices 쿼리 하나에 집중한다.
"""
from contextlib import contextmanager
from datetime import datetime
from unittest.mock import MagicMock, patch

from db.connection import DatabaseConnection
from tools.daily_trading_summary import print_today_trading_summary


class _TextDateSchemaCursor:
    """kis_template 스키마 시뮬레이션: daily_prices.date 는 text.

    ``date = %s::date`` 처럼 파라미터를 date 로 캐스팅해 text 컬럼과 비교하면
    실제 kis_template 에서 재현되는 psycopg2 UndefinedFunction 상당 예외를 던진다.
    ``date = %s`` (캐스팅 없음, text-대-text 비교)는 정상 처리한다.
    """

    def __init__(self, daily_price_stock_codes_by_date):
        self._by_date = daily_price_stock_codes_by_date
        self._last = None

    def execute(self, sql, params=None):
        ql = " ".join(sql.lower().split())
        params = params or ()

        if "from daily_prices" in ql and "count(distinct stock_code)" in ql:
            if "%s::date" in ql:
                raise Exception(
                    "operator does not exist: text = date\n"
                    "HINT:  No operator matches the given name and argument types."
                )
            self._last = ("daily_count", len(self._by_date.get(params[0], [])))
            return

        if "from virtual_trading_records" in ql and "coalesce(sum" in ql:
            self._last = ("agg", (0, 0, 0, 0))
        else:
            # BUY/SELL 내역, 보유종목 등 나머지 virtual_trading_records 쿼리
            self._last = ("rows", [])

    def fetchall(self):
        kind, val = self._last
        return val if kind == "rows" else []

    def fetchone(self):
        kind, val = self._last
        if kind == "agg":
            return val
        if kind == "daily_count":
            return (val,)
        return None

    def close(self):
        pass


class _FakeConn:
    def __init__(self, cursor):
        self._cursor = cursor

    def cursor(self):
        return self._cursor


def _patch_connection(monkeypatch, conn):
    @contextmanager
    def fake_get_connection():
        yield conn

    monkeypatch.setattr(
        DatabaseConnection, "get_connection", staticmethod(fake_get_connection)
    )


def test_daily_price_count_succeeds_against_text_date_column(monkeypatch, capsys):
    """kis_template(daily_prices.date=text) 스키마에서 리포트가 예외 없이 완주하고
    당일 종목수(2건)를 정확히 출력해야 한다."""
    cursor = _TextDateSchemaCursor({"2026-07-10": ["005930", "000660"]})
    conn = MagicMock(wraps=_FakeConn(cursor))
    conn.cursor.return_value = cursor
    _patch_connection(monkeypatch, conn)

    with patch(
        "tools.daily_trading_summary.now_kst",
        return_value=datetime(2026, 7, 10, 15, 35),
    ):
        print_today_trading_summary()

    out = capsys.readouterr().out
    assert "일봉 데이터 수집: 2개 종목 (2026-07-10)" in out


# ============================================================================
# is_test 필터 회귀 테스트 (2026-08-11)
#
# 배경: virtual_trading_records 는 페이퍼(가상) 매매 테이블이라 실측
# 1,207행(2026-06-01~08-11) 전부가 is_test=true 이고 false 행은 0건이다.
# 그런데 daily_trading_summary.py 는 매수(50행)·매도(93행)·보유(158행)·
# 누적(235행) 4곳에서 ``is_test = false`` 로 걸러서, 매일 15:35 리포트가
# 항상 "매매 없음 · 손익 0원"만 출력했다. 프로젝트 운영 규칙(MEMORY.md)에
# "페이퍼 매매는 is_test=true 가 정상이며 필터로 거르지 말 것"이 명시돼
# 있고, 형제 프로젝트 분리는 이미 source='kis_template' 필터가 담당하므로
# is_test 필터는 중복이자 오작동 원인이다. ``source`` 필터는 4곳 모두
# 그대로 유지해야 한다(형제 프로젝트 RoboTrader 와 테이블을 공유하므로).
# ============================================================================


class _IsTestAwareCursor:
    """가짜 virtual_trading_records + daily_prices 를 SQL 텍스트로 해석해
    실제 WHERE 절 필터(``is_test = false``/``source = %s``)를 그대로
    반영하는 in-memory 커서.

    분류는 is_test 존재 여부와 무관한 구조적 마커(coalesce(sum/not exists/
    action = 'buy'/action = 'sell')로만 하므로, 테스트가 검증하려는 필터
    바로 그 문자열로 자기 자신을 분류하는 순환 논리가 되지 않는다.
    """

    def __init__(self, records, today="2026-08-11"):
        self._records = records
        self._today = today
        self.executed_sql = []
        self._last = None

    def execute(self, sql, params=None):
        self.executed_sql.append(sql)
        ql = " ".join(sql.lower().split())
        params = params or ()

        if "from daily_prices" in ql:
            if "count(distinct" in ql:
                self._last = ("one", (0,))
            else:
                # 종가 미보유 -> 현재가 미해결(합계 제외). avg_buy 폴백은 2026-08-12
                # 제거됐다(아래 «현재가 3단계 해석» 블록 참조).
                self._last = ("one", None)
            return

        source_filter = params[0] if "source = %s" in ql else None
        if "is_test = false" in ql:
            is_test_filter = False
        elif "is_test = true" in ql:
            is_test_filter = True
        else:
            is_test_filter = None

        def base_match(r):
            if source_filter is not None and r["source"] != source_filter:
                return False
            if is_test_filter is not None and r["is_test"] != is_test_filter:
                return False
            return True

        if "coalesce(sum" in ql:
            sells = [r for r in self._records if base_match(r) and r["action"] == "SELL"]
            total_pl = sum((r["profit_loss"] or 0) for r in sells)
            win = sum(1 for r in sells if (r["profit_loss"] or 0) > 0)
            loss = sum(1 for r in sells if (r["profit_loss"] or 0) < 0)
            self._last = ("one", (total_pl, win, loss, len(sells)))
            return

        if "not exists" in ql:
            sell_buy_ids = {r["buy_record_id"] for r in self._records if r["action"] == "SELL"}
            rows = [
                r for r in self._records
                if r["action"] == "BUY" and base_match(r) and r["id"] not in sell_buy_ids
            ]
            rows.sort(key=lambda r: r["stock_name"])
            self._last = ("many", [
                (r["stock_code"], r["stock_name"], r["quantity"], r["price"],
                 r["target_profit_rate"], r["stop_loss_rate"])
                for r in rows
            ])
            return

        if "action = 'buy'" in ql:
            rows = [
                r for r in self._records
                if r["action"] == "BUY" and base_match(r)
                and r["timestamp"].strftime("%Y-%m-%d") == self._today
            ]
            self._last = ("many", [
                (r["stock_code"], r["stock_name"], r["quantity"], r["price"],
                 r["quantity"] * r["price"], r["target_profit_rate"], r["stop_loss_rate"],
                 r["timestamp"])
                for r in rows
            ])
            return

        if "action = 'sell'" in ql:
            rows = [
                r for r in self._records
                if r["action"] == "SELL" and base_match(r)
                and r["timestamp"].strftime("%Y-%m-%d") == self._today
            ]
            self._last = ("many", [
                (r["stock_code"], r["stock_name"], r["quantity"], r["price"],
                 r["quantity"] * r["price"], r["profit_loss"], r["profit_rate"],
                 r["timestamp"])
                for r in rows
            ])
            return

        raise AssertionError(f"unexpected query in _IsTestAwareCursor: {sql}")

    def fetchall(self):
        kind, val = self._last
        return val if kind == "many" else []

    def fetchone(self):
        kind, val = self._last
        return val if kind == "one" else None

    def close(self):
        pass


def _run_summary_with_records(monkeypatch, records, today="2026-08-11"):
    cursor = _IsTestAwareCursor(records, today=today)
    conn = MagicMock()
    conn.cursor.return_value = cursor
    _patch_connection(monkeypatch, conn)

    with patch(
        "tools.daily_trading_summary.now_kst",
        return_value=datetime(2026, 8, 11, 15, 35),
    ):
        print_today_trading_summary()

    return cursor


def test_is_test_true_rows_are_counted_not_filtered_out(monkeypatch, capsys):
    """대칭 단언 ①: is_test=true 행이 있으면(운영 중인 페이퍼 매매의 정상
    상태) 매수/매도/보유/누적 섹션에 «없음/0건»이 아니라 실제 건수가 나와야
    한다."""
    today = "2026-08-11"
    ts_buy = datetime(2026, 8, 11, 10, 0)
    ts_sell = datetime(2026, 8, 11, 14, 0)
    ts_hold = datetime(2026, 8, 11, 11, 0)

    buy_row = dict(
        id=1, action="BUY", stock_code="005930", stock_name="삼성전자",
        quantity=10, price=70000, target_profit_rate=0.03, stop_loss_rate=0.02,
        timestamp=ts_buy, is_test=True, source="kis_template",
        buy_record_id=None, profit_loss=None, profit_rate=None,
    )
    sell_row = dict(
        id=2, action="SELL", stock_code="005930", stock_name="삼성전자",
        quantity=10, price=75000, target_profit_rate=None, stop_loss_rate=None,
        timestamp=ts_sell, is_test=True, source="kis_template",
        buy_record_id=1, profit_loss=50000, profit_rate=0.071,
    )
    holding_buy = dict(
        id=3, action="BUY", stock_code="035420", stock_name="NAVER",
        quantity=3, price=200000, target_profit_rate=0.03, stop_loss_rate=0.02,
        timestamp=ts_hold, is_test=True, source="kis_template",
        buy_record_id=None, profit_loss=None, profit_rate=None,
    )

    _run_summary_with_records(monkeypatch, [buy_row, sell_row, holding_buy], today=today)

    out = capsys.readouterr().out
    assert "매수 내역 (2건)" in out
    assert "매도 내역 (1건)" in out
    assert "보유 종목 (1개)" in out
    assert "총 매매 횟수: 1회" in out
    assert "매수 내역: 없음" not in out
    assert "매도 내역: 없음" not in out
    assert "보유 종목: 없음" not in out


def test_no_records_still_reports_none(monkeypatch, capsys):
    """대칭 단언 ②: 행이 아예 없으면(is_test 값과 무관하게) «없음»/0건이
    나와야 한다. 한 방향만 단언하면(①만 있으면) 필터를 무엇으로 바꾸든
    통과하는 무의미한 테스트가 되므로 반드시 함께 확인한다."""
    _run_summary_with_records(monkeypatch, [])

    out = capsys.readouterr().out
    assert "매수 내역: 없음" in out
    assert "매도 내역: 없음" in out
    assert "보유 종목: 없음" in out
    assert "총 매매 횟수: 0회" in out


def test_virtual_trading_records_queries_drop_is_test_but_keep_source(monkeypatch):
    """실행된 SQL 문자열 자체를 단언한다: virtual_trading_records 를
    조회하는 4개 쿼리(매수/매도/보유/누적) 어디에도 ``is_test`` 조건이
    남아 있으면 안 되고, ``source`` 필터는 4곳 모두 유지돼야 한다
    (source 는 형제 프로젝트 RoboTrader 와의 테이블 공유 분리를 위한
    정상 필터이므로 건드리지 않는다)."""
    cursor = _run_summary_with_records(monkeypatch, [])

    vtr_queries = [sql for sql in cursor.executed_sql if "virtual_trading_records" in sql.lower()]
    assert len(vtr_queries) == 4, f"virtual_trading_records 쿼리 4개를 기대했으나 {len(vtr_queries)}개 실행됨"

    for sql in vtr_queries:
        ql = sql.lower()
        # "is_test =" (실제 필터 조건)만 검사한다 — 설명 주석에 "is_test"
        # 라는 단어 자체가 등장하는 것과 혼동하지 않기 위함.
        assert "is_test =" not in ql, f"is_test 조건이 남아 있음:\n{sql}"
        assert "source" in ql, f"source 필터가 사라짐:\n{sql}"


# ============================================================================
# 현재가 3단계 해석 회귀 테스트 (2026-08-12)
#
# 배경: 「2️⃣ 보유 종목 및 평가」의 현재가 조회에 날짜 조건이 없었다 —
#   SELECT close FROM daily_prices WHERE stock_code = %s ORDER BY date DESC LIMIT 1
# 리포트는 bot/system_monitor.py 가 매일 **15:35** 에 부르는데 daily_prices 의
# 당일 행은 **16:01 EOD 수집**에서 들어온다. 그래서 15:35 시점의 "최신 종가"는
# **구조적으로 언제나 전일 종가**다. 2026-08-12 실측: 보유 60종목 중 당일 종가와
# 일치한 건 1건뿐, 최대 괴리 6.46%(111770), 미실현 손익이 716,929 로 찍혔으나
# 실제는 654,769 (9.5% 과대).
#
# 부수 결함: ``current_price = float(price_row[0]) if price_row else avg_buy`` —
# 일봉 이력이 아예 없으면 평균매수가로 대체돼 그 종목 평가손익이 **정확히 0**
# 으로 찍혔다. 「데이터 없음」이 「정상값 0」으로 둔갑하는 경로라 경보로 안 잡힌다.
#
# 수정 후 해석 순서(3단계):
#   1) 주입된 in-memory 현재가 조회자(봇 프로세스 안에서 실행될 때).
#      값이 None 이거나 <= 0 이면 실패로 간주(거래정지 종목은 0 을 준다 —
#      2026-08-12 15:36~15:42 에 13종목이 "현재가 정보 없음 (값: 0)" ERROR).
#   2) daily_prices 의 **당일** 종가(날짜 명시 조회).
#   3) 해결 불가 -> "-" 표기 + 합계에서 제외 + 경고. avg_buy 대체 금지.
# ============================================================================

_UNSET = object()
_TODAY_PR = "2026-08-12"
_YESTERDAY_PR = "2026-08-11"


class _PriceResolutionCursor:
    """daily_prices 를 (종목, 날짜) 격자로 들고 SQL 을 그대로 해석하는 커서.

    핵심: 종가 조회 SQL 에 날짜 조건(``date = %s``)이 **있으면** 그 날짜 행만
    주고, **없으면** 실제 Postgres 처럼 ``ORDER BY date DESC LIMIT 1`` = 가장
    최신 행(=전일 종가)을 준다. 테스트가 결함을 흉내내는 게 아니라 DB 를
    모델링하므로, 날짜 조건이 빠진 구현은 자동으로 전일 종가를 집게 된다.
    """

    def __init__(self, holdings, daily_closes, today):
        # holdings: [(stock_code, stock_name, qty, avg_buy, tp, sl), ...]
        # daily_closes: {(stock_code, 'YYYY-MM-DD'): close}
        self._holdings = holdings
        self._daily = daily_closes
        self._today = today
        self.executed_sql = []
        self.close_queries = []
        self._last = None

    def execute(self, sql, params=None):
        self.executed_sql.append(sql)
        ql = " ".join(sql.lower().split())
        params = tuple(params or ())

        if "from daily_prices" in ql:
            if "count(distinct" in ql:
                n = len({c for (c, d) in self._daily if d == params[0]})
                self._last = ("one", (n,))
                return
            self.close_queries.append((sql, params))
            code = params[0]
            rows = {d: v for (c, d), v in self._daily.items() if c == code}
            if "date = %s" in ql:
                # 날짜 명시 조회 — 그 날짜 행이 있을 때만 반환
                want = params[1]
                self._last = ("one", (rows[want],) if want in rows else None)
            else:
                # 날짜 조건 없음 -> ORDER BY date DESC LIMIT 1 = 최신 행
                self._last = ("one", (rows[max(rows)],) if rows else None)
            return

        if "coalesce(sum" in ql:
            self._last = ("one", (0, 0, 0, 0))
            return
        if "not exists" in ql:
            self._last = ("many", list(self._holdings))
            return
        # 오늘의 매수/매도 내역 — 이 블록의 관심사가 아니므로 빈 결과
        self._last = ("many", [])

    def fetchall(self):
        kind, val = self._last
        return val if kind == "many" else []

    def fetchone(self):
        kind, val = self._last
        return val if kind == "one" else None

    def close(self):
        pass


def _run_price_summary(monkeypatch, holdings, daily_closes, price_lookup=_UNSET):
    cursor = _PriceResolutionCursor(holdings, daily_closes, _TODAY_PR)
    conn = MagicMock()
    conn.cursor.return_value = cursor
    _patch_connection(monkeypatch, conn)

    with patch(
        "tools.daily_trading_summary.now_kst",
        return_value=datetime(2026, 8, 12, 15, 35),
    ):
        if price_lookup is _UNSET:
            print_today_trading_summary()
        else:
            print_today_trading_summary(price_lookup)

    return cursor


def _holding_line(out, stock_code):
    for line in out.splitlines():
        if line.startswith(stock_code):
            return line
    raise AssertionError(f"보유 종목 행({stock_code})을 출력에서 찾지 못함:\n{out}")


def test_holding_price_does_not_fall_back_to_previous_close(monkeypatch, capsys):
    """당일 일봉이 아직 없으면(15:35 = EOD 수집 16:01 이전) **전일 종가를 쓰지
    않는다**. 현재가/평가금액/평가손익은 "-"로 표기되고 합계에서 빠진다."""
    holdings = [("111770", "종목A", 10, 80000, 0.03, 0.02)]
    daily = {("111770", _YESTERDAY_PR): 90700}

    _run_price_summary(monkeypatch, holdings, daily)

    out = capsys.readouterr().out
    line = _holding_line(out, "111770")
    assert "90,700" not in line, f"전일 종가를 현재가로 사용함:\n{line}"
    assert "907,000" not in line, f"전일 종가 기반 평가금액이 계산됨:\n{line}"
    assert line.split()[-1] == "-", f"미해결 표기가 없음:\n{line}"
    assert "현재가 미해결 1종목" in out


def test_holding_price_uses_today_close_when_present(monkeypatch, capsys):
    """대칭 단언: 당일 일봉이 **있으면** 당일 종가를 쓴다(전일 종가가 DB 에
    함께 있어도). 한 방향만 단언하면 "항상 미해결"로 만들어도 통과한다."""
    holdings = [("111770", "종목A", 10, 80000, 0.03, 0.02)]
    daily = {("111770", _YESTERDAY_PR): 90700, ("111770", _TODAY_PR): 85200}

    _run_price_summary(monkeypatch, holdings, daily)

    out = capsys.readouterr().out
    line = _holding_line(out, "111770")
    assert "85,200" in line, f"당일 종가를 사용하지 않음:\n{line}"
    assert "90,700" not in line
    assert "현재가 미해결" not in out


def test_injected_memory_price_wins_over_daily_close(monkeypatch, capsys):
    """주입된 in-memory 조회자의 값이 당일 종가보다 우선한다(1순위)."""
    holdings = [("111770", "종목A", 10, 80000, 0.03, 0.02)]
    daily = {("111770", _TODAY_PR): 85200}

    _run_price_summary(monkeypatch, holdings, daily, price_lookup=lambda code: 88000)

    out = capsys.readouterr().out
    line = _holding_line(out, "111770")
    assert "88,000" in line, f"in-memory 현재가가 무시됨:\n{line}"
    assert "85,200" not in line


def test_zero_or_none_memory_price_falls_through_to_daily(monkeypatch, capsys):
    """in-memory 값이 0(거래정지 종목이 주는 값)이거나 None 이면 1단계 실패로
    보고 당일 일봉으로 내려간다. 0 을 그대로 곱해 평가금액 0 을 만들면 안 된다."""
    holdings = [
        ("111770", "종목A", 10, 80000, 0.03, 0.02),
        ("222880", "종목B", 4, 50000, 0.03, 0.02),
    ]
    daily = {("111770", _TODAY_PR): 85200, ("222880", _TODAY_PR): 60000}
    lookup = {"111770": 0, "222880": None}

    _run_price_summary(monkeypatch, holdings, daily, price_lookup=lookup.get)

    out = capsys.readouterr().out
    line_a = _holding_line(out, "111770")
    line_b = _holding_line(out, "222880")
    assert "85,200" in line_a and "852,000" in line_a, line_a
    assert "60,000" in line_b and "240,000" in line_b, line_b
    assert "현재가 미해결" not in out


def test_unresolvable_price_is_excluded_from_totals_not_replaced_by_avg_buy(
    monkeypatch, capsys
):
    """3단계 전부 실패하면 그 종목은 합계에서 **빠지고** 경고가 뜬다.

    avg_buy 대체(구 폴백)였다면 평가손익 0 으로 조용히 합계에 섞여 총 매수금액이
    1,150,000 · 총 평가금액이 1,200,000 이 됐을 것이다. 그 수가 없어야 한다."""
    holdings = [
        ("005930", "해결됨", 10, 70000, 0.03, 0.02),   # 매수 700,000
        ("111770", "미해결", 5, 90000, 0.03, 0.02),    # 매수 450,000
    ]
    daily = {("005930", _TODAY_PR): 75000}  # 111770 은 일봉 자체가 없음

    _run_price_summary(monkeypatch, holdings, daily, price_lookup=lambda c: None)

    out = capsys.readouterr().out
    assert "현재가 미해결 1종목(합계에서 제외)" in out
    # 미해결 종목이 avg_buy 로 대체돼 합계에 섞이면 나올 수 밖에 없는 수들
    assert "1,150,000" not in out, "미해결 종목의 매수금액이 합계에 섞임"
    assert "1,200,000" not in out, "미해결 종목이 avg_buy 로 평가금액에 섞임"
    # 해결된 종목만으로 계산된 합계
    assert "750,000" in out
    assert "미실현 손익:          50,000원" in out


def test_holding_close_query_filters_by_today(monkeypatch):
    """실행된 SQL 자체를 단언: 보유 종목 종가 조회에 날짜 조건이 있어야 하고,
    파라미터로 **오늘 날짜**가 넘어가야 한다. (daily_prices.date 는 text
    'YYYY-MM-DD' 라 ::date 캐스팅은 금지 — 파일 상단 주석 참조.)"""
    holdings = [("111770", "종목A", 10, 80000, 0.03, 0.02)]
    daily = {("111770", _TODAY_PR): 85200}

    cursor = _run_price_summary(monkeypatch, holdings, daily)

    assert cursor.close_queries, "보유 종목 종가 조회가 실행되지 않음"
    for sql, params in cursor.close_queries:
        ql = " ".join(sql.lower().split())
        assert "date = %s" in ql, f"종가 조회에 날짜 조건이 없음:\n{sql}"
        assert "%s::date" not in ql, f"text 컬럼에 ::date 캐스팅 금지:\n{sql}"
        assert _TODAY_PR in params, f"오늘 날짜가 파라미터에 없음: {params}"


def test_price_lookup_is_optional_for_cli_usage(monkeypatch, capsys):
    """인자 없이(=CLI 단독 실행) 불러도 동작하며 2단계(당일 일봉)를 탄다."""
    holdings = [("111770", "종목A", 10, 80000, 0.03, 0.02)]
    daily = {("111770", _TODAY_PR): 85200}

    _run_price_summary(monkeypatch, holdings, daily)

    out = capsys.readouterr().out
    assert "85,200" in _holding_line(out, "111770")


def test_raising_price_lookup_falls_through_instead_of_killing_report(monkeypatch, capsys):
    """조회자가 예외를 던져도 리포트가 죽지 않고 2단계로 내려간다."""
    holdings = [("111770", "종목A", 10, 80000, 0.03, 0.02)]
    daily = {("111770", _TODAY_PR): 85200}

    def _boom(code):
        raise RuntimeError("intraday manager exploded")

    _run_price_summary(monkeypatch, holdings, daily, price_lookup=_boom)

    out = capsys.readouterr().out
    assert "85,200" in _holding_line(out, "111770")


def test_explicit_none_price_lookup_behaves_like_omitted(monkeypatch, capsys):
    """조회자로 ``None`` 을 명시해 넘겨도(주입 실패 시 호출부가 그렇게 한다)
    생략한 것과 같이 2단계로 내려가야 한다."""
    holdings = [("111770", "종목A", 10, 80000, 0.03, 0.02)]
    daily = {("111770", _TODAY_PR): 85200}

    _run_price_summary(monkeypatch, holdings, daily, price_lookup=None)

    out = capsys.readouterr().out
    assert "85,200" in _holding_line(out, "111770")
