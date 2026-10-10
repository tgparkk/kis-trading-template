"""최종 리뷰 I1 — 생존자 누락률: 코넥스 제외 · 상장 전 공시 제외 · (i) 공시 단위 · (ii) 회사 단위 · 분류별 내역."""
from datetime import date

from backtest.concept_axes.dt_dart_filter import surv as SV

CAL = [date(2022, 3, d) for d in (2, 3, 4, 7, 8)]
D1, D2, D3 = CAL[0], CAL[1], CAL[2]
LATE = date(2022, 3, 7)

KEYS = {("100", d) for d in CAL} | {("500", D1)} | {("600", D1)} | {("300", LATE), ("300", CAL[4])} \
    | {("700", CAL[4])}
FIRST = {"100": D1, "500": D1, "600": D1, "300": LATE, "700": CAL[4]}


def test_tagged_rate_is_per_filing_and_excludes_konex_and_prelisting():
    rows = [
        ("100", D1, "유상증자결정", "B", "K"),           # 있음
        ("200", D1, "유상증자결정", "B", "N"),           # 코넥스 → 제외
        ("300", D1, "최대주주변경", "B", "E"),           # 상장 전(첫 등장 3-07) → 제외
        ("400", D1, "유상증자결정", "B", "E"),           # 끝내 없음 → 누락
        ("500", D2, "유상증자결정", "B", "Y"),           # 상장 뒤 그날 없음 → 누락
        ("100", D2, "[기재정정]유상증자결정", "B", "K"),  # 정정 → 태그 아님
        ("100", date(2022, 3, 20), "유상증자결정", "B", "K"),  # 달력 밖 → 제외
    ]
    out = SV.survivorship(rows, CAL, KEYS, FIRST)
    assert out["n_i"] == 3 and abs(out["surv_i"] - 2 / 3) < 1e-12
    b = out["breakdown_i"]
    assert b == {"present": 1, "absent_day": 1, "never_present": 1, "later_listed": 1, "konex": 1, "out_of_cal": 1}


def test_periodic_rate_is_per_company():
    rows = [
        ("100", D1, "사업보고서 (2021.12)", "A", "Y"), ("100", D3, "분기보고서 (2022.03)", "A", "Y"),   # 있음
        ("600", D1, "사업보고서 (2021.12)", "A", "K"), ("600", D2, "분기보고서 (2022.03)", "A", "K"),   # 하루 없음 → 누락
        ("200", D1, "사업보고서 (2021.12)", "A", "N"),                                                # 코넥스
        ("300", D1, "사업보고서 (2021.12)", "A", "E"), ("300", CAL[4], "분기보고서 (2022.03)", "A", "E"),  # 상장 전 1건 빼고 있음
        ("700", D1, "사업보고서 (2021.12)", "A", "E"),                                                # 상장 전만 → 회사 제외
        ("400", D2, "사업보고서 (2021.12)", "A", "E"),                                                # 끝내 없음 → 누락
        ("800", D2, "[기재정정]사업보고서 (2021.12)", "A", "E"),                                       # 정정 → 정기 아님
        ("900", D2, "주요사항보고서(자기주식취득결정)", "B", "E"),                                      # 정기 아님 · 태그 아님
    ]
    out = SV.survivorship(rows, CAL, KEYS, FIRST)
    assert out["n_ii"] == 4 and abs(out["surv_ii"] - 0.5) < 1e-12
    assert out["breakdown_ii"] == {"present": 2, "absent_day": 1, "never_present": 1, "later_listed": 1,
                                   "konex": 1, "out_of_cal": 0}
    assert out["n_i"] == 0 and out["surv_i"] != out["surv_i"]     # 태그 공시 없음 → NaN


def test_breakdown_lines_render():
    rows = [("100", D1, "유상증자결정", "B", "K"), ("100", D1, "사업보고서 (2021.12)", "A", "K")]
    txt = SV.breakdown_text(SV.survivorship(rows, CAL, KEYS, FIRST))
    assert "있음 1" in txt and "코넥스 제외 0" in txt and "나중 상장 제외 0" in txt and "끝내 없음 0" in txt


class _Cur:
    def __init__(self, rows, log):
        self.rows, self.log = rows, log

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def execute(self, sql, params):
        self.log.append(sql)

    def fetchall(self):
        return self.rows


class _Conn:
    def __init__(self, rows):
        self.rows, self.log = rows, []

    def cursor(self):
        return _Cur(self.rows, self.log)

    def rollback(self):
        pass


def test_run_survivorship_wires_corp_cls_and_first_seen(monkeypatch):
    import pandas as pd

    from backtest.concept_axes.dt_dart_filter import run as RUN

    raw = [("200", D1, "유상증자결정", "B", "N"), ("400", D1, "유상증자결정", "B", None),
           ("100", D1, "유상증자결정", "B", "K"), ("300", D1, "최대주주변경", "B", "E")]
    conn = _Conn(raw)
    monkeypatch.setattr(RUN.LD, "load_trading_calendar", lambda c, a, b: [pd.Timestamp(d) for d in CAL])
    px = pd.DataFrame({"stock_code": ["100", "300"], "date": pd.to_datetime([D1, LATE])})
    out = RUN._survivorship(conn, px)
    assert "corp_cls" in conn.log[0]
    assert out["breakdown_i"] == {"present": 1, "absent_day": 0, "never_present": 1, "later_listed": 1,
                                  "konex": 1, "out_of_cal": 0}
    assert out["n_i"] == 2 and abs(out["surv_i"] - 0.5) < 1e-12
