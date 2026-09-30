# tests/collectors/test_minute_tasso_universe.py
"""분봉 수집 범위 확장(🔒 09-29 사장님 결정: top300 + 태쏘 후보 «후보가 된 날부터 20거래일») 단위 테스트.

가짜 KIS·가짜 DB 만 쓴다 — 실 API·실 DB 호출 0. 봉 모양은 실측(09-29 top300) 기준:
하루 09:00~15:19 = 380봉 · 과거 분봉 API 는 `input_hour` 로부터 뒤로 120봉(이른 시각이면 전날로 넘어간다).
  - 합집합·중복·순서(top300 먼저) · 영숫자 코드 · strip 뒤 중복 제거
  - 태쏘 조회 실패 → top300 만 + 연결 rollback(같은 연결로 적재 계속)
  - 20거래일 창 경계(추석 휴장 포함)
  - 정상일(top300·태쏘 겹침)에 요청일 필터가 rows 를 바꾸지 않음(특성 고정) · 다른 날 응답 거부
  - 결손일 보충: 다일([첫 후보일, P]) · 창/첫 후보일 앞은 안 봄 · 날짜 필터 · 폴백 거부 ·
    적게 받으면 미교체 · 부분 수신 거부 · 거래정지일 제외 · «종목-일» 상한(최근 날짜 먼저) ·
    이월·실패일 다음 날 재시도 · 종목-일별 예외 격리
  - 하루치 완전성 WARNING(적재는 그대로)
"""
from contextlib import contextmanager
from datetime import date, datetime, timedelta

import pandas as pd
import pytest

import collectors.minute_collector as mc
import collectors.minute_universe as mu
from collectors.minute_writer import df_to_minute_rows

# 가짜 거래일 달력(실제와 같게 09-24·25 추석 · 주말 제외)
CAL = ["20260921", "20260922", "20260923", "20260928", "20260929", "20260930"]
TODAY = "20260930"          # P = 09-29
P = "20260929"
TODAY_D = date(2026, 9, 30)
FULL_DAY = 380              # 실측 중앙값(09:00~15:19)


# ─────────────────────────── 봉 만들기 ───────────────────────────
def minutes(start_hm, n):
    t0 = datetime(2000, 1, 1, int(start_hm[:2]), int(start_hm[2:4]))
    return [(t0 + timedelta(minutes=i)).strftime("%H%M%S") for i in range(n)]


DAY_TIMES = minutes("0900", FULL_DAY)          # 090000 … 151900
assert DAY_TIMES[-1] == "151900"


def bars(ymd, times):
    """_process_chart_data 출력 모양의 분봉 df."""
    return pd.DataFrame([{
        "date": ymd, "time": t,
        "datetime": pd.Timestamp(datetime.strptime(ymd + t, "%Y%m%d%H%M%S")),
        "open": 100.0, "high": 101.0, "low": 99.0, "close": 100.0,
        "volume": 10.0, "amount": 1000.0,
    } for t in times])


def fake_past_api(data_days=None):
    """과거 분봉 API 흉내 — (input_date, input_hour) 에서 뒤로 120봉(요청일에 봉이 없으면 그 앞 날짜 봉).

    data_days: 봉이 있는 날(기본 = CAL 전부). 없는 날을 요청하면 앞 날짜 봉만 온다(= API 쪽 폴백).
    """
    days = [d for d in CAL if data_days is None or d in data_days]
    timeline = pd.concat([bars(d, DAY_TIMES) for d in days], ignore_index=True)
    keys = list(timeline["date"] + timeline["time"])        # 'YYYYMMDDHHMMSS' — 오름차순

    def api(input_date, input_hour):
        last = sum(1 for k in keys if k <= input_date + input_hour)   # 요청 시각 이하 봉 수
        if last == 0:
            return pd.DataFrame(), pd.DataFrame()
        return pd.DataFrame(), timeline.iloc[max(0, last - 120): last].reset_index(drop=True).copy()
    return api


# ─────────────────────────── 가짜 DB ───────────────────────────
class FakeLogger:
    def __init__(self):
        self.lines = []

    def __getattr__(self, lvl):
        return lambda msg, *a, **k: self.lines.append((lvl, msg % a if a else msg))


class FakeCursor:
    def __init__(self, conn):
        self.conn = conn
        self._rows = []

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def execute(self, sql, params=None):
        c = self.conn
        c.executed.append((sql, params))
        if "tasso_shadow.candidates" in sql:
            if c.tasso_error:
                raise c.tasso_error
            self._rows = list(c.tasso_rows)
        elif "JOIN daily_prices" in sql:
            # _MISSING_DAYS_SQL 의미: [start, p_iso] 안 일봉 있는 날 중 분봉 0행
            self._rows = []
            for code, start in zip(params["codes"], params["starts"]):
                for iso, vol in c.daily.get(code, []):
                    if start <= iso <= params["p_iso"] and (code, iso.replace("-", "")) not in c.minute_days:
                        self._rows.append((code, iso, vol))
        elif sql.strip().startswith("SELECT count(*) FROM minute_candles"):
            self._rows = [(c.existing.get(params, 0),)]
        else:
            self._rows = []

    def fetchall(self):
        return self._rows

    def fetchone(self):
        return self._rows[0] if self._rows else None


class FakeConn:
    def __init__(self, tasso_rows=(), tasso_error=None, daily=None, minute_days=(), existing=None):
        self.tasso_rows = list(tasso_rows)
        self.tasso_error = tasso_error
        self.daily = daily or {}                 # code -> [(iso, volume)]
        self.minute_days = set(minute_days)      # {(code, 'YYYYMMDD')} — 분봉 있는 날
        self.existing = existing or {}           # (code, ymd) -> 적재 직전 재확인 행수
        self.executed = []
        self.rollbacks = 0

    def cursor(self):
        return FakeCursor(self)

    def rollback(self):
        self.rollbacks += 1

    def commit(self):
        pass


def iso(ymd):
    return f"{ymd[:4]}-{ymd[4:6]}-{ymd[6:]}"


def daily_rows(days, vol=5000):
    return [(iso(d), vol) for d in days]


@pytest.fixture
def env(monkeypatch):
    """collect_minute 의 외부 의존을 전부 가짜로 바꾼다."""
    st = {"conn": FakeConn(), "top": [], "full": {}, "past": {}, "replaced": [],
          "full_calls": [], "past_calls": []}

    @contextmanager
    def _get_conn():
        yield st["conn"]

    def _full(code, ymd, sel):
        st["full_calls"].append((code, ymd, sel))
        return st["full"].get(code, bars(ymd, DAY_TIMES))

    def _past(div_code="J", stock_code="", input_hour="", input_date="", past_data_yn="Y", **k):
        st["past_calls"].append((stock_code, input_date, input_hour))
        fn = st["past"].get(stock_code, fake_past_api())
        return fn(input_date, input_hour)

    def _replace(conn, code, trade_date, rows):
        st["replaced"].append((code, trade_date, rows))
        conn.minute_days.add((code, trade_date))   # 다음 실행은 이 날을 «있음»으로 본다
        return len(rows)

    monkeypatch.setattr(mc, "select_top_volume", lambda n=300: list(st["top"]))
    monkeypatch.setattr(mc.KisDbConnection, "get_connection", _get_conn)
    monkeypatch.setattr(mc.kis_chart_api, "get_full_trading_day_data", _full)
    monkeypatch.setattr(mc.kis_chart_api, "get_inquire_time_dailychartprice", _past)
    monkeypatch.setattr(mc, "replace_minute_day", _replace)
    monkeypatch.setattr(mc, "_BACKFILL_SLEEP", 0)
    st["log"] = FakeLogger()
    monkeypatch.setattr(mc, "logger", st["log"])
    monkeypatch.setattr(mu, "logger", st["log"])
    return st


def backfilled(st):
    return [(c, d) for c, d, _ in st["replaced"] if d != TODAY]


def warnings(st):
    return [m for lvl, m in st["log"].lines if lvl == "warning"]


# ─────────────────────────── 합집합·순서 ───────────────────────────
def test_union_keeps_top300_first_dedups_and_passes_alnum_codes(env):
    env["top"] = ["000100", "000200", "000300"]
    env["conn"] = FakeConn(tasso_rows=[("000200", date(2026, 9, 30)),   # top300 과 중복
                                       ("0039P0", date(2026, 9, 29)),   # 영숫자 — 걸러지면 안 된다
                                       ("000400", date(2026, 9, 23))])
    out = mc.collect_minute(TODAY)
    assert [c for c, _, _ in env["full_calls"]] == ["000100", "000200", "000300", "0039P0", "000400"]
    assert out["codes"] == 5 and out["rows"] == 5 * FULL_DAY
    assert out["tasso"]["codes"] == 3 and out["tasso"]["extra"] == 2
    assert out["date_rejected"] == 0
    assert all(ymd == TODAY and sel == "153000" for _, ymd, sel in env["full_calls"])


def test_select_tasso_codes_dedups_after_strip_keeping_order_and_min_first_date():
    conn = FakeConn(tasso_rows=[("005930 ", date(2026, 9, 28)), ("0039P0", date(2026, 9, 29)),
                                ("005930", date(2026, 9, 23))])
    wf, rows = mu.select_tasso_codes(conn, TODAY_D)
    assert wf == date(2026, 9, 1)
    assert rows == [("005930", date(2026, 9, 23)), ("0039P0", date(2026, 9, 29))]


def test_dashed_target_date_is_normalized(env):
    env["top"] = ["000100"]
    mc.collect_minute("2026-09-30")
    assert env["full_calls"] == [("000100", TODAY, "153000")]


def test_tasso_query_failure_falls_back_to_top300_only(env):
    env["top"] = ["000100", "000200"]
    env["conn"] = FakeConn(tasso_error=RuntimeError('relation "tasso_shadow.candidates" does not exist'))
    out = mc.collect_minute(TODAY)
    assert [c for c, _, _ in env["full_calls"]] == ["000100", "000200"]
    assert out["codes"] == 2 and out["rows"] == 2 * FULL_DAY
    assert out["tasso"]["error"] and out["tasso"]["codes"] == 0 and "backfill" not in out["tasso"]
    assert env["conn"].rollbacks >= 1               # aborted 트랜잭션을 풀어야 적재가 이어진다
    assert len(env["replaced"]) == 2
    assert len(warnings(env)) == 1 and "태쏘 후보 조회 실패" in warnings(env)[0]
    assert env["past_calls"] == []                  # 보충도 안 돈다


def test_window_query_uses_20_trading_days_including_today(env):
    out = mc.collect_minute(TODAY)
    sql, params = next(x for x in env["conn"].executed if "tasso_shadow.candidates" in x[0])
    assert "in_ra OR in_rb" in sql and "arm" not in sql.split("WHERE")[1]   # arm 무관
    assert params == (date(2026, 9, 1), TODAY_D)
    assert out["tasso"]["window"] == "2026-09-01~2026-09-30"


# ─────────────────────────── 20거래일 창 경계 ───────────────────────────
def test_window_start_skips_chuseok_holidays():
    # 09-29 를 1일째로 20거래일: 09-24·25(추석)·주말을 건너뛰어 08-31 이 20일째(평일만 세면 09-02).
    assert mu.tasso_window_start(date(2026, 9, 29)) == date(2026, 8, 31)
    assert mu.tasso_window_start(date(2026, 9, 29), n=1) == date(2026, 9, 29)
    assert mu.tasso_window_start(date(2026, 9, 29), n=3) == date(2026, 9, 23)


def test_window_start_counts_exactly_n_trading_days(monkeypatch):
    cal = [date(2026, 1, 1) + timedelta(days=i) for i in range(0, 60, 2)]   # 가짜 거래일(격일)

    def prev(dt):
        return datetime.combine(max(x for x in cal if x < dt.date()), datetime.min.time())

    monkeypatch.setattr(mu, "get_previous_trading_day", prev)
    start = mu.tasso_window_start(cal[-1])
    assert start == cal[-20]
    assert len([d for d in cal if start <= d <= cal[-1]]) == 20


# ─────────────────────────── 당일 수집 ───────────────────────────
def test_normal_day_overlap_rows_identical_to_pre_filter_behavior(env):
    """특성 고정: 정상일(전부 요청일 봉 · top300·태쏘 겹침)엔 요청일 필터가 적재 행을 1개도 바꾸지 않는다."""
    env["top"] = ["000100", "000200"]
    env["conn"] = FakeConn(tasso_rows=[("000200", date(2026, 9, 29)), ("0039P0", date(2026, 9, 30))])
    dfs = {c: bars(TODAY, DAY_TIMES) for c in ("000100", "000200", "0039P0")}
    env["full"] = dfs
    out = mc.collect_minute(TODAY)
    assert out["rows"] == 3 * FULL_DAY and out["date_rejected"] == 0
    today_writes = [(c, d, r) for c, d, r in env["replaced"] if d == TODAY]
    assert [c for c, _, _ in today_writes] == ["000100", "000200", "0039P0"]
    for code, _, rows in today_writes:
        assert rows == df_to_minute_rows(code, dfs[code])      # 필터 전(기존) 동작과 동일
    assert warnings(env) == []                                  # 완전한 하루 → 경고 0


def test_main_loop_rejects_fallback_and_strips_cross_day_rows(env):
    env["top"] = ["000100"]
    env["conn"] = FakeConn(tasso_rows=[("0039P0", date(2026, 9, 30))])
    env["full"] = {
        # 거래정지일 모양 — 오늘 봉 0 · 전날 오후 봉만 → 적재하면 P 분봉을 절단 재적재한다
        "0039P0": bars(P, minutes("1331", 109)),
        # 섞인 응답 — 오늘 봉만 적재
        "000100": pd.concat([bars(P, minutes("1500", 5)), bars(TODAY, DAY_TIMES)]),
    }
    out = mc.collect_minute(TODAY)
    assert out["date_rejected"] == 1
    assert [(c, d) for c, d, _ in env["replaced"]] == [("000100", TODAY)]
    assert all(r["trade_date"] == TODAY for r in env["replaced"][0][2])
    assert out["rows"] == FULL_DAY


def test_incomplete_day_warns_but_still_loads(env):
    env["top"] = ["000100", "000200"]
    env["full"] = {"000100": bars(TODAY, minutes("0915", 245)),     # 09:15 시작
                   "000200": bars(TODAY, minutes("0900", 300))}     # 13:59 끝
    out = mc.collect_minute(TODAY)
    assert out["rows"] == 245 + 300                                  # 적재는 그대로
    w = [m for m in warnings(env) if "불완전" in m]
    assert len(w) == 2
    assert "000100" in w[0] and "091500" in w[0]
    assert "000200" in w[1] and "135900" in w[1]


# ─────────────────────────── 결손일 보충 ───────────────────────────
def test_backfill_filters_to_requested_day_and_dedups(env):
    env["conn"] = FakeConn(tasso_rows=[("0039P0", date(2026, 9, 29))],
                           daily={"0039P0": daily_rows([P])})
    out = mc.collect_minute(TODAY)
    bf = out["tasso"]["backfill"]
    assert bf["upto"] == P and bf["target"] == 1 and bf["codes"] == 1 and bf["ok"] == 1
    assert backfilled(env) == [("0039P0", P)]
    rows = next(r for c, d, r in env["replaced"] if d == P)
    assert {r["trade_date"] for r in rows} == {P}                       # 10:00 요청의 전날 봉 제거
    assert len({r["datetime"] for r in rows}) == len(rows) == FULL_DAY  # 구간 경계 중복 제거
    assert [r["idx"] for r in rows] == list(range(FULL_DAY))
    assert bf["rows"] == FULL_DAY
    # 호출 예산 — 종목-일당 정확히 4호출 · 전부 요청일
    assert [(d, h) for _, d, h in env["past_calls"]] == [(P, h) for h in mc._SEGMENT_ENDS]
    assert out["rows"] == FULL_DAY                                      # rows = 당일 적재만
    assert not [m for m in warnings(env) if "불완전" in m]


def test_backfill_covers_all_missing_days_from_first_candidate_date(env):
    """(a) stable 전용 후보의 scan_date 당일 (b) 이미 후보였던 종목의 과거 결손일 — 둘 다 채운다."""
    env["conn"] = FakeConn(
        tasso_rows=[("STB001", date(2026, 9, 23)),      # 첫 후보일 09-23 → 09-23·09-28·09-29 결손
                    ("TOP001", date(2026, 9, 28))],     # 09-28 은 top300 으로 이미 있음 → 09-29 만
        daily={"STB001": daily_rows(["20260922", "20260923", "20260928", P]),   # 09-22 = 후보 전
               "TOP001": daily_rows(["20260923", "20260928", P])},
        minute_days={("TOP001", "20260928")})
    out = mc.collect_minute(TODAY)
    bf = out["tasso"]["backfill"]
    assert bf["target"] == 4 and bf["codes"] == 2 and bf["ok"] == 4 and bf["skip"] == {}
    # 최근 날짜 먼저 · 같은 날은 최근 후보 종목(tasso 순서) 먼저
    assert backfilled(env) == [("STB001", P), ("TOP001", P), ("STB001", "20260928"),
                               ("STB001", "20260923")]
    sql, params = next(x for x in env["conn"].executed if "JOIN daily_prices" in x[0])
    assert params["starts"] == ["2026-09-23", "2026-09-28"] and params["p_iso"] == "2026-09-29"


def test_backfill_skips_codes_whose_first_candidate_date_is_after_p(env):
    env["conn"] = FakeConn(tasso_rows=[("NEW000", date(2026, 9, 30)), ("OLD000", date(2026, 9, 29))],
                           daily={"NEW000": daily_rows([P]), "OLD000": daily_rows([P])})
    out = mc.collect_minute(TODAY)
    sql, params = next(x for x in env["conn"].executed if "JOIN daily_prices" in x[0])
    assert params["codes"] == ["OLD000"]
    assert backfilled(env) == [("OLD000", P)] and out["tasso"]["backfill"]["target"] == 1


def test_backfill_excludes_halted_days_without_calling_api(env):
    env["conn"] = FakeConn(tasso_rows=[("HALT00", date(2026, 9, 28))],
                           daily={"HALT00": [(iso("20260928"), 0), (iso(P), 7000)]})
    out = mc.collect_minute(TODAY)
    bf = out["tasso"]["backfill"]
    assert bf["target"] == 1 and bf["ok"] == 1 and bf["skip"] == {"halt": 1}
    assert {d for _, d, _ in env["past_calls"]} == {P}
    assert backfilled(env) == [("HALT00", P)]


def test_backfill_rejects_fallback_response(env):
    # 09-28 에 봉이 없는 종목(API 는 앞 날짜 09-23 봉만 준다) → 다른 날 응답 거부
    env["conn"] = FakeConn(tasso_rows=[("0039P0", date(2026, 9, 28))],
                           daily={"0039P0": daily_rows(["20260928"])})
    env["past"] = {"0039P0": fake_past_api(data_days={"20260922", "20260923"})}
    out = mc.collect_minute(TODAY)
    bf = out["tasso"]["backfill"]
    assert bf["ok"] == 0 and bf["skip"] == {"other_date": 1}
    assert backfilled(env) == []


def test_backfill_does_not_replace_with_fewer_rows(env):
    conn = FakeConn(existing={("0039P0", P): 400})
    assert mc._backfill_one(conn, "0039P0", P) == ("fewer", 0)
    assert env["replaced"] == []
    conn = FakeConn(existing={("0039P0", P): 100})     # 기존이 더 적으면 교체한다
    assert mc._backfill_one(conn, "0039P0", P) == ("ok", FULL_DAY)


def test_backfill_rejects_partial_api_failure(env):
    ok = fake_past_api()
    env["past"] = {"0039P0": lambda d, h: None if h == "140000" else ok(d, h)}
    assert mc._backfill_one(FakeConn(), "0039P0", P) == ("api_fail", 0)
    assert env["replaced"] == []


def test_backfill_cap_is_per_stock_day_recent_first_and_carries_over(env):
    codes = ["A00001", "A00002", "A00003"]
    env["conn"] = FakeConn(tasso_rows=[(c, date(2026, 9, 28)) for c in codes],
                           daily={c: daily_rows(["20260928", P]) for c in codes})
    tasso = env["conn"].tasso_rows
    bf = mc._backfill_missing_days(env["conn"], tasso, TODAY_D, cap=4)
    assert bf["target"] == 6 and bf["codes"] == 3 and bf["ok"] == 4 and bf["skip"] == {"cap": 2}
    assert backfilled(env) == [("A00001", P), ("A00002", P), ("A00003", P), ("A00001", "20260928")]
    assert len(env["past_calls"]) == 4 * len(mc._SEGMENT_ENDS)
    # 다음 EOD — 못 채운 2 종목-일이 그대로 0행이라 자동으로 이어 받는다
    bf2 = mc._backfill_missing_days(env["conn"], tasso, TODAY_D, cap=4)
    assert bf2["target"] == 2 and bf2["ok"] == 2 and bf2["skip"] == {}
    assert backfilled(env)[4:] == [("A00002", "20260928"), ("A00003", "20260928")]


def test_backfill_failed_day_is_retried_next_run(env):
    env["conn"] = FakeConn(tasso_rows=[("0039P0", date(2026, 9, 29))],
                           daily={"0039P0": daily_rows([P])})
    ok = fake_past_api()
    state = {"fail": True}
    env["past"] = {"0039P0": lambda d, h: None if state["fail"] and h == "120000" else ok(d, h)}
    bf = mc._backfill_missing_days(env["conn"], env["conn"].tasso_rows, TODAY_D, cap=60)
    assert bf["ok"] == 0 and bf["skip"] == {"api_fail": 1}
    state["fail"] = False
    bf = mc._backfill_missing_days(env["conn"], env["conn"].tasso_rows, TODAY_D, cap=60)
    assert bf["ok"] == 1 and backfilled(env) == [("0039P0", P)]


def test_backfill_default_cap_is_60_stock_days(env):
    codes = ["B%05d" % i for i in range(33)]
    env["conn"] = FakeConn(tasso_rows=[(c, date(2026, 9, 28)) for c in codes],
                           daily={c: daily_rows(["20260928", P]) for c in codes})
    out = mc.collect_minute(TODAY)
    bf = out["tasso"]["backfill"]
    assert mc.TASSO_BACKFILL_MAX == 60
    assert bf["target"] == 66 and bf["ok"] == 60 and bf["skip"] == {"cap": 6}
    assert len(env["past_calls"]) == 60 * len(mc._SEGMENT_ENDS)
    assert all(d == P for c, d in backfilled(env)[:33])         # 최근 날짜 전부 먼저


def test_backfill_exception_is_isolated_per_stock_day(env, monkeypatch):
    env["conn"] = FakeConn(tasso_rows=[("C00001", date(2026, 9, 29)), ("C00002", date(2026, 9, 29))],
                           daily={"C00001": daily_rows([P]), "C00002": daily_rows([P])})
    real = mc._backfill_one

    def flaky(conn, code, ymd):
        if code == "C00001":
            raise RuntimeError("DB boom")
        return real(conn, code, ymd)

    monkeypatch.setattr(mc, "_backfill_one", flaky)
    before = env["conn"].rollbacks
    bf = mc.collect_minute(TODAY)["tasso"]["backfill"]
    assert bf["ok"] == 1 and bf["skip"] == {"error": 1}
    assert env["conn"].rollbacks > before


def test_backfill_stage_failure_keeps_today_result(env, monkeypatch):
    env["top"] = ["000100"]
    env["conn"] = FakeConn(tasso_rows=[("0039P0", date(2026, 9, 29))])

    def boom(*a, **k):
        raise RuntimeError("missing-days query boom")

    monkeypatch.setattr(mc, "_backfill_missing_days", boom)
    out = mc.collect_minute(TODAY)
    assert out["codes"] == 2 and out["rows"] == 2 * FULL_DAY
    assert "error" in out["tasso"]["backfill"]


def test_summary_info_line_is_single(env):
    env["top"] = ["000100"]
    env["conn"] = FakeConn(tasso_rows=[("0039P0", date(2026, 9, 28))],
                           daily={"0039P0": daily_rows(["20260928", P])})
    mc.collect_minute(TODAY)
    infos = [m for lvl, m in env["log"].lines if lvl == "info"]
    assert len(infos) == 1
    assert "태쏘 후보 창 2026-09-01~2026-09-30 1종목(top300 밖 +1)" in infos[0]
    assert f"결손일 보충(~{P}) 대상 2종목-일(1종목) → 성공 2({2 * FULL_DAY}행)" in infos[0]
