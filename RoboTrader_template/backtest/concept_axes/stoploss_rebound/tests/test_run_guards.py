"""run — SQL 원문 = 동결 문서 · 실행 전 확인 거부 경로 전부 · preflight 금지 열 · 개봉 순서·1회 표식(가짜 연결만)."""
from __future__ import annotations

import hashlib
import json
import re
import subprocess
import textwrap
from datetime import date, datetime, time

import pytest

from backtest.concept_axes.ledger8 import exitsim8 as X
from backtest.concept_axes.stoploss_rebound import run as R


# ── SQL 원문 = 동결 문서 ──────────────────────────────────────────────────
def _doc_sql_blocks():
    text = R.PREREG.read_text(encoding="utf-8")
    blocks = [textwrap.dedent(m.group(2)) if m.group(1) else m.group(2)
              for m in re.finditer(r"^( *)```sql\n(.*?)\n\1```", text, re.S | re.M)]
    blocks = [textwrap.dedent("\n".join(ln for ln in b.splitlines())) for b in blocks]
    return blocks


def test_frozen_sql_constants_are_verbatim_from_prereg():
    blocks = _doc_sql_blocks()
    assert len(blocks) == 3
    ev = [b for b in blocks if "손절 이벤트 모집단 (E)" in b]
    lot = [b for b in blocks if "T3 로트 모집단 (L)" in b]
    ctl = [b for b in blocks if b.startswith("SELECT DISTINCT b.stock_code")]
    assert ev == [R.EVENT_SQL] and lot == [R.LOT_SQL] and ctl == [R.CONTROL_SQL]
    assert R.LOT_CAP_LINE in R.LOT_SQL


def test_frozen_doc_blob_and_md5():
    assert R.prereg_blob() == R.PREREG_FROZEN_BLOB
    assert hashlib.md5(R.PREREG.read_bytes()).hexdigest() == R.PREREG_FROZEN_MD5


def test_sql_wrappers_keep_original_text():
    assert R.inner(R.EVENT_SQL) == R.EVENT_SQL[:-1]
    assert R.inner(R.EVENT_SQL) in R.wrap(R.EVENT_SQL, "count(*)")
    body = R.inner(R.LOT_SQL)
    assert ";" not in body.splitlines()[-1] and body.splitlines()[-1].endswith("§12-4 ② 전제(10-16 KOSPI 행 존재)")
    unc = R.lot_sql_uncapped()
    assert R.LOT_CAP_LINE not in unc and unc.replace("  ;", R.LOT_CAP_LINE) == R.LOT_SQL


def test_named_params_keep_casts_and_escape_percent():
    q = R.named(R.CONTROL_SQL)
    assert ":g" not in q and ":c" not in q and re.search(r"(?<!:):t\b", q) is None
    assert q.count("::date") == R.CONTROL_SQL.count("::date") and "'손절 실행%%'" in q
    assert q.count("%(g)s") == 2 and q.count("%(c)s") == 1


# ── 정적 가드 ───────────────────────────────────────────────────────────
def _checks(**kw):
    base = dict(blob_of=lambda: R.PREREG_FROZEN_BLOB, dirty_of=lambda: [], d_asof=date(2026, 10, 16), unresolved=())
    base.update(kw)
    return R.static_checks("sealed", **base)


def test_static_checks_pass_when_all_good():
    R.enforce(_checks())


@pytest.mark.parametrize("kw,needle", [
    (dict(blob_of=lambda: "0" * 40), "동결 blob"),
    (dict(dirty_of=lambda: [" M backtest/concept_axes/stoploss_rebound/run.py"]), "미커밋"),
    (dict(dirty_of=lambda: ["?? backtest/concept_axes/stoploss_rebound/results/x.md"]), "미커밋"),
    (dict(d_asof=date(2026, 10, 15)), "D_asof"),
    (dict(unresolved=("Q1",)), "해석 질문"),
])
def test_static_checks_each_refusal(kw, needle):
    with pytest.raises(R.Refuse) as e:
        R.enforce(_checks(**kw))
    assert e.value.code == R.EXIT_STATIC and needle in e.value.reason


def test_static_checks_git_failure_is_refusal(monkeypatch):
    monkeypatch.setattr(R, "_git", lambda *a: subprocess.CompletedProcess(a, 128, "", "fatal"))
    with pytest.raises(R.Refuse):
        R.enforce(R.static_checks("sealed", unresolved=()))


def test_unresolved_questions_block_sealed_now():
    assert R.UNRESOLVED                                  # 확정 전에는 실제 봉인·개봉이 막혀 있어야 한다
    with pytest.raises(R.Refuse):
        R.enforce(R.static_checks("sealed", blob_of=lambda: R.PREREG_FROZEN_BLOB, dirty_of=lambda: []))


def test_check_rules_mismatch_refuses():
    rules = {s: X.ExitRules(tp, sl, mh) for s, (tp, sl, mh) in R.EXPECT_RULES.items()}
    R.check_rules(rules)
    rules["book_pullback_ma5"] = X.ExitRules(0.15, 0.05, 30)
    with pytest.raises(R.Refuse) as e:
        R.check_rules(rules)
    assert e.value.code == R.EXIT_RULES


# ── 가짜 연결 ───────────────────────────────────────────────────────────
class FakeCursor:
    def __init__(self, conn):
        self.conn = conn
        self.description = None
        self._rows = []
        self.fetched = False

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def execute(self, sql, args=None):
        self.conn.sqls.append(sql)
        cols, rows = self.conn.answer(sql, args)
        self.description = [(c,) for c in cols]
        self._rows = rows

    def fetchall(self):
        self.fetched = True
        self.conn.fetched += 1
        return self._rows


class FakeConn:
    def __init__(self, answer):
        self.answer = answer
        self.sqls = []
        self.fetched = 0

    def cursor(self):
        return FakeCursor(self)


def test_guarded_fetch_refuses_forbidden_columns_before_fetch():
    conn = FakeConn(lambda s, a: (["id", "stop_fill_price"], [(1, 99.0)]))
    with pytest.raises(R.Refuse):
        R.guarded_fetch(conn, "SELECT …")
    assert conn.fetched == 0
    conn = FakeConn(lambda s, a: (["id", "Close"], [(1, 99.0)]))
    with pytest.raises(R.Refuse):
        R.guarded_fetch(conn, "SELECT …")
    conn = FakeConn(lambda s, a: (["strategy", "n"], [("x", 1)]))
    assert R.guarded_fetch(conn, "SELECT …") == [("x", 1)]


def _preflight_answer(kospi_rows: int, have_codes):
    def answer(sql, args):
        if "max(date) AS d" in sql:
            return ["d"], [("2026-10-08",)]
        if sql.startswith("SELECT strategy, count(*) AS n") and "손절 이벤트" in sql:
            return ["strategy", "n"], [("book_pullback_ma20", 2)]
        if sql.startswith("SELECT count(*) AS n, count(DISTINCT id)"):
            return ["n", "n_id"], [(5, 5)]
        if sql.startswith("SELECT strategy, count(*) AS n"):
            return ["strategy", "n"], [("book_pullback_ma5", 5)]
        if sql.startswith("SELECT DISTINCT stock_code FROM (") and "손절 이벤트" in sql:
            return ["stock_code"], [("000001",)]
        if sql.startswith("SELECT DISTINCT stock_code FROM ("):
            return ["stock_code"], [("000002",)]
        if "stock_code = 'KOSPI' AND date = %s" in sql:
            return ["n"], [(kospi_rows,)]
        if sql.startswith("SELECT DISTINCT stock_code FROM daily_prices"):
            return ["stock_code"], [(c,) for c in have_codes]
        if sql.startswith("SELECT count(DISTINCT stock_code) AS n"):
            return ["n"], [(2,)]
        raise AssertionError(f"예상 밖 질의: {sql[:80]}")
    return answer


FORBID_RE = re.compile(r"\b(" + "|".join(sorted(R.FORBIDDEN_COLS)) + r")\b", re.I)


def _outer_select(sql: str) -> str:
    return sql.split(" FROM", 1)[0]


@pytest.mark.parametrize("kospi,codes,code", [(0, [], R.EXIT_DATA), (1, ["000001"], R.EXIT_DATA),
                                             (1, ["000001", "000002"], R.EXIT_OK)])
def test_preflight_counts_only_and_refusal_codes(monkeypatch, kospi, codes, code):
    monkeypatch.setattr(R, "static_checks", lambda stage: [("동결 blob", True, "ok")])
    monkeypatch.setattr(R, "fetch", lambda *a, **k: (_ for _ in ()).throw(AssertionError("preflight 에서 fetch 금지")))
    conn = FakeConn(_preflight_answer(kospi, codes))
    assert R.run_preflight(conn) == code
    for sql in conn.sqls:
        assert not FORBID_RE.search(_outer_select(sql)), sql[:120]


def test_preflight_reports_static_failure_code(monkeypatch):
    monkeypatch.setattr(R, "static_checks", lambda stage: [("미해결 해석 질문 0", False, "Q1")])
    conn = FakeConn(_preflight_answer(1, ["000001", "000002"]))
    assert R.run_preflight(conn) == R.EXIT_STATIC


def test_preconditions_static_refusal_happens_before_any_db(monkeypatch):
    monkeypatch.setattr(R, "static_checks", lambda stage: [("동결 blob", False, "다름")])
    conn = FakeConn(lambda s, a: (_ for _ in ()).throw(AssertionError("DB 질의 금지")))
    with pytest.raises(R.Refuse) as e:
        R.preconditions(conn, "sealed")
    assert e.value.code == R.EXIT_STATIC and conn.sqls == []


@pytest.mark.parametrize("kospi,codes", [(0, ["000001", "000002"]), (1, ["000001"])])
def test_preconditions_require_d_asof_rows(monkeypatch, kospi, codes):
    monkeypatch.setattr(R, "static_checks", lambda stage: [])
    conn = FakeConn(_preflight_answer(kospi, codes))
    with pytest.raises(R.Refuse) as e:
        R.preconditions(conn, "open")
    assert e.value.code == R.EXIT_DATA
    R.preconditions(FakeConn(_preflight_answer(1, ["000001", "000002"])), "open")


# ── 적재 가드 ───────────────────────────────────────────────────────────
def test_load_lots_refuses_duplicate_lot_rows(monkeypatch):
    ts = datetime(2026, 8, 10, 10, 0)
    rows = [(1, "book_pullback_ma5", "000001", ts, 7, ts, "손절 실행"), (1, "book_pullback_ma5", "000001", ts, 8, ts, "x")]
    monkeypatch.setattr(R, "fetch", lambda conn, sql, args=None: rows)
    with pytest.raises(R.Refuse) as e:
        R.load_lots(None)
    assert e.value.code == R.EXIT_DATA


def test_load_all_refuses_sample_n_mismatch(monkeypatch):
    monkeypatch.setattr(R, "load_calendar", lambda conn: [R.D_ASOF])
    monkeypatch.setattr(R, "load_events", lambda conn, with_price: [])
    monkeypatch.setattr(R, "load_lots", lambda conn, sql=R.LOT_SQL: [])
    monkeypatch.setattr(R, "fetch", lambda conn, sql, args=None: [(3,)])
    with pytest.raises(R.Refuse) as e:
        R.load_all(None, "sealed")
    assert e.value.code == R.EXIT_DATA and "표본 N" in e.value.reason


def test_load_events_sealed_projection_has_no_price(monkeypatch):
    seen = []
    monkeypatch.setattr(R, "fetch", lambda conn, sql, args=None: seen.append(sql) or [])
    R.load_events(None, with_price=False)
    R.load_events(None, with_price=True)
    assert "stop_fill_price" not in _outer_select(seen[0]) and "stop_fill_price" in _outer_select(seen[1])


# ── 개봉 가드 · 1회 표식 ─────────────────────────────────────────────────
@pytest.fixture()
def opened(tmp_path, monkeypatch):
    monkeypatch.setattr(R, "SEALED_MD", tmp_path / "sealed_report.md")
    monkeypatch.setattr(R, "META", tmp_path / "run_meta.json")
    monkeypatch.setattr(R, "_git", lambda *a: subprocess.CompletedProcess(a, 0, "", ""))
    monkeypatch.setattr(R, "fingerprint", lambda conn, codes, mk: {"vtr": "x"})
    D = type("D", (), {"minutes": {}})()
    return tmp_path, D


def test_open_guard_requires_sealed_report(opened):
    tmp, D = opened
    with pytest.raises(R.Refuse) as e:
        R.open_guard(None, D, dict(codes=[]))
    assert e.value.code == R.EXIT_ORDER


def test_open_guard_requires_sealed_report_committed(opened, monkeypatch):
    tmp, D = opened
    (tmp / "sealed_report.md").write_text("x", encoding="utf-8")
    monkeypatch.setattr(R, "_git", lambda *a: subprocess.CompletedProcess(a, 1, "", "error"))
    with pytest.raises(R.Refuse) as e:
        R.open_guard(None, D, dict(codes=[]))
    assert e.value.code == R.EXIT_ORDER


def test_open_guard_marker_and_fingerprint(opened):
    tmp, D = opened
    (tmp / "sealed_report.md").write_text("x", encoding="utf-8")
    (tmp / "run_meta.json").write_text(json.dumps({}), encoding="utf-8")
    with pytest.raises(R.Refuse) as e:
        R.open_guard(None, D, dict(codes=[]))                      # 봉인 기록 없음
    assert e.value.code == R.EXIT_ORDER
    (tmp / "run_meta.json").write_text(json.dumps({"sealed": {"fp": {"vtr": "y"}}}), encoding="utf-8")
    with pytest.raises(R.Refuse) as e:
        R.open_guard(None, D, dict(codes=[]))                      # 지문 다름 = 소급 수정
    assert e.value.code == R.EXIT_FINGERPRINT
    (tmp / "run_meta.json").write_text(json.dumps({"sealed": {"fp": {"vtr": "x"}}}), encoding="utf-8")
    m = R.open_guard(None, D, dict(codes=[]))
    R.mark_open(m)
    with pytest.raises(R.Refuse) as e:
        R.open_guard(None, D, dict(codes=[]))                      # 두 번째 개봉
    assert e.value.code == R.EXIT_ORDER and "1회 실행" in e.value.reason


def test_main_refusal_returns_code(monkeypatch):
    class C:
        def close(self):
            pass

    monkeypatch.setattr(R, "connect", lambda: C())
    monkeypatch.setattr(R, "run_sealed", lambda conn: (_ for _ in ()).throw(R.Refuse(R.EXIT_STATIC, "x")))
    assert R.main(["--stage", "sealed"]) == R.EXIT_STATIC
    monkeypatch.setattr(R, "connect", lambda: (_ for _ in ()).throw(RuntimeError("no db")))
    assert R.main(["--stage", "preflight"]) == R.EXIT_DATA


def test_fidelity_date_tolerance_uses_kospi_days():
    cal = [date(2026, 9, d) for d in (1, 2, 3, 4, 7, 8)]
    D = R.Data(cal + [R.D_ASOF], [], [], {}, {}, {}, {}, {}, {}, {})
    assert D.tdist(date(2026, 9, 4), date(2026, 9, 7)) == 1          # 주말 건너 1 거래일
    assert D.tdist(date(2026, 9, 3), date(2026, 9, 7)) == 2
    assert time(9, 5) == R.LT.EARLY_FILL


def _units_for_asym(ev_x, ev_n, c_x, c_n):
    from backtest.concept_axes.stoploss_rebound import lots as LT
    w = LT.Win(True, 10)
    ev = R.Event(1, "s", "000001", datetime(2026, 8, 10, 10), 1)
    out = []
    for i in range(ev_n):
        cs = [f"c{i}_{j}" for j in range(c_n // ev_n)]
        out.append(R.EvUnit(ev, 10, "X2" if i < ev_x else "", w, cs, {c: w for c in cs}, [], {}, 100.0))
    k = 0
    for u in out:
        for c in u.controls:
            if k < c_x:
                u.c_excl[c] = "X2"
                k += 1
    return out


@pytest.mark.parametrize("ev_x,c_x,warn", [(5, 3, False), (6, 3, True), (5, 2, True)])
def test_asymmetry_warning_is_strictly_above_two_points(ev_x, c_x, warn):
    s = R.exclusion_summary(_units_for_asym(ev_x, 100, c_x, 100))
    assert s["ev_den"] == 100 and s["c_den"] == 100 and s["warn"] is warn
