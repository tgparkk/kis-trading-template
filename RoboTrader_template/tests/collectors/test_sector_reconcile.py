"""섹터 reconcile 게이트 테스트 (T13). DB 를 쓰지 않는다 — 게이트는 순수 함수다."""
import os
import sys
from datetime import date, datetime, timedelta

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from collectors import sector_collector as sc  # noqa: E402

D = date(2026, 9, 7)


def _facts(**kw):
    f = {"u_market": 2772, "ksic_code_nonnull": 2772, "ksic3_name_nonnull": 2765,
         "new_rows": 0, "stats_rows": 547, "g": {"ksic2": 61, "ksic3": 159, "ksic5": 324},
         "duplicates": 0, "max_last_seen": datetime(2026, 9, 7, 16, 5),
         "is_trading_day": True, "last_seen_deadline": date(2026, 9, 2),
         "prev_days": ["2026-09-04", "2026-09-03", "2026-09-02"],
         "prev_new_rows": [], "prev_recon_dates": []}
    f.update(kw)
    return f


def _summary(**kw):
    s = {"trade_date": "2026-09-07",
         "map": {"written": True, "source_asof": "2026-09-07", "stale": False,
                 "null_rate": {"ksic_code": 0.0, "ksic3_name": 0.003}},
         "ksic_fill": {"fill_calls": 0, "recheck_calls": 200, "recheck_changed": 0},
         "stats": {"rows": 547, "G": {"ksic2": 61, "ksic3": 159, "ksic5": 324},
                   "undefined": {"no_label": 5, "no_prev": 1,
                                 "short_code": {"ksic2": 0, "ksic3": 0, "ksic5": 1370}}},
         "names": {"codes": 158, "low_share": []}}
    for k, v in kw.items():
        if isinstance(v, dict) and isinstance(s.get(k), dict):
            s[k] = dict(s[k], **v)
        else:
            s[k] = v
    return s


def test_healthy_day_is_pass():
    out = sc.evaluate_gates(D, _summary(), [_summary(), _summary()], _facts())
    assert out["verdict"] == "PASS", (out["fails"], out["warns"])
    assert out["real_rows"] == 547 and out["overlap"] == 5
    assert abs(out["coverage"] - 1.0) < 1e-9
    assert out["value_match_rate"] > 0.99, "value_match_rate 는 «높을수록 좋다»(비-NULL 비율)"


def test_gate1_coverage_below_98_is_fail():
    out = sc.evaluate_gates(D, _summary(), [], _facts(ksic_code_nonnull=2700))
    assert out["verdict"] == "FAIL" and any("gate1" in f for f in out["fails"])


def test_gate1_empty_u_market_is_fail_not_a_note():
    """🔴 분모 0 은 «모르는 것»이 아니라 «퇴화한 DB 사실»(stock_market 빈 표)이다.
    note 로 접으면 그 날은 PASS 로 나가고, 커버리지 게이트가 통째로 무음이 된다."""
    out = sc.evaluate_gates(D, _summary(), [_summary()], _facts(u_market=0))
    assert out["verdict"] == "FAIL"
    assert any("U_market 0 — 커버리지 계산 불가" in f for f in out["fails"])
    assert not any("U_market 0" in n for n in out["notes"]), "note 로 남으면 PASS 로 접힌다"


def test_gate2_g_floor_is_fail_and_swing_is_warn():
    out = sc.evaluate_gates(D, _summary(), [], _facts(g={"ksic2": 61, "ksic3": 40, "ksic5": 324}))
    assert out["verdict"] == "FAIL" and any("gate2" in f for f in out["fails"])
    prev = _summary(stats={"G": {"ksic2": 61, "ksic3": 159, "ksic5": 100}})
    out2 = sc.evaluate_gates(D, _summary(), [prev], _facts())
    assert out2["verdict"] == "WARN" and any("ksic5" in x for x in out2["warns"])


def test_gate3_no_prev_threshold_is_not_a_doubling_rule():
    """🔴 기저가 0~3 이라 「전일의 2배」 규칙은 1건에 걸린다.
    문턱 = max(20, 3 × 직전 20거래일 중앙값)."""
    prevs = [_summary(stats={"undefined": {"no_label": 5, "no_prev": 0,
                                           "short_code": {}}}) for _ in range(20)]
    ok = _summary(stats={"undefined": {"no_label": 5, "no_prev": 1, "short_code": {}}})
    assert sc.evaluate_gates(D, ok, prevs, _facts())["verdict"] == "PASS"
    bad = _summary(stats={"undefined": {"no_label": 5, "no_prev": 189, "short_code": {}}})
    out = sc.evaluate_gates(D, bad, prevs, _facts())
    assert out["verdict"] == "WARN" and any("no_prev" in x for x in out["warns"])


def test_gate3_no_label_jump_is_warn():
    prev = _summary(stats={"undefined": {"no_label": 5, "no_prev": 0, "short_code": {}}})
    today = _summary(stats={"undefined": {"no_label": 60, "no_prev": 0, "short_code": {}}})
    out = sc.evaluate_gates(D, today, [prev], _facts())
    assert out["verdict"] == "WARN" and any("no_label" in x for x in out["warns"])


def test_gate4_zero_remaining_is_not_stalled():
    """0=0=0 은 정상 — 채울 게 없는 것이다."""
    out = sc.evaluate_gates(D, _summary(), [_summary(), _summary()],
                            _facts(new_rows=0, prev_new_rows=[0, 0, 0]))
    assert out["verdict"] == "PASS"


def test_gate4_stalled_positive_remaining_is_warn():
    out = sc.evaluate_gates(D, _summary(), [_summary(), _summary()],
                            _facts(new_rows=7, prev_new_rows=[7, 7, 7]))
    assert out["verdict"] == "WARN" and any("정체" in x for x in out["warns"])


def test_gate4_recheck_stopped_20_days_is_warn():
    """재확인 순환이 20거래일 연속 0 이면 정지 의심."""
    prevs = [_summary(ksic_fill={"recheck_calls": 0}) for _ in range(19)]
    today = _summary(ksic_fill={"recheck_calls": 0})
    out = sc.evaluate_gates(D, today, prevs, _facts())
    assert out["verdict"] == "WARN" and any("recheck" in x for x in out["warns"])


def test_gate4_recheck_history_shorter_than_20_is_a_note_not_a_warn():
    """🔴 M-a — 「이력이 없다」를 「재확인이 멈췄다」로 오표기하면 안 된다.

    결측 summary 를 0 으로 접으면 rc_hist 길이가 «항상» 20 이라 「이력 부족」 note 가
    도달 불가가 되고, 관측이 5거래일뿐인데 전부 0 인 날이 정지 WARN 으로 둔갑한다.
    관측(non-None summary)이 20 미만이면 판정을 «보류»한다.
    """
    prevs = [_summary(ksic_fill={"recheck_calls": 0}) for _ in range(4)]
    today = _summary(ksic_fill={"recheck_calls": 0})          # 관측 5개 · 전부 0
    out = sc.evaluate_gates(D, today, prevs, _facts())
    assert not any("recheck_calls" in x for x in out["warns"]), (
        "관측 5개로 20거래일 정지를 단정했다: %s" % out["warns"])
    assert any("재확인 이력 5/20" in n and "판정 보류" in n for n in out["notes"]), (
        "보류 사유가 없다(무징후 절단): %s" % out["notes"])


def test_gate4_missing_summaries_do_not_count_as_zero_recheck():
    """🔴 M-a — 결측 20일 + 오늘 0 은 「20거래일 연속 0」이 아니다(관측 1개).
    대칭: 관측이 실제로 20개 모이면 WARN 이 난다(위 20일 테스트)."""
    out = sc.evaluate_gates(D, _summary(ksic_fill={"recheck_calls": 0}),
                            [None] * 20, _facts(prev_recon_dates=[]))
    assert not any("recheck_calls" in x for x in out["warns"]), out["warns"]
    assert any("재확인 이력 1/20" in n for n in out["notes"]), out["notes"]


def test_gate5_written_false_two_days_is_fail():
    """🔴 얼어붙은 명부 — 2거래일 연속 미갱신은 FAIL."""
    today = _summary(map={"written": False})
    prev = _summary(map={"written": False})
    out = sc.evaluate_gates(D, today, [prev], _facts())
    assert out["verdict"] == "FAIL" and any("gate5" in f for f in out["fails"])


def test_gate5_last_seen_stale_is_fail():
    """「값 없음은 변경 아님」이 만든 사각 — 소스가 통째로 NULL 이 돼도 커버리지는 통과한다."""
    out = sc.evaluate_gates(D, _summary(), [],
                            _facts(max_last_seen=datetime(2026, 9, 1, 16, 0),
                                   last_seen_deadline=date(2026, 9, 2)))
    assert out["verdict"] == "FAIL" and any("last_seen" in f for f in out["fails"])


def test_gate6_null_rate_spike_is_warn():
    prev = _summary(map={"null_rate": {"ksic_code": 0.001, "ksic3_name": 0.003}})
    today = _summary(map={"null_rate": {"ksic_code": 0.02, "ksic3_name": 0.003}})
    out = sc.evaluate_gates(D, today, [prev], _facts())
    assert out["verdict"] == "WARN" and any("null_rate" in x for x in out["warns"])


def test_gate6_stale_not_measured_is_warn_not_a_pass():
    """🔴 map.stale 은 3상태다(Task 8) — None 은 «미측정»이지 «신선함»이 아니다.
    False 로 접으면 낡은 캐시가 무음으로 통과한다."""
    today = _summary(map={"stale": None, "stale_error": "probe boom"})
    out = sc.evaluate_gates(D, today, [_summary()], _facts())
    assert out["verdict"] == "WARN", (out["fails"], out["warns"])
    assert any("stale 미측정" in x for x in out["warns"])
    assert any("probe boom" in x for x in out["warns"]), "실패 사유가 경보에 안 실렸다"


def test_holiday_skips_the_scoreboard_gate_with_a_reason():
    """휴장일엔 성적표가 없는 게 정상 — FAIL 이 아니라 «사유가 남는 PASS» 다."""
    out = sc.evaluate_gates(D, _summary(), [_summary(), _summary()],
                            _facts(is_trading_day=False, stats_rows=0, g={}))
    assert out["verdict"] == "PASS", (out["fails"], out["warns"])
    assert not out["fails"]
    assert any("휴장일" in n for n in out["notes"])


def test_missing_db_facts_are_noted_not_silently_passed():
    """🔴 무징후 절단 금지 — 사실이 «없어서» 못 잰 게이트는 notes 에 사유가 남아야 한다.
    조용히 넘어가면 그 게이트는 「한 번도 발동 안 함」이 되고 「이상 없음」과 구별이 안 된다."""
    f = _facts()
    del f["duplicates"]
    del f["new_rows"]
    out = sc.evaluate_gates(D, _summary(), [_summary()], f)
    assert any("gate8" in n for n in out["notes"]), "명부 중복을 못 쟀는데 사유가 없다"
    assert any("gate4" in n and "new_rows" in n for n in out["notes"]), \
        "잔량 정체를 못 쟀는데 사유가 없다"
    assert out["verdict"] == "PASS", (out["fails"], out["warns"])


def test_gate7_publish_delay_three_days_is_warn():
    late = _summary(map={"source_asof": "2026-09-04"})
    out = sc.evaluate_gates(D, late, [late, late], _facts())
    assert out["verdict"] == "WARN" and any("게시" in x for x in out["warns"])


def test_gate8_duplicate_map_rows_is_fail():
    out = sc.evaluate_gates(D, _summary(), [], _facts(duplicates=3))
    assert out["verdict"] == "FAIL" and any("gate8" in f for f in out["fails"])


def test_gate9_missing_summary_warn_then_fail():
    """오늘 summary 없음 = 1일 WARN · 3거래일 연속이면 FAIL."""
    one = sc.evaluate_gates(D, None, [_summary(), _summary()], _facts())
    assert one["verdict"] == "WARN"
    three = sc.evaluate_gates(D, None, [None, None], _facts())
    assert three["verdict"] == "FAIL" and any("gate9" in f for f in three["fails"])


def test_gate9_history_absent_passes_with_reason_but_lost_warns():
    """이력 «부족»은 PASS + 사유 · 이력 «유실»(그 «날짜의» recon 행은 있는데 파일이 없다)은 WARN."""
    absent = sc.evaluate_gates(D, _summary(), [], _facts())
    assert absent["verdict"] == "PASS" and any("이력 부족" in n for n in absent["notes"])
    # 🔴 [None]*20 도 「이력 부족」이다 — `not prev_summaries` 로 재면 사유가 안 찍힌다
    none20 = sc.evaluate_gates(D, _summary(), [None] * 20, _facts(prev_recon_dates=[]))
    assert any("이력 부족" in n for n in none20["notes"])
    lost = sc.evaluate_gates(D, _summary(), [None],
                             _facts(prev_days=["2026-09-04"],
                                    prev_recon_dates=["2026-09-04"]))
    assert lost["verdict"] == "WARN" and any("유실" in x for x in lost["warns"])
    # 「그 날짜」가 아닌 recon 행에는 발동하지 않는다
    other = sc.evaluate_gates(D, _summary(), [None],
                              _facts(prev_days=["2026-09-04"],
                                     prev_recon_dates=["2026-08-31"]))
    assert not any("유실" in x for x in other["warns"])


def test_verdict_vocabulary_and_iso_trade_date(monkeypatch):
    """판정 어휘는 PASS/WARN/FAIL 셋뿐 · recon 행의 trade_date 는 ISO 다
    (minute 의 'YYYYMMDD' 와 섞지 않는다)."""
    written = {}

    class _CM:
        def __enter__(self):
            return object()

        def __exit__(self, *a):
            return False

    monkeypatch.setattr(sc.KisDbConnection, "get_connection", lambda: _CM())
    monkeypatch.setattr(sc.w, "ensure_tables", lambda conn: None)
    monkeypatch.setattr(sc, "_db_facts", lambda conn, d, prev_days: _facts())
    monkeypatch.setattr(sc, "_read_summary", lambda d: _summary())
    monkeypatch.setattr(sc, "_prev_trading_days", lambda conn, d, n: [])
    monkeypatch.setattr(
        sc.w, "upsert_reconciliation",
        lambda conn, td, rr, nr, ov, cov, vmr, verdict: written.update(
            {"td": td, "rr": rr, "nr": nr, "ov": ov, "cov": cov, "vmr": vmr, "v": verdict}))
    out = sc.reconcile_sector("20260907")
    assert out["verdict"] in ("PASS", "WARN", "FAIL")
    assert written["td"] == "2026-09-07"
    assert written["rr"] == 547 and written["ov"] == 5
    # 🔴 두 비율은 «서로 다른 값»이라야 swap 회귀를 잡는다(1.0 vs 2765/2772).
    assert abs(written["cov"] - 1.0) < 1e-9, "coverage 자리에 다른 값이 갔다"
    assert abs(written["vmr"] - 2765.0 / 2772.0) < 1e-9, \
        "value_match_rate 자리에 다른 값이 갔다(coverage 와 뒤바뀌었나)"
