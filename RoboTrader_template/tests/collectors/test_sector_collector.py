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


from datetime import datetime, timedelta  # noqa: E402

from collectors import sector_collector as sc  # noqa: E402
from collectors import sector_writer as w  # noqa: E402

TD = date(2026, 9, 7)
NOW = datetime(2026, 9, 7, 16, 5)


def _row(**kw):
    r = {"valid_from": date(2026, 1, 2), "ksic_code": None, "ksic_source": None,
         "ksic3_name": None, "corp_code": None, "ksic_checked_at": None}
    r.update(kw)
    return r


def test_fill_targets_need_corp_code_and_missing_ksic():
    """(a) 대상 = corp_code 있고 ksic_code 없는 열린 줄."""
    opens = {"AAAAA1": _row(corp_code="00000001"),
             "BBBBB1": _row(corp_code="00000002", ksic_code="264"),
             "CCCCC1": _row()}
    assert sc._fill_targets(opens, {}, NOW) == ["AAAAA1"]


def test_parent_copied_rows_are_never_dart_targets():
    """🔴 부모 코드로 자식을 묻지 않는다 — ksic_source LIKE 'parent:%' 는 대상 밖."""
    opens = {"00104K": _row(corp_code="00126380", ksic_source="parent:001040")}
    assert sc._fill_targets(opens, {}, NOW) == []


def test_nodata_within_30_days_is_not_called():
    """「없다」고 답한 지 30일이 안 됐으면 호출 0."""
    opens = {"AAAAA1": _row(corp_code="00000001")}
    assert sc._fill_targets(opens, {"AAAAA1": NOW - timedelta(days=29)}, NOW) == []


def test_nodata_older_than_30_days_is_retried():
    """🔑 「없다」는 답도 틀릴 수 있다(재무 082660 교훈) — 30일 지나면 다시 두드린다."""
    opens = {"AAAAA1": _row(corp_code="00000001")}
    assert sc._fill_targets(opens, {"AAAAA1": NOW - timedelta(days=31)}, NOW) == ["AAAAA1"]


def test_recheck_order_is_checked_at_asc_nulls_first():
    """재확인 순환 커서 = ksic_checked_at ASC NULLS FIRST · 대상은 dart/snapshot 만 ·
    corp_code 가 없으면 물을 수단이 없으므로 대상이 아니다."""
    opens = {
        "AAAAA1": _row(ksic_code="264", ksic_source="dart", corp_code="0000000A",
                       ksic_checked_at=datetime(2026, 8, 20, 9, 0)),
        "BBBBB1": _row(ksic_code="264", ksic_source="snapshot_20260807",
                       corp_code="0000000B"),
        "CCCCC1": _row(ksic_code="264", ksic_source="dart", corp_code="0000000C",
                       ksic_checked_at=datetime(2026, 8, 1, 9, 0)),
        "DDDDD1": _row(ksic_code="264", ksic_source="parent:DDDDD0",
                       corp_code="0000000D"),
        "EEEEE1": _row(ksic_code="264", ksic_source="dart"),      # corp_code 없음
    }
    assert sc._recheck_targets(opens, set(), 10) == ["BBBBB1", "CCCCC1", "AAAAA1"]
    assert sc._recheck_targets(opens, {"BBBBB1"}, 10) == ["CCCCC1", "AAAAA1"]
    assert sc._recheck_targets(opens, set(), 2) == ["BBBBB1", "CCCCC1"]


def test_recheck_rail_trips_on_count_and_ratio():
    """🔴 표본 기준 레일 — 30건 초과 «또는» 20% 초과."""
    w.check_recheck_rail(200, 30)          # 경계: 30건·15% → 통과
    with pytest.raises(RuntimeError):
        w.check_recheck_rail(200, 31)      # 건수 초과
    with pytest.raises(RuntimeError):
        w.check_recheck_rail(100, 25)      # 비율 초과(25%)
    w.check_recheck_rail(0, 0)             # 응답 0 이면 무판정


class _DummyCM:
    def __enter__(self):
        return object()

    def __exit__(self, *a):
        return False


class _FakeFetcher:
    """corp_code → 응답을 미리 정해 둔다. quota=<n> 이면 n번째 호출에서 020."""

    def __init__(self, answers=None, quota_at=None):
        self.answers = answers or {}
        self.quota_at = quota_at
        self.calls = 0
        self.status_counts = {}
        self.asked = []

    def fetch(self, corp_code):
        self.calls += 1
        self.asked.append(corp_code)
        if self.quota_at is not None and self.calls >= self.quota_at:
            raise DartQuotaExceeded("020")
        induty = self.answers.get(corp_code)
        st = "000" if induty else "013"
        self.status_counts[st] = self.status_counts.get(st, 0) + 1
        return st, ({"status": "000", "induty_code": induty} if induty
                    else {"status": "013"})


def _patch_fill(monkeypatch, open_rows, nodata=None, capture=None):
    # 🔴 `capture or {}` 는 «빈 dict»(항상 그렇다)에서 새 dict 를 만들어
    #    호출측 cap 에 아무것도 안 남는다 — 여기서 한 번만 정규화한다.
    capture = {} if capture is None else capture
    monkeypatch.setattr(w, "load_open_rows", lambda conn: dict(open_rows))
    monkeypatch.setattr(w, "load_nodata", lambda conn: dict(nodata or {}))
    monkeypatch.setattr(w, "upsert_nodata",
                        lambda conn, code: capture.setdefault("nodata", []).append(code))
    monkeypatch.setattr(sc, "append_company_raw", lambda p, payload: 1)

    def _apply(conn, responses, trade_date, rail=False, source="eod"):
        capture.setdefault("applied", []).append((list(responses), rail))
        changed = [r["stock_code"] for r in responses if r.get("ksic_code") == "999"]
        if rail:
            w.check_recheck_rail(len([r for r in responses if r.get("recheck")]), len(changed))
        return {"closed": 0, "inserted": 0, "updated": len(responses),
                "counts": {"changed": len(changed), "filled": len(responses) - len(changed),
                           "new": 0, "unchanged": 0, "skipped_past": 0},
                "changed_codes": changed, "guard": {}}

    monkeypatch.setattr(w, "apply_ksic_updates", _apply)


def test_no_dart_key_skips_fill(monkeypatch):
    """키가 없으면 EOD 를 막지 않고 스킵한다(corp_events·재무 전례)."""
    out = sc.fill_ksic(object(), TD, key="")
    assert out["skipped"] == "no_dart_key" and out["fill_calls"] == 0


def test_quota_stops_fill_and_records(monkeypatch):
    """020 이면 채우기를 중단하고 «기록»한다 — 재확인도 안 돈다."""
    cap = {}
    opens = dict(("AAAA%02d" % i, _row(corp_code="0000000%d" % i)) for i in range(5))
    _patch_fill(monkeypatch, opens, capture=cap)
    f = _FakeFetcher(quota_at=3)
    out = sc.fill_ksic(object(), TD, fetcher=f, key="k")
    assert out["quota_hit"] is True
    assert out["recheck_calls"] == 0, "한도 초과 뒤에 재확인을 또 돌리면 안 된다"


def test_nodata_response_is_recorded(monkeypatch):
    """induty_code 가 비면 nodata 기록 — 30일 뒤 재시도용 커서다."""
    cap = {}
    opens = {"AAAAA1": _row(corp_code="00000001")}
    _patch_fill(monkeypatch, opens, capture=cap)
    out = sc.fill_ksic(object(), TD, fetcher=_FakeFetcher({}), key="k")
    assert out["nodata"] == 1 and cap["nodata"] == ["AAAAA1"]


def test_recheck_budget_is_cap_minus_fill(monkeypatch):
    """재확인 예산 = 300 − 채우기 호출 수."""
    cap = {}
    opens = {}
    for i in range(3):
        opens["AAAA%02d" % i] = _row(corp_code="000000A%d" % i)
    for i in range(10):
        opens["BBBB%02d" % i] = _row(ksic_code="264", ksic_source="dart",
                                     corp_code="000000B%d" % i)
    _patch_fill(monkeypatch, opens, capture=cap)
    f = _FakeFetcher(dict(("000000A%d" % i, "264") for i in range(3)))
    out = sc.fill_ksic(object(), TD, fetcher=f, cap=8, recheck_max=200, key="k")
    assert out["fill_calls"] == 3
    assert out["recheck_calls"] == 5, "예산은 cap(8) − 채우기(3) = 5 여야 한다"


def test_recheck_rail_rolls_back_and_raises(monkeypatch):
    """🔴 값→값 31건이면 그날 재확인분 전부 롤백 + RuntimeError(부분 집계는 보존)."""
    cap = {}
    opens = dict(("BBBB%03d" % i,
                  _row(ksic_code="264", ksic_source="dart", corp_code="00000%03d" % i))
                 for i in range(40))
    _patch_fill(monkeypatch, opens, capture=cap)
    f = _FakeFetcher(dict(("00000%03d" % i, "999") for i in range(40)))
    with pytest.raises(sc.SectorStageError) as e:
        sc.fill_ksic(object(), TD, fetcher=f, key="k")
    assert e.value.partial["rail_tripped"] is True
    assert e.value.partial["recheck_calls"] == 40, "부분 집계가 보존돼야 §8-4 가 그날을 본다"
