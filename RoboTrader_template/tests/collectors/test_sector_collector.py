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
    """corp_code → 응답을 미리 정해 둔다. quota=<n> 이면 n번째 호출에서 020.

    fails           : 그 corp_code 는 ("HTTP_FAIL", {}) — 진짜 fetcher 가 재시도를
                      소진했을 때 돌려주는 토큰이다(013「없다」와 «다른» 것이다).
    calls_per_fetch : fetch 한 번이 먹는 «호출» 수(진짜 fetcher 는 재시도로 최대 6).
    """

    def __init__(self, answers=None, quota_at=None, fails=None, calls_per_fetch=1):
        self.answers = answers or {}
        self.quota_at = quota_at
        self.fails = set(fails or ())
        self.calls_per_fetch = calls_per_fetch
        self.calls = 0
        self.fetches = 0
        self.status_counts = {}
        self.asked = []

    def _bump(self, st):
        self.status_counts[st] = self.status_counts.get(st, 0) + 1

    def fetch(self, corp_code):
        self.calls += self.calls_per_fetch
        self.fetches += 1
        self.asked.append(corp_code)
        if self.quota_at is not None and self.calls >= self.quota_at:
            raise DartQuotaExceeded("020")
        if corp_code in self.fails:
            self._bump("HTTP_FAIL")
            return "HTTP_FAIL", {}
        induty = self.answers.get(corp_code)
        st = "000" if induty else "013"
        self._bump(st)
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
    """020 이면 채우기를 중단하고 «기록»한다 — 재확인도 안 돈다.

    🔴 fix 1 (#3) — 픽스처에 (b) «대상»이 없으면 recheck_calls==0 은 quota 와
       무관하게 «자동»으로 나온다(공허한 단언). 대상 10건을 넣어 0 이 오직 quota
       때문임을 증명한다.
    """
    cap = {}
    opens = dict(("AAAA%02d" % i, _row(corp_code="0000000%d" % i)) for i in range(5))
    for i in range(10):
        opens["BBBB%02d" % i] = _row(ksic_code="264", ksic_source="dart",
                                     corp_code="000000B%d" % i)
    assert len(sc._recheck_targets(opens, set(), 200)) == 10, \
        "픽스처에 재확인 대상이 있어야 단언이 공허하지 않다"
    _patch_fill(monkeypatch, opens, capture=cap)
    f = _FakeFetcher(quota_at=3)
    out = sc.fill_ksic(object(), TD, fetcher=f, key="k")
    assert out["quota_hit"] is True
    assert out["recheck_targets"] == 0 and out["recheck_calls"] == 0, \
        "한도 초과 뒤에 재확인을 또 돌리면 안 된다"


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


# ---------------------------------------------------------------- Task 5 fix 1
# #1 실패는 「없다」가 아니다 · #2 예산·연속실패 · #4 레일 실배선 · #5 summary 보존


def test_http_fail_is_not_recorded_as_nodata(monkeypatch):
    """🔴 #1 — 실패(HTTP_FAIL)를 nodata 로 적으면 30일 동안 조용해져 «고장을 감춘다».
    행은 그대로 두고 건수만 센다 — 내일 다시 두드린다."""
    cap = {}
    opens = {"AAAAA1": _row(corp_code="00000001")}
    _patch_fill(monkeypatch, opens, capture=cap)
    f = _FakeFetcher(fails={"00000001"})
    out = sc.fill_ksic(object(), TD, fetcher=f, key="k")
    assert out["fetch_failed"] == 1
    assert out["nodata"] == 0 and "nodata" not in cap, "실패를 「없다」로 적었다"
    assert "applied" not in cap, "실패는 행을 만지지 않는다"


def test_unexpected_status_is_not_recorded_as_nodata(monkeypatch):
    """🔴 #1 — 예상외 status(013·000 아님)도 실패다. 같은 규칙을 받는다."""
    cap = {}
    opens = {"AAAAA1": _row(corp_code="00000001")}
    _patch_fill(monkeypatch, opens, capture=cap)

    class _OddFetcher(_FakeFetcher):
        def fetch(self, corp_code):
            self.calls += 1
            self.fetches += 1
            self._bump("100")
            return "100", {"status": "100", "message": "필수값 누락"}

    out = sc.fill_ksic(object(), TD, fetcher=_OddFetcher(), key="k")
    assert out["fetch_failed"] == 1 and out["nodata"] == 0 and "nodata" not in cap


def test_http_fail_in_recheck_does_not_advance_checked_at(monkeypatch):
    """🔴 #1 — (b) 에서 실패한 종목은 응답에 넣지 않는다. 넣으면 ksic_checked_at 이
    전진해 «못 물어본» 종목이 큐 맨 뒤로 밀린다(다음 날 재시도가 사라진다)."""
    cap = {}
    opens = {"BBBBB1": _row(ksic_code="264", ksic_source="dart", corp_code="0000000B"),
             "CCCCC1": _row(ksic_code="264", ksic_source="dart", corp_code="0000000C")}
    _patch_fill(monkeypatch, opens, capture=cap)
    f = _FakeFetcher({"0000000C": "264"}, fails={"0000000B"})
    out = sc.fill_ksic(object(), TD, fetcher=f, key="k")
    assert out["fetch_failed"] == 1 and out["recheck_calls"] == 2
    applied = [r for resp, _rail in cap["applied"] for r in resp]
    assert [r["stock_code"] for r in applied] == ["CCCCC1"], \
        "실패한 BBBBB1 이 응답에 섞이면 커서가 전진한다"


def test_recheck_checks_budget_before_every_call(monkeypatch):
    """🔴 #2 — fetch 하나가 내부 재시도로 최대 6호출을 쓴다. 예산을 «대상 수»로만
    잡으면 200종목 × 6 = 1,200 호출이 나가 DART ≤300/일 을 깬다 —
    매 호출 전 검사가 최종 방어선이다."""
    cap = {}
    opens = dict(("BBBB%02d" % i,
                  _row(ksic_code="264", ksic_source="dart", corp_code="000000B%d" % i))
                 for i in range(10))
    _patch_fill(monkeypatch, opens, capture=cap)
    f = _FakeFetcher(dict(("000000B%d" % i, "264") for i in range(10)), calls_per_fetch=3)
    out = sc.fill_ksic(object(), TD, fetcher=f, cap=6, key="k")
    assert f.fetches == 2, "cap 6 = 3호출짜리 fetch 2번(루프 내 검사가 없으면 6번 = 18호출)"
    assert out["recheck_calls"] == 6
    assert out["cap_hit"] is True, "무징후 절단 금지 — 상한에 걸린 사실이 summary 에 있어야 한다"


def test_recheck_stops_after_consecutive_fetch_failures(monkeypatch):
    """🔴 #2 — 연속 실패 5회면 그날 재확인을 멈춘다(예산을 태우며 조용히 실패하지 않는다)."""
    cap = {}
    opens = dict(("BBBB%02d" % i,
                  _row(ksic_code="264", ksic_source="dart", corp_code="000000B%d" % i))
                 for i in range(10))
    _patch_fill(monkeypatch, opens, capture=cap)
    f = _FakeFetcher(fails=set("000000B%d" % i for i in range(10)))
    out = sc.fill_ksic(object(), TD, fetcher=f, key="k")
    assert sc.FETCH_FAIL_STREAK_MAX == 5
    assert f.fetches == 5 and out["fetch_failed"] == 5
    assert out["fetch_fail_stop"] is True


def test_writer_exception_is_promoted_to_stage_error_with_partial(monkeypatch):
    """🔴 #5 — DB 예외도 summary 를 들고 올라간다(스펙 §4 「어떤 경우에도」).
    예외만 던지면 그날의 fill_calls·nodata 가 통째로 사라져 게이트가 그날을 못 본다."""
    cap = {}
    opens = {"AAAAA1": _row(corp_code="00000001")}
    _patch_fill(monkeypatch, opens, capture=cap)

    def _boom(*a, **kw):
        raise ValueError("DB down")

    monkeypatch.setattr(w, "apply_ksic_updates", _boom)
    f = _FakeFetcher({"00000001": "264"})
    with pytest.raises(sc.SectorStageError) as e:
        sc.fill_ksic(object(), TD, fetcher=f, key="k")
    assert e.value.partial["fill_calls"] == 1
    assert isinstance(e.value.__cause__, ValueError), "원인 예외 chain 이 끊기면 안 된다"


# --- #4 레일 «실배선» — 패치는 DB 커서까지만. writer 를 통째로 대체하면 레일 코드가
#     테스트에서 한 번도 실행되지 않는다.

_OPEN_COLS = ("stock_code", "valid_from", "ksic_code", "ksic_source", "ksic3_name",
              "corp_code", "market", "kosdaq_dept", "products", "listing_date",
              "settle_month", "source", "source_asof", "ksic_checked_at", "last_seen_at")


class _FakeCursor:
    """열린 줄·nodata SELECT 만 답하는 커서. 쓰기 SQL 은 «로그만» 남긴다."""

    def __init__(self, db):
        self.db = db
        self.description = None
        self._rows = []

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def execute(self, sql, params=None):
        self.db.log.append((sql, params))
        if "FROM stock_sector_map WHERE valid_to IS NULL" in sql:
            self.description = [(c,) for c in _OPEN_COLS]
            self._rows = [tuple(r.get(c) for c in _OPEN_COLS) for r in self.db.rows]
        elif "FROM sector_ksic_nodata" in sql:
            self.description = [("stock_code",), ("checked_at",)]
            self._rows = []
        else:
            self._rows = []

    def fetchall(self):
        return list(self._rows)

    def fetchone(self):
        return self._rows[0] if self._rows else None


class _FakeDb:
    def __init__(self, rows):
        self.rows = rows
        self.log = []
        self.commits = 0
        self.rollbacks = 0

    def cursor(self):
        return _FakeCursor(self)

    def commit(self):
        self.commits += 1

    def rollback(self):
        self.rollbacks += 1

    def writes(self):
        return [s for s, _p in self.log
                if s.strip().upper().startswith(("INSERT", "UPDATE"))]


def _rows_for_recheck(n, prefix="R", ksic="264"):
    out = []
    for i in range(n):
        code = "%s%04d" % (prefix, i)
        r = _row(ksic_code=ksic, ksic_source="dart", corp_code="C" + code)
        r["stock_code"] = code
        out.append(r)
    return out


def test_recheck_rail_fires_inside_real_apply_ksic_updates(monkeypatch):
    """🔴 #4 — 표본 레일이 «진짜» apply_ksic_updates 안에서 발화하고 한 행도 안 쓴다.
    (분모 1,000 이라 §3.1 5% 가드는 31/1000 = 3.1% 로 통과 — 걸리는 건 표본 레일이다)"""
    rows = _rows_for_recheck(1000)
    db = _FakeDb(rows)
    monkeypatch.setattr(sc, "append_company_raw", lambda p, payload: 1)
    answers = dict((r["corp_code"], "999" if i < 31 else "264")
                   for i, r in enumerate(rows[:40]))
    f = _FakeFetcher(answers)
    with pytest.raises(sc.SectorStageError) as e:
        sc.fill_ksic(db, TD, fetcher=f, recheck_max=40, key="k")
    assert "재확인 급변" in str(e.value) and "31/40" in str(e.value)
    assert e.value.partial["rail_tripped"] is True
    assert e.value.partial["recheck_calls"] == 40
    assert db.writes() == [], "레일이 걸렸는데 행이 써졌다"
    assert db.commits == 0


def test_five_percent_guard_fires_inside_real_apply_ksic_updates(monkeypatch):
    """🔴 #4 — §3.1 5% 급변 가드도 실경로에서 발화한다(계획 단계에서 터져 쓰기 0).
    6/100 = 6% > 5% 이고 표본으로는 6/40 = 15% ≤ 20% 라 «가드»가 걸린 것이 확실하다."""
    rows = _rows_for_recheck(100)
    db = _FakeDb(rows)
    monkeypatch.setattr(sc, "append_company_raw", lambda p, payload: 1)
    answers = dict((r["corp_code"], "999" if i < 6 else "264")
                   for i, r in enumerate(rows[:40]))
    f = _FakeFetcher(answers)
    with pytest.raises(sc.SectorStageError) as e:
        sc.fill_ksic(db, TD, fetcher=f, recheck_max=40, key="k")
    assert "6/100" in str(e.value), "표본 레일이 아니라 5% 가드가 걸려야 한다"
    assert e.value.partial["recheck_calls"] == 40, "부분 집계는 어떤 경우에도 보존된다"
    assert db.writes() == [] and db.commits == 0


def test_recopy_preferred_uses_shared_parent_bundle():
    """🔴 #6 — 재복사가 sector_writer 의 «한 개짜리» 부모 복사 헬퍼를 쓴다."""
    parent = _row(ksic_code="264", ksic_source="dart", ksic3_name="가",
                  corp_code="00126380")
    parent["stock_code"] = "001040"
    child = _row()
    child["stock_code"] = "00104K"
    db = _FakeDb([parent, child])
    res = sc.recopy_preferred(db, TD)
    assert res["counts"]["filled"] == 1 and res["updated"] == 1
    sets = [p for s, p in db.log if s.strip().upper().startswith("UPDATE")][0]
    assert sets["ksic_code"] == "264" and sets["ksic_source"] == "parent:001040"
    assert sets["ksic3_name"] == "가" and sets["corp_code"] == "00126380"


def test_rank_pct_hand_computed_with_ties():
    """T6 ① 동률: G=4 중앙값 [3,1,1,−2] → rank [0,2,2,3] · pct [100, 33.3, 33.3, 0].
    «좋거나 같은»(≥) 다른 업종 수 = 태쏘 rank_pct(side='left') 와 동치."""
    out = sc.rank_and_pct([3.0, 1.0, 1.0, -2.0])
    assert [r for r, _ in out] == [0, 2, 2, 3]
    assert [round(p, 1) for _, p in out] == [100.0, 33.3, 33.3, 0.0]


def test_rank_pct_hand_computed_without_ties():
    """T6 ② 동률 없음: [3,1,0,−2] → [0,1,2,3] · [100, 66.7, 33.3, 0]."""
    out = sc.rank_and_pct([3.0, 1.0, 0.0, -2.0])
    assert [r for r, _ in out] == [0, 1, 2, 3]
    assert [round(p, 1) for _, p in out] == [100.0, 66.7, 33.3, 0.0]


def test_rank_pct_single_sector_gives_null():
    """T6 ③ G=1 → 백분위 NULL(0 이 아니다 — 0 은 «최하위»라는 뜻이 된다)."""
    out = sc.rank_and_pct([0.5])
    assert out == [(0, None)]


def test_sector_label_truncation():
    """T5 — 길이 3·4 코드는 ksic5 에서 미정(4자리 키는 CHECK 를 통과하지 못한다)."""
    assert sc.sector_label("264", 2) == "26"
    assert sc.sector_label("264", 3) == "264"
    assert sc.sector_label("264", 5) is None
    assert sc.sector_label("2611", 5) is None
    assert sc.sector_label("26110", 5) == "26110"
    assert sc.sector_label(None, 2) is None
    assert sc.sector_label("A1234", 2) is None, "비숫자 접두는 미정(CHECK 위반 방지)"


def test_no_prev_close_is_counted_not_dropped():
    """T5 — 20일 창 안에 직전 봉이 없으면 r 미정. 조용히 빼지 말고 «세어» 남긴다."""
    rows = [("AAAAA1", 110.0, 105.0, 100.0), ("BBBBB1", 50.0, 50.0, None)]
    labels = {"AAAAA1": "264", "BBBBB1": "264"}
    stat, und = sc.compute_day_stats(rows, labels)
    assert und["no_prev"] == 1
    k3 = [r for r in stat if r["taxonomy"] == "ksic3"]
    assert len(k3) == 1 and k3[0]["n_members"] == 1


def test_unlabeled_stock_is_counted_not_dropped():
    """T5 — 라벨 없는 종목은 fail-closed(빼고 «센다»)."""
    rows = [("AAAAA1", 110.0, 105.0, 100.0), ("BBBBB1", 50.0, 55.0, 50.0)]
    labels = {"AAAAA1": "264"}
    stat, und = sc.compute_day_stats(rows, labels)
    assert und["no_label"] == 1
    assert und["short_code"]["ksic5"] == 1, "264 는 ksic5 에서 미정이라 «센다»"


def test_stats_window_sql_filters_inside_the_window():
    """🔴 창 «안»에 close>0 과 술어를 건다 — 창 밖에서 걸면 0원 봉이 prev_close 후보로
    남아 수익률이 무한대가 된다(태쏘 load_day 와 같은 순서)."""
    head = sc._STATS_SQL.split(") SELECT")[0]
    assert "close > 0" in head
    assert "stock_code ~ " in head
    assert "LAG(close)" in head


def test_day_stats_hand_computed_sector():
    """중앙값·급등·상승비율·G·순위를 한 번에 손계산으로 고정한다."""
    rows = [
        # (code, high, close, prev_close) — r = close/prev − 1
        ("AAAAA1", 120.0, 103.0, 100.0),   # r=+3%   up: 120 >= 115 → True
        ("AAAAA2", 101.0, 101.0, 100.0),   # r=+1%   up: 101 >= 115 → False
        ("BBBBB1", 100.0,  98.0, 100.0),   # r=−2%   up False
    ]
    labels = {"AAAAA1": "26110", "AAAAA2": "26110", "BBBBB1": "27110"}
    stat, und = sc.compute_day_stats(rows, labels)
    by = dict(((r["taxonomy"], r["sector_key"]), r) for r in stat)
    a = by[("ksic5", "26110")]
    b = by[("ksic5", "27110")]
    assert a["n_members"] == 2 and b["n_members"] == 1
    assert a["g_sectors"] == 2 and b["g_sectors"] == 2
    assert abs(a["ret_median"] - 0.02) < 1e-9      # (0.03 + 0.01)/2
    assert a["up_count"] == 1 and b["up_count"] == 0
    assert abs(a["pos_ratio"] - 1.0) < 1e-9 and abs(b["pos_ratio"] - 0.0) < 1e-9
    assert a["rank_median"] == 0 and b["rank_median"] == 1
    assert abs(a["pct_median"] - 100.0) < 1e-9 and abs(b["pct_median"] - 0.0) < 1e-9
    # 같은 종목이 ksic2·ksic3 에도 들어간다
    assert by[("ksic2", "26")]["n_members"] == 2
    assert by[("ksic3", "261")]["n_members"] == 2
    assert und["no_label"] == 0 and und["no_prev"] == 0


def test_compute_day_stats_is_deterministic():
    """T7-b — 같은 입력이면 «완전히 같은» 행이 나온다(UPSERT 멱등의 전제)."""
    rows = [("AAAAA1", 120.0, 103.0, 100.0), ("BBBBB1", 100.0, 98.0, 100.0)]
    labels = {"AAAAA1": "26110", "BBBBB1": "27110"}
    one, u1 = sc.compute_day_stats(rows, labels)
    two, u2 = sc.compute_day_stats(rows, labels)
    assert one == two and u1 == u2


class _LogSpy:
    """logger 대역 — 어느 레벨로 «무엇이» 나갔는지 본다.
    「무징후 절단 금지」는 summary 만으로는 못 지킨다 — 로그 레벨까지가 계약이다."""

    def __init__(self):
        self.warning_msgs = []
        self.info_msgs = []
        self.error_msgs = []

    @staticmethod
    def _fmt(msg, args):
        return (msg % args) if args else msg

    def warning(self, msg, *args):
        self.warning_msgs.append(self._fmt(msg, args))

    def info(self, msg, *args):
        self.info_msgs.append(self._fmt(msg, args))

    def error(self, msg, *args):
        self.error_msgs.append(self._fmt(msg, args))


def _patch_stats(monkeypatch, rows, labels, spy=None, stale_by_tax=None):
    """compute_stats 의 DB 경계를 전부 가짜로 바꾼다. 반환 = 호출 기록."""
    seen = {"upsert": [], "delete": []}
    monkeypatch.setattr(sc, "load_day_rows", lambda conn, d: rows)
    monkeypatch.setattr(w, "map_as_of", lambda conn, d: labels)

    def _up(conn, r):
        seen["upsert"].append(len(r))
        return len(r)

    def _del(conn, d, tax, keep):
        seen["delete"].append((tax, sorted(keep)))
        return (stale_by_tax or {}).get(tax, 0)

    monkeypatch.setattr(w, "upsert_stats", _up)
    monkeypatch.setattr(w, "delete_stale_stats", _del)
    if spy is not None:
        monkeypatch.setattr(sc, "logger", spy)
    return seen


def test_compute_stats_warns_on_undefined_and_reports_universe(monkeypatch):
    """🔴 #1 — 미정 건수는 summary «와» WARNING 둘 다에 나와야 한다(무징후 절단 금지).
    분모가 없으면 「short_code.ksic5 = 921」이 큰지 작은지 알 수 없다 → universe 를 돌려준다."""
    rows = [("AAAAA1", 120.0, 103.0, 100.0), ("BBBBB1", 100.0, 98.0, 100.0),
            ("CCCCC1", 50.0, 50.0, None)]                 # 직전 봉 없음 → no_prev
    labels = [("AAAAA1", "26110"), ("BBBBB1", "27110"), ("CCCCC1", "264")]
    spy = _LogSpy()
    _patch_stats(monkeypatch, rows, labels, spy=spy)
    res = sc.compute_stats(None, TD)
    assert res["universe"] == 3, "분모(입력 행수)가 summary 에 없다"
    assert res["undefined"]["no_prev"] == 1
    hit = [m for m in spy.warning_msgs if "no_prev=1" in m]
    assert hit, "미정이 있는데 WARNING 이 없다: %s" % spy.warning_msgs
    assert "입력 3행" in hit[0], "WARNING 에 분모가 없다: %s" % hit[0]


def test_compute_stats_does_not_warn_when_nothing_is_undefined(monkeypatch):
    """#1 — 경고는 «조건부»다. 항상 울리면 경고가 소음이 되어 마비된다."""
    rows = [("AAAAA1", 120.0, 103.0, 100.0), ("BBBBB1", 100.0, 98.0, 100.0)]
    labels = [("AAAAA1", "26110"), ("BBBBB1", "27110")]
    spy = _LogSpy()
    _patch_stats(monkeypatch, rows, labels, spy=spy)
    res = sc.compute_stats(None, TD)
    assert res["undefined"]["no_prev"] == 0 and res["undefined"]["no_label"] == 0
    assert [m for m in spy.warning_msgs if "미정" in m] == [], spy.warning_msgs


def test_compute_stats_deletes_stale_sector_rows(monkeypatch):
    """🔴 #2 — 재계산은 «교체»다. UPSERT 뒤에 이번 키 집합에 없는 옛 행을 지운다.
    안 지우면 옛 G 기준의 g_sectors·rank_*·pct_* 를 가진 유령 행이 그날 표에 남아
    그날 표가 «내부 불일치»가 된다."""
    rows = [("AAAAA1", 120.0, 103.0, 100.0), ("BBBBB1", 100.0, 98.0, 100.0)]
    labels = [("AAAAA1", "26110"), ("BBBBB1", "27110")]
    spy = _LogSpy()
    seen = _patch_stats(monkeypatch, rows, labels, spy=spy, stale_by_tax={"ksic3": 2})
    res = sc.compute_stats(None, TD)
    by_tax = dict(seen["delete"])
    assert sorted(by_tax) == ["ksic2", "ksic3", "ksic5"], "taxonomy 3종 모두 교체돼야 한다"
    assert by_tax["ksic5"] == ["26110", "27110"]
    assert by_tax["ksic3"] == ["261", "271"]
    assert by_tax["ksic2"] == ["26", "27"]
    assert res["stale_deleted"] == {"ksic2": 0, "ksic3": 2, "ksic5": 0}
    assert [m for m in spy.warning_msgs if "유령" in m], \
        "삭제가 있었는데 WARNING 이 없다: %s" % spy.warning_msgs


@pytest.mark.parametrize("rows,labels,expect", [
    ([], [], "no_daily"),
    ([("AAAAA1", 120.0, 103.0, 100.0)], [], "empty_map"),
])
def test_compute_stats_skip_paths_never_delete(monkeypatch, rows, labels, expect):
    """🔴 #2 — 계산이 «비었을» 때 지우면 유효 행이 날아간다. 스킵 경로는 삭제 0회."""
    seen = _patch_stats(monkeypatch, rows, labels)
    res = sc.compute_stats(None, TD)
    assert res["skipped"] == expect
    assert seen["delete"] == [] and seen["upsert"] == []


def test_compute_stats_deletes_nothing_when_no_row_is_computable(monkeypatch):
    """🔴 #2 — 일봉·명부는 있는데 계산 결과가 0행인 날(전부 no_prev)도 «삭제 금지»다.
    스킵 경로만 막으면 이 구멍으로 그날 표가 통째로 지워진다."""
    rows = [("AAAAA1", 50.0, 50.0, None), ("BBBBB1", 50.0, 50.0, None)]
    labels = [("AAAAA1", "26110"), ("BBBBB1", "27110")]
    seen = _patch_stats(monkeypatch, rows, labels)
    res = sc.compute_stats(None, TD)
    assert res["rows"] == 0
    assert seen["delete"] == [], "계산 0행인데 유효 행을 지웠다"
    assert res["stale_deleted"] == {}, "«안 돌았다»와 «돌았는데 0»은 다르다"


def test_compute_stats_skips_delete_for_a_taxonomy_with_no_computed_rows(monkeypatch):
    """🔴 M-b — 「계산하지 않은 것은 지우지 않는다」는 «taxonomy 수준»까지다.

    날짜 수준 가드(`if stat_rows:`)만 있으면 3자리 라벨만 있는 날처럼 «한 taxonomy 만»
    0버킷인 경우 빈 keep 이 그 taxonomy 의 그날 행 «전부»를 지운다(빈 keep = 전부 삭제).
    그 taxonomy 는 «측정하지 않았다» → 삭제 0회 · None(모른다) · WARNING.
    """
    rows = [("AAAAA1", 120.0, 103.0, 100.0), ("BBBBB1", 100.0, 98.0, 100.0)]
    labels = [("AAAAA1", "264"), ("BBBBB1", "271")]   # 3자리뿐 → ksic5 버킷 0
    spy = _LogSpy()
    seen = _patch_stats(monkeypatch, rows, labels, spy=spy)
    res = sc.compute_stats(None, TD)
    by_tax = dict(seen["delete"])
    assert "ksic5" not in by_tax, "빈 keep 으로 ksic5 를 통째로 지웠다: %s" % seen["delete"]
    assert res["stale_deleted"]["ksic5"] is None, (
        "«안 쟀다»는 None 이라야 한다(0 으로 접으면 「지울 게 없었다」로 읽힌다)")
    assert [m for m in spy.warning_msgs if "ksic5" in m and "삭제 건너뜀" in m], (
        "무징후 절단 — taxonomy 삭제를 건너뛰었는데 WARNING 이 없다: %s" % spy.warning_msgs)
    # 나머지 taxonomy 는 «평소대로» 교체된다 — 가드가 전부를 멈추면 유령 행이 남는다.
    assert sorted(by_tax) == ["ksic2", "ksic3"]
    assert by_tax["ksic3"] == ["264", "271"] and by_tax["ksic2"] == ["26", "27"]
    assert res["stale_deleted"]["ksic2"] == 0 and res["stale_deleted"]["ksic3"] == 0


def _patch_collect(monkeypatch, calls, map_exc=None, fill_exc=None):
    """collect_sector 가 DB·네트워크를 전혀 안 타게 기본값을 깐다."""
    monkeypatch.setattr(sc.KisDbConnection, "get_connection", lambda: _DummyCM())
    monkeypatch.setattr(sc.w, "ensure_tables", lambda conn: None)
    monkeypatch.setattr(sc, "_load_dart_key", lambda: "k")
    monkeypatch.setattr(sc, "maybe_refresh_corp_code", lambda conn, key, **kw: False)
    monkeypatch.setattr(sc, "_write_summary",
                        lambda d, s: calls.append(("summary", dict(s))))

    def _map(conn, d, **kw):
        calls.append(("map", d))
        if map_exc:
            raise map_exc
        return {"written": True, "source_asof": "2026-09-07", "matched": 2772}

    def _fill(conn, d, **kw):
        calls.append(("fill", d))
        if fill_exc:
            raise fill_exc
        return {"fill_calls": 1, "recheck_calls": 2, "recheck_changed": 0}

    monkeypatch.setattr(sc, "update_map", _map)
    monkeypatch.setattr(sc, "fill_ksic", _fill)
    monkeypatch.setattr(sc, "recopy_preferred",
                        lambda conn, d, **kw: calls.append(("recopy", d)) or {"counts": {}})
    monkeypatch.setattr(sc, "compute_stats",
                        lambda conn, d: calls.append(("stats", d)) or {"rows": 547, "G": {}})
    monkeypatch.setattr(sc.w, "rebuild_ksic_names",
                        lambda conn: calls.append(("names", None)) or {"codes": 158,
                                                                       "low_share": []})


def test_map_failure_does_not_stop_other_stages(monkeypatch):
    """🔴 ①이 터져도 ②③④ 는 돈다 — _safe 까지 올라가면 summary 가 안 써져
    §8-5 가 그날을 못 본다."""
    calls = []
    _patch_collect(monkeypatch, calls, map_exc=RuntimeError("캐시 404"))
    out = sc.collect_sector("2026-09-07")
    names = [c[0] for c in calls]
    assert names[:5] == ["map", "fill", "recopy", "stats", "names"]
    assert out["map"]["written"] is False and "캐시 404" in out["map"]["error"]
    assert out["stats"]["rows"] == 547


def test_summary_is_always_written(monkeypatch):
    """summary 는 «어떤 경우에도» 쓴다 — 게이트들이 파일을 읽기 때문이다."""
    calls = []
    _patch_collect(monkeypatch, calls, map_exc=RuntimeError("boom"),
                   fill_exc=RuntimeError("dart down"))
    sc.collect_sector("2026-09-07")
    written = [c for c in calls if c[0] == "summary"]
    assert len(written) == 1
    s = written[0][1]
    assert s["trade_date"] == "2026-09-07"
    assert s["map"]["written"] is False
    assert "dart down" in s["ksic_fill"]["error"]


def test_dart_quota_does_not_stop_stats(monkeypatch):
    """T8 — 020 으로 ②가 끊겨도 성적표는 진행한다."""
    calls = []
    _patch_collect(monkeypatch, calls,
                   fill_exc=sc.SectorStageError("quota", partial={"quota_hit": True,
                                                                  "recheck_calls": 0}))
    out = sc.collect_sector("2026-09-07")
    assert out["ksic_fill"]["quota_hit"] is True
    assert out["ksic_fill"]["recheck_calls"] == 0, "부분 집계가 보존돼야 한다"
    assert ("stats", date(2026, 9, 7)) in calls


def test_summary_roundtrip(tmp_path, monkeypatch):
    """summary 파일 저장·읽기 — 없으면 None(그 게이트가 WARN 으로 처리한다)."""
    monkeypatch.setattr(sc, "SECTOR_DIR", str(tmp_path))
    d = date(2026, 9, 7)
    assert sc._read_summary(d) is None
    sc._write_summary(d, {"trade_date": "2026-09-07", "map": {"written": True}})
    assert os.path.basename(sc._summary_path(d)) == "sector_summary_2026-09-07.json"
    assert sc._read_summary(d)["map"]["written"] is True


def test_recopy_failure_keeps_the_fill_tally(monkeypatch):
    """🔴 (c) 재복사가 급변 가드(plan_map_changes)로 터져도 ② 가 «이미 쓴 호출» 집계는
    살아야 한다 — e.partial 만 보면 그날 fill_calls·nodata·cap_hit 이 사라져
    DART ≤300/일 회계와 §8 게이트가 그날을 못 본다."""
    calls = []
    _patch_collect(monkeypatch, calls)

    def _boom(conn, d, **kw):
        raise RuntimeError("섹터 명부 소스 급변 - 한 행도 쓰지 않음")

    monkeypatch.setattr(sc, "recopy_preferred", _boom)
    out = sc.collect_sector("2026-09-07")
    assert out["ksic_fill"]["fill_calls"] == 1, "재복사 실패가 ② 집계를 지웠다"
    assert out["ksic_fill"]["recheck_calls"] == 2
    assert "급변" in out["ksic_fill"]["error"]
    assert out["stats"]["rows"] == 547, "③ 은 그래도 돌아야 한다"


def _csv_row(code, name="업종명", market="KOSPI", dept="", products="제품"):
    """parse_desc_csv 가 내놓는 행 모양 그대로(부수 열 5종 + 이름)."""
    return {"stock_code": code, "market": market, "ksic3_name": name,
            "kosdaq_dept": dept, "products": products,
            "listing_date": "2000-01-01", "settle_month": "12월"}


def _patch_update_map(monkeypatch, open_rows, universe, csv_rows, cmap=None,
                      snap=None, stale_days=0, stale_exc=None, spy=None):
    """update_map 의 «경계»(DB·캐시)만 가짜로 바꾼다 — 후보 dict 를 만드는 본문과
    parent_code·apply_parent_rule·is_blank 는 «진짜»가 돈다.

    반환 seen["cands"] = 스텁된 plan_map_changes 가 받은 후보 dict(부모 규칙 «적용 후»).
    """
    seen = {}
    monkeypatch.setattr(w, "load_open_rows", lambda conn: dict(open_rows))
    monkeypatch.setattr(w, "open_market_counts", lambda conn: {"KOSPI": len(open_rows)})
    monkeypatch.setattr(w, "load_stock_industry", lambda conn: dict(snap or {}))
    monkeypatch.setattr(sc, "load_universe", lambda conn: list(universe))
    monkeypatch.setattr(sc, "load_map", lambda conn: dict(cmap or {}))
    monkeypatch.setattr(kdc, "load_desc", lambda d, existing, fetcher=None: {
        "source_asof": date(2026, 9, 4), "rows": list(csv_rows),
        "counts": {"KOSPI": len(csv_rows), "KOSDAQ": 0},
        "dropped": {"konex": 0, "bad_code": 0}, "archive": None})

    def _plan(open_rows_arg, cands, trade_date, **kw):
        seen["cands"] = cands
        seen["plan_kwargs"] = kw
        return {"inplace": [], "close": [], "open_new": [], "changed_codes": [],
                "skipped_past": [], "skipped_missing": [], "guard": {},
                "counts": {"changed": 0, "filled": 0, "new": 0, "unchanged": 0,
                           "skipped_past": 0, "skipped_missing": 0}}

    def _stale(conn, source_asof, trade_date):
        if stale_exc is not None:
            raise stale_exc
        return stale_days

    monkeypatch.setattr(w, "plan_map_changes", _plan)
    monkeypatch.setattr(w, "write_map",
                        lambda conn, plan, source: {"closed": 0, "inserted": 1,
                                                    "updated": 2})
    monkeypatch.setattr(sc, "_stale_trading_days", _stale)
    if spy is not None:
        monkeypatch.setattr(sc, "logger", spy)
    return seen


# 픽스처 — 보통주 2(하나는 CSV 없음) · 우선주 1 · 스냅샷 시딩 대상 1
_UM_UNIVERSE = ["000270", "000660", "005930", "005935"]
_UM_CSV = [_csv_row("000270", "자동차 제조업"),
           _csv_row("005930", "반도체 제조업"),
           _csv_row("005935", "")]                    # 우선주 Industry 는 실측 전부 빈칸
_UM_OPEN = {
    "000270": _row(corp_code=None),                                    # KSIC 빈칸
    "000660": _row(ksic_code="26120", ksic_source="dart", corp_code="00164742"),
    "005930": _row(ksic_code="26110", ksic_source="dart", corp_code="00126380"),
    "005935": _row(ksic_code="99999", ksic_source="dart", corp_code="00999999"),
}
_UM_SNAP = {"000270": "29291", "005930": "11111"}      # 005930 은 «빈칸이 아니라» 시딩 금지
_UM_CMAP = {"000270": "00256598"}                      # 005930 은 없음 → 열린 줄 폴백


def test_update_map_builds_candidates_by_the_four_rules(monkeypatch):
    """🔴 #1 — update_map 을 «진짜로» 부른다(다른 T14 테스트는 통째로 스텁한다).
    plan_map_changes 에 넘어간 후보 dict 로 §3.1 규칙 4개를 한꺼번에 못박는다."""
    spy = _LogSpy()
    seen = _patch_update_map(monkeypatch, _UM_OPEN, _UM_UNIVERSE, _UM_CSV,
                             cmap=_UM_CMAP, snap=_UM_SNAP, spy=spy)
    out = sc.update_map(object(), TD, use_snapshot=True)
    cands = seen["cands"]
    assert sorted(cands) == _UM_UNIVERSE, "순회는 CSV 행이 아니라 U_all 이다"

    # (a) 보통주 + CSV 있음 → 부수 열이 CSV 값으로 «들어온다»
    c = cands["005930"]
    assert c["market"] == "KOSPI" and c["products"] == "제품"
    assert c["ksic3_name"] == "반도체 제조업" and c["settle_month"] == "12월"
    assert c["listing_date"] == "2000-01-01" and c["kosdaq_dept"] == ""
    assert c["source_asof"] == date(2026, 9, 4)

    # (b) CSV 에 없는 종목 → 부수 열 «키 자체가 없다»(None 이 아니다).
    #     plan_map_changes 의 `if f in cand` 가 기존 DB 값을 보존한다 — 무징후 절단 금지.
    nc = cands["000660"]
    for f in ("market", "kosdaq_dept", "products", "listing_date",
              "settle_month", "ksic3_name"):
        assert f not in nc, "%s 키가 있으면 저장된 값이 NULL 로 덮인다" % f
    assert nc["ksic_code"] == "26120" and nc["corp_code"] == "00164742"
    assert [m for m in spy.warning_msgs if "캐시 CSV 에 없는 U_all 종목 1개" in m], \
        "no_csv 는 건수로 경고돼야 한다: %s" % spy.warning_msgs

    # (c) 우선주는 «열린 줄 KSIC(99999)를 승계하지 않는다» — 부모 값이 이긴다.
    p = cands["005935"]
    assert p["ksic_code"] == "26110", "우선주가 자기 열린 줄 KSIC 를 물고 왔다"
    assert p["ksic_source"] == "parent:005930"
    assert p["corp_code"] == "00126380", "corp_code 도 부모와 한 몸이다"
    assert p["ksic3_name"] == "반도체 제조업", "우선주 빈 Industry 는 부모 이름을 받는다"

    # (d) 스냅샷 시딩은 «열린 줄 KSIC 이 빈칸일 때만»
    assert cands["000270"]["ksic_code"] == "29291"
    assert cands["000270"]["ksic_source"] == "snapshot_20260807"
    assert cands["005930"]["ksic_code"] == "26110", "빈칸이 아닌데 스냅샷이 덮었다"
    assert cands["005930"]["ksic_source"] == "dart"

    # corp_code 폴백 — dart_corp_code 우선, 없으면 열린 줄
    assert cands["000270"]["corp_code"] == "00256598"
    assert cands["005930"]["corp_code"] == "00126380"

    # matched = «CSV 에 있는» 후보 수(null_rate 의 분모) · no_csv 는 뺀다
    assert out["matched"] == 3 and out["no_csv"] == 1 and out["universe"] == 4
    assert out["null_rate"]["ksic_code"] == 0.0
    assert out["null_rate"]["ksic3_name"] == 0.0
    assert out["written"] is True and out["db"] == {"closed": 0, "inserted": 1,
                                                    "updated": 2}


def test_update_map_does_not_seed_snapshot_without_the_flag(monkeypatch):
    """use_snapshot=False(=EOD 판)면 스냅샷은 «읽지도» 않는다 — 부트스트랩 전용이다."""
    seen = _patch_update_map(monkeypatch, _UM_OPEN, _UM_UNIVERSE, _UM_CSV,
                             cmap=_UM_CMAP, snap=_UM_SNAP)
    sc.update_map(object(), TD)
    assert seen["cands"]["000270"]["ksic_code"] is None


def test_update_map_flags_a_stale_cache(monkeypatch):
    """게시일이 6 거래일 낡으면 stale=True + WARNING(문턱은 >5)."""
    spy = _LogSpy()
    _patch_update_map(monkeypatch, _UM_OPEN, _UM_UNIVERSE, _UM_CSV, stale_days=6,
                      spy=spy)
    out = sc.update_map(object(), TD)
    assert out["stale"] is True and out["stale_days"] == 6
    assert [m for m in spy.warning_msgs if "낡았다" in m], spy.warning_msgs

    spy5 = _LogSpy()
    _patch_update_map(monkeypatch, _UM_OPEN, _UM_UNIVERSE, _UM_CSV, stale_days=5,
                      spy=spy5)
    out5 = sc.update_map(object(), TD)
    assert out5["stale"] is False, "경계 5 는 아직 낡지 않았다"
    assert [m for m in spy5.warning_msgs if "낡았다" in m] == []


def test_stale_probe_failure_does_not_report_an_unwritten_map(monkeypatch):
    """🔴 #2 — write_map 은 «이미 커밋»된 뒤에 신선도 측정이 돈다. 거기서 터진 예외를
    밖으로 내보내면 summary 가 map.written=False 로 «거짓 보고»를 해서 Task 9 게이트 5가
    오발하고, partial 이 source_asof·null_rate·db 를 잃어 게이트 6·7 이 무음으로 건너뛴다.

    🔑 stale 은 False 가 «아니라» None(미측정)이다 — 「모른다」를 「안전」으로 접지 않는다."""
    spy = _LogSpy()
    _patch_update_map(monkeypatch, _UM_OPEN, _UM_UNIVERSE, _UM_CSV,
                      stale_exc=RuntimeError("current transaction is aborted"),
                      spy=spy)
    out = sc.update_map(object(), TD)
    assert out["written"] is True, "썼는데 안 썼다고 보고했다"
    assert out["stale"] is None, "「모른다」를 False 로 접었다"
    assert out["stale_days"] is None
    assert "current transaction is aborted" in out["stale_error"]
    assert out["source_asof"] == "2026-09-04" and out["db"]["inserted"] == 1
    assert out["null_rate"]["ksic_code"] is not None
    assert [m for m in spy.warning_msgs if "stale 미측정" in m], spy.warning_msgs


def test_stale_error_is_none_on_the_happy_path(monkeypatch):
    """키 모양은 «항상 같다» — 성공한 날은 stale_error=None(키 부재가 아니다)."""
    _patch_update_map(monkeypatch, _UM_OPEN, _UM_UNIVERSE, _UM_CSV, stale_days=1)
    out = sc.update_map(object(), TD)
    assert out["stale_error"] is None and out["stale"] is False


# ───────────────────────── T14 — CLI(시간 가드·백필·gz 폴백) ─────────────────────────
def test_weekday_eod_window_is_refused():
    """§5-5 — 평일 15:30~17:00 은 EOD 와 겹친다. --force 없이는 거부."""
    with pytest.raises(RuntimeError) as e:
        sc._guard_window(force=False, now=datetime(2026, 9, 7, 16, 0))   # 월요일
    assert "15:30" in str(e.value)
    sc._guard_window(force=True, now=datetime(2026, 9, 7, 16, 0))        # --force 는 통과
    sc._guard_window(force=False, now=datetime(2026, 9, 7, 15, 29))      # 창 전
    sc._guard_window(force=False, now=datetime(2026, 9, 7, 17, 0))       # 창 끝(포함 안 함)
    sc._guard_window(force=False, now=datetime(2026, 9, 5, 16, 0))       # 토요일


def _patch_backfill(monkeypatch, calls, rows=550):
    """backfill 이 DB·파일을 안 타게 한다(라이브 3표 대조·리포트도 스텁)."""
    monkeypatch.setattr(sc.KisDbConnection, "get_connection", lambda: _DummyCM())
    monkeypatch.setattr(sc.w, "ensure_tables", lambda conn: None)
    monkeypatch.setattr(sc, "_live_three_table_counts",
                        lambda conn: {"daily_prices": 1, "minute_candles": 2,
                                      "virtual_trading_records": 3})
    monkeypatch.setattr(sc, "_report", lambda name, lines: "(report)")
    monkeypatch.setattr(sc, "_trading_days_between",
                        lambda conn, a, b: ["2026-09-04", "2026-09-07"])
    monkeypatch.setattr(sc, "compute_stats",
                        lambda conn, d: calls.append(d) or {"rows": rows,
                                                            "G": {"ksic3": 159},
                                                            "undefined": {}})


def test_backfill_dry_run_writes_nothing(monkeypatch):
    """--dry-run 은 쓰기 0 · 리포트만."""
    calls = []
    _patch_backfill(monkeypatch, calls)
    out = sc.backfill(date(2026, 9, 4), date(2026, 9, 7), dry_run=True, force=True)
    assert calls == [], "dry-run 인데 성적표를 계산·적재했다"
    assert out["dry_run"] is True and out["days"] == 2


def test_backfill_writes_each_trading_day(monkeypatch):
    """거래일마다 한 번씩 돈다 · 라이브 3표 전후가 같아야 통과한다."""
    calls = []
    _patch_backfill(monkeypatch, calls)
    out = sc.backfill(date(2026, 9, 4), date(2026, 9, 7), force=True)
    assert calls == [date(2026, 9, 4), date(2026, 9, 7)]
    assert out["rows"] == 1100 and out["days_with_rows"] == 2


def test_gz_fetcher_reads_archive(tmp_path, monkeypatch):
    """--regen-map 은 «보관 gz» 를 캐시 CSV 처럼 읽는다(네트워크 0)."""
    import gzip
    monkeypatch.setattr(kdc, "ARCHIVE_DIR", str(tmp_path))
    raw = _csv([("005930", "삼성전자", "KOSPI", "", "반도체 제조업")])
    with gzip.open(os.path.join(str(tmp_path), "krx_desc_2026-09-04.csv.gz"), "wb") as fh:
        fh.write(raw)
    fn = sc._gz_fetcher()
    assert fn("x/2026-09-05.csv") == (404, b"")
    status, body = fn("x/2026-09-04.csv")
    assert status == 200 and body == raw


# ── T14 보강 — 브리프에 테스트가 없는 «안전 장치» 경로(가드 전면 적용·라이브 3표·스냅샷 복구) ──
_WRITE_FNS = ("write_map", "apply_ksic_updates", "upsert_stats", "delete_stats",
              "delete_stale_stats", "upsert_nodata", "rebuild_ksic_names",
              "upsert_reconciliation", "reset_map_from", "snapshot_map",
              "restore_map", "drop_map_snapshot")
_WRITE_ORCH = ("compute_stats", "update_map", "recopy_preferred", "fill_ksic",
               "maybe_refresh_corp_code")


def _forbid_writes(monkeypatch):
    """쓰기 함수를 «전부» 지뢰로 바꾼다 — dry-run 이 하나라도 부르면 즉시 터진다.

    🔑 「쓰기 0」을 눈으로 확인하는 대신 «부르면 실패»로 못 박는다. 나중에 dry-run
       분기에 쓰기가 새로 들어와도 이 테스트가 잡는다.
    """
    def _mine(name):
        def _fn(*a, **kw):
            raise AssertionError("dry-run 인데 쓰기 함수를 불렀다: %s" % name)
        return _fn

    for name in _WRITE_FNS:
        monkeypatch.setattr(sc.w, name, _mine("w." + name))
    for name in _WRITE_ORCH:
        monkeypatch.setattr(sc, name, _mine("sc." + name))


class _GuardConn:
    """가드보다 «먼저» DB 를 열면 알 수 있게 하는 지뢰 연결."""

    def __enter__(self):
        raise AssertionError("시간 가드보다 «먼저» DB 를 열었다")

    def __exit__(self, *a):
        return False


def test_every_cli_op_checks_the_time_window(monkeypatch):
    """🔴 가드가 «모든» CLI 진입점의 첫 문장이다 — 하나라도 빠지면 그 경로만 EOD 와 겹친다.

    DB 연결을 지뢰로 깔았으므로, 가드가 없으면 RuntimeError 가 아니라 AssertionError 가 난다.
    """
    monkeypatch.setattr(sc, "now_kst", lambda: datetime(2026, 9, 7, 16, 0))   # 월 16:00
    monkeypatch.setattr(sc.KisDbConnection, "get_connection", lambda: _GuardConn())
    ops = {
        "bootstrap": lambda: sc.bootstrap(date(2026, 9, 7)),
        "backfill": lambda: sc.backfill(date(2026, 9, 4), date(2026, 9, 7)),
        "regen_stats": lambda: sc.regen_stats(date(2026, 9, 4), date(2026, 9, 7)),
        "regen_map": lambda: sc.regen_map(date(2026, 9, 4)),
        "delete_stats_cli": lambda: sc.delete_stats_cli(date(2026, 9, 4), date(2026, 9, 7)),
    }
    for name, fn in ops.items():
        with pytest.raises(RuntimeError) as e:
            fn()
        assert "15:30" in str(e.value), "%s 에 시간 가드가 없다: %s" % (name, e.value)


class _CountFlip:
    """라이브 3표 행수 — 두 번째 호출부터 «다른» 값을 준다(작업이 실제로 썼다는 뜻)."""

    def __init__(self):
        self.n = 0

    def __call__(self, conn):
        self.n += 1
        return {"daily_prices": 1 if self.n == 1 else 2,
                "minute_candles": 2, "virtual_trading_records": 3}


def test_backfill_raises_when_live_three_tables_change(monkeypatch):
    """🔴 라이브 3표가 «한 행이라도» 바뀌면 즉시 예외 — 리포트는 «먼저» 남긴다."""
    calls = []
    reports = []
    _patch_backfill(monkeypatch, calls)
    monkeypatch.setattr(sc, "_live_three_table_counts", _CountFlip())
    monkeypatch.setattr(sc, "_report", lambda name, lines: reports.append(name) or "(r)")
    with pytest.raises(RuntimeError) as e:
        sc.backfill(date(2026, 9, 4), date(2026, 9, 7), force=True)
    assert "라이브 3표" in str(e.value)
    assert reports == ["backfill_report"], "터지기 «전»에 근거를 남겨야 한다"


def _patch_bootstrap(monkeypatch, cov, counts=None, reports=None):
    """bootstrap 비-dry 경로를 DB·DART 없이 굴린다."""
    monkeypatch.setattr(sc, "_load_dart_key", lambda: "k")
    monkeypatch.setattr(sc.KisDbConnection, "get_connection", lambda: _DummyCM())
    monkeypatch.setattr(sc.w, "ensure_tables", lambda conn: None)
    monkeypatch.setattr(sc, "_live_three_table_counts",
                        counts or (lambda conn: {"daily_prices": 1, "minute_candles": 2,
                                                 "virtual_trading_records": 3}))
    monkeypatch.setattr(sc, "load_u_market", lambda conn: ["005930", "005935"])
    monkeypatch.setattr(sc, "maybe_refresh_corp_code", lambda conn, key, **kw: False)
    monkeypatch.setattr(sc, "update_map", lambda conn, d, **kw: {"written": True})
    monkeypatch.setattr(sc, "_coverage", lambda conn, umkt: dict(cov))
    monkeypatch.setattr(sc, "fill_ksic", lambda conn, d, **kw: {"status_counts": {},
                                                               "nodata": 0, "filled": 1})
    monkeypatch.setattr(sc, "recopy_preferred", lambda conn, d, **kw: {"counts": {}})
    monkeypatch.setattr(sc.w, "rebuild_ksic_names", lambda conn: {"codes": 1, "low_share": []})
    monkeypatch.setattr(sc, "_unlabeled_list", lambda conn, umkt: [])
    monkeypatch.setattr(sc, "_report",
                        lambda name, lines: (reports if reports is not None else []).append(name)
                        or "(r)")


def test_bootstrap_raises_when_live_three_tables_change(monkeypatch):
    """🔴 부트스트랩도 라이브 3표를 전후로 잰다 — 바뀌면 커버리지 게이트보다 «먼저» 터진다."""
    reports = []
    _patch_bootstrap(monkeypatch, {"ksic_code": 1.0, "ksic3_name": 1.0, "u_market": 2},
                     counts=_CountFlip(), reports=reports)
    with pytest.raises(RuntimeError) as e:
        sc.bootstrap(date(2026, 9, 7), force=True)
    assert "라이브 3표" in str(e.value)
    assert reports == ["bootstrap_report"]


def test_bootstrap_gate_stops_below_98_percent(monkeypatch):
    """🔴 3b 후 커버리지가 하나라도 98% 미만이면 «백필로 넘어가지 않는다»."""
    _patch_bootstrap(monkeypatch, {"ksic_code": 0.99, "ksic3_name": 0.97, "u_market": 2})
    with pytest.raises(RuntimeError) as e:
        sc.bootstrap(date(2026, 9, 7), force=True)
    assert "게이트 미달" in str(e.value)
    # 둘 다 넘으면 통과한다 — 문턱이 «항상 실패»가 아님을 대칭으로 못 박는다.
    _patch_bootstrap(monkeypatch, {"ksic_code": 0.99, "ksic3_name": 0.99, "u_market": 2})
    out = sc.bootstrap(date(2026, 9, 7), force=True)
    assert out["dry_run"] is False and out["steps"]["coverage_after_3b"]["ksic3_name"] == 0.99


def test_bootstrap_writes_a_partial_report_before_reraising(monkeypatch):
    """🔴 I2 — 단계 1~4 중간에 죽으면 «리포트 뒤 raise» 다(regen_stats 와 같은 모양).

    ①corp_code·②명부는 이미 «커밋된» 뒤다. 리포트 없이 예외만 올리면 「어디까지
    반영됐고 무엇이 남았나」가 파일로 안 남아 복구 근거가 사라진다.
    """
    reports = []
    _patch_bootstrap(monkeypatch, {"ksic_code": 1.0, "ksic3_name": 1.0, "u_market": 2})
    monkeypatch.setattr(sc, "_report",
                        lambda name, lines: reports.append((name, list(lines))) or "(r)")

    def _boom(conn, d, **kw):
        raise RuntimeError("DART 응답 없음")

    monkeypatch.setattr(sc, "fill_ksic", _boom)
    with pytest.raises(RuntimeError) as e:
        sc.bootstrap(date(2026, 9, 7), force=True)
    assert "DART 응답 없음" in str(e.value), "원인 예외가 다른 것으로 바뀌었다"
    assert [n for n, _ in reports] == ["bootstrap_report"], (
        "터지기 «전»에 근거를 남겨야 한다: %s" % reports)
    body = "\n".join(reports[0][1])
    assert "fill_ksic" in body, "실패한 «단계»가 리포트에 없다: %s" % body
    assert "DART 응답 없음" in body, "오류 문구가 리포트에 없다: %s" % body
    assert "라이브 3표" in body, "라이브 3표 before 가 리포트에 없다: %s" % body
    assert "2단계 후 커버리지" in body, "측정된 coverage 가 리포트에 없다: %s" % body


def test_bootstrap_dry_run_writes_nothing_and_predicts_coverage(monkeypatch):
    """--dry-run = DB 쓰기 0 · DART 0 · gz 0 · 두 커버리지 예측치를 인쇄한다."""
    seen = {}
    _forbid_writes(monkeypatch)
    monkeypatch.setattr(sc, "_load_dart_key", lambda: "k")
    monkeypatch.setattr(sc.KisDbConnection, "get_connection", lambda: _DummyCM())
    monkeypatch.setattr(sc.w, "ensure_tables", lambda conn: None)
    monkeypatch.setattr(sc, "_live_three_table_counts",
                        lambda conn: {"daily_prices": 1, "minute_candles": 2,
                                      "virtual_trading_records": 3})
    monkeypatch.setattr(sc, "load_u_market", lambda conn: ["005930", "005935"])
    monkeypatch.setattr(sc.w, "load_open_rows", lambda conn: {"005930": _row()})
    monkeypatch.setattr(sc.w, "open_market_counts", lambda conn: {})
    monkeypatch.setattr(sc.w, "load_stock_industry", lambda conn: {"005930": "264"})
    monkeypatch.setattr(sc, "load_map", lambda conn: {"005930": "C1"})
    monkeypatch.setattr(sc, "load_universe", lambda conn: ["005930", "005935"])
    monkeypatch.setattr(sc, "_report", lambda name, lines: "(r)")

    def _desc(trade_date, existing=None, fetcher=None, archive=True):
        seen["archive"] = archive
        return {"rows": [{"stock_code": "005930", "ksic3_name": "반도체 제조업"}]}

    monkeypatch.setattr(kdc, "load_desc", _desc)
    out = sc.bootstrap(date(2026, 9, 7), dry_run=True, force=True)
    assert seen["archive"] is False, "dry-run 이 gz 를 남기면 「쓰기 0」이 거짓이 된다"
    assert out["dry_run"] is True
    # 부모(005930)가 스냅샷 시드 → 우선주 자식(005935)까지 3b 에서 복사받는다.
    assert out["steps"]["predicted_coverage_after_3b"] == {"ksic_code": 1.0, "ksic3_name": 1.0}
    assert out["steps"]["would_dart_calls"] == 0 and out["steps"]["matched"] == 1


class _RegenCursor:
    def __init__(self, db):
        self.db = db
        self._rows = []

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def execute(self, sql, params=None):
        self.db.log.append(sql)
        if "min(valid_from)" in sql:
            self._rows = [(self.db.first_eod,)]
        else:
            self._rows = []

    def fetchone(self):
        return self._rows[0] if self._rows else None

    def fetchall(self):
        return list(self._rows)


class _RegenConn:
    def __init__(self, first_eod=date(2026, 9, 1), order=None):
        self.first_eod = first_eod
        self.log = []
        self.order = order if order is not None else []

    def cursor(self):
        return _RegenCursor(self)

    def commit(self):
        self.order.append("commit")

    def rollback(self):
        self.order.append("rollback")

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def test_regen_map_dry_run_writes_nothing(monkeypatch):
    """--regen-map --dry-run 은 스냅샷도 reset 도 «하지 않는다» — 건수만 센다."""
    _forbid_writes(monkeypatch)
    conn = _RegenConn()
    monkeypatch.setattr(sc.KisDbConnection, "get_connection", lambda: conn)
    monkeypatch.setattr(sc.w, "ensure_tables", lambda c: None)
    monkeypatch.setattr(sc, "_trading_days_between",
                        lambda c, a, b: ["2026-09-04", "2026-09-07"])
    out = sc.regen_map(date(2026, 9, 4), dry_run=True, force=True)
    assert out == {"from": "2026-09-04", "days": 2, "jsonl_days": 0, "dry_run": True}


def test_regen_map_refuses_before_the_first_eod_day(monkeypatch):
    """🔴 하한 = 첫 EOD 날짜. 부트스트랩 행(2021-01-04)은 gz 로 재현할 수 없다."""
    conn = _RegenConn(first_eod=date(2026, 9, 10))
    monkeypatch.setattr(sc.KisDbConnection, "get_connection", lambda: conn)
    monkeypatch.setattr(sc.w, "ensure_tables", lambda c: None)
    with pytest.raises(RuntimeError) as e:
        sc.regen_map(date(2026, 9, 4), force=True)
    assert "2026-09-10" in str(e.value)


def test_regen_map_snapshots_first_and_restores_on_failure(monkeypatch):
    """🔴 순서가 전부다 — ①스냅샷 ②reset ③(터짐) ④rollback ⑤restore.

    일자별 재구축은 단계마다 커밋되므로, 스냅샷이 reset «뒤»에 찍히면 되돌릴 원본이
    이미 잘린 뒤다. 실패했는데 drop_map_snapshot 이 돌면 유일한 원본이 사라진다.
    """
    order = []
    conn = _RegenConn(order=order)
    monkeypatch.setattr(sc.KisDbConnection, "get_connection", lambda: conn)
    monkeypatch.setattr(sc.w, "ensure_tables", lambda c: None)
    monkeypatch.setattr(sc, "_trading_days_between", lambda c, a, b: ["2026-09-04"])
    monkeypatch.setattr(sc.w, "snapshot_map", lambda c: order.append("snapshot") or 7)
    monkeypatch.setattr(sc.w, "reset_map_from",
                        lambda c, d: order.append("reset") or {"deleted": 1, "reopened": 2})
    monkeypatch.setattr(sc.w, "restore_map", lambda c: order.append("restore") or 7)
    monkeypatch.setattr(sc.w, "drop_map_snapshot", lambda c: order.append("drop"))

    def _boom(conn_, day, **kw):
        order.append("update_map")
        raise RuntimeError("5% 급변 가드")

    monkeypatch.setattr(sc, "update_map", _boom)
    with pytest.raises(RuntimeError) as e:
        sc.regen_map(date(2026, 9, 4), force=True)
    assert "급변 가드" in str(e.value), "원인 예외가 삼켜졌다"
    assert order == ["snapshot", "reset", "update_map", "rollback", "restore"], order
    assert "drop" not in order, "실패했는데 유일한 복구 원본을 지웠다"


def test_regen_map_drops_the_snapshot_only_on_success(monkeypatch):
    """성공하면 스냅샷을 지운다 — 남아 있으면 다음 실행이 snapshot_map 에서 멈춘다."""
    order = []
    conn = _RegenConn(order=order)
    monkeypatch.setattr(sc.KisDbConnection, "get_connection", lambda: conn)
    monkeypatch.setattr(sc.w, "ensure_tables", lambda c: None)
    monkeypatch.setattr(sc, "_trading_days_between", lambda c, a, b: ["2026-09-04"])
    monkeypatch.setattr(sc.w, "snapshot_map", lambda c: order.append("snapshot") or 7)
    monkeypatch.setattr(sc.w, "reset_map_from",
                        lambda c, d: order.append("reset") or {"deleted": 1, "reopened": 2})
    monkeypatch.setattr(sc.w, "restore_map", lambda c: order.append("restore") or 7)
    monkeypatch.setattr(sc.w, "drop_map_snapshot", lambda c: order.append("drop"))
    monkeypatch.setattr(sc, "update_map",
                        lambda c, day, **kw: order.append("update_map") or {})
    monkeypatch.setattr(sc, "recopy_preferred",
                        lambda c, day, **kw: order.append("recopy") or {"counts": {}})
    monkeypatch.setattr(sc.w, "rebuild_ksic_names",
                        lambda c: order.append("names") or {"codes": 1, "low_share": []})
    monkeypatch.setattr(sc, "_report", lambda name, lines: "(r)")
    out = sc.regen_map(date(2026, 9, 4), force=True)
    assert order == ["snapshot", "reset", "update_map", "recopy", "names", "drop"], order
    assert "restore" not in order
    assert out["deleted"] == 1 and out["reopened"] == 2 and out["snapshot_rows"] == 7
    assert out["replayed_responses"] == 0, "보관 jsonl 이 없는 날은 KSIC 계열을 «보존»한다"


def test_regen_stats_dry_run_deletes_nothing(monkeypatch):
    """--regen --dry-run 은 지우지도 다시 계산하지도 않고, 리포트만 남긴다."""
    _forbid_writes(monkeypatch)
    reports = []
    monkeypatch.setattr(sc.KisDbConnection, "get_connection", lambda: _DummyCM())
    monkeypatch.setattr(sc.w, "ensure_tables", lambda conn: None)
    monkeypatch.setattr(sc, "_trading_days_between",
                        lambda conn, a, b: ["2026-09-04", "2026-09-07"])
    monkeypatch.setattr(sc, "_report",
                        lambda name, lines: reports.append((name, list(lines))) or "(r)")
    out = sc.regen_stats(date(2026, 9, 4), date(2026, 9, 7), taxonomy="ksic3",
                         dry_run=True, force=True)
    assert [n for n, _ in reports] == ["regen_stats_report"]
    assert out["from"] == "2026-09-04" and out["to"] == "2026-09-07"
    assert out["days"] == 2 and out["dry_run"] is True
    assert out["would_delete_taxonomy"] == "ksic3" and out["report"] == "(r)"
    # 🔑 dry-run 은 재지 않았다 — 「모른다」를 0 으로 접지 않는다(집 규약).
    assert out["deleted"] is None and out["rows"] is None and out["days_with_rows"] is None


def test_delete_stats_dry_run_only_counts(monkeypatch):
    """--delete-stats --dry-run 은 «셀 뿐»이고 리포트를 남긴다."""
    _forbid_writes(monkeypatch)
    lines = {}

    class _Cur:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def execute(self, sql, params=None):
            lines["sql"] = sql
            lines["params"] = list(params)

        def fetchone(self):
            return (12,)

    class _Conn:
        def cursor(self):
            return _Cur()

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    monkeypatch.setattr(sc.KisDbConnection, "get_connection", lambda: _Conn())
    monkeypatch.setattr(sc.w, "ensure_tables", lambda conn: None)
    monkeypatch.setattr(sc, "_report", lambda name, l: "(r)")
    out = sc.delete_stats_cli(date(2026, 9, 4), date(2026, 9, 7), taxonomy="ksic5",
                              dry_run=True, force=True)
    assert out["would_delete"] == 12 and out["dry_run"] is True and out["report"] == "(r)"
    assert lines["sql"].strip().upper().startswith("SELECT"), "dry-run 이 DELETE 를 냈다"
    assert lines["params"][-1] == "ksic5", "taxonomy 가 셈에서 빠졌다"


# ── T14 fix1 — 리포트 공백 2건(#1 regen_stats · #2 regen_map) + CLI 플래그 조합 ──
def _patch_regen_stats(monkeypatch, reports, days=("2026-09-04", "2026-09-07"),
                       rows_by_day=None, boom_on=None, deleted=5):
    """regen_stats 실경로를 DB 없이 굴린다. reports 에 (이름, 줄들) 이 쌓인다."""
    monkeypatch.setattr(sc.KisDbConnection, "get_connection", lambda: _DummyCM())
    monkeypatch.setattr(sc.w, "ensure_tables", lambda conn: None)
    monkeypatch.setattr(sc, "_trading_days_between", lambda conn, a, b: list(days))
    monkeypatch.setattr(sc.w, "delete_stats", lambda conn, a, b, tax=None: deleted)
    by_day = dict(rows_by_day or {})

    def _stats(conn, d):
        if boom_on and d.isoformat() == boom_on:
            raise RuntimeError("일봉 결손")
        return {"rows": by_day.get(d.isoformat(), 100)}

    monkeypatch.setattr(sc, "compute_stats", _stats)
    monkeypatch.setattr(sc, "_report",
                        lambda name, lines: reports.append((name, list(lines))) or "(r)")


def test_regen_stats_success_writes_a_report(monkeypatch):
    """🔴 #1 — 5 op 중 regen_stats 만 리포트가 없었다. 실경로도 근거를 남긴다."""
    reports = []
    _patch_regen_stats(monkeypatch, reports,
                       rows_by_day={"2026-09-04": 550, "2026-09-07": 0})
    out = sc.regen_stats(date(2026, 9, 4), date(2026, 9, 7), taxonomy="ksic3", force=True)
    assert [n for n, _ in reports] == ["regen_stats_report"]
    assert out["deleted"] == 5 and out["rows"] == 550 and out["days_with_rows"] == 1
    assert out["days"] == 2 and out["taxonomy"] == "ksic3" and out["dry_run"] is False
    assert isinstance(out["elapsed_sec"], float) and out["report"] == "(r)"
    body = "\n".join(reports[0][1])
    for token in ("5", "550", "ksic3", "days_with_rows"):
        assert token in body, "리포트에 %s 가 없다: %s" % (token, body)


def test_regen_stats_midway_failure_reports_before_reraising(monkeypatch):
    """🔴 #1 — 임의 구간을 «먼저 지운 뒤» 하루씩 되살린다. 중간에 죽으면
    「무엇을 지웠고 어디까지 되살렸나」가 파일로 남지 않으면 복구 근거가 사라진다."""
    reports = []
    _patch_regen_stats(monkeypatch, reports, boom_on="2026-09-07")
    with pytest.raises(RuntimeError) as e:
        sc.regen_stats(date(2026, 9, 4), date(2026, 9, 7), force=True)
    assert "일봉 결손" in str(e.value), "원인 예외가 삼켜졌다"
    assert [n for n, _ in reports] == ["regen_stats_report"], "터지기 «전»에 근거를 남겨야 한다"
    body = "\n".join(reports[0][1])
    assert "2026-09-07" in body, "실패한 «날짜»가 리포트에 없다"
    assert "일봉 결손" in body, "오류 내용이 리포트에 없다"
    assert "5" in body and "1/2" in body, "삭제 건수·진행된 날 수가 리포트에 없다: %s" % body


def test_regen_map_reports_days_it_wrote_that_the_original_did_not(monkeypatch):
    """🔴 #2 — docstring 은 「원본이 written=false 였던 날도 재생은 쓴다 · 리포트에
    그 날짜 수를 남긴다」고 약속했는데 update_map 반환을 버리고 있었다.

    소급 라벨이 «원본보다 늘어나는» 날이므로 무징후로 지나가면 안 된다.
    보관 jsonl 이 없어 KSIC 계열을 «보존»한 날도 같은 이유로 센다.
    """
    spy = _LogSpy()
    conn = _RegenConn()
    reports = []
    monkeypatch.setattr(sc, "logger", spy)
    monkeypatch.setattr(sc.KisDbConnection, "get_connection", lambda: conn)
    monkeypatch.setattr(sc.w, "ensure_tables", lambda c: None)
    monkeypatch.setattr(sc, "_trading_days_between",
                        lambda c, a, b: ["2026-09-04", "2026-09-07", "2026-09-08",
                                         "2026-09-09"])
    monkeypatch.setattr(sc.w, "snapshot_map", lambda c: 7)
    monkeypatch.setattr(sc.w, "reset_map_from", lambda c, d: {"deleted": 1, "reopened": 2})
    monkeypatch.setattr(sc.w, "drop_map_snapshot", lambda c: None)
    # 09-08 은 재생에서도 못 썼다 — 원본 기록과 무관하게 세면 안 된다.
    monkeypatch.setattr(sc, "update_map",
                        lambda c, day, **kw: {"written": day.isoformat() != "2026-09-08"})
    monkeypatch.setattr(sc, "recopy_preferred", lambda c, day, **kw: {"counts": {}})
    monkeypatch.setattr(sc.w, "rebuild_ksic_names", lambda c: {"codes": 1, "low_share": []})
    prev = {"2026-09-04": {"map": {"written": True}},     # 원본도 썼다 → 세지 않는다
            "2026-09-07": {"map": {"written": False}},    # 원본이 못 썼다 → 센다
            "2026-09-08": {"map": {"written": False}}}    # 재생도 못 썼다 → 세지 않는다
    monkeypatch.setattr(sc, "_read_summary", lambda d: prev.get(d.isoformat()))
    monkeypatch.setattr(sc, "_report",
                        lambda n, lines: reports.append((n, list(lines))) or "(r)")

    out = sc.regen_map(date(2026, 9, 4), force=True)
    # 09-09 는 summary 파일이 «아예 없다» — 「모른다」를 「썼다」로 접으면 안 된다.
    assert out["regen_wrote_where_original_didnt"] == 2
    assert out["regen_wrote_where_original_didnt_dates"] == ["2026-09-07", "2026-09-09"]
    assert out["preserved_ksic_days"] == 4, "jsonl 이 하나도 없으니 4일 전부 «보존»이다"
    body = "\n".join(reports[0][1])
    assert "2026-09-07" in body and "2026-09-09" in body
    assert [m for m in spy.warning_msgs if "원본이" in m and "2026-09-07" in m], spy.warning_msgs
    assert [m for m in spy.warning_msgs if "보존" in m], spy.warning_msgs


def test_regen_map_says_nothing_extra_when_the_replay_matches_the_original(tmp_path,
                                                                           monkeypatch):
    """대칭 — 원본이 전부 썼고 jsonl 도 전부 있으면 두 집계는 0 이고 WARNING 도 없다."""
    spy = _LogSpy()
    conn = _RegenConn()
    monkeypatch.setattr(sc, "logger", spy)
    monkeypatch.setattr(sc, "SECTOR_DIR", str(tmp_path))
    open(os.path.join(str(tmp_path), "dart_company_2026-09-04.jsonl"),
         "w", encoding="utf-8").close()          # 빈 보관분(응답 0건)
    monkeypatch.setattr(sc.KisDbConnection, "get_connection", lambda: conn)
    monkeypatch.setattr(sc.w, "ensure_tables", lambda c: None)
    monkeypatch.setattr(sc, "_trading_days_between", lambda c, a, b: ["2026-09-04"])
    monkeypatch.setattr(sc.w, "snapshot_map", lambda c: 7)
    monkeypatch.setattr(sc.w, "reset_map_from", lambda c, d: {"deleted": 1, "reopened": 2})
    monkeypatch.setattr(sc.w, "drop_map_snapshot", lambda c: None)
    monkeypatch.setattr(sc, "update_map", lambda c, day, **kw: {"written": True})
    monkeypatch.setattr(sc, "recopy_preferred", lambda c, day, **kw: {"counts": {}})
    monkeypatch.setattr(sc.w, "rebuild_ksic_names", lambda c: {"codes": 1, "low_share": []})
    monkeypatch.setattr(sc.w, "load_open_rows", lambda c: {})
    monkeypatch.setattr(sc, "_read_summary", lambda d: {"map": {"written": True}})
    monkeypatch.setattr(sc, "_report", lambda n, lines: "(r)")
    out = sc.regen_map(date(2026, 9, 4), force=True)
    assert out["jsonl_days"] == 1
    assert out["regen_wrote_where_original_didnt"] == 0
    assert out["regen_wrote_where_original_didnt_dates"] == []
    assert out["preserved_ksic_days"] == 0
    assert not [m for m in spy.warning_msgs if "원본이" in m or "보존" in m], spy.warning_msgs


def _args(**kw):
    ns = sc.argparse.Namespace(bootstrap=False, backfill=False, regen=False,
                               regen_map=False, delete_stats=False,
                               reconcile_only=None, dry_run=False, force=False)
    for k, v in kw.items():
        setattr(ns, k, v)
    return ns


def test_cli_rejects_flag_combinations_that_are_silently_ignored():
    """🔴 D1 + Minor2 — argparse 가 조용히 삼키는 조합을 «거부»한다.

    ① --dry-run/--force 를 작업 플래그 없이 주면 마지막 else 가지(collect_sector =
       진짜 EOD 수집)로 떨어져 두 플래그가 «무시된 채» 실제 수집이 돈다.
    ② op 두 개를 같이 주면 elif 사슬이 앞의 하나만 돌고 나머지는 조용히 버려진다.
    """
    errs = []

    def _error(msg):
        errs.append(msg)
        raise SystemExit(2)

    for kw in ({"dry_run": True}, {"force": True},
               {"dry_run": True, "reconcile_only": "2026-09-07"},
               {"bootstrap": True, "backfill": True},
               {"regen": True, "regen_map": True, "dry_run": True}):
        del errs[:]
        with pytest.raises(SystemExit):
            sc._check_cli_flags(_args(**kw), _error)
        assert errs, "거부해야 할 조합인데 통과했다: %s" % kw

    # 대칭 — 정상 조합은 통과하고 «고른 op» 를 돌려준다.
    del errs[:]
    assert sc._check_cli_flags(_args(backfill=True, dry_run=True, force=True),
                               _error) == "backfill"
    assert sc._check_cli_flags(_args(), _error) is None              # EOD 판(기본)
    assert sc._check_cli_flags(_args(reconcile_only="2026-09-07"), _error) is None
    assert errs == [], errs
