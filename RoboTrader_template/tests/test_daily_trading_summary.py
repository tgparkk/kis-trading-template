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
import re
from contextlib import contextmanager
from datetime import datetime
from unittest.mock import MagicMock, patch

from db.connection import DatabaseConnection
from tools.daily_trading_summary import GROSS_LABEL_SUFFIX, print_today_trading_summary


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
            # 🔴 이 더블은 승/패 «술어를 읽지 않는다» — > 0 / < 0 을 파이썬 쪽에
            # 하드코딩해 둔다. 그래서 §3 집계 SQL 의 술어를 >= 0 으로 바꿔도,
            # 심지어 SQL 안에 수수료 식을 심어도 «출력을 보는 테스트는 전부
            # 통과»한다(2026-08-14 리뷰 실측). §3 의 SQL 경로는 반드시
            # test_cumulative_aggregate_sql_* 의 «문자열 단언»으로 지켜야 한다.
            # 여기 계산을 SQL 해석으로 바꾸려 하지 말 것 — 더블이 프로덕션
            # 술어를 흉내내기 시작하면 순환 논리가 된다.
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
    # 라벨은 gross 꼬리표를 달되(2026-08-14 후속) 값은 그대로여야 한다.
    assert f"미실현 손익{GROSS_LABEL_SUFFIX}:          50,000원" in out


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


# ============================================================================
# 손익 라벨이 net 을 참칭했다 (2026-08-14)
#
# 배경: ``virtual_trading_records.profit_loss`` 는 **gross**((매도가-매수가)
# ×수량)로, 위탁수수료(매수·매도 각 0.015%)와 증권거래세(매도 0.18%)가 빠져
# 있다. 그런데 리포트는 그 합계를 「총 손익」·「실현 손익」이라는, 실현된
# net 으로 읽히는 라벨로 찍었다. 2026-08-14 실측: 리포트 284,104원 vs 실제
# net 270,335원(core.fund_manager "매매 손익 반영" 로그 합) → **5.1% 과대**.
# 누적으로는 paper_strategy_equity.realized_pnl_cum −13,381,292 vs 실제 net
# −15,067,053 → 손실을 1,685,761원 **과소** 표기.
#
# 🔴 수정 방침 = **라벨만 정정. 수수료를 리포트에서 재계산하지 않는다.**
# 이 프로젝트엔 적용 시점이 달라 서로 어긋나는 현금 원장이 이미 둘 있고,
# 리포트에 세 번째 수수료 계산식을 심는 건 「두 번째 틀린 숫자」를 만드는
# 일이다. 조사 결과 **net 실현손익은 DB 어디에도 적재돼 있지 않다**:
#   - virtual_trading_records — profit_loss/profit_rate 뿐, 수수료 컬럼 없음
#   - paper_strategy_equity.realized_pnl_cum — 같은 gross 컬럼의 SUM
#     (tools/paper_strategy_equity.py replay_strategy_equity)
#   - paper_trading_state.eod_balance — **현금 잔고**이지 실현손익이 아니다
#   - core/trading_decision_engine.py 의 pnl_with_fees(=net) 는 FundManager
#     메모리와 로그에만 남고 어느 테이블에도 적재되지 않는다
# ⇒ 숫자는 그대로 두고, 그 숫자가 gross 임을 라벨이 스스로 밝히게 한다.
# ============================================================================

_GROSS_MARKS = ("gross", "수수료")


def _labelled_lines(out, *prefixes):
    """출력에서 주어진 접두사로 시작하는 줄들(양끝 공백 제거 후)."""
    return [ln.strip() for ln in out.splitlines()
            if ln.strip().startswith(prefixes)]


def _declares_gross(line):
    return any(mark in line for mark in _GROSS_MARKS)


def _pnl_records(gross_pl=50000):
    """매수 1건 + 그 매수를 청산한 매도 1건(gross 손익 지정)."""
    buy = dict(
        id=1, action="BUY", stock_code="005930", stock_name="삼성전자",
        quantity=10, price=70000, target_profit_rate=0.03, stop_loss_rate=0.02,
        timestamp=datetime(2026, 8, 11, 10, 0), is_test=True, source="kis_template",
        buy_record_id=None, profit_loss=None, profit_rate=None,
    )
    sell = dict(
        id=2, action="SELL", stock_code="005930", stock_name="삼성전자",
        quantity=10, price=75000, target_profit_rate=None, stop_loss_rate=None,
        timestamp=datetime(2026, 8, 11, 14, 0), is_test=True, source="kis_template",
        buy_record_id=1, profit_loss=gross_pl, profit_rate=0.071,
    )
    return [buy, sell]


def test_daily_sell_total_label_declares_gross(monkeypatch, capsys):
    """§1 매도 내역의 합계 라벨은 그 값이 gross(수수료·세금 미반영)임을 밝혀야
    한다. 「총 손익:」이라고만 쓰면 실현된 net 으로 읽힌다."""
    _run_summary_with_records(monkeypatch, _pnl_records())

    out = capsys.readouterr().out
    lines = _labelled_lines(out, "총 손익")
    assert lines, f"매도 합계 손익 줄을 찾지 못함:\n{out}"
    for line in lines:
        assert _declares_gross(line), f"gross 임을 밝히지 않은 손익 라벨:\n{line}"


def test_cumulative_realized_label_declares_gross_and_keeps_the_number(
    monkeypatch, capsys
):
    """§3 누적 「실현 손익」도 마찬가지다.

    **대칭 단언**: 라벨을 고치면서 숫자를 바꾸면(=수수료를 리포트에서 새로
    계산해 「세 번째 원장」을 만들면) 안 된다. gross 합계 50,000 이 그대로
    찍혀야 하고, 동시에 어디서도 그 값을 net/순손익이라 부르면 안 된다.
    """
    _run_summary_with_records(monkeypatch, _pnl_records(gross_pl=50000))

    out = capsys.readouterr().out
    realized = [ln for ln in _labelled_lines(out, "실현 손익")
                if not ln.startswith("미실현")]
    assert realized, f"실현 손익 줄을 찾지 못함:\n{out}"
    for line in realized:
        assert _declares_gross(line), f"gross 임을 밝히지 않은 실현손익 라벨:\n{line}"
        assert "50,000" in line, f"gross 합계 값이 바뀌었다:\n{line}"

    assert "순손익" not in out, (
        "net 을 적재된 값처럼 표기했다 — DB 에 net 실현손익은 없다:\n" + out
    )


def test_report_discloses_that_net_is_not_available(monkeypatch, capsys):
    """숫자가 gross 라는 사실과 「net 은 적재돼 있지 않다」는 사실을 리포트가
    명시해야 한다. 라벨만 바꾸고 이유를 안 남기면 다음 사람이 또 net 으로
    읽는다(이 파일은 「표시값 ≠ 실제값」으로 이미 두 번 고쳐졌다)."""
    _run_summary_with_records(monkeypatch, _pnl_records())

    out = capsys.readouterr().out
    assert "수수료" in out and "거래세" in out, f"수수료/세금 미반영 고지가 없음:\n{out}"


def test_cumulative_query_alias_is_not_a_bare_realized_pl(monkeypatch):
    """실행된 SQL 자체를 단언: 누적 집계의 별칭이 ``total_realized_pl`` 이면
    gross 합계를 「실현손익」이라 부르는 오해가 코드 안에도 남는다."""
    cursor = _run_summary_with_records(monkeypatch, _pnl_records())

    agg = [sql for sql in cursor.executed_sql
           if "virtual_trading_records" in sql.lower() and "coalesce(sum" in sql.lower()]
    assert len(agg) == 1, f"누적 집계 쿼리 1개를 기대했으나 {len(agg)}개"
    ql = agg[0].lower()
    assert "as total_realized_pl," not in ql and not ql.rstrip().endswith("as total_realized_pl"), (
        f"gross 합계를 total_realized_pl 로 부르고 있다:\n{agg[0]}"
    )
    assert "gross" in ql, f"별칭이 gross 임을 밝히지 않음:\n{agg[0]}"


# ============================================================================
# gross 에서 «파생된 판정»(승/패·승률)이 라벨 없이 찍혔다 (2026-08-14 후속)
#
# 배경: c1b9dc3 은 «금액» 라벨만 gross 로 정정하고, 같은 gross 컬럼에서
# 파생된 «판정»은 그대로 뒀다. 판정 쪽이 더 나쁘다 — 금액은 읽는 사람이
# 보정할 수 있지만 승/패는 이미 내려진 결론이기 때문이다. 리뷰가 제시한
# 구성 사례:
#     매수 100주 @10,000 = 1,000,000 / 매도 100주 @10,010 = 1,001,000
#     gross = +1,000
#     수수료·세금 = 150(매수) + 150.15(매도) + 1,801.80(거래세) = 2,101.95
#     net   = −1,102
# 즉 **돈을 잃은** 포트폴리오가 「승률: 1/1 (100.0%)」로 찍힌다.
#
# 🔴 방침은 c1b9dc3 과 동일 — **라벨만. net 승률을 계산하지 않는다.**
# 손익 금액과 똑같은 이유다(적용 시점이 달라 서로 어긋나는 현금 원장이 이미
# 둘이고, 리포트에 심는 세 번째 수수료 계산식은 「두 번째 틀린 숫자」가 된다).
# 다만 다음 사실은 산술 없이 말할 수 있어 고지문에 넣는다:
#   · 수수료·세금은 항상 양수이므로 **모든** 거래에서 net ≤ gross 다.
#     ⇒ {net 승} ⊆ {gross 승} ⇒ **gross 승률은 net 승률의 상한**이다.
# 「상한」은 부등호지 수식이 아니라서 원장을 새로 만들지 않는다.
#
# 부수 정정 ①: §1 은 ``pl >= 0``(0원이 «승»), §3 SQL 은 ``> 0``/``< 0``
# (0원은 승도 패도 아니지만 총 매매 횟수에는 남음)이라 **한 리포트 안의 두
# 승률이 서로 다를 수 있었다**. §3 쪽(``> 0``)으로 통일한다 — 0원 거래는
# 수수료·거래세만큼 확정 net 손실이라 «승»으로 셀 근거가 없다.
# 부수 정정 ②: §2 보유 표의 평가손익·수익률·합계도 gross 이고, §3 의
# 「미실현 손익」 줄만 꼬리표를 못 받았다(위아래 두 줄은 받았다).
# ============================================================================


def _breakeven_win_records():
    """리뷰의 구성 사례 — gross +1,000 이지만 net 은 −1,102 인 매도 1건."""
    buy = dict(
        id=1, action="BUY", stock_code="005930", stock_name="삼성전자",
        quantity=100, price=10000, target_profit_rate=0.03, stop_loss_rate=0.02,
        timestamp=datetime(2026, 8, 11, 10, 0), is_test=True, source="kis_template",
        buy_record_id=None, profit_loss=None, profit_rate=None,
    )
    sell = dict(
        id=2, action="SELL", stock_code="005930", stock_name="삼성전자",
        quantity=100, price=10010, target_profit_rate=None, stop_loss_rate=None,
        timestamp=datetime(2026, 8, 11, 14, 0), is_test=True, source="kis_template",
        buy_record_id=1, profit_loss=1000, profit_rate=0.001,
    )
    return [buy, sell]


def _flat_pl_records():
    """gross 이익 매도 1건 + gross 손익이 정확히 0 인 매도 1건.

    0원 거래는 수수료·거래세만큼 **확정 net 손실**이다. §1(``>= 0``)과
    §3(``> 0``)의 관례가 어긋나 있으면 두 승률이 100.0% 와 50.0% 로
    갈린다 — 그 불일치를 잡는 표본이다.
    """
    rows = []
    for idx, (code, name, pl) in enumerate(
        [("005930", "삼성전자", 30000), ("000660", "SK하이닉스", 0)], start=1
    ):
        rows.append(dict(
            id=idx * 10, action="BUY", stock_code=code, stock_name=name,
            quantity=10, price=70000, target_profit_rate=0.03, stop_loss_rate=0.02,
            timestamp=datetime(2026, 8, 11, 10, 0), is_test=True,
            source="kis_template", buy_record_id=None,
            profit_loss=None, profit_rate=None,
        ))
        rows.append(dict(
            id=idx * 10 + 1, action="SELL", stock_code=code, stock_name=name,
            quantity=10, price=73000, target_profit_rate=None, stop_loss_rate=None,
            timestamp=datetime(2026, 8, 11, 14, 0), is_test=True,
            source="kis_template", buy_record_id=idx * 10,
            profit_loss=pl, profit_rate=0.0,
        ))
    return rows


def _win_rate_lines(out):
    return _labelled_lines(out, "승률")


def test_gross_win_on_a_net_loss_is_never_rendered_unqualified(monkeypatch, capsys):
    """리뷰의 구성 사례 — gross 는 +1,000 이지만 net 은 −1,102 인 거래 하나로
    이뤄진 리포트는 **꼬리표 없는 「승률: 100.0%」를 찍으면 안 된다**.

    §1(당일 매도)·§3(누적) 두 곳 모두 해당한다.
    """
    _run_summary_with_records(monkeypatch, _breakeven_win_records())

    out = capsys.readouterr().out
    rate_lines = _win_rate_lines(out)
    assert len(rate_lines) == 2, f"승률 줄 2개(§1·§3)를 기대했으나: {rate_lines}\n{out}"
    for line in rate_lines:
        assert _declares_gross(line), (
            "net 으로는 손실인 거래가 꼬리표 없는 승률로 찍혔다:\n" + line
        )

    bare = [ln.strip() for ln in out.splitlines()
            if ln.strip().startswith("승률") and not _declares_gross(ln)]
    assert not bare, f"꼬리표 없는 승률 줄이 남아 있다: {bare}"


def test_win_rate_value_is_not_recomputed_as_net(monkeypatch, capsys):
    """**대칭 단언**: 라벨을 고치면서 값을 net 으로 다시 계산하면 안 된다.

    이 사례의 net 승률은 0% 지만, 리포트가 그 0% 를 찍으면 「세 번째
    원장」(수수료 계산식)을 리포트에 심었다는 뜻이다. gross 판정 그대로
    1/1 · 100.0% 가 남아 있어야 한다. 한 방향(꼬리표만)만 단언하면 값을
    바꾼 구현도 통과한다.
    """
    _run_summary_with_records(monkeypatch, _breakeven_win_records())

    out = capsys.readouterr().out
    rate_lines = _win_rate_lines(out)
    assert all("100.0%" in ln for ln in rate_lines), (
        f"gross 승률 값이 바뀌었다(수수료를 리포트에서 재계산한 흔적): {rate_lines}"
    )
    assert any("1/1" in ln for ln in rate_lines), f"§1 승/건수 표기가 바뀌었다: {rate_lines}"

    win_loss = _labelled_lines(out, "승/패", "승:")
    assert win_loss, f"승/패 건수 줄을 찾지 못함:\n{out}"
    for line in win_loss:
        assert _declares_gross(line), f"gross 임을 밝히지 않은 승/패 줄:\n{line}"


def test_zero_gross_trade_is_not_counted_as_a_win_in_either_section(monkeypatch, capsys):
    """§1 과 §3 의 승/패 관례가 같아야 한다 — 0원 거래는 «승»이 아니다.

    §1 이 ``pl >= 0``, §3 이 ``> 0`` 이면 같은 리포트 안에서 승률이
    100.0% 와 50.0% 로 갈린다. 두 줄이 같은 수를 말하는지 직접 대조한다.
    """
    _run_summary_with_records(monkeypatch, _flat_pl_records())

    out = capsys.readouterr().out
    rate_lines = _win_rate_lines(out)
    assert len(rate_lines) == 2, f"승률 줄 2개를 기대했으나: {rate_lines}\n{out}"
    assert all("50.0%" in ln for ln in rate_lines), (
        f"0원 거래를 «승»으로 센 승률이 있다(§1·§3 관례 불일치): {rate_lines}"
    )
    assert any("1/2" in ln for ln in rate_lines), f"§1 승/건수 표기: {rate_lines}"
    assert "총 매매 횟수: 2회" in out


def test_gross_disclaimer_covers_the_verdicts_not_just_the_amounts(monkeypatch, capsys):
    """고지문이 승/패·승률 **아래**에 오고, 판정까지 포함해 말해야 한다.

    c1b9dc3 시점의 고지문은 §3 손익 줄 바로 뒤(=승/패·승률 «위»)에 있었고
    문구도 「위 손익은」이라 판정을 자연스럽게 덮지 못했다.
    """
    _run_summary_with_records(monkeypatch, _breakeven_win_records())

    out = capsys.readouterr().out
    lines = [ln.strip() for ln in out.splitlines()]

    disclaimer_idx = [i for i, ln in enumerate(lines)
                      if ln.startswith("⚠️") and "gross" in ln]
    assert disclaimer_idx, f"gross 고지문을 찾지 못함:\n{out}"

    rate_idx = [i for i, ln in enumerate(lines) if ln.startswith("승률")]
    assert rate_idx, f"승률 줄을 찾지 못함:\n{out}"

    assert max(disclaimer_idx) > max(rate_idx), (
        "고지문이 승/패·승률보다 위에 있어 판정을 덮지 못한다 "
        f"(고지문 {disclaimer_idx}, 승률 {rate_idx})"
    )

    disclaimer = lines[max(disclaimer_idx)]
    assert "승" in disclaimer, f"고지문이 승/패·승률을 언급하지 않는다:\n{disclaimer}"
    assert "상한" in disclaimer, (
        "gross 승률이 net 승률의 «상한»이라는 사실(부등호 — 산술 아님)이 없다:\n"
        + disclaimer
    )


def test_holdings_table_declares_gross_for_unrealized_columns(monkeypatch, capsys):
    """§2 보유 표의 평가손익·수익률·합계도 gross 다 — 표 머리에 고지가 있어야
    하고, 표 자체(값·정렬)는 그대로여야 한다."""
    holdings = [("111770", "종목A", 10, 80000, 0.03, 0.02)]
    daily = {("111770", _TODAY_PR): 85200}

    _run_price_summary(monkeypatch, holdings, daily)

    out = capsys.readouterr().out
    note = [ln.strip() for ln in out.splitlines()
            if "평가손익" in ln and _declares_gross(ln)]
    assert note, f"§2 평가손익/수익률이 gross 임을 밝히는 줄이 없다:\n{out}"

    line = _holding_line(out, "111770")
    assert "85,200" in line and "852,000" in line, line


def test_unrealized_pl_line_declares_gross(monkeypatch, capsys):
    """§3 「미실현 손익」 줄만 꼬리표를 못 받았다(바로 위·아래 두 줄은 받았다)."""
    holdings = [("111770", "종목A", 10, 80000, 0.03, 0.02)]
    daily = {("111770", _TODAY_PR): 85200}

    _run_price_summary(monkeypatch, holdings, daily)

    out = capsys.readouterr().out
    unrealized = _labelled_lines(out, "미실현 손익")
    assert unrealized, f"미실현 손익 줄을 찾지 못함:\n{out}"
    for line in unrealized:
        assert _declares_gross(line), f"gross 임을 밝히지 않은 미실현 손익 줄:\n{line}"
    # 값 불변: 10주 × (85,200 − 80,000) = 52,000
    assert any("52,000" in ln for ln in unrealized), unrealized


# ============================================================================
# 후속 리뷰 정정 (2026-08-14) — 「라벨만」 원칙을 라벨 «문구» 에도 적용한다
#
# 리뷰가 실행으로 반증한 것: 고지문이 «부등식이 허락하지 않는 것»을 단언하고
# 있었다.
#   「gross 승 중 일부는 실제로는 net 패다」  ← 존재 주장(declarative)
#   「위 승률은 net 승률의 «상한»이지 net 승률이 아니다」 ← 강부등호 주장
# 내가 가진 근거는 「수수료 > 0 ⇒ net ≤ gross ⇒ {net 승} ⊆ {gross 승}」뿐이고,
# 이는 «~일 수 있다» 까지만 허락한다. 부분집합은 진부분집합이 아니다.
#
# 🔑 그리고 이 지점이 날카롭다: **「실제로 일부가 손익분기 아래에 있다」를
# 세우는 일이 바로 내가 (옳게) 거절한 손익분기 계산 그 자체다.** 산술을
# 피하려고 쓴 문장이 산술을 했어야만 참이 되는 문장이었다 — 즉 이 파일이
# 없애려던 「표시 ≠ 실제」를 내가 한 건 더 만든 셈이다.
#
# 반증 표본 두 개(둘 다 아래 테스트로 고정):
#   · gross +10,000 / 매수금액 1,000,000 (10% — 손익분기의 약 50배)
#     → net 패로 뒤집히는 승이 «0건». gross 승률 = net 승률(둘 다 100%)이라
#       「상한이지 net 승률이 아니다」까지 함께 거짓이 된다.
#   · 매매 0건 → 승/패 0회인데도 「일부는 net 패다」가 그대로 렌더링된다.
# ============================================================================

# 강화된(=근거 없는) 주장 형태. 재강화 방지용으로 문구를 못박는다.
_OVERCLAIM_PHRASES = (
    "net 패다",            # 「일부는 실제로는 net 패다」 — 존재 주장
    "net 승률이 아니다",     # 「상한이지 net 승률이 아니다」 — 강부등호 주장
)


def _disclaimer_line(out):
    lines = [ln.strip() for ln in out.splitlines()
             if ln.strip().startswith("⚠️") and "gross" in ln]
    assert lines, f"gross 고지문을 찾지 못함:\n{out}"
    return lines[-1]


def _comfortable_win_records():
    """gross +10,000 / 매수금액 1,000,000 — 손익분기(약 0.21%)의 50배쯤 되는
    10% 수익이라 net 으로도 «확실히» 승이다. 이 표본에서는 gross 승률과 net
    승률이 «같다» — 둘이 다르다고 단언하는 문구는 여기서 거짓이 된다."""
    buy = dict(
        id=1, action="BUY", stock_code="005930", stock_name="삼성전자",
        quantity=100, price=10000, target_profit_rate=0.03, stop_loss_rate=0.02,
        timestamp=datetime(2026, 8, 11, 10, 0), is_test=True, source="kis_template",
        buy_record_id=None, profit_loss=None, profit_rate=None,
    )
    sell = dict(
        id=2, action="SELL", stock_code="005930", stock_name="삼성전자",
        quantity=100, price=11000, target_profit_rate=None, stop_loss_rate=None,
        timestamp=datetime(2026, 8, 11, 14, 0), is_test=True, source="kis_template",
        buy_record_id=1, profit_loss=10000, profit_rate=0.10,
    )
    return [buy, sell]


def test_disclaimer_does_not_claim_gross_and_net_win_rates_actually_differ(
    monkeypatch, capsys
):
    """gross 승률 == net 승률인 표본에서 「둘은 다르다」고 단언하면 안 된다.

    부분집합(⊆)은 진부분집합(⊊)이 아니다. 리포트는 net 을 모르므로 어느
    쪽인지 «알 수 없고», 알 수 없는 것을 단언하면 그게 새 「표시 ≠ 실제」다.
    """
    _run_summary_with_records(monkeypatch, _comfortable_win_records())

    out = capsys.readouterr().out
    disclaimer = _disclaimer_line(out)

    for phrase in _OVERCLAIM_PHRASES:
        assert phrase not in disclaimer, (
            f"부등식이 허락하지 않는 단언이 남아 있다({phrase!r}):\n{disclaimer}"
        )
    assert "수 있다" in disclaimer, (
        "가능성 표현(«~일 수 있다»)이 없다 — 단언으로 읽힌다:\n" + disclaimer
    )
    assert "상한" in disclaimer, f"상한이라는 사실 자체는 남아야 한다:\n{disclaimer}"


def test_disclaimer_holds_when_there_are_no_trades_at_all(monkeypatch, capsys):
    """매매 0건 — 「gross 승 중 일부는 net 패다」는 공집합에 대한 존재 주장이라
    명백히 거짓이었다. 가능성 표현이면 공허참이라 문제없다."""
    _run_summary_with_records(monkeypatch, [])

    out = capsys.readouterr().out
    disclaimer = _disclaimer_line(out)

    for phrase in _OVERCLAIM_PHRASES:
        assert phrase not in disclaimer, (
            f"매매 0건인데도 존재 주장이 렌더링된다({phrase!r}):\n{disclaimer}"
        )
    assert "총 매매 횟수: 0회" in out


# ----------------------------------------------------------------------------
# 매도 행 «색/부호»도 승/패 관례를 따라야 한다 (리뷰 Required 2)
#
# 집계는 > 0 으로 통일했는데 행 렌더링은 >= 0 그대로였다. 그래서 0원 거래가
# «초록 + 부호» 로 찍히면서 승률은 50% — 이 커밋이 스스로 내세운 명제
# (「한 리포트 안에 서로 다른 승률이 둘 있는 것 자체가 결함」)를 한 층 아래에서
# 그대로 어긴다.
# ----------------------------------------------------------------------------

def _three_way_sell_records():
    """이익·손실·0원 매도 각 1건 — 색/부호 3분기를 한 번에 본다."""
    rows = []
    for idx, (code, name, pl, rate) in enumerate([
        ("005930", "이익", 30000, 0.043),
        ("000660", "손실", -20000, -0.028),
        ("035420", "보합", 0, 0.0),
    ], start=1):
        rows.append(dict(
            id=idx * 10, action="BUY", stock_code=code, stock_name=name,
            quantity=10, price=70000, target_profit_rate=0.03, stop_loss_rate=0.02,
            timestamp=datetime(2026, 8, 11, 10, 0), is_test=True,
            source="kis_template", buy_record_id=None,
            profit_loss=None, profit_rate=None,
        ))
        rows.append(dict(
            id=idx * 10 + 1, action="SELL", stock_code=code, stock_name=name,
            quantity=10, price=73000, target_profit_rate=None, stop_loss_rate=None,
            timestamp=datetime(2026, 8, 11, 14, 0), is_test=True,
            source="kis_template", buy_record_id=idx * 10,
            profit_loss=pl, profit_rate=rate,
        ))
    return rows


def _sell_row(out, stock_code):
    for line in out.splitlines():
        if stock_code in line and ("🟢" in line or "🔴" in line or "⚪" in line):
            return line
    raise AssertionError(f"매도 행({stock_code})을 찾지 못함:\n{out}")


def test_zero_pl_sell_row_is_not_coloured_as_a_win(monkeypatch, capsys):
    """0원 매도 행은 «승»으로 색칠되면 안 된다 — 집계(> 0)와 같은 관례.

    대칭 단언: 이익 행은 여전히 🟢, 손실 행은 여전히 🔴 이어야 한다. 한쪽만
    보면 「전부 ⚪ 로 칠하기」도 통과한다.
    """
    _run_summary_with_records(monkeypatch, _three_way_sell_records())

    out = capsys.readouterr().out
    win_row = _sell_row(out, "005930")
    loss_row = _sell_row(out, "000660")
    flat_row = _sell_row(out, "035420")

    assert "🟢" in win_row and "🔴" not in win_row, win_row
    assert "🔴" in loss_row and "🟢" not in loss_row, loss_row
    assert "🟢" not in flat_row, f"0원 거래가 승으로 색칠됐다:\n{flat_row}"
    assert "⚪" in flat_row, f"0원 거래에 보합 표기가 없다:\n{flat_row}"
    # 부호도 같은 관례 — 0.0% 앞에 «+» 를 붙이면 이익으로 읽힌다.
    assert "+" not in flat_row.split("⚪")[1], f"0원 거래에 + 부호가 붙었다:\n{flat_row}"


def test_zero_unrealized_holding_row_is_not_coloured_as_a_win(monkeypatch, capsys):
    """§2 보유 행도 같은 관례를 쓴다 — 여기서만 🟢 를 남기면 한 리포트 안에
    색 관례가 둘이 되어 방금 고친 결함을 형태만 바꿔 되살린다."""
    holdings = [("111770", "보합", 10, 80000, 0.03, 0.02)]
    daily = {("111770", _TODAY_PR): 80000}   # 현재가 == 평균매수가 -> 평가손익 0

    _run_price_summary(monkeypatch, holdings, daily)

    out = capsys.readouterr().out
    line = _holding_line(out, "111770")
    assert "🟢" not in line, f"평가손익 0 이 승으로 색칠됐다:\n{line}"
    assert "⚪" in line, f"평가손익 0 에 보합 표기가 없다:\n{line}"


# ----------------------------------------------------------------------------
# §3 승/패 술어는 «SQL 안»에 있다 — 더블이 대신 계산하므로 출력 단언으로는
# 절대 관측되지 않는다 (리뷰 Required 3)
#
# 리뷰 실측: 누적 집계 SQL 의 ``profit_loss > 0`` 을 ``>= 0`` 으로 바꿔도
# 23개 테스트가 «전부 green». _IsTestAwareCursor 는 술어를 읽지 않고 파이썬
# 쪽에 > 0 / < 0 을 하드코딩해 두었기 때문이다. 즉 이 커밋이 닫으려던 바로 그
# 불일치(§1 vs §3)가 SQL 쪽에서는 무방비였다.
#
# 🔴 같은 사각지대는 «수수료 식» 도 숨긴다 — SQL 안에 수수료를 곱해 넣어도
# 어떤 테스트도 깨지지 않는다. 그래서 이 파일의 하드 제약(「세 번째 원장
# 금지」)을 SQL 문자열로 직접 못박는다. 선례: 바로 위
# test_cumulative_query_alias_is_not_a_bare_realized_pl.
# ----------------------------------------------------------------------------

def _aggregate_sql(monkeypatch):
    cursor = _run_summary_with_records(monkeypatch, _pnl_records())
    agg = [sql for sql in cursor.executed_sql
           if "virtual_trading_records" in sql.lower() and "coalesce(sum" in sql.lower()]
    assert len(agg) == 1, f"누적 집계 쿼리 1개를 기대했으나 {len(agg)}개"
    return agg[0], " ".join(agg[0].lower().split())


def test_cumulative_aggregate_sql_uses_strict_win_loss_predicates(monkeypatch):
    """§3 승/패 술어를 SQL 문자열로 단언한다 — 0원은 승도 패도 아니다.

    출력만 보는 테스트는 여기서 무력하다(값이 테스트 더블에서 나온다).
    """
    sql, ql = _aggregate_sql(monkeypatch)

    assert "profit_loss > 0" in ql, f"승 술어가 바뀌었다:\n{sql}"
    assert "profit_loss < 0" in ql, f"패 술어가 바뀌었다:\n{sql}"
    assert "profit_loss >= 0" not in ql, f"0원이 «승»으로 세어진다:\n{sql}"
    assert "profit_loss <= 0" not in ql, f"0원이 «패»로 세어진다:\n{sql}"


def test_cumulative_aggregate_sql_contains_no_fee_arithmetic(monkeypatch):
    """이 리포트의 하드 제약(«세 번째 원장 금지»)을 SQL 경로에서도 지킨다.

    더블이 SQL 을 해석하지 않으므로 여기에 수수료 식을 심으면 출력 단언은
    전부 통과한다. 문자열로 직접 막는 수밖에 없다.
    """
    sql, ql = _aggregate_sql(monkeypatch)

    for literal in ("0.00015", "0.0018", "0.015", "0.18"):
        assert literal not in ql, f"수수료/세율 리터럴이 SQL 에 심겼다({literal}):\n{sql}"
    for word in ("commission", "tax", "수수료", "거래세"):
        assert word not in ql, f"수수료 계산 흔적이 SQL 에 있다({word}):\n{sql}"
    for op in ("profit_loss *", "profit_loss -", "profit_loss /", "profit_loss +"):
        assert op not in ql, f"profit_loss 를 가공하고 있다({op}):\n{sql}"


# ----------------------------------------------------------------------------
# 승/패 합이 총 매매 횟수와 안 맞는 것을 «독자가» 알 수 있어야 한다 (리뷰 LOW 4)
#
# 「총 매매 횟수: 2회 / 승·패: 1회 / 0회」는 1+0 ≠ 2 인데, 코드 주석에만 이유가
# 있고 리포트 독자는 그 주석을 못 본다. 게다가 「1승 0패」는 순진하게 읽으면
# 100% 다. 보합 건수를 함께 찍어 삼항이 «더해지게» 만든다 — 건수 뺄셈이지
# 수수료 모델이 아니다.
# ----------------------------------------------------------------------------

def test_win_loss_flat_counts_add_up_to_total_trades(monkeypatch, capsys):
    """승 + 패 + 보합 = 총 매매 횟수 가 리포트 «표면»에서 성립해야 한다."""
    _run_summary_with_records(monkeypatch, _flat_pl_records())

    out = capsys.readouterr().out
    assert "총 매매 횟수: 2회" in out

    tally = _labelled_lines(out, "승/패")
    assert tally, f"승/패 줄을 찾지 못함:\n{out}"
    line = tally[0]
    assert "보합" in line, f"보합 건수가 없어 삼항이 더해지지 않는다:\n{line}"
    assert _declares_gross(line), line
    # 승 1 / 패 0 / 보합 1 = 2
    counts = [int(tok) for tok in re.findall(r"(\d+)회", line)]
    assert sum(counts) == 2, f"승+패+보합 이 총 매매 횟수와 다르다: {line}"


def test_holdings_note_does_not_understate_the_missing_costs(monkeypatch, capsys):
    """§2 고지가 «매도 쪽 비용만» 빠진 것처럼 말하면 안 된다 (리뷰 LOW 5).

    평가손익에는 이미 지불한 «매수» 위탁수수료도 안 들어 있다. 「지금 청산하면
    수수료·거래세만큼 줄어든다」는 그 한 다리를 빠뜨린 서술이었다.
    """
    holdings = [("111770", "종목A", 10, 80000, 0.03, 0.02)]
    daily = {("111770", _TODAY_PR): 85200}

    _run_price_summary(monkeypatch, holdings, daily)

    out = capsys.readouterr().out
    note = [ln.strip() for ln in out.splitlines()
            if "평가손익" in ln and _declares_gross(ln)]
    assert note, f"§2 gross 고지를 찾지 못함:\n{out}"
    assert "매수" in note[0], f"이미 낸 매수 수수료 언급이 없다:\n{note[0]}"
    assert "매도" in note[0], f"청산 시 낼 매도 비용 언급이 없다:\n{note[0]}"
