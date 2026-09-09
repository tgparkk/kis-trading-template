# tests/collectors/test_index_collector.py
"""지수 수집기 테스트.

🔴 2026-08-17 — `reconcile_index` 4개 테스트 삭제:
   「새 DB index_daily vs 레거시 robotrader_quant.daily_prices(KS11/KQ11)」 대조였고,
   그 함수가 레거시 DB 폐기와 함께 제거되면서 같이 사라졌다.
   **없어진 함수를 계속 시험할 수는 없다.**
   (삭제: exact_match_pass · no_new_data_fail · provisional_within_1pct_pass ·
    large_discrepancy_fail · 그리고 오직 그 4개만 쓰던 DB mock 헬퍼 일체)

   ⚠️ 잃어버린 커버리지 자기신고: (b) 「FDR 미설치로 index_daily 가 조용히 비는」
      실패를 잡던 가드가 이 삭제로 사라진다. 다만 그 가드는 **레거시 DB 가 살아
      있어야** 작동했고(비교 대상이 없으면 EMPTY 로 빠진다) 지금은 legacy 게이트가
      꺼져 있어 이미 휴면이었다. 대체 감시는 `bot/system_monitor.py` 의 EOD 로그
      (`지수 {…}`)와 `core/regime/index_refresh.py` 쪽 신선도 점검이 담당한다.
"""
import collectors.index_collector as ic
from collectors.index_collector import INDEX_TICKERS


def test_index_tickers_map():
    assert INDEX_TICKERS == {"KOSPI": "KS11", "KOSDAQ": "KQ11"}


def test_legacy_reconcile_helpers_are_gone():
    """레거시 대조 심볼 재유입 방지 — 죽은 DB 에 직접 붙던 코드다."""
    for nm in ("reconcile_index", "reconcile_verdict", "_LEGACY_CODE_MAP"):
        assert not hasattr(ic, nm), f"제거된 심볼이 되살아났다: {nm}"


def test_collect_index_is_still_exported():
    """수집 자체(kis_template.index_daily 적재)는 그대로 남아야 한다."""
    assert callable(ic.collect_index)


# ════════════════════════════════════════════════════════════════════════════
# 2026-09-10 — 소스 KIS 전환 + 신선도 경보 (설계 §3·§4)
#
# 회귀 고정: 2026-09-08 에 FDR 이 «옛 6봉»을 정상 반환해 index_daily 가 09-07 에서
# 멈췄는데 로그·EOD 요약은 전부 정상이었다. 「N행 갱신」은 「오늘 것이 들어왔다」의
# 증거가 아니다 ⇒ new_rows 는 «직전 max 보다 뒤인 행 수»여야 한다.
# ════════════════════════════════════════════════════════════════════════════
import sys
from datetime import datetime

import pandas as pd
import pytest


def _kis_bar(d, close="7000.00", vol="240446"):
    return {"stck_bsop_date": d, "bstp_nmix_oprc": "6900.00", "bstp_nmix_hgpr": "7100.00",
            "bstp_nmix_lwpr": "6800.00", "bstp_nmix_prpr": close, "acml_vol": vol}


def _kis_df(dates):
    return pd.DataFrame([_kis_bar(d) for d in dates])


def _fdr_df(dates):
    idx = pd.to_datetime(dates)
    n = len(dates)
    return pd.DataFrame({"Open": [1.0] * n, "High": [1.0] * n, "Low": [1.0] * n,
                         "Close": [1.0] * n, "Volume": [1.0] * n}, index=idx)


class _FakeCursor:
    def __init__(self, db):
        self.db = db
        self._all = []
        self._one = None

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def execute(self, sql, params=None):
        self.db.executed.append((sql, params))
        head = sql.strip()
        if "FROM index_daily" in sql and "max(date)" in sql:
            self._all = [(k, v) for k, v in sorted(self.db.index_max.items()) if v]
        elif "FROM daily_prices" in sql and "max(date)" in sql:
            self._one = (self.db.oracle_max,) if self.db.oracle_max else None
        elif head.startswith("INSERT INTO index_daily"):
            self.db.upserted.append(params)
            code, d = params["index_code"], params["date"]
            if self.db.index_max.get(code) is None or d > self.db.index_max[code]:
                self.db.index_max[code] = d
        elif head.startswith("INSERT INTO collection_reconciliation"):
            self.db.recon.append(params)

    def fetchall(self):
        return self._all

    def fetchone(self):
        return self._one


class _FakeConn:
    """index_daily 최신일과 오라클 최신일만 흉내내는 DB 대역 (네트워크·DB 접속 0)."""

    def __init__(self, index_max, oracle_max):
        self.index_max = dict(index_max)
        self.oracle_max = oracle_max
        self.executed, self.upserted, self.recon = [], [], []
        self.commits = 0

    def cursor(self):
        return _FakeCursor(self)

    def commit(self):
        self.commits += 1

    def rollback(self):
        pass

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


@pytest.fixture
def wired(monkeypatch):
    """collect_index 의 외부 의존(now·DB·KIS·FDR)을 전부 대역으로 갈아끼운다."""
    state = {"fdr_calls": [], "kis_calls": [], "auth": True}

    def _install(conn, kis_by_code=None, kis_exc=None, fdr_by_ticker=None,
                 now=datetime(2026, 9, 10, 15, 49)):
        state["conn"] = conn
        monkeypatch.setattr(ic, "now_kst", lambda: now)
        monkeypatch.setattr(ic, "KisDbConnection",
                            type("_DB", (), {"get_connection": staticmethod(lambda: conn)}))
        monkeypatch.setattr(ic, "_kis_auth", lambda: state["auth"])

        def _kis(code, s, e):
            state["kis_calls"].append((code, s, e))
            if kis_exc is not None:
                raise kis_exc
            return (kis_by_code or {}).get(code)

        def _fdr(ticker, start):
            state["fdr_calls"].append((ticker, start))
            return (fdr_by_ticker or {}).get(ticker)

        monkeypatch.setattr(ic, "_kis_index_df", _kis)
        monkeypatch.setattr(ic, "_fdr_index_df", _fdr)
        return state

    return _install


def test_collect_index_uses_kis_and_never_touches_fdr(wired, monkeypatch):
    """소스가 kis 면 FinanceDataReader 를 «import 조차» 하지 않는다."""
    class _FdrStub:
        calls = []

        @staticmethod
        def DataReader(ticker, start=None):
            _FdrStub.calls.append(ticker)
            raise AssertionError("KIS 소스인데 FDR 이 불렸다")

    monkeypatch.setitem(sys.modules, "FinanceDataReader", _FdrStub)
    conn = _FakeConn({"KOSPI": "2026-09-09", "KOSDAQ": "2026-09-09"}, "2026-09-10")
    st = wired(conn, kis_by_code={"0001": _kis_df(["20260910"]), "1001": _kis_df(["20260910"])})

    res = ic.collect_index()

    assert res["src"] == "kis" and res["stale"] == []
    assert res["KOSPI"] == 1 and res["KOSDAQ"] == 1
    assert st["fdr_calls"] == [] and _FdrStub.calls == []
    assert sorted(c[0] for c in st["kis_calls"]) == ["0001", "1001"]


def test_collect_index_return_keys_are_preserved(wired):
    """EOD 요약이 f-string 으로 흘리는 두 키는 정수 그대로 남아야 한다."""
    conn = _FakeConn({"KOSPI": "2026-09-09", "KOSDAQ": "2026-09-09"}, "2026-09-10")
    wired(conn, kis_by_code={"0001": _kis_df(["20260910"]), "1001": _kis_df(["20260910"])})

    res = ic.collect_index()

    assert isinstance(res["KOSPI"], int) and isinstance(res["KOSDAQ"], int)
    assert set(res) == {"KOSPI", "KOSDAQ", "src", "stale"}


def test_collect_index_falls_back_to_fdr_when_kis_raises(wired):
    """KIS «예외»(404 → None 포함)는 폴백 사유다."""
    conn = _FakeConn({"KOSPI": "2026-09-09", "KOSDAQ": "2026-09-09"}, "2026-09-10")
    st = wired(conn, kis_exc=RuntimeError("KIS 지수 일봉 응답 없음"),
               fdr_by_ticker={"KS11": _fdr_df(["2026-09-10"]), "KQ11": _fdr_df(["2026-09-10"])})

    res = ic.collect_index()

    assert res["src"] == "fdr"
    assert sorted(c[0] for c in st["fdr_calls"]) == ["KQ11", "KS11"]
    assert res["KOSPI"] == 1 and res["KOSDAQ"] == 1


def test_collect_index_falls_back_when_auth_fails(wired):
    conn = _FakeConn({"KOSPI": "2026-09-09", "KOSDAQ": "2026-09-09"}, "2026-09-10")
    st = wired(conn, fdr_by_ticker={"KS11": _fdr_df(["2026-09-10"]),
                                    "KQ11": _fdr_df(["2026-09-10"])})
    st["auth"] = False

    assert ic.collect_index()["src"] == "fdr"


def test_collect_index_does_not_fall_back_on_empty_kis_result(wired, caplog):
    """🔴 «빈 결과»는 폴백 사유가 «아니다» — 폴백하면 죽은 FDR 의 옛 봉이 결함을 덮는다."""
    conn = _FakeConn({"KOSPI": "2026-09-05", "KOSDAQ": "2026-09-05"}, "2026-09-10")
    st = wired(conn, kis_by_code={"0001": pd.DataFrame(), "1001": pd.DataFrame()},
               fdr_by_ticker={"KS11": _fdr_df(["2026-09-10"]), "KQ11": _fdr_df(["2026-09-10"])})

    with caplog.at_level("WARNING"):
        res = ic.collect_index()

    assert res["src"] == "kis"
    assert st["fdr_calls"] == []                      # 폴백 금지
    assert res["KOSPI"] == 0 and res["KOSDAQ"] == 0
    assert res["stale"] == ["KOSDAQ", "KOSPI"]        # 0행은 판정 대상이다
    assert "[index-freshness] STALE axis=A" in caplog.text


def test_collect_index_stale_axis_a_when_index_lags_oracle(wired, caplog):
    """이번 결함 그대로: 소스가 «옛 6봉»을 주면 STALE 이어야 한다."""
    old = ["20260901", "20260902", "20260903", "20260904", "20260907"]
    conn = _FakeConn({"KOSPI": "2026-09-07", "KOSDAQ": "2026-09-07"}, "2026-09-10")
    wired(conn, kis_by_code={"0001": _kis_df(old), "1001": _kis_df(old)})

    with caplog.at_level("WARNING"):
        res = ic.collect_index()

    assert res["stale"] == ["KOSDAQ", "KOSPI"]
    assert "max=2026-09-07 ref=2026-09-10 lag=3 src=kis" in caplog.text


def test_new_rows_counts_dates_not_returned_rows(wired):
    """🔑 6행을 받아도 «새 날짜»가 0이면 new_rows == 0 (2026-09-08 회귀 고정)."""
    old = ["20260901", "20260902", "20260903", "20260904", "20260907", "20260831"]
    conn = _FakeConn({"KOSPI": "2026-09-07", "KOSDAQ": "2026-09-07"}, "2026-09-10")
    wired(conn, kis_by_code={"0001": _kis_df(old), "1001": _kis_df(old)})

    res = ic.collect_index()

    assert res["KOSPI"] == 6 and res["KOSDAQ"] == 6          # 「N행 갱신」은 6이지만
    trade_date, real_rows, new_rows, overlap, vmr, coverage, verdict = conn.recon[0]
    assert real_rows == 12 and new_rows == 0 and overlap == 12   # 새 날짜는 0이다
    assert verdict == "FAIL" and coverage == 0.0


def test_reconcile_row_contract(wired):
    """dataset='index' · ISO 날짜 · value_match_rate NULL · 정상이면 PASS/coverage 1.0."""
    conn = _FakeConn({"KOSPI": "2026-09-09", "KOSDAQ": "2026-09-09"}, "2026-09-10")
    wired(conn, kis_by_code={"0001": _kis_df(["20260909", "20260910"]),
                             "1001": _kis_df(["20260909", "20260910"])})

    ic.collect_index()

    sql = [s for s, _ in conn.executed
           if s.strip().startswith("INSERT INTO collection_reconciliation")]
    assert sql and "'index'" in sql[0]
    trade_date, real_rows, new_rows, overlap, vmr, coverage, verdict = conn.recon[0]
    assert trade_date == "2026-09-10"
    assert (real_rows, new_rows, overlap) == (4, 2, 2)
    assert vmr is None and coverage == 1.0 and verdict == "PASS"


def test_premarket_0740_does_not_false_alarm(wired, caplog):
    """🔴 07:40 오탐 회귀 — 오라클엔 오늘 행이 있고 지수는 T−1 뿐이어도 정상이다."""
    conn = _FakeConn({"KOSPI": "2026-09-09", "KOSDAQ": "2026-09-09"}, "2026-09-10")
    wired(conn, kis_by_code={"0001": _kis_df(["20260909"]), "1001": _kis_df(["20260909"])},
          now=datetime(2026, 9, 10, 7, 40))

    with caplog.at_level("WARNING"):
        res = ic.collect_index()

    assert res["stale"] == []
    assert "[index-freshness]" not in caplog.text
