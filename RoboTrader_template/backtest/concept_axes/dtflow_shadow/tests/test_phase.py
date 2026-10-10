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
