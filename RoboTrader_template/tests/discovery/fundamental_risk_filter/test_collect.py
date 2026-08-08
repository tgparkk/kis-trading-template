import gzip
import json
import os
import sys

import pytest

_SCRIPTS = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(
        os.path.abspath(__file__))))),
    "scripts", "discovery", "fundamental_risk_filter",
)
sys.path.insert(0, _SCRIPTS)

import dart_client as dc  # noqa: E402
import f2_collect as f2  # noqa: E402


class _FakeClient:
    """호출 순서를 기록하고 미리 정한 응답을 돌려주는 클라이언트."""

    def __init__(self, responses):
        self.responses = responses
        self.seen = []

    def fnltt_all(self, corp_code, bsns_year, reprt_code, fs_div):
        self.seen.append((corp_code, bsns_year, fs_div))
        return self.responses.pop(0)


ITEM = {"stock_code": "005930", "corp_code": "00126380", "bsns_year": "2022"}


def test_cfs_is_tried_first():
    c = _FakeClient([("000", "", [{"account_nm": "자본총계"}])])
    out = f2.collect_one(c, ITEM)
    assert c.seen[0][2] == "CFS"
    assert out["fs_div"] == "CFS"
    assert out["status"] == "000"


def test_falls_back_to_ofs_when_cfs_has_no_data():
    """연결재무제표가 없는 회사는 별도로 떨어진다 — 013 을 결측으로 확정하지 않는다."""
    c = _FakeClient([
        ("013", "무자료", []),
        ("000", "", [{"account_nm": "자본총계"}]),
    ])
    out = f2.collect_one(c, ITEM)
    assert [s[2] for s in c.seen] == ["CFS", "OFS"]
    assert out["fs_div"] == "OFS"
    assert out["status"] == "000"


def test_both_missing_records_013_not_an_empty_success():
    """둘 다 없으면 013 으로 «기록»한다. 성공으로 위장하지 않는다."""
    c = _FakeClient([("013", "무자료", []), ("013", "무자료", [])])
    out = f2.collect_one(c, ITEM)
    assert out["status"] == "013"
    assert out["rows"] == []
    assert out["fs_div"] is None


def test_quota_exceeded_propagates():
    """한도 초과는 삼키지 않는다 — 위로 올려 즉시 중단시킨다."""
    class _Q:
        def fnltt_all(self, *a, **k):
            raise dc.DartQuotaExceeded("020")

    with pytest.raises(dc.DartQuotaExceeded):
        f2.collect_one(_Q(), ITEM)


def test_load_done_reads_checkpoint(tmp_path):
    p = tmp_path / "raw.jsonl.gz"
    with gzip.open(p, "wt", encoding="utf-8") as f:
        f.write(json.dumps({"stock_code": "005930", "bsns_year": "2022"}) + "\n")
        f.write(json.dumps({"stock_code": "000660", "bsns_year": "2021"}) + "\n")
    done = f2.load_done(str(p))
    assert done == {("005930", "2022"), ("000660", "2021")}


def test_load_done_on_missing_file_is_empty(tmp_path):
    assert f2.load_done(str(tmp_path / "nope.jsonl.gz")) == set()


def test_load_done_tolerates_truncated_last_line(tmp_path):
    """중단 시점에 마지막 줄이 잘려 있을 수 있다. 그 한 줄만 버리고 재개한다."""
    p = tmp_path / "raw.jsonl.gz"
    with gzip.open(p, "wt", encoding="utf-8") as f:
        f.write(json.dumps({"stock_code": "005930", "bsns_year": "2022"}) + "\n")
        f.write('{"stock_code": "0006')
    done = f2.load_done(str(p))
    assert done == {("005930", "2022")}


def test_empty_000_is_not_recorded_as_success():
    """🔴 「데이터 없음」이 「성공」으로 둔갑하면 리스크 필터가 조용히 깨끗하다고 답한다."""
    c = _FakeClient([("000", "", []), ("000", "", [])])
    out = f2.collect_one(c, ITEM)
    assert out["status"] == "000_EMPTY"
    assert out["status"] != "000"
    assert out["rows"] == []
    assert out["fs_div"] is None


def test_load_done_survives_gzip_without_end_marker(tmp_path):
    """🔴 하드킬로 종료 마커가 없어도 앞부분은 살려야 한다.

    ⚠️ 이 테스트는 «종료 마커가 실제로 없는» 파일을 만들어야 의미가 있다.
       gzip 핸들을 닫으면 close() 가 트레일러(CRC32+ISIZE, 8바이트)를 써서
       «정상 gzip» 이 되고, EOFError 처리를 지워도 통과한다.
       그래서 정상 파일을 만든 뒤 끝 8바이트를 직접 잘라낸다.
    """
    good = tmp_path / "good.jsonl.gz"
    with gzip.open(good, "wt", encoding="utf-8") as f:
        f.write(json.dumps({"stock_code": "005930", "bsns_year": "2022"}) + "\n")
        f.write(json.dumps({"stock_code": "000660", "bsns_year": "2021"}) + "\n")

    truncated = tmp_path / "truncated.jsonl.gz"
    truncated.write_bytes(good.read_bytes()[:-8])   # 트레일러 제거

    done = f2.load_done(str(truncated))
    assert ("005930", "2022") in done               # 앞부분은 살아야 한다


# ── FIX1: 000/013 외의 status 는 즉시 올린다 ──────────────────────────────

def test_unexpected_status_raises_and_produces_no_record():
    """🔴 010/011(키 불량·미등록)은 즉시 올려야 한다.

    last 에 저장해 최종 레코드로 «기록»해 버리면 키·IP 문제 하나가 작업목록
    전체를 「수집 완료, 무자료」로 태우고 체크포인트에 영구히 박힌다.
    """
    c = _FakeClient([("010", "등록되지 않은 키", [])])
    with pytest.raises(dc.DartUnexpectedStatus) as exc:
        f2.collect_one(c, ITEM)
    assert exc.value.status == "010"
    assert exc.value.stock_code == ITEM["stock_code"]
    assert exc.value.bsns_year == ITEM["bsns_year"]
    # CFS 에서 이미 올렸으니 OFS 는 시도하지 않아야 한다 — 같은 키 문제를 두 번 겪을 이유가 없다.
    assert c.seen == [(ITEM["corp_code"], ITEM["bsns_year"], "CFS")]


def test_http_fail_status_raises_as_unexpected():
    """🔴 client 의 재시도 소진 sentinel(HTTP_FAIL)도 000/013 이 아니므로 올려야 한다."""
    c = _FakeClient([("HTTP_FAIL", "retries exhausted", [])])
    with pytest.raises(dc.DartUnexpectedStatus):
        f2.collect_one(c, ITEM)


def test_bad_field_status_raises_as_unexpected():
    """🔴 100/101(필드 오류)도 같은 취급 — 013(무자료)과 다르다."""
    c = _FakeClient([("100", "필드 오류", [])])
    with pytest.raises(dc.DartUnexpectedStatus):
        f2.collect_one(c, ITEM)


def test_013_and_000_empty_still_record_normally_after_fix1():
    """🔴 FIX1 이 000/013 만 «정상 진행»으로 좁혔지만, 013·000_EMPTY 자체는

    여전히 정상 기록이어야 한다 — 무자료는 사실이지 오류가 아니다.
    """
    c013 = _FakeClient([("013", "무자료", []), ("013", "무자료", [])])
    out013 = f2.collect_one(c013, ITEM)
    assert out013["status"] == "013"

    c_empty = _FakeClient([("000", "", []), ("000", "", [])])
    out_empty = f2.collect_one(c_empty, ITEM)
    assert out_empty["status"] == "000_EMPTY"


# ── FIX6: 단일 인스턴스 PID 잠금 ────────────────────────────────────────

def test_acquire_lock_takes_over_when_recorded_pid_is_dead(tmp_path):
    """🔴 stale-PID 경로 — 기록된 PID가 죽어 있으면 잠금을 가져가야 한다.

    실제 프로세스를 띄우지 않는다: 존재할 수 없는 PID(pid_t 범위를 넘는 값)를
    직접 파일에 기록해 「죽은 프로세스」를 흉내낸다.
    """
    lock = tmp_path / "f2_collect.lock"
    lock.write_text("999999999", encoding="utf-8")
    f2.acquire_lock(str(lock))  # 예외 없이 통과해야 한다
    assert lock.read_text(encoding="utf-8").strip() == str(os.getpid())


def test_acquire_lock_refuses_when_recorded_pid_is_alive(tmp_path):
    """🔴 살아있는 PID(테스트 프로세스 자신)가 잡고 있으면 거부해야 한다."""
    lock = tmp_path / "f2_collect.lock"
    lock.write_text(str(os.getpid()), encoding="utf-8")
    with pytest.raises(RuntimeError):
        f2.acquire_lock(str(lock))


def test_acquire_lock_treats_corrupt_lock_file_as_stale(tmp_path):
    """잠금파일 내용이 PID 가 아니면(손상) stale 로 간주하고 가져간다."""
    lock = tmp_path / "f2_collect.lock"
    lock.write_text("not-a-pid", encoding="utf-8")
    f2.acquire_lock(str(lock))
    assert lock.read_text(encoding="utf-8").strip() == str(os.getpid())


def test_acquire_lock_with_no_existing_file_succeeds(tmp_path):
    lock = tmp_path / "f2_collect.lock"
    f2.acquire_lock(str(lock))
    assert lock.exists()
    assert lock.read_text(encoding="utf-8").strip() == str(os.getpid())


def test_release_lock_removes_file(tmp_path):
    lock = tmp_path / "f2_collect.lock"
    lock.write_text(str(os.getpid()), encoding="utf-8")
    f2.release_lock(str(lock))
    assert not lock.exists()


def test_release_lock_on_missing_file_does_not_raise(tmp_path):
    """이미 없는 잠금파일을 릴리스해도 죽으면 안 된다(중복 릴리스·정리 경합)."""
    lock = tmp_path / "nope.lock"
    f2.release_lock(str(lock))  # 예외를 내면 실패
