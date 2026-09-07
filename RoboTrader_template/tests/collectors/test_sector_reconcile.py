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
