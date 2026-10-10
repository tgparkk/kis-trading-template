from datetime import date, timedelta

from backtest.concept_axes.dtflow_shadow import alerts as A
from backtest.concept_axes.dtflow_shadow import phase as P

DAYS = [date(2026, 10, 30) - timedelta(days=i) for i in range(12)]   # 내림차순(합성 연속일)


def _runs(n_ok=10, bad_day=None, snap_bad=None):
    out = []
    for d in DAYS[:n_ok]:
        out.append(dict(scan_date=d, run_kind="record", status="ok", avail_investor=0.99, avail_program=0.99,
                        avail_short=0.99, avail_credit=None))
        out.append(dict(scan_date=d, run_kind="snapshot_check", status="ok", snapshot_match=(d != snap_bad)))
    if bad_day:
        for r in out:
            if r["scan_date"] == bad_day and r["run_kind"] == "record":
                r["avail_short"] = 0.5
    return out


LAGS = {d: [3] * 40 for d in DAYS}


def test_seal_ready_all_good():
    ok, why = P.seal_ready(_runs(), LAGS, DAYS, k=3)
    assert ok, why


def test_seal_ready_requires_k_and_consecutive_days():
    assert not P.seal_ready(_runs(), LAGS, DAYS, k=None)[0]
    assert not P.seal_ready(_runs(n_ok=9), LAGS, DAYS, k=3)[0]
    assert not P.seal_ready(_runs(bad_day=DAYS[4]), LAGS, DAYS, k=3)[0]
    assert not P.seal_ready(_runs(snap_bad=DAYS[2]), LAGS, DAYS, k=3)[0]
    assert not P.seal_ready(_runs(), {d: [4] * 40 for d in DAYS}, DAYS, k=3)[0]   # 신용 가용률 0


def test_choose_k_table():
    lags = {DAYS[0]: [3, 3, 4, None], DAYS[1]: [3, 3, 3, 3]}
    t = dict((k, (mn, mean)) for k, mn, mean in P.choose_k_table(lags, ks=range(3, 5)))
    assert t[3][0] == 0.5 and t[4][0] == 0.75


def test_alert_body_and_dry_run():
    assert A.body(date(2026, 10, 12), "missed_token", 0) == "D=2026-10-12 status=missed_token n=0"
    sent = []
    assert A.send("x", dry_run=True, log=sent.append) and "[kis-dtflow-shadow] x" in sent[0]


from backtest.concept_axes.dtflow_shadow import store as ST  # noqa: E402


def _store_with_trial(runs):
    s = ST.MemoryStore()
    for i, r in enumerate(runs):
        s.write_run("trial", dict(rule_v="v1", run_at=f"t{i}", **r))
    return s


def test_decide_sealed_row_any_status_is_one_way():
    s = ST.MemoryStore()
    s.write_run("sealed", dict(rule_v="v1", scan_date=DAYS[0], run_kind="record", run_at="s0", status="missed_token"))
    assert P.decide(s, DAYS, None, LAGS) == "sealed"   # 트라이얼 창 미달이어도 봉인 행이 있으면 되돌리지 않음


def test_decide_empty_sealed_and_window_ready_is_sealed():
    s = _store_with_trial(_runs())
    assert P.decide(s, DAYS, 3, LAGS) == "sealed"


def test_decide_empty_sealed_and_window_not_ready_is_trial():
    s = _store_with_trial(_runs(n_ok=9))
    assert P.decide(s, DAYS, 3, LAGS) == "trial"


def test_alert_conf_percent_is_literal(monkeypatch, tmp_path):
    (tmp_path / "config").mkdir()
    (tmp_path / "config" / "key.ini").write_text("[TELEGRAM]\ntoken = 12:a%bc\nchat_id = 7\n", encoding="utf-8")
    monkeypatch.setenv("KIS_DTFLOW_SHADOW_CONFIG_DIR", str(tmp_path))
    assert A._conf() == ("12:a%bc", "7")


# ---- pre-freeze fix C1(B1): 정본 행 = (scan_date, run_kind)별 run_at 가장 이른 행 ----
def _snap_row(d, status, match, at):
    return dict(scan_date=d, run_kind="snapshot_check", status=status, snapshot_match=match, run_at=at)


def _without(kind):
    return [r for r in _runs() if not (r["scan_date"] == DAYS[3] and r["run_kind"] == kind)]


def test_seal_ready_earliest_snapshot_row_wins_either_order():
    base = _without("snapshot_check")
    good = _snap_row(DAYS[3], "ok", True, "2026-10-01T09:05:00")
    bad = _snap_row(DAYS[3], "ok", False, "2026-10-01T09:20:00")
    assert P.seal_ready(base + [good, bad], LAGS, DAYS, k=3)[0]
    assert P.seal_ready(base + [bad, good], LAGS, DAYS, k=3)[0]
    bad2 = _snap_row(DAYS[3], "ok", False, "2026-10-01T09:05:00")
    good2 = _snap_row(DAYS[3], "ok", True, "2026-10-01T09:20:00")
    assert not P.seal_ready(base + [bad2, good2], LAGS, DAYS, k=3)[0]
    assert not P.seal_ready(base + [good2, bad2], LAGS, DAYS, k=3)[0]


def test_seal_ready_no_snapshot_then_manual_ok_does_not_pass():
    base = _without("snapshot_check")
    ns = _snap_row(DAYS[3], "no_snapshot", None, "2026-10-01T09:05:00")
    manual = _snap_row(DAYS[3], "ok", True, "2026-10-01T10:30:00")
    assert not P.seal_ready(base + [ns, manual], LAGS, DAYS, k=3)[0]
    assert not P.seal_ready(base + [manual, ns], LAGS, DAYS, k=3)[0]


def test_seal_ready_earliest_record_row_is_canonical():
    base = _without("record")
    early_bad = dict(scan_date=DAYS[3], run_kind="record", status="missed_token", run_at="2026-10-01T07:52:00")
    late_ok = dict(scan_date=DAYS[3], run_kind="record", status="ok", run_at="2026-10-01T08:00:00",
                   avail_investor=0.99, avail_program=0.99, avail_short=0.99)
    assert not P.seal_ready(base + [early_bad, late_ok], LAGS, DAYS, k=3)[0]
    assert not P.seal_ready(base + [late_ok, early_bad], LAGS, DAYS, k=3)[0]
