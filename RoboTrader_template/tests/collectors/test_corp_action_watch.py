"""기업행위 미조정 이력 탐지 + 재수집 큐 (2026-08-03).

실측 데이터 출처: kis_template.daily_prices / corp_events(pykrx 정답지 105건).
"""
import json
import os

import collectors.corp_action_watch as caw


def _halt(n, price):
    """거래정지 n봉 — 종가 동결·거래량 0 (실측 패턴)."""
    return [(f"2026-04-{d:02d}", price, 0) for d in range(1, n + 1)]


# ── scan_series: 진짜 사례를 잡는가 ──────────────────────────────────────────

def test_detects_merge_011930_real_case():
    """011930 2026-05-15 1:10 액면병합 — 정지 13봉 후 3,995 → 39,950."""
    bars = _halt(13, 3995.0) + [("2026-05-15", 39950.0, 4756935)]
    out = caw.scan_series("011930", bars)
    assert len(out) == 1
    assert out[0]["resumption_date"] == "2026-05-15"
    assert out[0]["direction"] == "merge"
    assert out[0]["halt_bars"] == 13


def test_detects_merge_115160_even_though_factor_is_uninferable():
    """🔑 115160 은 재개일 +30% 상한 때문에 **배수를 추론할 수 없는** 사례다
    (9,370/721=12.996 → 화이트리스트 거부). 그래도 '기업행위가 있었다'는 탐지는
    반드시 돼야 한다 — 재수집 큐는 배수를 몰라도 동작한다."""
    bars = _halt(14, 721.0) + [("2026-04-30", 9370.0, 508282)]
    out = caw.scan_series("115160", bars)
    assert len(out) == 1 and out[0]["direction"] == "merge"


def test_detects_merge_039980_real_case():
    bars = _halt(13, 1481.0) + [("2026-04-29", 9630.0, 1208345)]
    assert len(caw.scan_series("039980", bars)) == 1


def test_detects_reference_price_update_while_still_halted_380540():
    """🔑 380540 실사례(2026-05-22, 1:2 병합): 정지가 안 풀린 채 **기준가만 갱신**됐다
    — 4,225 → 8,450 인데 거래량은 그대로 0. '거래량>0 인 해제봉'만 보던 초판이
    유일하게 놓친 건이다(정답지 32건 중 31건 탐지 → 이 수정으로 32/32)."""
    bars = _halt(8, 4225.0) + [("2026-05-22", 8450.0, 0), ("2026-05-26", 8450.0, 0)]
    out = caw.scan_series("380540", bars)
    assert len(out) == 1
    assert out[0]["resumption_date"] == "2026-05-22"
    assert out[0]["direction"] == "merge"


def test_detects_forward_split_direction():
    bars = _halt(10, 156500.0) + [("2026-05-18", 14300.0, 96078)]
    out = caw.scan_series("001130", bars)
    assert len(out) == 1 and out[0]["direction"] == "split"


# ── scan_series: 정상 케이스를 오탐하지 않는가 ───────────────────────────────

def test_no_false_positive_on_normal_trading():
    bars = [(f"2026-04-{d:02d}", 1000.0 + d * 5, 10000) for d in range(1, 15)]
    assert caw.scan_series("000001", bars) == []


def test_no_false_positive_on_already_adjusted_resumption():
    """이미 조정된 이력은 정지 해제일 종가비가 정상 밴드 안이다 — 실측상 정합군
    64건이 전부 여기 해당한다(오탐 0)."""
    bars = _halt(12, 5000.0) + [("2026-05-15", 5300.0, 900000)]   # +6%
    assert caw.scan_series("000002", bars) == []


def test_no_false_positive_on_limit_move_without_halt():
    """정지 없이 상한가만 친 날은 후보가 아니다(_HALT_MIN_BARS 미충족)."""
    bars = [("2026-04-01", 1000.0, 5000), ("2026-04-02", 1300.0, 90000)]
    assert caw.scan_series("000003", bars) == []


def test_short_halt_below_threshold_is_ignored():
    bars = _halt(2, 1000.0) + [("2026-05-15", 9000.0, 5000)]
    assert caw.scan_series("000004", bars) == []


def test_zero_price_rows_do_not_crash_or_trigger():
    """daily_prices 에 open=high=low=close=0 행이 실재한다 — 0 나누기 금지."""
    bars = _halt(10, 0.0) + [("2026-05-15", 9000.0, 5000)]
    assert caw.scan_series("000005", bars) == []
    bars2 = _halt(10, 1000.0) + [("2026-05-15", 0.0, 5000)]
    assert caw.scan_series("000006", bars2) == []


def test_halt_run_resets_between_separate_events():
    """정지-재개가 두 번이면 각각 독립 후보로 잡혀야 한다."""
    bars = (_halt(10, 1000.0)
            + [("2026-05-01", 10000.0, 5000), ("2026-05-02", 10100.0, 4000)]
            + [(f"2026-05-{d:02d}", 10100.0, 0) for d in range(3, 16)]
            + [("2026-05-20", 101000.0, 7000)])
    out = caw.scan_series("000007", bars)
    assert len(out) == 2


# ── 큐 적재 ─────────────────────────────────────────────────────────────────

def test_record_candidates_writes_jsonl_with_delay_and_status(tmp_path):
    path = str(tmp_path / "q.jsonl")
    cands = caw.scan_series("011930", _halt(13, 3995.0)
                            + [("2026-05-15", 39950.0, 4756935)])
    assert caw.record_candidates(cands, path=path) == 1
    rec = json.loads(open(path, encoding="utf-8").read().strip())
    assert rec["stock_code"] == "011930"
    assert rec["status"] == "pending"
    # fire-and-forget 금지 — 지연을 두고 나중에 확정한다
    assert rec["eligible_after"] == "2026-05-22"   # 재개일 + 7일
    assert rec["ratio"] > 9


def test_record_candidates_is_idempotent(tmp_path):
    path = str(tmp_path / "q.jsonl")
    cands = caw.scan_series("011930", _halt(13, 3995.0)
                            + [("2026-05-15", 39950.0, 4756935)])
    assert caw.record_candidates(cands, path=path) == 1
    assert caw.record_candidates(cands, path=path) == 0     # 재적재 없음
    assert len(open(path, encoding="utf-8").read().strip().splitlines()) == 1


def test_record_candidates_tolerates_corrupt_line(tmp_path):
    path = str(tmp_path / "q.jsonl")
    with open(path, "w", encoding="utf-8") as f:
        f.write("{not json}\n")
    cands = caw.scan_series("011930", _halt(13, 3995.0)
                            + [("2026-05-15", 39950.0, 4756935)])
    assert caw.record_candidates(cands, path=path) == 1


def test_queue_path_is_not_cwd_dependent(monkeypatch, tmp_path):
    """⚠️ utils/holiday_kis_sync 의 os.getcwd() 기반 캐시 경로가 다른 cwd 기동 시
    통째로 실패하던 전례가 있다 — 같은 실수를 반복하지 않는다."""
    monkeypatch.delenv("CORP_ACTION_QUEUE_PATH", raising=False)
    monkeypatch.chdir(tmp_path)
    p1 = caw.queue_path()
    monkeypatch.chdir(os.path.dirname(str(tmp_path)))
    assert caw.queue_path() == p1
    assert os.path.isabs(p1)


def test_queue_path_env_override(monkeypatch):
    monkeypatch.setenv("CORP_ACTION_QUEUE_PATH", "/tmp/custom.jsonl")
    assert caw.queue_path() == "/tmp/custom.jsonl"
