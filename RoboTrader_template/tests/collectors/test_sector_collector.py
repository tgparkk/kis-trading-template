"""섹터 수집기 테스트 (T4 · T5 · T6 · T7-b · T8 · T14). DB 를 쓰지 않는다."""
import os
import sys
from datetime import date

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from collectors import krx_desc_cache as kdc  # noqa: E402

HEADER = "Code,Name,Market,Sector,Industry,Products,ListingDate,SettleMonth,Representative,HomePage,Region"


def _csv(rows):
    """rows: [(code, name, market, sector, industry)] → 캐시 CSV 바이트."""
    body = [HEADER]
    for code, name, market, sector, industry in rows:
        body.append("%s,%s,%s,%s,%s,제품,2000-01-01,12월,대표,http://x,서울"
                    % (code, name, market, sector, industry))
    return ("\n".join(body) + "\n").encode("utf-8")


def _fake_fetcher(available):
    """available: {날짜 ISO: bytes} — 그 밖의 날짜는 404."""
    def _fn(url):
        key = url.rsplit("/", 1)[-1].replace(".csv", "")
        if key in available:
            return 200, available[key]
        return 404, b""
    return _fn


def test_backoff_records_publish_date_as_source_asof():
    """404 면 하루씩 후퇴하고, «실제로 읽은 파일의 날짜»가 source_asof 다."""
    raw = _csv([("005930", "삼성전자", "KOSPI", "", "반도체 제조업")])
    asof, body = kdc.fetch_desc_csv(date(2026, 9, 7),
                                    fetcher=_fake_fetcher({"2026-09-04": raw}))
    assert asof == date(2026, 9, 4)
    assert body == raw


def test_eighth_day_404_fails():
    """7일 후퇴까지 없으면 실패 — 조용히 빈 명부를 만들지 않는다."""
    with pytest.raises(RuntimeError) as e:
        kdc.fetch_desc_csv(date(2026, 9, 7), fetcher=_fake_fetcher({}))
    assert "2026-08-31" in str(e.value), "8번째 시도(7일 후퇴)까지 기록돼야 한다"


def test_konex_rows_are_ignored():
    """KONEX 는 U_all 밖이라 적재·검증 대상이 아니다."""
    raw = _csv([("005930", "삼성전자", "KOSPI", "", "반도체 제조업"),
                ("900001", "코넥스사", "KONEX", "", "기타")])
    rows, dropped = kdc.parse_desc_csv(raw)
    assert [r["stock_code"] for r in rows] == ["005930"]
    assert dropped["konex"] == 1


def test_kosdaq_global_folds_into_kosdaq_group():
    """소형 세그먼트(GLOBAL 50)는 KOSDAQ 묶음에 합쳐 30건 오차로 흔들리지 않게 한다."""
    raw = _csv([("035720", "카카오", "KOSPI", "", "포털"),
                ("247540", "에코프로", "KOSDAQ", "중견기업부", "전지"),
                ("196170", "알테오젠", "KOSDAQ GLOBAL", "우량기업부", "의약품")])
    rows, _ = kdc.parse_desc_csv(raw)
    assert kdc.market_counts(rows) == {"KOSPI": 1, "KOSDAQ": 2}


def test_scale_floor_blocks_partial_kosdaq(tmp_path, monkeypatch):
    """🔴 KOSDAQ 묶음만 20건 오면 한 행도 쓰지 않는다 — 보관 파일도 안 만든다."""
    monkeypatch.setattr(kdc, "ARCHIVE_DIR", str(tmp_path))
    rows = [("00%04d" % i, "n%d" % i, "KOSPI", "", "업종") for i in range(900)]
    rows += [("01%04d" % i, "m%d" % i, "KOSDAQ", "중견기업부", "업종") for i in range(20)]
    raw = _csv(rows)
    with pytest.raises(RuntimeError) as e:
        kdc.load_desc(date(2026, 9, 7), {"KOSPI": 943, "KOSDAQ": 1822},
                      fetcher=_fake_fetcher({"2026-09-07": raw}))
    assert "KOSDAQ" in str(e.value)
    assert os.listdir(str(tmp_path)) == [], "하한 미달인데 보관 파일이 생겼다"


def test_scale_floor_exempts_empty_baseline(tmp_path, monkeypatch):
    """기존 0건은 면제 — 아니면 최초 수집이 영원히 불가능하다."""
    monkeypatch.setattr(kdc, "ARCHIVE_DIR", str(tmp_path))
    raw = _csv([("005930", "삼성전자", "KOSPI", "", "반도체 제조업")])
    out = kdc.load_desc(date(2026, 9, 7), {}, fetcher=_fake_fetcher({"2026-09-07": raw}))
    assert out["source_asof"] == date(2026, 9, 7)
    assert len(out["rows"]) == 1
    assert os.path.basename(out["archive"]) == "krx_desc_2026-09-07.csv.gz"
    assert os.path.exists(out["archive"])


def test_zero_rows_fails():
    """0건은 성공이 아니다."""
    with pytest.raises(RuntimeError):
        kdc.parse_desc_csv((HEADER + "\n").encode("utf-8"))


def test_archive_false_writes_no_file(tmp_path, monkeypatch):
    """🔴 `--dry-run` 경로 — gz 를 안 쓰고 archive 는 None 이다.
    (로그 포맷이 basename(None) 으로 죽지 않는지도 여기서 걸린다)"""
    monkeypatch.setattr(kdc, "ARCHIVE_DIR", str(tmp_path))
    raw = _csv([("005930", "삼성전자", "KOSPI", "", "반도체 제조업")])
    out = kdc.load_desc(date(2026, 9, 7), {}, fetcher=_fake_fetcher({"2026-09-07": raw}),
                        archive=False)
    assert out["archive"] is None
    assert os.listdir(str(tmp_path)) == [], "dry-run 인데 보관 파일이 생겼다"
    assert len(out["rows"]) == 1 and out["source_asof"] == date(2026, 9, 7)


from collectors import dart_company_fetcher as dcf  # noqa: E402
from collectors.dart_financial_fetcher import DartBlocked, DartQuotaExceeded  # noqa: E402


class _Resp:
    def __init__(self, status_code=200, js=None):
        self.status_code = status_code
        self._js = js or {}

    def json(self):
        return self._js


class _Sess:
    def __init__(self, seq):
        self.seq = list(seq)
        self.gets = []
        self.closed = 0

    def get(self, url, params=None, timeout=None):
        self.gets.append(params)
        nxt = self.seq.pop(0)
        if isinstance(nxt, Exception):
            raise nxt
        return nxt

    def close(self):
        self.closed += 1


def test_company_fetcher_raises_on_quota(monkeypatch):
    """020(한도초과)은 «예외»로 올린다 — 삼키면 조용한 빈 수집이 성공으로 보인다."""
    monkeypatch.setattr(dcf.time, "sleep", lambda s: None)
    f = dcf.DartCompanyFetcher("k")
    f.session = _Sess([_Resp(200, {"status": "020", "message": "한도초과"})])
    with pytest.raises(DartQuotaExceeded):
        f.fetch("00126380")


def test_company_fetcher_blocks_after_three_transport_failures(monkeypatch):
    """전송 실패 3연속 = IP 차단으로 판단(재무 fetcher 와 같은 규약)."""
    import requests
    monkeypatch.setattr(dcf.time, "sleep", lambda s: None)
    f = dcf.DartCompanyFetcher("k")
    f.session = _Sess([requests.exceptions.ConnectionError(),
                       requests.exceptions.Timeout(),
                       requests.exceptions.ConnectionError()])
    monkeypatch.setattr(dcf.requests, "Session", lambda: f.session)
    with pytest.raises(DartBlocked):
        f.fetch("00126380")


def test_company_fetcher_returns_induty_code(monkeypatch):
    """정상 응답은 (status, payload) 로 그대로 돌려준다 — 파싱은 호출측 몫."""
    monkeypatch.setattr(dcf.time, "sleep", lambda s: None)
    f = dcf.DartCompanyFetcher("k")
    f.session = _Sess([_Resp(200, {"status": "000", "induty_code": "2611"})])
    status, js = f.fetch("00126380")
    assert status == "000" and js["induty_code"] == "2611"
    assert f.calls == 1 and f.status_counts["000"] == 1


def test_append_company_raw_returns_line_numbers(tmp_path):
    """§5-4 재생성의 원료 — 줄 번호가 1부터 증가해야 한다."""
    p = str(tmp_path / "dart_company_2026-09-07.jsonl")
    assert dcf.append_company_raw(p, {"a": 1}) == 1
    assert dcf.append_company_raw(p, {"a": 2}) == 2
    with open(p, encoding="utf-8") as fh:
        assert len(fh.readlines()) == 2
