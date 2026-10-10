"""
실전 보유 종목 기업행위 예고 점검(tools/exrights_morning_check.py) — 2026-10-10 사장님 (d)

DB 는 가짜 커서(SQL 문자열로 분기)로 대신한다 — 실 DB·KIS·텔레그램 호출 0.
검증 축: 제목 분류(정정 접두·공백·종속회사 제외) · 가격 불연속 · 종료 코드(0/3/2)
        · 보유 없음 경로 · --codes 경로 · --telegram(걸릴 때만 1건 · 토큰 미출력) · SELECT 만.
"""
import re
from datetime import date

import pytest

import tools.exrights_morning_check as emc


# ---------------------------------------------------------------------------
# 제목 분류
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("title, expected", [
    ("주요사항보고서(무상증자결정)", "무상증자결정"),
    ("[기재정정]주요사항보고서(유상증자결정)", "유상증자결정"),
    ("[첨부정정]주요사항보고서(유상증자결정)", "유상증자결정"),
    ("[기재정정]주요사항보고서(유무상증자결정)", "무상증자결정"),
    ("권리락              (무상증자)", "권리락"),
    ("권리락              (유상증자)", "권리락"),
    ("배당락              ", "배당락"),
    ("주식배당결정              ", "주식배당결정"),
    ("[기재정정]주식분할결정              ", "주식분할결정"),
    ("주식병합결정              ", "주식병합결정"),
    ("[기재정정]주요사항보고서(감자결정)", "감자결정"),
    ("주권매매거래정지              (무상증자)", "주권매매거래정지"),
    ("주권매매거래정지해제              (액면병합 주권 변경상장)", "주권매매거래정지"),
    ("주권 변경상장", "변경상장"),
])
def test_classify_corp_action_titles(title, expected):
    assert emc.classify_title(title) == expected


@pytest.mark.parametrize("title", [
    "유상증자결정(종속회사의주요경영사항)              ",          # 자회사 공시 — 제외
    "[기재정정]유상증자결정(종속회사의주요경영사항)              ",
    "감자결정(종속회사의주요경영사항)              ",
    "최대주주등소유주식변동신고서              ",
    "기업설명회(IR)개최(안내공시)",
    "매매거래정지및정지해제(중요내용공시)",                      # 정규식 밖(지정 정규식 유지)
    "", None,
])
def test_classify_non_corp_action_titles(title):
    assert emc.classify_title(title) is None


def test_strip_news_company_prefix_only_first_bracket():
    assert emc.strip_news_company("[퓨쳐켐] 권리락              (무상증자)").startswith("권리락")
    assert emc.strip_news_company("[가온전선] [기재정정]주식분할결정") == "[기재정정]주식분할결정"
    assert emc.classify_title(emc.strip_news_company("[코나아이] 주요사항보고서(무상증자결정)")) == "무상증자결정"


# ---------------------------------------------------------------------------
# 가격 불연속
# ---------------------------------------------------------------------------

ROWS_000500 = [  # daily_prices 실값(2026-06-26~07-01)
    ("2026-06-26", 308000, 343500, 283000, 329000),
    ("2026-06-29", 329500, 353500, 320500, 343000),
    ("2026-06-30", 240000, 244000, 210500, 233500),
]
ROWS_475460 = [
    ("2026-09-14", 8650, 8800, 8610, 8720),
    ("2026-09-15", 8700, 8780, 8090, 8290),
    ("2026-09-16", 2900, 3370, 2605, 2610),
]


def test_discontinuity_exrights_down():
    j = emc.detect_discontinuities(ROWS_000500)
    assert [x["date"] for x in j] == ["2026-06-30"]
    assert j[0]["low_ratio"] == pytest.approx(210500 / 343000)
    assert [x["date"] for x in emc.detect_discontinuities(ROWS_475460)] == ["2026-09-16"]


def test_discontinuity_merge_up():
    rows = [("d1", 1000, 1000, 1000, 1000), ("d2", 1000, 1010, 990, 1000), ("d3", 9000, 10400, 9000, 10000)]
    assert [x["date"] for x in emc.detect_discontinuities(rows)] == ["d3"]


def test_discontinuity_limit_moves_are_not_flagged():
    # 정확히 하한가(−30%)·상한가(+30%)는 한도 «안» — 경보 아님
    rows = [("d1", 100, 100, 100, 100), ("d2", 100, 100, 70, 70), ("d3", 70, 91, 70, 91)]
    assert emc.detect_discontinuities(rows) == []


def test_discontinuity_only_last_two_days_and_short_input():
    rows = [("d1", 100, 100, 100, 100), ("d2", 50, 50, 30, 30),
            ("d3", 30, 31, 29, 30), ("d4", 30, 31, 29, 30)]
    assert emc.detect_discontinuities(rows) == []        # d2 점프는 창 밖
    assert emc.detect_discontinuities(rows[:1]) == []
    assert emc.detect_discontinuities([]) == []
    assert emc.detect_discontinuities([("d1", 0, 0, 0, 0), ("d2", 1, 1, 1, 1)]) == []


# ---------------------------------------------------------------------------
# run() — 가짜 DB
# ---------------------------------------------------------------------------

class FakeCursor:
    def __init__(self, data):
        self.data = data
        self.executed = []
        self._rows = []

    def execute(self, sql, params=None):
        self.executed.append((sql, params))
        if self.data.get("raise_on_query"):
            raise RuntimeError("query failed")
        s = " ".join(sql.split())
        if "to_regclass" in s:
            self._rows = [(self.data.get("table_exists", True),)]
        elif f"FROM {emc.REAL_TABLE}" in s:
            self._rows = self.data.get("holdings", [])
        elif "FROM dart_disclosures" in s:
            code, since, as_of = params
            self._rows = [r for r in self.data.get("disc", {}).get(code, []) if since <= r[0] <= as_of]
        elif "FROM news" in s:
            code = params[0].strip("%")
            self._rows = self.data.get("news", {}).get(code, [])
        elif "FROM daily_prices" in s:
            code, _as_of, n = params
            self._rows = list(reversed(self.data.get("daily", {}).get(code, [])))[:n]
        else:
            raise AssertionError(f"예상 밖 SQL: {s[:80]}")

    def fetchone(self):
        return self._rows[0] if self._rows else None

    def fetchall(self):
        return list(self._rows)


class FakeConn:
    def __init__(self, data):
        self.cur = FakeCursor(data)
        self.closed = False

    def cursor(self):
        return self.cur

    def close(self):
        self.closed = True


def _run(data, argv, sender=None):
    conn = FakeConn(data)
    sent = []

    def _sender(cfg, text):
        sent.append((cfg, text))
        return True

    code = emc.run(argv, connect=lambda: conn, sender=sender or _sender)
    return code, conn, sent


DATA = {
    "disc": {
        "475460": [(date(2026, 9, 2), "주요사항보고서(무상증자결정)"),
                   (date(2026, 9, 15), "권리락              (무상증자)")],
        "000500": [(date(2026, 6, 16), "주요사항보고서(무상증자결정)")],   # 10-10 기준 116일 전 → 창 밖
        "005930": [(date(2026, 9, 30), "유상증자결정(종속회사의주요경영사항)              ")],
    },
    "news": {"475460": [(date(2026, 9, 15), "[와이씨켐] 권리락              (무상증자)")]},   # DART 와 중복 → 1건만
    "daily": {"000500": ROWS_000500[:2], "475460": ROWS_475460[:2], "005930": [
        ("2026-10-07", 100, 100, 100, 100), ("2026-10-08", 100, 101, 99, 100)]},
}


def test_codes_path_hit_exit3_and_dedupe(capsys):
    code, conn, sent = _run(DATA, ["--codes", "000500,475460,005930", "--as-of", "2026-10-10"])
    out = capsys.readouterr().out
    assert code == emc.EXIT_HIT
    assert "475460: ⚠️ 공시 2건" in out
    assert "000500: 걸린 것 없음" in out          # 90일 창 밖
    assert "005930: 걸린 것 없음" in out          # 종속회사 공시 제외
    assert sent == []                             # --telegram 없음 → 전송 0
    assert conn.closed
    assert all(" ".join(sql.split()).upper().startswith("SELECT") for sql, _ in conn.cur.executed)


def test_codes_path_no_hit_exit0(capsys):
    code, _conn, _sent = _run(DATA, ["--codes", "005930", "--as-of", "2026-10-10"])
    assert code == emc.EXIT_OK
    assert "결과: 걸린 것 없음" in capsys.readouterr().out


def test_historical_as_of_flags_discontinuity(capsys):
    data = dict(DATA, daily={"000500": ROWS_000500})
    code, _c, _s = _run(data, ["--codes", "000500", "--as-of", "2026-06-30"])
    out = capsys.readouterr().out
    assert code == emc.EXIT_HIT
    assert "2026-06-16 DART 주요사항보고서(무상증자결정)" in out
    assert "2026-06-30 가격 불연속" in out


def test_ledger_table_missing_is_no_holdings(capsys):
    code, conn, _s = _run({"table_exists": False}, ["--as-of", "2026-10-10"])
    assert code == emc.EXIT_OK
    assert "보유 없음" in capsys.readouterr().out
    assert len(conn.cur.executed) == 1                # to_regclass 만


def test_ledger_empty_is_no_holdings(capsys):
    code, _c, _s = _run({"table_exists": True, "holdings": []}, ["--as-of", "2026-10-10"])
    assert code == emc.EXIT_OK
    assert "미청산 0건" in capsys.readouterr().out


def test_ledger_holdings_are_checked(capsys):
    data = dict(DATA, table_exists=True, holdings=[("475460", "와이씨켐", 3, 8200.0)])
    code, _c, _s = _run(data, ["--as-of", "2026-09-16"])
    out = capsys.readouterr().out
    assert code == emc.EXIT_HIT
    assert "475460 와이씨켐 보유 3주 평단 8,200원" in out


def test_data_errors_exit2(capsys):
    def boom():
        raise RuntimeError("no db")
    assert emc.run(["--codes", "000500"], connect=boom) == emc.EXIT_DATA_ERROR
    code, conn, _s = _run({"raise_on_query": True}, ["--codes", "000500"])
    assert code == emc.EXIT_DATA_ERROR and conn.closed
    assert emc.run(["--codes", "12345"], connect=boom) == emc.EXIT_DATA_ERROR
    assert emc.run(["--as-of", "2026-13-01"], connect=boom) == emc.EXIT_DATA_ERROR


def _key_ini(tmp_path, enabled="true"):
    p = tmp_path / "key.ini"
    p.write_text(f"[TELEGRAM]\nenabled={enabled}\ntoken=SECRET-TOKEN-123\nchat_id=42\n", encoding="utf-8")
    return p


def test_telegram_sent_once_on_hit_without_printing_token(tmp_path, capsys):
    key = _key_ini(tmp_path)
    code, _c, sent = _run(DATA, ["--codes", "475460", "--as-of", "2026-10-10",
                                 "--telegram", "--key-ini", str(key)])
    out = capsys.readouterr().out
    assert code == emc.EXIT_HIT
    assert len(sent) == 1
    assert sent[0][0] == {"token": "SECRET-TOKEN-123", "chat_id": "42"}
    assert "475460" in sent[0][1]
    assert "SECRET-TOKEN-123" not in out


def test_telegram_not_sent_without_hit_or_when_disabled(tmp_path, capsys):
    key = _key_ini(tmp_path)
    code, _c, sent = _run(DATA, ["--codes", "005930", "--as-of", "2026-10-10",
                                 "--telegram", "--key-ini", str(key)])
    assert code == emc.EXIT_OK and sent == []
    key_off = _key_ini(tmp_path, enabled="false")
    code, _c, sent = _run(DATA, ["--codes", "475460", "--as-of", "2026-10-10",
                                 "--telegram", "--key-ini", str(key_off)])
    assert code == emc.EXIT_HIT and sent == []
    assert "텔레그램 생략" in capsys.readouterr().out


def test_real_table_matches_settings_ssot():
    from config.settings import real_trading_table_name
    assert emc.REAL_TABLE == real_trading_table_name("daytrading")


def test_holdings_query_rejects_unexpected_table():
    with pytest.raises(ValueError):
        emc.load_open_holdings(FakeCursor({}), "virtual_trading_records; DROP")


def test_exclude_kosdaq_subsidiary_wording():
    for t in ["주요사항보고서(감자결정)(자회사의주요경영사항)", "유상증자결정(자회사의주요경영사항)",
              "유상증자결정(종속회사의주요경영사항)"]:
        assert emc.classify_title(t) is None, t
    assert emc.classify_title("주요사항보고서(감자결정)") is not None


def test_report_header_has_run_time(capsys):
    _run(DATA, ["--codes", "005930", "--as-of", "2026-10-10"])
    assert re.search(r"기준일 2026-10-10 · 실행 \d\d:\d\d:\d\d · 대상", capsys.readouterr().out)


def test_read_telegram_config_malformed_and_percent(tmp_path, capsys):
    bad = tmp_path / "bad.ini"
    bad.write_text("[TELEGRAM]\ntoken=SECRET-TOKEN-123\nthis line has no delimiter\n", encoding="utf-8")
    assert emc.read_telegram_config(bad) is None
    out = capsys.readouterr().out
    assert "ParsingError" in out and "SECRET-TOKEN-123" not in out and "no delimiter" not in out
    pct = tmp_path / "pct.ini"
    pct.write_text("[TELEGRAM]\nenabled=true\ntoken=ab%cd\nchat_id=42\n", encoding="utf-8")
    assert emc.read_telegram_config(pct) == {"token": "ab%cd", "chat_id": "42"}
    notbool = tmp_path / "nb.ini"
    notbool.write_text("[TELEGRAM]\nenabled=maybe\ntoken=x\nchat_id=1\n", encoding="utf-8")
    assert emc.read_telegram_config(notbool) is None
    assert "ValueError" in capsys.readouterr().out


def test_exit2_with_telegram_sends_one_short_failure_notice(tmp_path, capsys):
    key = _key_ini(tmp_path)
    sent = []

    def boom():
        raise RuntimeError("host=10.0.0.1 password=hunter2")

    code = emc.run(["--codes", "000500", "--telegram", "--key-ini", str(key)], connect=boom,
                   sender=lambda cfg, text: sent.append(text) or True)
    assert code == emc.EXIT_DATA_ERROR
    assert sent == ["[기업행위 점검 실패] 데이터 오류(RuntimeError) — 수동 확인"]
    assert "hunter2" not in sent[0]


def test_query_failure_with_telegram_sends_once(tmp_path):
    key = _key_ini(tmp_path)
    code, _c, sent = _run({"raise_on_query": True}, ["--codes", "000500", "--telegram", "--key-ini", str(key)])
    assert code == emc.EXIT_DATA_ERROR
    assert len(sent) == 1 and sent[0][1].startswith("[기업행위 점검 실패] 데이터 오류(")


def test_unexpected_exception_sends_once_and_exits_2(tmp_path, monkeypatch, capsys):
    key = _key_ini(tmp_path)
    monkeypatch.setattr(emc, "format_report", lambda *a, **k: (_ for _ in ()).throw(KeyError("secret-host")))
    code, _c, sent = _run(DATA, ["--codes", "475460", "--as-of", "2026-10-10",
                                 "--telegram", "--key-ini", str(key)])
    assert code == emc.EXIT_DATA_ERROR
    assert len(sent) == 1 and sent[0][1] == "[기업행위 점검 실패] 데이터 오류(KeyError) — 수동 확인"
    assert "secret-host" not in capsys.readouterr().out


def test_failure_without_telegram_flag_sends_nothing(tmp_path):
    code, _c, sent = _run({"raise_on_query": True}, ["--codes", "000500", "--key-ini", str(_key_ini(tmp_path))])
    assert code == emc.EXIT_DATA_ERROR and sent == []


def test_failure_notice_send_error_does_not_crash(tmp_path, capsys):
    key = _key_ini(tmp_path)

    def bad_sender(cfg, text):
        raise OSError("token in url")

    def boom():
        raise RuntimeError("x")

    code = emc.run(["--codes", "000500", "--telegram", "--key-ini", str(key)], connect=boom, sender=bad_sender)
    assert code == emc.EXIT_DATA_ERROR
    out = capsys.readouterr().out
    assert "OSError" in out and "token in url" not in out


def test_no_holdings_with_telegram_stays_silent(tmp_path):
    key = _key_ini(tmp_path)
    for data in ({"table_exists": False}, {"table_exists": True, "holdings": []}):
        code, _c, sent = _run(data, ["--telegram", "--key-ini", str(key), "--as-of", "2026-10-10"])
        assert code == emc.EXIT_OK and sent == []
