"""
실전 보유 종목 기업행위 예고 점검(tools/exrights_morning_check.py) — 2026-10-10 사장님 (d)

DB 는 가짜 커서(SQL 문자열로 분기)로 대신한다 — 실 DB·KIS·텔레그램 호출 0.
검증 축: 제목 분류(정정 접두·공백·종속회사 제외) · 가격 불연속 · 종료 코드(0/3/2)
        · 보유 없음 경로 · --codes 경로 · --telegram(걸릴 때만 1건 · 토큰 미출력) · SELECT 만.
2026-10-28 ⑪ 보강: 대상 = 실전 보유 + 페이퍼 미청산 보유(실전/페이퍼·전략 칸) · 상폐·정리매매·관리종목·감자
        패턴 · «가격제한폭 초과» 블록(직전 거래일 |returns_1d|>0.30 ∩ 보유).
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
    # 10-10 사장님: 합병·분할·주식교환/이전 (DART 실제 표기)
    ("주요사항보고서(회사합병결정)", "회사합병결정"),
    ("[기재정정]주요사항보고서(회사합병결정)", "회사합병결정"),
    ("회사합병결정              ", "회사합병결정"),
    ("주요사항보고서(회사분할결정)", "회사분할결정"),
    ("[첨부정정]주요사항보고서(회사분할결정)", "회사분할결정"),
    ("회사분할합병결정", "회사분할합병결정"),
    ("[기재정정]주요사항보고서(회사분할합병결정)", "회사분할합병결정"),
    ("주요사항보고서(주식교환ㆍ이전결정)", "주식교환ㆍ이전결정"),
    ("[기재정정]주식교환ㆍ이전결정", "주식교환ㆍ이전결정"),
    ("주식교환·이전결정", "주식교환·이전결정"),                 # 가운뎃점 U+00B7 변형
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
    "주요사항보고서(교환사채권발행결정)",                        # 교환사채 발행 — 합병·교환 아님
    "[기재정정]전환청구권ㆍ신주인수권ㆍ교환청구권행사",
    "전환가액ㆍ신주인수권행사가액ㆍ교환가액의조정(안내공시)",
    "자기교환사채만기전취득결정(제10회차)",
    "본점소재지이전",                                            # 본점 이전
    "기타경영사항(자율공시)(코넥스시장이전상장결정)",
    "투자판단관련주요경영사항(이중항체MT103기술이전계약체결)",
    "기타경영사항(자율공시)(소규모합병승인이사회결의(주주총회갈음)결과보고)",  # 존속회사 쪽 후속 보고
    "회사합병결정(종속회사의주요경영사항)",                      # 자회사 합병 — 제외
    "[기재정정]주요사항보고서(회사합병결정)(자회사의주요경영사항)",
    "[기재정정]주식교환ㆍ이전결정(종속회사의주요경영사항)",
    "[기재정정]회사분할결정(종속회사의주요경영사항)",
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
            default = self.data.get("table_exists", True)
            self._rows = [(self.data.get("tables", {}).get(params[0], default),)]
        elif "MAX(date)" in s:
            self._rows = [(self.data.get("limit_prev", "2026-01-01"),)]
        elif "returns_1d" in s:
            self._rows = self.data.get("limit_rows", [])
        elif f"FROM {emc.PAPER_TABLE}" in s:
            self._rows = self.data.get("paper_holdings", [])
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
    assert "참고: 합병은 보유 종목이 존속(흡수하는) 회사면 대개 영향 없음" in out
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
    # 실전·페이퍼 원장 존재 확인(to_regclass) 2건만 — 보유가 없으면 더 묻지 않는다
    assert [p for _s, p in conn.cur.executed] == [(emc.REAL_TABLE,), (emc.PAPER_TABLE,)]


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


# ---------------------------------------------------------------------------
# 2026-10-28 ⑪ 보강 — 패턴 · 페이퍼 보유 · 가격제한폭 초과 블록
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("title, expected", [
    ("상장폐지결정", "상장폐지"),
    ("[기재정정]상장폐지결정", "상장폐지"),
    ("상장폐지사유발생", "상장폐지"),
    ("정리매매개시", "정리매매"),
    ("관리종목지정(감사의견거절)", "관리종목"),
    ("주요사항보고서(무상감자)", "감자"),
    ("주요사항보고서(감자결정)", "감자결정"),          # 기존 패턴이 먼저(낱말 그대로 유지)
])
def test_classify_delisting_and_capital_reduction_titles(title, expected):
    assert emc.classify_title(title) == expected


def test_new_patterns_still_respect_subsidiary_exclusion():
    assert emc.classify_title("감자결정(종속회사의주요경영사항)") is None
    assert emc.classify_title("상장폐지결정(자회사의주요경영사항)") is None


def test_paper_holdings_are_checked_with_label_column(capsys):
    data = dict(DATA, table_exists=True, holdings=[("475460", "와이씨켐", 3, 8200.0)],
                paper_holdings=[("475460", "와이씨켐", "rs_leader", 5, 8100.0),
                                ("005930", "삼성전자", "book_pullback_ma20", 2, 70000.0)])
    code, conn, _s = _run(data, ["--as-of", "2026-09-16"])
    out = capsys.readouterr().out
    assert code == emc.EXIT_HIT
    assert "대상 2종목" in out
    assert "475460 와이씨켐 보유 3주 평단 8,200원 [실전] · 보유 5주 평단 8,100원 [페이퍼·rs_leader]" in out
    assert "005930 삼성전자 보유 2주 평단 70,000원 [페이퍼·book_pullback_ma20]: 걸린 것 없음" in out
    paper_sql = [" ".join(q.split()) for q, _p in conn.cur.executed if f"FROM {emc.PAPER_TABLE}" in q]
    assert len(paper_sql) == 1 and "is_test = true" in paper_sql[0] and "GROUP BY b.stock_code, b.strategy" in paper_sql[0]
    assert all(" ".join(q.split()).upper().startswith("SELECT") for q, _ in conn.cur.executed)


def test_paper_only_when_real_ledger_missing(capsys):
    data = dict(DATA, tables={emc.REAL_TABLE: False, emc.PAPER_TABLE: True},
                paper_holdings=[("475460", "와이씨켐", "minervini_volume_dryup", 4, 8300.0)])
    code, _c, _s = _run(data, ["--as-of", "2026-09-16"])
    out = capsys.readouterr().out
    assert code == emc.EXIT_HIT
    assert "475460 와이씨켐 보유 4주 평단 8,300원 [페이퍼·minervini_volume_dryup]: ⚠️" in out
    assert "실전 원장 없음" in out


def test_paper_holdings_query_rejects_unexpected_table():
    with pytest.raises(ValueError):
        emc.load_paper_holdings(FakeCursor({}), "real_trading_daytrading; DROP")


LIMIT_ROWS = [  # (stock_code, returns_1d, close, corp_events 건수) — DB 10-27 실값 꼴
    ("004415", -0.34874290348742903, 803.0, 0),
    ("032685", -0.6996966632962589, 297.0, 0),
    ("215790", 3.376876876876877, 2915.0, 1),
]


def test_limit_band_block_flags_held_code(capsys):
    data = dict(DATA, table_exists=True, holdings=[],
                paper_holdings=[("004415", "서울식품우", "rs_leader", 10, 1500.0)],
                limit_prev="2026-10-27", limit_rows=LIMIT_ROWS,
                daily={"004415": [("2026-10-26", 1300, 1300, 1200, 1233), ("2026-10-27", 1200, 1210, 800, 803)]})
    code, conn, sent = _run(data, ["--as-of", "2026-10-28"])
    out = capsys.readouterr().out
    assert code == emc.EXIT_HIT
    assert "어제(2026-10-27) ±30% 밖 종목 3개 · 그중 corp_events 없는 2개" in out
    assert "🔴 가격제한폭 밖 004415 [페이퍼·rs_leader]: 2026-10-27 수익률 -34.87% · 종가 803 · corp_events 0건" in out
    assert "가격제한폭 밖 보유 0" not in out
    q = [(" ".join(s.split()), p) for s, p in conn.cur.executed if "returns_1d" in s]
    assert len(q) == 1
    sql, params = q[0]
    assert "ABS(p.returns_1d) > %s" in sql and "p.volume > 0" in sql and "FROM corp_events" in sql
    assert params[0] == "2026-10-27" and params[1] == emc.LIMIT_BAND_RETURN == 0.30
    assert set(params[2]) == set(emc.PSEUDO_TICKERS) and len(emc.PSEUDO_TICKERS) == 6


def test_limit_band_block_no_held_code_prints_zero_line(capsys):
    data = dict(DATA, table_exists=True, holdings=[("005930", "삼성전자", 1, 70000.0)],
                limit_prev="2026-10-27", limit_rows=LIMIT_ROWS)
    code, _c, _s = _run(data, ["--as-of", "2026-10-10"])
    out = capsys.readouterr().out
    assert code == emc.EXIT_OK                                   # 출력만 · 걸린 것 없음
    assert "가격제한폭 밖 보유 0 · 어제(2026-10-27) ±30% 밖 종목 3개 · 그중 corp_events 없는 2개" in out
    assert "🔴" not in out
    assert out.index("가격제한폭 밖 보유 0") < out.index("결과: 걸린 것 없음")


def test_limit_band_block_without_prev_day(capsys):
    data = dict(DATA, limit_prev=None)
    code, _c, _s = _run(data, ["--codes", "005930", "--as-of", "2026-10-10"])
    assert code == emc.EXIT_OK
    assert "가격제한폭 점검 못 함(직전 거래일 없음)" in capsys.readouterr().out


# 10-28 리뷰 후속: «지정우려»류 안내 공시는 걸림이 아니라 rc 0 «참고» 줄 (222420 · 2026-08-06)
CONCERN_TITLE = "기타시장안내(관리종목지정우려종목)              (주가 1,000원 미달)"


def test_concern_notice_is_not_hit_but_reference_line(capsys):
    assert emc.classify_title(CONCERN_TITLE) is None
    assert emc.classify_title("기타시장안내(상장폐지우려)") is None
    assert emc.classify_concern(CONCERN_TITLE) == "관리종목지정우려"
    data = dict(DATA, disc={"222420": [(date(2026, 8, 6), CONCERN_TITLE)]},
                daily={"222420": [("2026-10-26", 1000, 1010, 990, 1000), ("2026-10-27", 1000, 1010, 990, 1000)]})
    code, _c, sent = _run(data, ["--codes", "222420", "--as-of", "2026-10-28"])
    out = capsys.readouterr().out
    assert code == emc.EXIT_OK
    assert "- 222420: 걸린 것 없음 (참고 1건)" in out
    assert "    · 참고 2026-08-06 DART 기타시장안내(관리종목지정우려종목) (주가 1,000원 미달)" in out
    assert "결과: 걸린 것 없음" in out and sent == []


def test_designation_notice_is_still_hit(capsys):
    assert emc.classify_title("관리종목지정") == "관리종목"
    assert emc.classify_concern("관리종목지정") is None
    data = dict(DATA, disc={"222420": [(date(2026, 10, 20), "관리종목지정              (감사의견거절)")]})
    code, _c, _s = _run(data, ["--codes", "222420", "--as-of", "2026-10-28"])
    out = capsys.readouterr().out
    assert code == emc.EXIT_HIT
    assert "222420: ⚠️ 공시 1건" in out and "참고 " not in out
